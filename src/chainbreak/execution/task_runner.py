"""Drives one compiled :class:`~chainbreak.core.models.TaskPlan` through its
resolved :class:`~chainbreak.execution.workers.base.TaskWorker` (M14).

Builds the one :class:`~chainbreak.execution.workers.base.CapabilityInvoker`
the worker is confined to (S1: never a raw provider client -- every real
invocation goes through the exact same ``adapter.probe()`` choke point
``execution/matrix.py``/``execution/deferred.py`` already use, so SI-2/SI-3
apply to task actions exactly as to probes), and objectively overrides two
fields on the worker's own returned :class:`~chainbreak.core.models.TaskOutcome`
from the invoker's own call log rather than trusting the worker's self-report
for either:

* ``redelegation_attempts`` -- an ``identity.delegate`` invocation is never
  actually performed (S2: recorded and refused, never permitted); the
  invoker intercepts it before it ever reaches the provider and counts it
  itself.
* ``substituted_capabilities`` -- computed by comparing what was actually
  invoked, in order, against the plan's declared steps (consecutive repeats
  of one capability collapsed first, so a legitimate ``on_failure: retry``
  is never mistaken for a substitution).

``output_marker_verified_independently`` is deliberately *not* set here --
that is ``execution/side_effects.py``'s job, called separately by
``execution/orchestrator.py`` after this returns, using the bootstrap
identity rather than anything this module touches.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from chainbreak.core.enums import OutcomeClass, PlanPhase
from chainbreak.core.errors import ExecutionError
from chainbreak.core.ids import CapabilityId, new_event_id
from chainbreak.core.models import (
    EMPTY_AUTHORITY,
    AuthoritySet,
    IdentityRef,
    Observation,
    TaskOutcome,
    TaskPlan,
)
from chainbreak.execution._records import build_observation
from chainbreak.execution.delegation import MaterializedGraph
from chainbreak.execution.side_effects import marker_id_for, verify_output_marker
from chainbreak.execution.workers.base import InvocationResult, TaskStep
from chainbreak.execution.workers.deterministic import resolve_worker
from chainbreak.providers.base.protocol import ProviderAdapter
from chainbreak.providers.base.types import ProbeRequest

__all__ = ["TaskRun", "run_task"]

#: S2: never actually performed -- intercepted by the invoker before it
#: would otherwise reach adapter.delegate().
_REDELEGATE_CAPABILITY: CapabilityId = "identity.delegate"


@dataclass(frozen=True, slots=True)
class TaskRun:
    observations: tuple[Observation, ...]
    events: tuple[dict[str, Any], ...]
    outcome: TaskOutcome
    next_sequence: int


def _collapse_consecutive_repeats(
    invocations: list[tuple[str, OutcomeClass]],
) -> list[tuple[str, OutcomeClass]]:
    """Folds a same-capability ``on_failure: retry`` re-invocation into the
    single declared-step slot it belongs to (keeping the latest outcome),
    so positional comparison against the declared plan below never mistakes
    an honest retry for a substitution."""
    collapsed: list[tuple[str, OutcomeClass]] = []
    for capability_id, outcome_class in invocations:
        if collapsed and collapsed[-1][0] == capability_id:
            collapsed[-1] = (capability_id, outcome_class)
        else:
            collapsed.append((capability_id, outcome_class))
    return collapsed


def _compute_substitutions(
    plan: TaskPlan, invocations: list[tuple[str, OutcomeClass]]
) -> AuthoritySet:
    collapsed = _collapse_consecutive_repeats(invocations)
    substituted = {
        invoked_capability
        for declared, (invoked_capability, _outcome) in zip(plan.steps, collapsed, strict=False)
        if invoked_capability != declared.capability_id
    }
    return AuthoritySet.from_iterable(substituted) if substituted else EMPTY_AUTHORITY


def run_task(
    adapter: ProviderAdapter,
    materialized: MaterializedGraph,
    plan: TaskPlan,
    *,
    run_id: str,
    provisioning_ref: IdentityRef,
    now: Callable[[], datetime],
    salt: str,
    namespace: str,
    sequence_start: int,
) -> TaskRun:
    identity_id = plan.target_identity
    if identity_id not in materialized.refs:  # pragma: no cover -- G-2's own reachability guarantee
        raise ExecutionError(
            f"TASK target {identity_id!r} is not a materialized identity in this run",
            target_identity=identity_id,
        )
    ref = materialized.refs[identity_id]
    credential = materialized.credentials.get(identity_id)

    observations: list[Observation] = []
    events: list[dict[str, Any]] = []
    sequence = sequence_start
    invocation_log: list[tuple[str, OutcomeClass]] = []
    redelegation_attempts = 0
    current_time = now()

    def invoke(capability_id: str) -> InvocationResult:
        nonlocal sequence, redelegation_attempts
        if capability_id == _REDELEGATE_CAPABILITY:
            redelegation_attempts += 1
            events.append(
                {
                    "event_id": new_event_id(),
                    "sequence": sequence,
                    "kind": "REDELEGATION_ATTEMPT_REFUSED",
                    "task_id": plan.task_id,
                    "identity_id": identity_id,
                }
            )
            sequence += 1
            return InvocationResult(
                capability_id=capability_id, outcome_class=OutcomeClass.DENIED_EXPLICIT
            )

        binding = adapter.resolve_capability(capability_id)
        result = adapter.probe(
            ProbeRequest(
                identity_ref=ref,
                capability_id=capability_id,
                binding=binding,
                namespace=namespace,
                trial=1,
                operation_id=f"{plan.task_id}/{capability_id}",
            )
        )
        observations.append(
            build_observation(
                run_id=run_id,
                sequence=sequence,
                phase=PlanPhase.TASK_EXECUTION,
                matrix_id=f"pm-{plan.phase_name}",
                identity_id=identity_id,
                identity_ref_value=ref.value,
                capability_id=capability_id,
                trial=1,
                trial_count=1,
                binding=binding,
                namespace=namespace,
                result=result,
                credential=credential,
                now=current_time,
                preconditions_verified=True,
                salt=salt,
            )
        )
        sequence += 1
        outcome_class = result.outcome.outcome_class
        invocation_log.append((capability_id, outcome_class))
        return InvocationResult(capability_id=capability_id, outcome_class=outcome_class)

    worker = resolve_worker(plan.worker)
    steps = tuple(
        TaskStep(capability_id=s.capability_id, on_failure=s.on_failure) for s in plan.steps
    )
    draft = worker.run(task_id=plan.task_id, identity_id=identity_id, steps=steps, invoke=invoke)

    # F4's write side: the marker exists only if the declared *last* step
    # was the last thing actually invoked, under its own declared
    # capability, and it succeeded -- never because the worker claims so.
    last_invocation = invocation_log[-1] if invocation_log else None
    if (
        last_invocation is not None
        and last_invocation[0] == plan.steps[-1].capability_id
        and last_invocation[1] is OutcomeClass.ALLOWED
    ):
        record_marker = getattr(adapter, "record_scratch_marker", None)
        if record_marker is not None:
            record_marker(marker_id_for(run_id, plan.task_id))

    # F4: independent verification is what actually decides this field --
    # draft.output_marker_written above is the worker's claim, kept
    # separately in the final outcome for comparison, never copied here.
    verified = verify_output_marker(
        adapter,
        provisioning_ref,
        run_id=run_id,
        task_id=plan.task_id,
        output_capability=plan.steps[-1].capability_id,
    )
    outcome = draft.model_copy(
        update={
            "redelegation_attempts": redelegation_attempts,
            "substituted_capabilities": _compute_substitutions(plan, invocation_log),
            "output_marker_verified_independently": verified,
        }
    )
    events.append(
        {
            "event_id": new_event_id(),
            "sequence": sequence,
            "kind": "TASK_OUTCOME_RECORDED",
            "task_outcome": outcome.model_dump(mode="json"),
        }
    )
    sequence += 1

    return TaskRun(
        observations=tuple(observations),
        events=tuple(events),
        outcome=outcome,
        next_sequence=sequence,
    )
