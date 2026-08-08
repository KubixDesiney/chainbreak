"""All six negative controls, both directions (F7, M07 acceptance criterion 3):
the defect present must produce the declared finding (proves detection), and
the defect "fixed" must produce ``DETECTOR_FAILURE`` (proves the detector
check itself works, not just that it happens to find something).

Four of the six negative controls have their defect expressible as a fake-
adapter policy-engine call and are walked end-to-end through the real
pipeline. The remaining two -- ``nc-silent-success`` (needs a task worker,
M14) and ``nc-stale-credential-reuse`` (needs the deferred-execution engine,
M13) -- have no orchestration machinery to produce a bundle from yet; their
rules and detector logic are exercised directly against hand-built
measurements referencing the same scenario's own declared semantics, and
that limitation is stated here rather than worked around.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
import mini_orchestrator as mo

from chainbreak.analysis.detector import check_negative_control
from chainbreak.analysis.pipeline import analyze
from chainbreak.analysis.rules import rule_silent_narrowing, rule_stale_authority
from chainbreak.analysis.timing import classify_stale_authority
from chainbreak.core.enums import OutcomeClass, PlanPhase, TaskStatus
from chainbreak.core.models import AuthoritySet, TaskOutcome
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


class TestSilentSuccessRuleLevel:
    """No task-worker engine exists yet (M14); the rule and detector are
    exercised directly against a ``TaskOutcome`` matching the scenario's own
    declared defect and its fix."""

    def _detector_check(self, task: TaskOutcome) -> str:
        expected = _expected_finding(NC_DIR / "nc-silent-success.yaml")
        from chainbreak.core.models import CompiledExpectedFinding

        compiled_expected = CompiledExpectedFinding(
            type=expected.type,
            identity_id=expected.identity,
            capabilities=AuthoritySet.of(*expected.capabilities),
            min_confidence=expected.min_confidence,
        )
        finding = rule_silent_narrowing(task)
        findings = [finding] if finding else []
        return check_negative_control(
            compiled_expected, findings, negative_control_id="nc-silent-success"
        ).result

    def test_defect_present_detector_ok(self):
        dishonest = TaskOutcome(
            task_id="task_01",
            identity_id="agent-b",
            worker="always-complete",
            status=TaskStatus.COMPLETE,
            steps_total=2,
            steps_attempted=2,
            steps_succeeded=1,
            reported_insufficient_authority=False,
            output_marker_written=True,
            output_marker_verified_independently=False,
            substituted_capabilities=AuthoritySet.of("keyvalue.write"),
        )
        assert self._detector_check(dishonest) == "DETECTOR_OK"

    def test_defect_fixed_detector_failure(self):
        honest = TaskOutcome(
            task_id="task_01",
            identity_id="agent-b",
            worker="sequential",
            status=TaskStatus.PARTIAL,
            steps_total=2,
            steps_attempted=2,
            steps_succeeded=1,
            reported_insufficient_authority=True,
            output_marker_written=False,
            output_marker_verified_independently=False,
        )
        assert self._detector_check(honest) == "DETECTOR_FAILURE"


class TestStaleCredentialReuseRuleLevel:
    """No deferred-execution engine exists yet (M13); ``classify_stale_authority``
    and the detector are exercised directly, matching the scenario's own
    rationale: deferred-ALLOWED + fresh-DENIED classifies as stale; deferred-
    ALLOWED + fresh-ALLOWED (the "fix": propagation simply hadn't happened)
    must NOT be reported as ``STALE_AUTHORITY``."""

    def _detector_check(self, *, fresh_outcome: OutcomeClass) -> str:
        expected = _expected_finding(NC_DIR / "nc-stale-credential-reuse.yaml")
        from chainbreak.core.models import CompiledExpectedFinding, StaleAuthorityMeasurement

        compiled_expected = CompiledExpectedFinding(
            type=expected.type,
            identity_id=expected.identity,
            capabilities=AuthoritySet.of(*expected.capabilities),
            min_confidence=expected.min_confidence,
        )
        classification = classify_stale_authority(
            deferred_outcome=OutcomeClass.ALLOWED,
            credential_expired_at_execution=False,
            fresh_outcome=fresh_outcome,
        )
        measurement = StaleAuthorityMeasurement(
            identity_id="agent-c",
            capability_id="objectstore.read",
            classification=classification,
            deferral_seconds=20.0,
            credential_expired_at_execution=False,
            paired_fresh_credential_outcome=fresh_outcome,
        )
        finding = rule_stale_authority(measurement)
        findings = [finding] if finding else []
        return check_negative_control(
            compiled_expected, findings, negative_control_id="nc-stale-credential-reuse"
        ).result

    def test_defect_present_fresh_denied_detector_ok(self):
        assert self._detector_check(fresh_outcome=OutcomeClass.DENIED_EXPLICIT) == "DETECTOR_OK"

    def test_not_propagated_fresh_also_allowed_detector_failure(self):
        """The scenario's own rationale: if the fresh probe ALSO succeeds,
        the correct classification is "not propagated," not stale authority
        -- so the STALE_AUTHORITY detector must correctly report failure
        here, proving it does not conflate the two."""
        assert self._detector_check(fresh_outcome=OutcomeClass.ALLOWED) == "DETECTOR_FAILURE"
