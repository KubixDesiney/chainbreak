"""M12 acceptance criteria: the revocation-propagation benchmark, driven
through the real ``execution/orchestrator.py`` (``mutation.py``/
``polling.py``/``revert.py``) rather than the M10/M11-era
``tests/fixtures/mini_orchestrator.py`` stand-in.

Setup mirrors ``test_scope_attenuation.py``'s ``_run`` helper exactly, since
these are the same orchestrator entry point -- the only difference is which
scenario corpus and adapter profile each test needs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chainbreak.analysis.pipeline import analyze
from chainbreak.analysis.timing import PollSample, compute_revocation_window
from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.enums import FindingType, MutationKind, OutcomeClass, RunStatus
from chainbreak.core.models import CompiledScenario, SafetyEnvelope
from chainbreak.evidence.writer import BundleWriter
from chainbreak.execution.orchestrator import OrchestrationResult, orchestrate
from chainbreak.providers.fake.adapter import FakeProviderAdapter
from chainbreak.providers.fake.probes import build_fake_preconditions
from chainbreak.providers.fake.session import virtual_ms_to_datetime
from chainbreak.scenarios.loader import load_and_compile

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
REVOCATION_DIR = REPO_ROOT / "scenarios" / "revocation"
NC_DIR = REPO_ROOT / "scenarios" / "_negative-controls"


def _run(
    scenario_path: Path,
    tmp_path: Path,
    registry: BindingRegistry,
    *,
    run_id: str,
    adapter: FakeProviderAdapter,
) -> tuple[Path, OrchestrationResult]:
    compiled: CompiledScenario = load_and_compile(scenario_path, registry=registry)
    envelope = SafetyEnvelope(
        allowed_account_ids=(adapter.account_ref,),
        allowed_regions=(adapter.region,),
        namespace=adapter.namespace,
        namespace_pattern=f"^{adapter.namespace}$",
    )
    writer = BundleWriter(
        tmp_path,
        run_id,
        scenario_ref={
            "id": compiled.scenario_id,
            "version": compiled.scenario_version,
            "family": "revocation",
            "api_version": "chainbreak.dev/v1alpha1",
            "compiled_hash": compiled.compiled_hash,
        },
        provenance={
            "chainbreak_version": "0.1.0a0",
            "capability_catalog_version": compiled.catalog_version,
            "provider": "fake",
            "provider_adapter_version": compiled.adapter_version,
            "python_version": "3.12",
            "config_fingerprint": "sha256:" + ("3" * 64),
        },
    )
    with writer as sink:
        result = orchestrate(
            compiled,
            adapter,
            sink,
            build_fake_preconditions(adapter.markers),
            run_id=run_id,
            envelope=envelope,
            seed=5,
            max_duration_seconds=600,
            now=lambda: virtual_ms_to_datetime(adapter.clock.now_ms),
        )
    return tmp_path / run_id, result


def _events(run_dir: Path) -> list[dict[str, object]]:
    events_path = run_dir / "events.jsonl"
    if not events_path.is_file():
        return []
    with events_path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _finding_types(run_dir: Path) -> list[str]:
    result = analyze(run_dir)
    return [f.type.value for f in result.findings]


class TestFiveMechanismsExecuteAndAreRecorded:
    """Acceptance criterion 1: all five mechanisms execute and are recorded
    with their measurements. Two (UPDATE_TRUST_POLICY,
    DELETE_SESSION_POLICY_SCOPE) are built-in negative controls -- they still
    "execute and are recorded", just as a no-op with an honest
    NO_TRANSITION_OBSERVED, never a crash."""

    @pytest.mark.parametrize(
        "scenario_name,expected_kind",
        [
            ("inline-deny", MutationKind.ATTACH_INLINE_DENY),
            ("remove-policy", MutationKind.REMOVE_INLINE_POLICY),
            ("revoke-older-sessions", MutationKind.REVOKE_OLDER_SESSIONS),
            ("delete-session-scope", MutationKind.DELETE_SESSION_POLICY_SCOPE),
            ("trust-policy-null-condition", MutationKind.UPDATE_TRUST_POLICY),
        ],
    )
    def test_scenario_completes_and_records_its_mutation_kind(
        self,
        tmp_path: Path,
        synthetic_aws_registry: BindingRegistry,
        scenario_name: str,
        expected_kind: MutationKind,
    ) -> None:
        adapter = FakeProviderAdapter(seed=5)
        run_dir, result = _run(
            REVOCATION_DIR / f"{scenario_name}.yaml",
            tmp_path,
            synthetic_aws_registry,
            run_id=f"run-{scenario_name}",
            adapter=adapter,
        )
        assert result.status is RunStatus.COMPLETED

        events = _events(run_dir)
        mutation_events = [e for e in events if e.get("kind") == "POLICY_MUTATION_APPLIED"]
        assert len(mutation_events) == 1
        assert mutation_events[0]["mutation_kind"] == expected_kind.value
        assert mutation_events[0]["receipt"]["confirmed"] is True

        revert_logs = [e for e in events if e.get("kind") == "REVERT_LOG_WRITTEN"]
        assert len(revert_logs) == 1

    def test_positive_mechanisms_observe_a_transition(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        for scenario_name in ("inline-deny", "remove-policy", "revoke-older-sessions"):
            adapter = FakeProviderAdapter(seed=5)
            run_dir, _ = _run(
                REVOCATION_DIR / f"{scenario_name}.yaml",
                tmp_path,
                synthetic_aws_registry,
                run_id=f"run-transition-{scenario_name}",
                adapter=adapter,
            )
            events = _events(run_dir)
            poll_stops = [e for e in events if e.get("kind") == "POLL_STOPPED"]
            transition_stop = next(e for e in poll_stops if e["phase_name"] == "poll-transition")
            assert transition_stop["stop_reason"] == "STABLE_DENIAL", scenario_name


class TestRevertRestoresDeclaredAuthority:
    """Acceptance criterion 4 (and F8/F9): a completed run's revertible
    mutations are actually reverted, restoring the identity's declared
    authority -- re-probed directly against the same adapter after
    ``orchestrate()`` returns."""

    def test_inline_deny_is_reverted_after_the_run_completes(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        adapter = FakeProviderAdapter(seed=5)
        run_dir, result = _run(
            REVOCATION_DIR / "inline-deny.yaml",
            tmp_path,
            synthetic_aws_registry,
            run_id="run-revert-check",
            adapter=adapter,
        )
        assert result.status is RunStatus.COMPLETED

        events = _events(run_dir)
        reverted = [e for e in events if e.get("kind") == "MUTATION_REVERTED"]
        assert len(reverted) == 1
        assert reverted[0]["receipt"]["confirmed"] is True

        # engine.identity_allow reflects the restored (declared) state
        # directly -- objectstore.read was denied mid-run and must be back.
        assert "objectstore.read" in adapter.engine.identity_allow("agent-b")

    def test_revoke_older_sessions_is_not_actionable(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        adapter = FakeProviderAdapter(seed=5)
        run_dir, result = _run(
            REVOCATION_DIR / "revoke-older-sessions.yaml",
            tmp_path,
            synthetic_aws_registry,
            run_id="run-revert-sessions",
            adapter=adapter,
        )
        assert result.status is RunStatus.COMPLETED
        events = _events(run_dir)
        assert not [e for e in events if e.get("kind") == "MUTATION_REVERTED"]
        revert_log = next(e for e in events if e.get("kind") == "REVERT_LOG_WRITTEN")
        assert revert_log["actionable"] is False
        assert "cannot be un-revoked" in revert_log["action"]


class TestNegativeControls:
    """Acceptance criterion 3: both negative controls behave as declared."""

    def test_trust_policy_null_condition_observes_no_transition(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        adapter = FakeProviderAdapter(seed=5)
        run_dir, result = _run(
            REVOCATION_DIR / "trust-policy-null-condition.yaml",
            tmp_path,
            synthetic_aws_registry,
            run_id="run-nc-trust",
            adapter=adapter,
        )
        assert result.status is RunStatus.COMPLETED
        assert FindingType.NO_TRANSITION_OBSERVED.value in _finding_types(run_dir)

    def test_nc_no_revocation_observes_no_transition(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        adapter = FakeProviderAdapter(seed=5)
        run_dir, result = _run(
            NC_DIR / "nc-no-revocation.yaml",
            tmp_path,
            synthetic_aws_registry,
            run_id="run-nc-cross-identity",
            adapter=adapter,
        )
        assert result.status is RunStatus.COMPLETED
        assert FindingType.NO_TRANSITION_OBSERVED.value in _finding_types(run_dir)


class TestKnownTruthTimingAcrossProfiles:
    """Acceptance criterion 2, through the real orchestrator: the measured
    window must contain the fake's own known ``propagation_delay_ms`` at
    every delay setting M12 names (0, 500, 2000, 10000ms)."""

    @pytest.mark.parametrize("propagation_delay_ms", [0, 500, 2000, 10000])
    def test_measured_window_contains_the_true_propagation_delay(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry, propagation_delay_ms: int
    ) -> None:
        # jitter=0 for a deterministic, exact bound rather than a tolerance.
        adapter = FakeProviderAdapter(seed=5, propagation_delay_ms=propagation_delay_ms)
        run_dir, result = _run(
            REVOCATION_DIR / "inline-deny.yaml",
            tmp_path,
            synthetic_aws_registry,
            run_id=f"run-known-truth-{propagation_delay_ms}",
            adapter=adapter,
        )
        assert result.status is RunStatus.COMPLETED

        events = _events(run_dir)
        mutation_event = next(e for e in events if e.get("kind") == "POLICY_MUTATION_APPLIED")
        mutation_sent_ns = mutation_event["timing"]["monotonic_ns"]

        observations = []
        with (run_dir / "observations.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    observations.append(json.loads(line))
        samples = [
            PollSample(
                monotonic_ns=o["timing"]["monotonic_start_ns"],
                outcome=OutcomeClass(o["outcome"]["outcome_class"]),
            )
            for o in observations
            if o["phase"] == "POST_MUTATION"
        ]
        measurement = compute_revocation_window(
            samples,
            identity_id="agent-b",
            capability_id="objectstore.read",
            mutation_kind=MutationKind.ATTACH_INLINE_DENY,
            mutation_sent_ns=mutation_sent_ns,
            poll_interval_ms=500,
            mutation_receipt_confirmed=True,
        )
        assert measurement.transition_observed is True
        window = measurement.transition_window
        assert window is not None
        true_delay_s = propagation_delay_ms / 1000
        assert window.low <= true_delay_s <= window.high


class TestNoScalarTimingValue:
    """F5's hard requirement: the transition window is never flattened to a
    bare scalar anywhere in ``findings.json``. Forces a REVOCATION_DELAY
    finding (an assertive expectation with an unreachably low threshold) so
    there is an actual transition-window-bearing finding to inspect --
    inline-deny.yaml's own ``informational`` severity never produces one."""

    def test_revocation_delay_finding_carries_a_window_not_a_scalar(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        adapter = FakeProviderAdapter(seed=5, propagation_delay_ms=2000)
        compiled: CompiledScenario = load_and_compile(
            REVOCATION_DIR / "inline-deny.yaml", registry=synthetic_aws_registry
        )
        assertive = compiled.expectations[-1].model_copy(
            update={"severity": "assertive", "max_seconds": 0.01}
        )
        compiled = compiled.model_copy(
            update={"expectations": (*compiled.expectations[:-1], assertive)}
        )

        envelope = SafetyEnvelope(
            allowed_account_ids=(adapter.account_ref,),
            allowed_regions=(adapter.region,),
            namespace=adapter.namespace,
            namespace_pattern=f"^{adapter.namespace}$",
        )
        run_id = "run-no-scalar"
        writer = BundleWriter(
            tmp_path,
            run_id,
            scenario_ref={
                "id": compiled.scenario_id,
                "version": compiled.scenario_version,
                "family": "revocation",
                "api_version": "chainbreak.dev/v1alpha1",
                "compiled_hash": compiled.compiled_hash,
            },
            provenance={
                "chainbreak_version": "0.1.0a0",
                "capability_catalog_version": compiled.catalog_version,
                "provider": "fake",
                "provider_adapter_version": compiled.adapter_version,
                "python_version": "3.12",
                "config_fingerprint": "sha256:" + ("3" * 64),
            },
        )
        with writer as sink:
            result = orchestrate(
                compiled,
                adapter,
                sink,
                build_fake_preconditions(adapter.markers),
                run_id=run_id,
                envelope=envelope,
                seed=5,
                max_duration_seconds=600,
                now=lambda: virtual_ms_to_datetime(adapter.clock.now_ms),
            )
        assert result.status is RunStatus.COMPLETED

        run_dir = tmp_path / run_id
        analysis = analyze(run_dir)
        delay_findings = [f for f in analysis.findings if f.type is FindingType.REVOCATION_DELAY]
        assert len(delay_findings) == 1
        observed = delay_findings[0].observed_state
        window = observed["transition_window"]
        assert set(window) == {"low", "high"}
        assert isinstance(window["low"], (int, float))
        assert isinstance(window["high"], (int, float))
        # No sibling scalar key claiming to be *the* transition time.
        assert "transition_seconds" not in observed
        assert "delay_seconds" not in observed
        assert "value" not in observed
