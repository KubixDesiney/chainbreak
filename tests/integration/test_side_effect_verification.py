"""M14's own stated core test: a worker claiming an output marker it did
not write must be caught even when its step counts are internally
consistent -- the milestone's own explicit reasoning for why independent
verification, not self-report cross-checking, is what makes this family's
detection robust.

Exercises ``execution/side_effects.py::verify_output_marker`` both directly
and through ``execution/task_runner.py``'s real wiring.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from chainbreak.core.enums import DelegationMechanism, TaskStatus
from chainbreak.core.models import AuthoritySet, DelegationEdge, TaskOutcome, TaskPlan, TaskStepPlan
from chainbreak.execution.delegation import MaterializedGraph
from chainbreak.execution.side_effects import marker_id_for, verify_output_marker
from chainbreak.execution.task_runner import run_task
from chainbreak.providers.base.types import DelegationRequest
from chainbreak.providers.fake.adapter import FakeProviderAdapter

pytestmark = pytest.mark.integration

_FULL_AUTHORITY = AuthoritySet.of("objectstore.read", "keyvalue.write")
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


class TestVerifyOutputMarkerDirectly:
    def test_absent_marker_is_unverified(self) -> None:
        adapter = FakeProviderAdapter(seed=1)
        bootstrap_ref = adapter.register_identity("bootstrap")
        assert (
            verify_output_marker(adapter, bootstrap_ref, run_id="run-1", task_id="never-written")
            is False
        )

    def test_recorded_marker_is_verified(self) -> None:
        adapter = FakeProviderAdapter(seed=1)
        bootstrap_ref = adapter.register_identity("bootstrap")
        adapter.record_scratch_marker(marker_id_for("run-1", "task-a"))
        verified = verify_output_marker(adapter, bootstrap_ref, run_id="run-1", task_id="task-a")
        assert verified is True

    def test_marker_is_scoped_to_run_and_task(self) -> None:
        """A marker recorded for one run/task must not verify a different
        one -- T-08's run-scoping requirement applies here too."""
        adapter = FakeProviderAdapter(seed=1)
        bootstrap_ref = adapter.register_identity("bootstrap")
        adapter.record_scratch_marker(marker_id_for("run-1", "task-a"))
        assert (
            verify_output_marker(adapter, bootstrap_ref, run_id="run-2", task_id="task-a") is False
        )
        assert (
            verify_output_marker(adapter, bootstrap_ref, run_id="run-1", task_id="task-b") is False
        )

    def test_adapter_without_the_escape_hatch_reports_unverified_never_a_guess(self) -> None:
        class _NoMarkerSupport:
            pass

        adapter = _NoMarkerSupport()
        assert verify_output_marker(adapter, object(), run_id="run-1", task_id="task-a") is False


class TestConsistentLiarCaughtByIndependentVerification:
    """The milestone's own core case: deterministic.always-complete reports
    an internally consistent COMPLETE (steps_succeeded == steps_total) --
    comparing status against self-reported step counts alone finds
    *nothing wrong*. Only independent verification catches it."""

    def test_self_reported_counts_are_internally_consistent(self) -> None:
        adapter, materialized = _materialize(granted=_FULL_AUTHORITY)
        bootstrap_ref = adapter.register_identity("bootstrap")
        plan = TaskPlan(
            phase_name="run-task",
            task_id="t1",
            worker="deterministic.always-complete",
            target_identity="agent-b",
            requires_capabilities=_FULL_AUTHORITY,
            steps=_STEPS,
        )
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
        # The claim alone is self-consistent: COMPLETE and steps_succeeded
        # == steps_total agree with each other.
        assert not run.outcome.claims_complete_but_is_not
        # Yet independent verification -- the only thing that actually
        # touches the fake's own storage rather than the worker's claim --
        # disagrees with the marker claim, which is what actually catches it.
        assert run.outcome.claims_output_that_does_not_exist
        assert run.outcome.output_marker_verified_independently is False

    def test_caught_even_though_it_never_touched_the_real_provider_at_all(self) -> None:
        """The strongest form of the case: this worker doesn't even
        attempt anything (no observations at all), so there is no
        "compare claimed vs. actual step outcomes" signal whatsoever --
        the marker check is the only thing that can catch it."""
        adapter, materialized = _materialize(granted=_FULL_AUTHORITY)
        bootstrap_ref = adapter.register_identity("bootstrap")
        plan = TaskPlan(
            phase_name="run-task",
            task_id="t1",
            worker="deterministic.always-complete",
            target_identity="agent-b",
            requires_capabilities=_FULL_AUTHORITY,
            steps=_STEPS,
        )
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
        assert run.observations == ()
        assert run.outcome.output_marker_written is True
        assert run.outcome.output_marker_verified_independently is False


class _NoScratchMarkerSupportAdapter:
    """A minimal stand-in shaped like a future real-time adapter (M17):
    no ``record_scratch_marker``/``scratch_marker_exists`` escape hatches.
    ``execution/task_runner.py`` must still run correctly against it --
    just always reporting the marker unverified, never guessing."""

    def __init__(self, inner: FakeProviderAdapter) -> None:
        self._inner = inner
        self.namespace = inner.namespace

    def resolve_capability(self, capability_id: str):
        return self._inner.resolve_capability(capability_id)

    def probe(self, request):
        return self._inner.probe(request)

    def delegate(self, request):
        return self._inner.delegate(request)


class TestNoScratchMarkerHook:
    def test_task_runner_still_runs_and_reports_unverified(self) -> None:
        inner, materialized = _materialize(granted=_FULL_AUTHORITY)
        adapter = _NoScratchMarkerSupportAdapter(inner)
        bootstrap_ref = inner.register_identity("bootstrap")
        plan = TaskPlan(
            phase_name="run-task",
            task_id="t1",
            worker="deterministic.sequential",
            target_identity="agent-b",
            requires_capabilities=_FULL_AUTHORITY,
            steps=_STEPS,
        )
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
        assert run.outcome.status is TaskStatus.COMPLETE  # the real steps still succeeded
        assert run.outcome.output_marker_verified_independently is False


class TestHonestWorkerMarkerAgreesWithVerification:
    def test_successful_last_step_is_independently_confirmed(self) -> None:
        adapter, materialized = _materialize(granted=_FULL_AUTHORITY)
        bootstrap_ref = adapter.register_identity("bootstrap")
        plan = TaskPlan(
            phase_name="run-task",
            task_id="t1",
            worker="deterministic.sequential",
            target_identity="agent-b",
            requires_capabilities=_FULL_AUTHORITY,
            steps=_STEPS,
        )
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
        assert run.outcome.status is TaskStatus.COMPLETE
        assert run.outcome.output_marker_written == run.outcome.output_marker_verified_independently
        assert run.outcome.output_marker_verified_independently is True
        assert isinstance(run.outcome, TaskOutcome)
