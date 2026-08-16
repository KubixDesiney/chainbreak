"""``execution/orchestrator.py``'s error and edge paths not already exercised
by ``test_scope_attenuation.py``'s happy path: an unmapped phase name, a
failed preflight, F6 re-delegation actually firing mid-run, and the
not-yet-implemented ``PhaseKind`` branches (M10's own stated risk: the phase
loop is written against the full enum from the start, even though only
``PROBE`` is exercised by any scenario shipped today).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.enums import PhaseKind, PlanPhase
from chainbreak.core.errors import ExecutionError, SafetyEnvelopeError
from chainbreak.core.models import PlanStep, SafetyEnvelope
from chainbreak.evidence.writer import BundleWriter
from chainbreak.execution.orchestrator import resolve_plan_phase
from chainbreak.providers.base.types import PreflightCheck, PreflightReport
from chainbreak.providers.fake.adapter import FakeProviderAdapter
from chainbreak.providers.fake.probes import build_fake_preconditions
from chainbreak.providers.fake.session import virtual_ms_to_datetime
from chainbreak.scenarios.loader import load_and_compile

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
BASIC_SCENARIO = REPO_ROOT / "scenarios" / "scope-attenuation" / "basic.yaml"


def _envelope(adapter: FakeProviderAdapter) -> SafetyEnvelope:
    return SafetyEnvelope(
        allowed_account_ids=(adapter.account_ref,),
        allowed_regions=(adapter.region,),
        namespace=adapter.namespace,
        namespace_pattern=f"^{adapter.namespace}$",
    )


def _writer(tmp_path: Path, run_id: str, compiled: object) -> BundleWriter:
    return BundleWriter(
        tmp_path,
        run_id,
        scenario_ref={
            "id": compiled.scenario_id,  # type: ignore[attr-defined]
            "version": compiled.scenario_version,  # type: ignore[attr-defined]
            "family": "scope-attenuation",
            "api_version": "chainbreak.dev/v1alpha1",
            "compiled_hash": compiled.compiled_hash,  # type: ignore[attr-defined]
        },
        provenance={
            "chainbreak_version": "0.1.0a0",
            "capability_catalog_version": compiled.catalog_version,  # type: ignore[attr-defined]
            "provider": "fake",
            "provider_adapter_version": compiled.adapter_version,  # type: ignore[attr-defined]
            "python_version": "3.12",
            "config_fingerprint": "sha256:" + ("3" * 64),
        },
    )


class TestResolvePlanPhase:
    def test_paired_fresh_credential_phase_is_explicitly_mapped(self) -> None:
        assert resolve_plan_phase("paired-fresh-credential") is PlanPhase.PAIRED_FRESH_CREDENTIAL

    def test_unmapped_phase_name_raises_a_named_execution_error(self) -> None:
        with pytest.raises(ExecutionError, match="no PlanPhase mapping"):
            resolve_plan_phase("a-phase-name-nobody-registered")


class TestPreflightFailurePropagates:
    def test_a_failed_preflight_aborts_before_anything_is_written(
        self,
        tmp_path: Path,
        synthetic_aws_registry: BindingRegistry,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from chainbreak.execution.orchestrator import orchestrate

        compiled = load_and_compile(BASIC_SCENARIO, registry=synthetic_aws_registry)
        adapter = FakeProviderAdapter(seed=1)

        # SafetyGate's own account/region/namespace checks pass (matching
        # envelope), so this exercises preflight's *own* independent check
        # rather than re-triggering SafetyGate's.
        monkeypatch.setattr(
            adapter,
            "preflight",
            lambda envelope: PreflightReport(
                passed=False,
                checks=(PreflightCheck(name="account", passed=False, detail="mismatched"),),
            ),
        )

        writer = _writer(tmp_path, "run-preflight-fail", compiled)
        with pytest.raises(SafetyEnvelopeError, match="preflight failed"), writer as sink:
            orchestrate(
                compiled,
                adapter,
                sink,
                build_fake_preconditions(adapter.markers),
                run_id="run-preflight-fail",
                envelope=_envelope(adapter),
                seed=1,
                max_duration_seconds=600,
                now=lambda: virtual_ms_to_datetime(adapter.clock.now_ms),
            )

        # F2: an aborted run leaves unsealed-but-present evidence, never a
        # manifest.json (finalize() must never have run).
        run_dir = tmp_path / "run-preflight-fail"
        assert not (run_dir / "manifest.json").is_file()
        assert (run_dir / "observations.jsonl").is_file()


class TestReDelegationFiresDuringARealRun:
    def test_forced_redelegation_writes_an_event_and_completes(
        self,
        tmp_path: Path,
        synthetic_aws_registry: BindingRegistry,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from chainbreak.core.enums import RunStatus
        from chainbreak.execution.orchestrator import orchestrate

        # Forces F6's threshold to fire for every matrix, without needing to
        # actually run a credential down to a genuinely short remaining
        # lifetime (basic.yaml's default lifetimes are hours; the estimated
        # matrix duration is a fraction of a second).
        monkeypatch.setattr(
            "chainbreak.execution.delegation.needs_redelegation", lambda *args, **kwargs: True
        )

        compiled = load_and_compile(BASIC_SCENARIO, registry=synthetic_aws_registry)
        adapter = FakeProviderAdapter(seed=1)
        writer = _writer(tmp_path, "run-redelegate", compiled)
        with writer as sink:
            result = orchestrate(
                compiled,
                adapter,
                sink,
                build_fake_preconditions(adapter.markers),
                run_id="run-redelegate",
                envelope=_envelope(adapter),
                seed=1,
                max_duration_seconds=600,
                now=lambda: virtual_ms_to_datetime(adapter.clock.now_ms),
            )

        assert result.status is RunStatus.COMPLETED
        import json

        events_path = tmp_path / "run-redelegate" / "events.jsonl"
        with events_path.open(encoding="utf-8") as handle:
            events = [json.loads(line) for line in handle if line.strip()]
        assert any(e["kind"] == "CREDENTIAL_REDELEGATED" for e in events)


class TestUnimplementedPhaseKinds:
    """The full ``PhaseKind`` enum has had an explicit branch since M14 --
    ``PROBE``, ``SNAPSHOT``, ``MUTATE``, ``POLL``, ``WAIT``,
    ``DEFERRED_EXECUTION`` and ``TASK``. Nothing is "not yet implemented"
    any more; a compiled step of any real kind with no matching plan is a
    compiler invariant violation instead (below), and the orchestrator's own
    trailing ``else`` (a new ``PhaseKind`` member added with no branch) is
    structurally unreachable through any value this enum has today."""

    def _compiled_with_extra_step(self, registry: BindingRegistry, kind: PhaseKind):
        compiled = load_and_compile(BASIC_SCENARIO, registry=registry)
        extra = PlanStep(order=len(compiled.plan), phase_name="baseline", kind=kind)
        return compiled.model_copy(update={"plan": (*compiled.plan, extra)})

    @pytest.mark.parametrize(
        "kind",
        [
            PhaseKind.MUTATE,
            PhaseKind.POLL,
            PhaseKind.WAIT,
            PhaseKind.DEFERRED_EXECUTION,
            PhaseKind.TASK,
        ],
    )
    def test_mutate_and_poll_without_a_matching_compiled_plan_is_an_invariant_violation(
        self,
        kind: PhaseKind,
        tmp_path: Path,
        synthetic_aws_registry: BindingRegistry,
    ) -> None:
        """M12/M13/M14: a ``MUTATE``/``POLL``/``WAIT``/``DEFERRED_EXECUTION``/
        ``TASK`` ``PlanStep`` with no corresponding compiled plan is a
        genuine compiler invariant violation (the real compiler always
        produces both together, see ``scenarios/compiler.py``'s
        ``_build_mutation_plans``/``_build_poll_plans``/``_build_wait_plans``/
        ``_build_deferred_execution_plans``/``_build_task_plans``) -- this
        test's own synthetic step deliberately has no matching plan, to
        exercise that guard directly."""
        from chainbreak.execution.orchestrator import orchestrate

        compiled = self._compiled_with_extra_step(synthetic_aws_registry, kind)
        adapter = FakeProviderAdapter(seed=1)
        writer = _writer(tmp_path, f"run-noplan-{kind.value.lower()}", compiled)

        with pytest.raises(ExecutionError, match="compiler invariant was violated"), writer as sink:
            orchestrate(
                compiled,
                adapter,
                sink,
                build_fake_preconditions(adapter.markers),
                run_id=f"run-noplan-{kind.value.lower()}",
                envelope=_envelope(adapter),
                seed=1,
                max_duration_seconds=600,
                now=lambda: virtual_ms_to_datetime(adapter.clock.now_ms),
            )

    def test_snapshot_is_a_harmless_no_op_when_reached(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        from chainbreak.core.enums import RunStatus
        from chainbreak.execution.orchestrator import orchestrate

        compiled = self._compiled_with_extra_step(synthetic_aws_registry, PhaseKind.SNAPSHOT)
        adapter = FakeProviderAdapter(seed=1)
        writer = _writer(tmp_path, "run-snapshot", compiled)

        with writer as sink:
            result = orchestrate(
                compiled,
                adapter,
                sink,
                build_fake_preconditions(adapter.markers),
                run_id="run-snapshot",
                envelope=_envelope(adapter),
                seed=1,
                max_duration_seconds=600,
                now=lambda: virtual_ms_to_datetime(adapter.clock.now_ms),
            )
        assert result.status is RunStatus.COMPLETED
