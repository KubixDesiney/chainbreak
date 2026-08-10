"""All six negative controls, both directions (F7, M07 acceptance criterion 3):
the defect present must produce the declared finding (proves detection), and
the defect "fixed" must produce ``DETECTOR_FAILURE`` (proves the detector
check itself works, not just that it happens to find something).

All six negative controls -- ``nc-stale-credential-reuse`` since M13 and
``nc-silent-success`` since M14 -- are now walked end-to-end through the
real pipeline; the four scope-attenuation/delegation-drift/revocation
controls above still use ``mini_orchestrator`` (a lighter-weight stand-in
that predates the real orchestrator's own coverage of those families).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
import mini_orchestrator as mo

from chainbreak.analysis.pipeline import analyze
from chainbreak.core.enums import PlanPhase, RunStatus
from chainbreak.core.models import AuthoritySet, CompiledScenario, SafetyEnvelope
from chainbreak.evidence.writer import BundleWriter
from chainbreak.execution.orchestrator import orchestrate
from chainbreak.providers.fake.adapter import FakeProviderAdapter
from chainbreak.providers.fake.probes import build_fake_preconditions
from chainbreak.providers.fake.session import virtual_ms_to_datetime
from chainbreak.scenarios.loader import load_and_compile
from chainbreak.scenarios.safety import load_scenario_yaml
from chainbreak.scenarios.schema import ScenarioDocument

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
NC_DIR = REPO_ROOT / "scenarios" / "_negative-controls"


def _expected_finding(scenario_path: Path):
    document = ScenarioDocument(**load_scenario_yaml(scenario_path))
    assert document.spec.negative_control is not None
    return document.spec.negative_control.expect_finding


class TestScopeExpansion:
    PATH = NC_DIR / "nc-scope-expansion.yaml"

    def test_defect_present_detector_ok(self, tmp_path: Path, synthetic_aws_registry):
        compiled, adapter, refs, credentials = mo.compile_and_delegate(
            self.PATH, synthetic_aws_registry, seed=1
        )
        adapter.engine.apply_allow("agent-b", AuthoritySet.of("keyvalue.read"))
        observations = mo.probe_observations(
            compiled, adapter, refs, "nc-scope-1", phase=PlanPhase.POST_DELEGATION
        )
        run_dir = mo.write_bundle(
            tmp_path, "nc-scope-1", compiled, observations, credentials=credentials
        )
        result = analyze(run_dir)
        assert {c.negative_control_id: c.result for c in result.detector_checks}[
            "nc-scope-expansion"
        ] == "DETECTOR_OK"

    def test_defect_fixed_detector_failure(self, tmp_path: Path, synthetic_aws_registry):
        compiled, adapter, refs, credentials = mo.compile_and_delegate(
            self.PATH, synthetic_aws_registry, seed=1
        )
        observations = mo.probe_observations(
            compiled, adapter, refs, "nc-scope-2", phase=PlanPhase.POST_DELEGATION
        )
        run_dir = mo.write_bundle(
            tmp_path, "nc-scope-2", compiled, observations, credentials=credentials
        )
        result = analyze(run_dir)
        assert {c.negative_control_id: c.result for c in result.detector_checks}[
            "nc-scope-expansion"
        ] == "DETECTOR_FAILURE"


class TestSurvivingAuthority:
    PATH = NC_DIR / "nc-surviving-authority.yaml"

    def test_defect_present_detector_ok(self, tmp_path: Path, synthetic_aws_registry):
        compiled, adapter, refs, credentials = mo.compile_and_delegate(
            self.PATH, synthetic_aws_registry, seed=2
        )
        # Hop-2 intends to drop function.invoke; the defect is agent-b's role
        # retaining it anyway (the scenario's own rationale).
        adapter.engine.apply_allow("agent-b", AuthoritySet.of("function.invoke"))
        observations = mo.probe_observations(
            compiled, adapter, refs, "nc-surv-1", phase=PlanPhase.POST_DELEGATION
        )
        run_dir = mo.write_bundle(
            tmp_path, "nc-surv-1", compiled, observations, credentials=credentials
        )
        result = analyze(run_dir)
        assert {c.negative_control_id: c.result for c in result.detector_checks}[
            "nc-surviving-authority"
        ] == "DETECTOR_OK"

    def test_defect_fixed_detector_failure(self, tmp_path: Path, synthetic_aws_registry):
        compiled, adapter, refs, credentials = mo.compile_and_delegate(
            self.PATH, synthetic_aws_registry, seed=2
        )
        observations = mo.probe_observations(
            compiled, adapter, refs, "nc-surv-2", phase=PlanPhase.POST_DELEGATION
        )
        run_dir = mo.write_bundle(
            tmp_path, "nc-surv-2", compiled, observations, credentials=credentials
        )
        result = analyze(run_dir)
        assert {c.negative_control_id: c.result for c in result.detector_checks}[
            "nc-surviving-authority"
        ] == "DETECTOR_FAILURE"


class TestNonMonotoneChain:
    PATH = NC_DIR / "nc-non-monotone-chain.yaml"

    def test_defect_present_detector_ok(self, tmp_path: Path, synthetic_aws_registry):
        compiled, adapter, refs, credentials = mo.compile_and_delegate(
            self.PATH, synthetic_aws_registry, seed=3
        )
        # Agent C's role grants keyvalue.write, which no ancestor holds.
        adapter.engine.apply_allow("agent-c", AuthoritySet.of("keyvalue.write"))
        observations = mo.probe_observations(
            compiled, adapter, refs, "nc-mono-1", phase=PlanPhase.POST_DELEGATION
        )
        run_dir = mo.write_bundle(
            tmp_path, "nc-mono-1", compiled, observations, credentials=credentials
        )
        result = analyze(run_dir)
        assert {c.negative_control_id: c.result for c in result.detector_checks}[
            "nc-non-monotone-chain"
        ] == "DETECTOR_OK"

    def test_defect_fixed_detector_failure(self, tmp_path: Path, synthetic_aws_registry):
        compiled, adapter, refs, credentials = mo.compile_and_delegate(
            self.PATH, synthetic_aws_registry, seed=3
        )
        observations = mo.probe_observations(
            compiled, adapter, refs, "nc-mono-2", phase=PlanPhase.POST_DELEGATION
        )
        run_dir = mo.write_bundle(
            tmp_path, "nc-mono-2", compiled, observations, credentials=credentials
        )
        result = analyze(run_dir)
        assert {c.negative_control_id: c.result for c in result.detector_checks}[
            "nc-non-monotone-chain"
        ] == "DETECTOR_FAILURE"


class TestNoRevocation:
    PATH = NC_DIR / "nc-no-revocation.yaml"

    def _build(self, tmp_path: Path, registry, *, poll_target: str) -> Path:
        from chainbreak.providers.base.types import ProbeRequest

        compiled, adapter, _refs, credentials = mo.compile_and_delegate(self.PATH, registry, seed=4)
        event, _ = mo.mutate_and_poll(
            adapter, "agent-a", denies=("objectstore.read",), baseline_poll_count=0, poll_count=0
        )
        ref = adapter._make_ref(poll_target)
        results = []
        for _ in range(9):
            adapter.advance_clock(500)
            binding = adapter.resolve_capability("objectstore.read")
            result = adapter.probe(
                ProbeRequest(
                    identity_ref=ref,
                    capability_id="objectstore.read",
                    binding=binding,
                    namespace=adapter.namespace,
                    trial=1,
                )
            )
            results.append(("objectstore.read", result))
        poll_observations = mo.poll_results_to_observations(results, poll_target, "nc-norev")
        return mo.write_bundle(
            tmp_path,
            "nc-norev",
            compiled,
            poll_observations,
            events=[event],
            credentials=credentials,
        )

    def test_defect_present_watching_unaffected_identity_detector_ok(
        self, tmp_path: Path, synthetic_aws_registry
    ):
        run_dir = self._build(tmp_path, synthetic_aws_registry, poll_target="agent-b")
        result = analyze(run_dir)
        assert {c.negative_control_id: c.result for c in result.detector_checks}[
            "nc-no-revocation"
        ] == "DETECTOR_OK"

    def test_defect_fixed_watching_the_actually_mutated_identity_detector_failure(
        self, tmp_path: Path, synthetic_aws_registry
    ):
        """The "fix": poll the identity that was *actually* mutated. A real
        transition is then observed, which is not what the negative control
        declares (``NO_TRANSITION_OBSERVED``), so the detector must fail."""
        run_dir = self._build(tmp_path, synthetic_aws_registry, poll_target="agent-a")
        result = analyze(run_dir)
        assert {c.negative_control_id: c.result for c in result.detector_checks}[
            "nc-no-revocation"
        ] == "DETECTOR_FAILURE"


class TestSilentSuccess:
    """M14: walked end-to-end through the real orchestrator, like every
    other negative control in this file except (for now)
    ``nc-scope-expansion``'s siblings that still use ``mini_orchestrator``.
    The "fix" is the same compiled scenario with its dishonest worker
    swapped for the honest one -- the scenario's own declared defect is
    which worker runs the task, not its structure."""

    PATH = NC_DIR / "nc-silent-success.yaml"

    def _run(self, tmp_path: Path, registry, *, run_id: str, defect_fixed: bool = False) -> Path:
        compiled = load_and_compile(self.PATH, registry=registry)
        if defect_fixed:
            fixed_task_plans = tuple(
                plan.model_copy(update={"worker": "deterministic.sequential"})
                for plan in compiled.task_plans
            )
            compiled = compiled.model_copy(update={"task_plans": fixed_task_plans})
        adapter = FakeProviderAdapter(seed=17)
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
                "family": "silent-narrowing",
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
                seed=17,
                max_duration_seconds=600,
                now=lambda: virtual_ms_to_datetime(adapter.clock.now_ms),
            )
        assert result.status is RunStatus.COMPLETED
        return tmp_path / run_id

    def test_defect_present_detector_ok(self, tmp_path: Path, synthetic_aws_registry) -> None:
        run_dir = self._run(tmp_path, synthetic_aws_registry, run_id="nc-silent-present")
        result = analyze(run_dir)
        assert {c.negative_control_id: c.result for c in result.detector_checks}[
            "nc-silent-success"
        ] == "DETECTOR_OK"

    def test_defect_fixed_honest_worker_detector_failure(
        self, tmp_path: Path, synthetic_aws_registry
    ) -> None:
        """The "fix": deterministic.sequential (the honest worker) reports
        PARTIAL and reported_insufficient_authority=True instead -- failing
        loudly, which is EXPECTED_BEHAVIOR, not SILENT_NARROWING."""
        run_dir = self._run(
            tmp_path, synthetic_aws_registry, run_id="nc-silent-fixed", defect_fixed=True
        )
        result = analyze(run_dir)
        assert {c.negative_control_id: c.result for c in result.detector_checks}[
            "nc-silent-success"
        ] == "DETECTOR_FAILURE"


class TestStaleCredentialReuse:
    """M13: walked end-to-end through the real orchestrator."""

    PATH = NC_DIR / "nc-stale-credential-reuse.yaml"

    def _run(self, tmp_path: Path, registry, *, run_id: str, defect_fixed: bool = False) -> Path:
        compiled: CompiledScenario = load_and_compile(self.PATH, registry=registry)
        if defect_fixed:
            # The "fix": no mutation is ever applied, so agent-c's pinned
            # and freshly minted credentials necessarily agree (both
            # ALLOWED) -- nothing is stale, and the detector must correctly
            # report DETECTOR_FAILURE rather than finding staleness anyway.
            # The auto-inserted SNAPSHOT steps are left in place: with no
            # matching MutationPlan, orchestrator.py's own SNAPSHOT branch
            # treats that as the harmless no-op it already documents.
            compiled = compiled.model_copy(
                update={
                    "plan": tuple(step for step in compiled.plan if step.phase_name != "revoke"),
                    "mutation_plans": (),
                }
            )
        adapter = FakeProviderAdapter(seed=13)
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
                "family": "stale-authority",
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
                seed=13,
                max_duration_seconds=600,
                now=lambda: virtual_ms_to_datetime(adapter.clock.now_ms),
            )
        assert result.status is RunStatus.COMPLETED
        return tmp_path / run_id

    def test_defect_present_detector_ok(self, tmp_path: Path, synthetic_aws_registry) -> None:
        run_dir = self._run(tmp_path, synthetic_aws_registry, run_id="nc-stale-present")
        result = analyze(run_dir)
        assert {c.negative_control_id: c.result for c in result.detector_checks}[
            "nc-stale-credential-reuse"
        ] == "DETECTOR_OK"

    def test_defect_fixed_no_mutation_detector_failure(
        self, tmp_path: Path, synthetic_aws_registry
    ) -> None:
        """The scenario's own rationale: with no mutation ever applied, the
        deferred and fresh probes necessarily agree -- nothing is stale, so
        the STALE_AUTHORITY detector must correctly report failure here,
        proving it does not manufacture a finding out of an unrelated pair."""
        run_dir = self._run(
            tmp_path, synthetic_aws_registry, run_id="nc-stale-fixed", defect_fixed=True
        )
        result = analyze(run_dir)
        assert {c.negative_control_id: c.result for c in result.detector_checks}[
            "nc-stale-credential-reuse"
        ] == "DETECTOR_FAILURE"
