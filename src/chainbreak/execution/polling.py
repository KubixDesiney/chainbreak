"""Serial polling for one (identity, capability) cell during a revocation
transition (F2/F3): advances the provider's clock by the compiled
``interval_ms``, probes, and records an :class:`~chainbreak.core.models
.Observation` per poll -- both before a mutation (warming a stable-ALLOW
baseline, F3) and after one (waiting for a stable denial, F2) use this same
function, distinguished only by the compiled ``PollPlan.stop_on`` target.

Every poll observation is tagged ``PlanPhase.POST_MUTATION`` regardless of
whether it ran before or after the mutation it is measuring against: F5's
revocation window is computed purely from each sample's monotonic timestamp
relative to the mutation's own ``t_M``, so the *phase* on the wire only
needs to mark "this observation is polling-family data", not encode which
side of the mutation it fell on (:mod:`chainbreak.analysis.pipeline`'s
``_revocation_findings`` already relies on exactly this).

**Clock advance.** ``advance_clock`` is a fake-adapter-specific escape hatch
(not part of the ``ProviderAdapter`` Protocol, matching ``cli/run.py``'s own
precedent). When it is absent, this module sleeps against the shared
monotonic run deadline between real-provider polls.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from chainbreak.core.clock import RunClock
from chainbreak.core.enums import OutcomeClass, PlanPhase
from chainbreak.core.errors import ExecutionError
from chainbreak.core.models import Observation, PollPlan
from chainbreak.execution._records import build_observation
from chainbreak.execution.delegation import MaterializedGraph
from chainbreak.providers.base.protocol import ProviderAdapter
from chainbreak.providers.base.types import ProbeRequest

__all__ = ["PollRun", "run_poll_phase"]


@dataclass(frozen=True, slots=True)
class PollRun:
    observations: tuple[Observation, ...]
    next_sequence: int
    stop_reason: str
    poll_count: int


def _matches_target(outcome_class: OutcomeClass, *, stop_on: str) -> bool:
    # Only ever called for STABLE_ALLOW/STABLE_DENIAL -- run_poll_phase's own
    # loop skips this entirely when stop_on is TIMEOUT (it never stabilizes
    # early by design).
    if stop_on == "STABLE_ALLOW":
        return outcome_class is OutcomeClass.ALLOWED
    return outcome_class.is_denial


def run_poll_phase(
    adapter: ProviderAdapter,
    materialized: MaterializedGraph,
    plan: PollPlan,
    *,
    run_id: str,
    matrix_id: str,
    now: Callable[[], datetime],
    salt: str,
    namespace: str,
    sequence_start: int,
    clock: RunClock | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> PollRun:
    identity_id = plan.target_identity
    if identity_id not in materialized.refs:
        raise ExecutionError(
            f"poll target {identity_id!r} is not a materialized identity in this run",
            target_identity=identity_id,
        )
    ref = materialized.refs[identity_id]
    credential = materialized.credentials.get(identity_id)
    binding = adapter.resolve_capability(plan.capability_id)

    observations: list[Observation] = []
    sequence = sequence_start
    consecutive = 0
    elapsed_ms = 0
    max_ms = plan.max_duration_seconds * 1000
    advance_clock = getattr(adapter, "advance_clock", None)
    stop_reason = "TIMEOUT"

    while True:
        if advance_clock is not None:
            advance_clock(plan.interval_ms)
        else:
            # Real providers need wall time for propagation to occur.  Sleep
            # against the monotonic run deadline, never past it.
            if clock is not None:
                clock.check()
                if clock.remaining_seconds < plan.interval_ms / 1000:
                    sleep(clock.remaining_seconds)
                    clock.check()
            else:
                sleep(plan.interval_ms / 1000)
        elapsed_ms += plan.interval_ms
        current_time = now()

        result = adapter.probe(
            ProbeRequest(
                identity_ref=ref,
                capability_id=plan.capability_id,
                binding=binding,
                namespace=namespace,
                trial=1,
            )
        )
        if clock is not None:
            clock.check()
        observations.append(
            build_observation(
                run_id=run_id,
                sequence=sequence,
                phase=PlanPhase.POST_MUTATION,
                matrix_id=matrix_id,
                identity_id=identity_id,
                identity_ref_value=ref.value,
                capability_id=plan.capability_id,
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

        if plan.stop_on != "TIMEOUT":
            if _matches_target(result.outcome.outcome_class, stop_on=plan.stop_on):
                consecutive += 1
            else:
                consecutive = 0
            if consecutive >= plan.stability_count:
                stop_reason = plan.stop_on
                break

        if elapsed_ms >= max_ms:
            stop_reason = "TIMEOUT"
            break

    return PollRun(
        observations=tuple(observations),
        next_sequence=sequence,
        stop_reason=stop_reason,
        poll_count=len(observations),
    )
