"""``WAIT`` and ``DEFERRED_EXECUTION`` phases (M13): the stale-authority
benchmark's own execution machinery, sitting alongside
``execution/mutation.py``/``polling.py``/``revert.py`` as the compiler's
per-``PhaseKind`` execution modules.

**WAIT (F2).** The deferral interval is advanced on the provider's own
virtual clock when one exists (``advance_clock``, the same fake-adapter-
specific escape hatch ``execution/polling.py`` already uses) so a 600 s
deferral runs instantly in CI; a real-time adapter without that hook falls
back to actually sleeping against the shared monotonic deadline. Either way,
the credential materialized before this phase is never touched: no keepalive,
no refresh. The waiting is the experiment.

**DEFERRED_EXECUTION (F1/F3).** Resolves the pinned credential recorded at
an earlier phase (``execution/credential_store.py``), probes every
capability in the compiled universe *without* re-delegating (unlike
``matrix.py``'s ordinary PROBE handling, which always calls
``delegation.ensure_fresh_credential`` first -- skipping that call is the
whole point: F1 requires the deferred probe to use exactly the credential
minted at ``credential_source``, not a possibly-refreshed one), tags those
observations ``PlanPhase.DEFERRED_EXECUTION``, then *unconditionally* mints
a brand-new credential for the same identity (never merely "if the old one
is close to expiring" -- ``ensure_fresh_credential``'s F6 threshold would
frequently decide a still-comfortably-valid pinned credential needs no
refresh, which would silently reuse the *same* session for the "fresh" leg
and defeat F3 entirely) and immediately probes again, tagged
``PlanPhase.PAIRED_FRESH_CREDENTIAL``. The pair is the measurement
(EXPERIMENT_PROTOCOL.md section 4, step 6).

Order matters and is deliberate: the pinned probe runs *before* the fresh
credential is minted, because the fake adapter tracks liveness/session-scope
per identity keyed to its *most recently issued* credential
(``providers/fake/adapter.py``) -- delegating first would make the "pinned"
probe silently observe the fresh session instead.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from chainbreak.core.clock import RunClock
from chainbreak.core.enums import PlanPhase
from chainbreak.core.errors import ExecutionError
from chainbreak.core.ids import new_event_id
from chainbreak.core.models import DeferredExecutionPlan, Observation, WaitPlan
from chainbreak.execution._records import build_observation
from chainbreak.execution.credential_store import CredentialStore
from chainbreak.execution.delegation import MaterializedGraph
from chainbreak.providers.base.protocol import ProviderAdapter
from chainbreak.providers.base.types import DelegationRequest, ProbeRequest

__all__ = ["DeferredExecutionRun", "run_deferred_execution_phase", "run_wait_phase"]


def run_wait_phase(
    adapter: ProviderAdapter,
    plan: WaitPlan,
    *,
    sequence: int,
    clock: RunClock | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """F2: advance time by ``plan.wait_seconds`` without touching any
    credential. Returns the ``WAIT_COMPLETED`` evidence event."""
    advance_clock = getattr(adapter, "advance_clock", None)
    if advance_clock is not None:
        advance_clock(plan.wait_seconds * 1000)
        mechanism = "virtual_clock"
    else:
        if clock is not None:
            clock.check()
            if clock.remaining_seconds < plan.wait_seconds:
                sleep(clock.remaining_seconds)
                clock.check()
            else:
                sleep(plan.wait_seconds)
                clock.check()
        else:
            sleep(plan.wait_seconds)
        mechanism = "real_sleep"
    return {
        "event_id": new_event_id(),
        "sequence": sequence,
        "kind": "WAIT_COMPLETED",
        "phase_name": plan.phase_name,
        "wait_seconds": plan.wait_seconds,
        "mechanism": mechanism,
    }


@dataclass(frozen=True, slots=True)
class DeferredExecutionRun:
    observations: tuple[Observation, ...]
    events: tuple[dict[str, Any], ...]
    next_sequence: int


def run_deferred_execution_phase(
    adapter: ProviderAdapter,
    materialized: MaterializedGraph,
    credential_store: CredentialStore,
    plan: DeferredExecutionPlan,
    *,
    run_id: str,
    now: Callable[[], datetime],
    salt: str,
    namespace: str,
    sequence_start: int,
) -> DeferredExecutionRun:
    identity_id = plan.target_identity
    if identity_id not in materialized.refs:  # pragma: no cover -- G-2's own reachability guarantee
        raise ExecutionError(
            f"DEFERRED_EXECUTION target {identity_id!r} is not a materialized identity",
            target_identity=identity_id,
        )
    edge = materialized.edges_by_target.get(identity_id)
    if edge is None:
        raise ExecutionError(
            f"DEFERRED_EXECUTION target {identity_id!r} has no delegation edge to re-delegate "
            "along -- the paired fresh-credential probe (F3) requires a delegated identity, "
            "never the root",
            target_identity=identity_id,
        )

    pinned_credential = credential_store.resolve(plan.credential_source, identity_id)

    # M13: from here on, this identity's probes consult a snapshot frozen at
    # each delegate() call rather than live/pending state -- the mechanism
    # that makes STALE_AUTHORITY_LIVE_CREDENTIAL genuinely, deterministically
    # observable rather than racing the fake's propagation-delay clock (see
    # providers/fake/adapter.py::enable_authority_caching's own docstring).
    # A real-time adapter has no such hook; the deferred probe still runs
    # correctly against it (M17), just without this fake-specific control.
    enable_caching = getattr(adapter, "enable_authority_caching", None)
    if enable_caching is not None:
        enable_caching(identity_id)

    observations: list[Observation] = []
    events: list[dict[str, Any]] = []
    sequence = sequence_start
    current_time = now()

    ref = materialized.refs[identity_id]
    for capability_id in plan.capabilities:
        binding = adapter.resolve_capability(capability_id)
        result = adapter.probe(
            ProbeRequest(
                identity_ref=ref,
                capability_id=capability_id,
                binding=binding,
                namespace=namespace,
                trial=1,
            )
        )
        observations.append(
            build_observation(
                run_id=run_id,
                sequence=sequence,
                phase=PlanPhase.DEFERRED_EXECUTION,
                matrix_id=f"pm-{plan.phase_name}",
                identity_id=identity_id,
                identity_ref_value=ref.value,
                capability_id=capability_id,
                trial=1,
                trial_count=1,
                binding=binding,
                namespace=namespace,
                result=result,
                credential=pinned_credential,
                now=current_time,
                preconditions_verified=True,
                salt=salt,
            )
        )
        sequence += 1

    # F3: unconditional -- never gated by remaining lifetime (unlike
    # delegation.ensure_fresh_credential's F6 threshold).
    fresh_result = adapter.delegate(
        DelegationRequest(
            source_identity=materialized.refs[edge.source_id],
            target_identity_id=edge.target_id,
            mechanism=edge.mechanism,
            requested_duration_s=edge.credential_lifetime_s,
            intended_capabilities=edge.intended_capabilities,
        )
    )
    materialized.refs[identity_id] = fresh_result.identity_ref
    materialized.credentials[identity_id] = fresh_result.record
    fresh_result.credential.scrub()  # M11 S2 -- see delegation.py's identical comment
    fresh_credential = fresh_result.record

    events.append(
        {
            "event_id": new_event_id(),
            "sequence": sequence,
            "kind": "PAIRED_FRESH_CREDENTIAL_MINTED",
            "phase_name": plan.phase_name,
            "identity_id": identity_id,
            "edge_id": edge.edge_id,
            "pinned_credential_id": pinned_credential.credential_id,
            "fresh_credential_id": fresh_credential.credential_id,
        }
    )
    sequence += 1

    fresh_ref = materialized.refs[identity_id]
    for capability_id in plan.capabilities:
        binding = adapter.resolve_capability(capability_id)
        result = adapter.probe(
            ProbeRequest(
                identity_ref=fresh_ref,
                capability_id=capability_id,
                binding=binding,
                namespace=namespace,
                trial=1,
            )
        )
        observations.append(
            build_observation(
                run_id=run_id,
                sequence=sequence,
                phase=PlanPhase.PAIRED_FRESH_CREDENTIAL,
                matrix_id=f"pm-{plan.phase_name}",
                identity_id=identity_id,
                identity_ref_value=fresh_ref.value,
                capability_id=capability_id,
                trial=1,
                trial_count=1,
                binding=binding,
                namespace=namespace,
                result=result,
                credential=fresh_credential,
                now=current_time,
                preconditions_verified=True,
                salt=salt,
            )
        )
        sequence += 1

    return DeferredExecutionRun(
        observations=tuple(observations), events=tuple(events), next_sequence=sequence
    )
