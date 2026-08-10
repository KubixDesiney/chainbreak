"""M14 acceptance criterion 1: all four deterministic workers implemented
and exercised, driven through ``execution/task_runner.py`` directly against
a real, hand-materialized one-hop graph (matching ``test_mutation.py``'s and
``test_deferred.py``'s own precedent for testing one ``execution/`` module
directly rather than only through a full scenario corpus).

Also exercises the milestone's own explicit requirement: the ``substituting``
and ``redelegating`` workers' contract violations are reported *distinctly*
-- as different ``FindingType``s, never collapsed into one -- from
``deterministic.always-complete``'s plain ``SILENT_NARROWING``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from chainbreak.analysis.task_contract import task_contract_findings
from chainbreak.core.enums import DelegationMechanism, FindingType, OutcomeClass, TaskStatus
from chainbreak.core.models import AuthoritySet, DelegationEdge, TaskPlan, TaskStepPlan
from chainbreak.execution.delegation import MaterializedGraph
from chainbreak.execution.task_runner import run_task
from chainbreak.providers.base.types import DelegationRequest
from chainbreak.providers.fake.adapter import FakeProviderAdapter

pytestmark = pytest.mark.integration

_STEPS = (
    TaskStepPlan(capability_id="objectstore.read", on_failure="continue"),
    TaskStepPlan(capability_id="keyvalue.write", on_failure="continue"),
)


def _materialize(*, granted: AuthoritySet) -> tuple[FakeProviderAdapter, MaterializedGraph]:
    adapter = FakeProviderAdapter(seed=1)
    root_ref = adapter.register_identity("principal", allow=AuthoritySet.of("identity.delegate"))
    edge = DelegationEdge(
        edge_id="hop-1",
        source_id="principal",
        target_id="agent-b",
        mechanism=DelegationMechanism.ROLE_CHAIN,
        requested_capabilities=granted,
        intended_capabilities=granted,
        expected_effective=granted,
        credential_lifetime_s=3600,
    )
    result = adapter.delegate(
        DelegationRequest(
            source_identity=root_ref,
            target_identity_id="agent-b",
            mechanism=edge.mechanism,
            requested_duration_s=edge.credential_lifetime_s,
            intended_capabilities=edge.intended_capabilities,
        )
    )
    materialized = MaterializedGraph(
        refs={"principal": root_ref, "agent-b": result.identity_ref},
        credentials={"principal": None, "agent-b": result.record},
        edges_by_target={"principal": None, "agent-b": edge},
    )
    return adapter, materialized


def _plan(worker: str) -> TaskPlan:
    return TaskPlan(
        phase_name="run-task",
        task_id="t1",
        worker=worker,
        target_identity="agent-b",
        requires_capabilities=AuthoritySet.of("objectstore.read", "keyvalue.write"),
        steps=_STEPS,
    )


def _run(worker: str, *, granted: AuthoritySet):
    adapter, materialized = _materialize(granted=granted)
    bootstrap_ref = adapter.register_identity("bootstrap")
    run = run_task(
        adapter,
        materialized,
        _plan(worker),
        run_id="run-1",
        provisioning_ref=bootstrap_ref,
        now=lambda: datetime.now(UTC),
        salt="test-salt",
        namespace=adapter.namespace,
        sequence_start=0,
    )
    return run


_FULL_AUTHORITY = AuthoritySet.of("objectstore.read", "keyvalue.write")


class TestSequential:
    def test_honest_success_with_full_authority(self) -> None:
        run = _run("deterministic.sequential", granted=_FULL_AUTHORITY)
        assert run.outcome.status is TaskStatus.COMPLETE
        assert run.outcome.steps_succeeded == 2
        assert run.outcome.output_marker_written is True
        assert run.outcome.output_marker_verified_independently is True
        assert run.outcome.redelegation_attempts == 0
        assert not run.outcome.substituted_capabilities

    def test_honest_partial_reporting_when_denied(self) -> None:
        """F2: a genuinely denied step is reported honestly -- PARTIAL and
        reported_insufficient_authority=True, never COMPLETE."""
        run = _run("deterministic.sequential", granted=AuthoritySet.of("objectstore.read"))
        assert run.outcome.status is TaskStatus.PARTIAL
        assert run.outcome.steps_succeeded == 1
        assert run.outcome.reported_insufficient_authority is True
        assert run.outcome.output_marker_written is False
        assert run.outcome.output_marker_verified_independently is False


class TestAlwaysComplete:
    def test_lies_but_is_caught_by_independent_verification(self) -> None:
        run = _run("deterministic.always-complete", granted=_FULL_AUTHORITY)
        assert run.outcome.status is TaskStatus.COMPLETE
        assert run.outcome.steps_succeeded == run.outcome.steps_total  # internally consistent
        assert run.outcome.output_marker_written is True
        assert run.outcome.output_marker_verified_independently is False
        assert not run.observations  # never invoked anything real at all


class TestSubstituting:
    def test_substitution_objectively_detected(self) -> None:
        run = _run("deterministic.substituting", granted=_FULL_AUTHORITY)
        assert run.outcome.substituted_capabilities == AuthoritySet.of("identity.whoami")
        assert run.outcome.output_marker_verified_independently is False


class TestRedelegating:
    def test_redelegation_refused_and_recorded_real_work_still_succeeds(self) -> None:
        run = _run("deterministic.redelegating", granted=_FULL_AUTHORITY)
        assert run.outcome.redelegation_attempts == 1
        assert any(e["kind"] == "REDELEGATION_ATTEMPT_REFUSED" for e in run.events)
        # S2: refused -- no delegate() ever actually happened for this identity.
        assert not any(o.capability_id == "identity.delegate" for o in run.observations)
        # Its real steps still ran and succeeded, independent of the attempt.
        assert run.outcome.status is TaskStatus.COMPLETE
        assert run.outcome.output_marker_verified_independently is True


class TestContractViolationsReportedDistinctly:
    """The milestone's own explicit requirement: substituting and
    redelegating produce findings distinct from each other and from plain
    SILENT_NARROWING, never collapsed into one."""

    def test_substituting_produces_a_distinct_capability_substituted_finding(self) -> None:
        """The substitution manifests as an unverified marker too (the
        declared output capability was genuinely never invoked), so
        SILENT_NARROWING legitimately also fires -- CAPABILITY_SUBSTITUTED
        must still appear as its own, separate finding, never merged away."""
        run = _run("deterministic.substituting", granted=_FULL_AUTHORITY)
        findings = task_contract_findings([run.outcome], [_plan("deterministic.substituting")])
        types = [f.type for f in findings]
        assert FindingType.CAPABILITY_SUBSTITUTED in types
        assert types.count(FindingType.CAPABILITY_SUBSTITUTED) == 1
        assert len(findings) == len({f.finding_id for f in findings}), (
            "each violation must be its own Finding with its own id, not merged into one"
        )

    def test_redelegating_produces_redelegation_attempted_not_silent_narrowing(self) -> None:
        run = _run("deterministic.redelegating", granted=_FULL_AUTHORITY)
        findings = task_contract_findings([run.outcome], [_plan("deterministic.redelegating")])
        types = {f.type for f in findings}
        assert FindingType.REDELEGATION_ATTEMPTED in types
        assert FindingType.SILENT_NARROWING not in types

    def test_always_complete_produces_only_silent_narrowing(self) -> None:
        run = _run("deterministic.always-complete", granted=_FULL_AUTHORITY)
        findings = task_contract_findings([run.outcome], [_plan("deterministic.always-complete")])
        types = {f.type for f in findings}
        assert types == {FindingType.SILENT_NARROWING}

    def test_permitted_substitution_produces_no_finding(self) -> None:
        """A scenario declaring must_not_substitute: false never flags it,
        regardless of what the invocation log shows."""
        run = _run("deterministic.substituting", granted=_FULL_AUTHORITY)
        permissive_plan = _plan("deterministic.substituting").model_copy(
            update={"must_not_substitute": False}
        )
        findings = task_contract_findings([run.outcome], [permissive_plan])
        assert not any(f.type is FindingType.CAPABILITY_SUBSTITUTED for f in findings)


class TestRetryDoesNotFalselyLookLikeSubstitution:
    """A same-capability on_failure: retry re-invocation must never be
    mistaken for a substitution by the positional comparison against the
    declared plan (execution/task_runner.py collapses consecutive repeats
    before comparing, precisely for this)."""

    def test_retry_of_denied_first_step_then_honest_second_step_is_not_substitution(self) -> None:
        adapter, materialized = _materialize(granted=AuthoritySet.of("keyvalue.write"))
        plan = TaskPlan(
            phase_name="run-task",
            task_id="t1",
            worker="deterministic.sequential",
            target_identity="agent-b",
            requires_capabilities=AuthoritySet.of("objectstore.read", "keyvalue.write"),
            steps=(
                TaskStepPlan(capability_id="objectstore.read", on_failure="retry"),
                TaskStepPlan(capability_id="keyvalue.write", on_failure="continue"),
            ),
        )
        bootstrap_ref = adapter.register_identity("bootstrap")
        run = run_task(
            adapter,
            materialized,
            plan,
            run_id="run-1",
            provisioning_ref=bootstrap_ref,
            now=lambda: datetime.now(UTC),
            salt="test-salt",
            namespace=adapter.namespace,
            sequence_start=0,
        )
        assert not run.outcome.substituted_capabilities
        denied = [o for o in run.observations if o.capability_id == "objectstore.read"]
        assert len(denied) == 2  # the original attempt plus exactly one retry
        assert all(o.outcome.outcome_class is OutcomeClass.DENIED_IMPLICIT for o in denied)
        # keyvalue.write (granted) still ran and is correctly recognized as
        # the declared last step, not a substitution, despite the retry
        # shifting its position in the raw invocation log.
        assert run.outcome.output_marker_verified_independently is True
