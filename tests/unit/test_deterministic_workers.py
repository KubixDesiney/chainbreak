"""``execution/workers/deterministic.py`` (M14): the branches easiest to
exercise directly against a stub ``CapabilityInvoker`` rather than a full
provider/materialized graph -- ``on_failure: abort``, an all-steps-denied
FAILED status, a substituting worker's own earlier step also denied, a
redelegating worker whose real steps are also denied, and the worker
registry's unknown-id error.
"""

from __future__ import annotations

import pytest

from chainbreak.core.enums import OutcomeClass, TaskStatus
from chainbreak.core.errors import ExecutionError
from chainbreak.execution.workers.base import InvocationResult, TaskStep
from chainbreak.execution.workers.deterministic import WORKERS, resolve_worker

pytestmark = pytest.mark.unit

_STEPS = (
    TaskStep(capability_id="objectstore.read", on_failure="abort"),
    TaskStep(capability_id="keyvalue.write", on_failure="continue"),
)


def _all_denied_invoker(capability_id: str) -> InvocationResult:
    return InvocationResult(capability_id=capability_id, outcome_class=OutcomeClass.DENIED_IMPLICIT)


class TestSequentialAbort:
    def test_abort_stops_before_the_second_step(self) -> None:
        worker = WORKERS["deterministic.sequential"]
        outcome = worker.run(
            task_id="t1", identity_id="agent-b", steps=_STEPS, invoke=_all_denied_invoker
        )
        assert outcome.steps_attempted == 1  # never reached the second step
        assert outcome.status is TaskStatus.FAILED


class TestSequentialAllDeniedIsFailed:
    def test_status_failed_when_nothing_succeeds(self) -> None:
        worker = WORKERS["deterministic.sequential"]
        continue_steps = (
            TaskStep(capability_id="objectstore.read", on_failure="continue"),
            TaskStep(capability_id="keyvalue.write", on_failure="continue"),
        )
        outcome = worker.run(
            task_id="t1", identity_id="agent-b", steps=continue_steps, invoke=_all_denied_invoker
        )
        assert outcome.status is TaskStatus.FAILED
        assert outcome.steps_succeeded == 0
        assert outcome.steps_attempted == 2  # both attempted, both denied


class TestSubstitutingEarlierStepAlsoDenied:
    def test_a_non_final_step_can_also_fail(self) -> None:
        worker = WORKERS["deterministic.substituting"]
        outcome = worker.run(
            task_id="t1",
            identity_id="agent-b",
            steps=_STEPS,
            invoke=_all_denied_invoker,
        )
        # The worker always claims full success (F3-adjacent dishonesty),
        # but its own step_outcomes record what the invoker actually said.
        assert outcome.step_outcomes[0].succeeded is False
        assert outcome.status is TaskStatus.COMPLETE


class TestRedelegatingRealStepsCanFailToo:
    def test_insufficient_authority_reported_when_real_steps_are_denied(self) -> None:
        worker = WORKERS["deterministic.redelegating"]
        outcome = worker.run(
            task_id="t1", identity_id="agent-b", steps=_STEPS, invoke=_all_denied_invoker
        )
        assert outcome.reported_insufficient_authority is True
        assert outcome.output_marker_written is False


class TestResolveWorkerUnknownId:
    def test_unknown_worker_id_raises_naming_known_workers(self) -> None:
        with pytest.raises(ExecutionError, match="no worker registered") as excinfo:
            resolve_worker("deterministic.nonexistent")
        assert excinfo.value.context["worker_id"] == "deterministic.nonexistent"
