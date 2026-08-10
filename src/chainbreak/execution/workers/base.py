"""``TaskWorker`` Protocol (M14, F1): defined purely in terms of a
capability-invoker and a returned :class:`~chainbreak.core.models.TaskOutcome`
-- nothing about how a worker decides what to do, what scenario it is
running, or which provider is behind it. A future LLM-backed worker (v0.4,
ADR-007) must be able to implement exactly this same interface with no
downstream change; building this Protocol around
``execution/workers/deterministic.py``'s own implementation would foreclose
the comparison that makes this benchmark family worth having.

S1: ``CapabilityInvoker`` is the *only* way a worker may act. It is built by
``execution/task_runner.py``, closing over the real provider adapter,
identity ref, binding resolution and namespace -- a worker never sees a raw
provider client, so SI-2/SI-3 apply to task actions exactly as they do to
probes, by construction (the invoker's own implementation is what calls
``adapter.probe()``, the same choke point ``execution/matrix.py`` and
``execution/deferred.py`` already go through).

``redelegation_attempts`` and ``substituted_capabilities`` on the returned
``TaskOutcome`` are not read from a worker's own report: they are computed
by ``execution/task_runner.py`` from the invoker's own objective call log --
the same "never trust self-report for anything independently observable"
discipline F4 applies to the output marker. A worker's ``run()`` may set
either field to anything; the runner overwrites both, and always overwrites
``output_marker_verified_independently`` (which by definition cannot be
known until *after* the worker returns).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from chainbreak.core.enums import OutcomeClass
from chainbreak.core.ids import CapabilityId, IdentityId
from chainbreak.core.models import TaskOutcome

__all__ = ["CapabilityInvoker", "InvocationResult", "TaskStep", "TaskWorker"]


@dataclass(frozen=True, slots=True)
class TaskStep:
    """One declared step of a task -- the worker-facing projection of
    :class:`~chainbreak.core.models.TaskStepPlan`."""

    capability_id: CapabilityId
    on_failure: str  # "continue" | "abort" | "retry"


@dataclass(frozen=True, slots=True)
class InvocationResult:
    """What invoking one capability during a task actually did."""

    capability_id: CapabilityId
    outcome_class: OutcomeClass

    @property
    def succeeded(self) -> bool:
        return self.outcome_class is OutcomeClass.ALLOWED


CapabilityInvoker = Callable[[CapabilityId], InvocationResult]


@runtime_checkable
class TaskWorker(Protocol):
    """F1: a capability-invoker in, a ``TaskOutcome`` out. Nothing else."""

    def run(
        self,
        *,
        task_id: str,
        identity_id: IdentityId,
        steps: Sequence[TaskStep],
        invoke: CapabilityInvoker,
    ) -> TaskOutcome: ...
