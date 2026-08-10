"""Executes one compiled :class:`~chainbreak.core.models.ProbeMatrix`: C-2
preconditions, C-1 control-capability calibration per identity, C-6 shuffled
capability order with a recorded seed, and ADR-012's trial repetition.

A :class:`~chainbreak.core.errors.PreconditionFailedError` or
:class:`~chainbreak.core.errors.ControlCapabilityFailedError` raised from
here propagates to the caller uncaught. "Discard the matrix" -- throwing
away whatever was collected so far for it and moving on to the next one --
is ``orchestrator.py``'s job, not this module's; this module's only
responsibility is knowing *when* that must happen.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from chainbreak.capabilities.preconditions import PreconditionRegistry
from chainbreak.core.enums import PlanPhase
from chainbreak.core.errors import PreconditionFailedError
from chainbreak.core.ids import new_event_id
from chainbreak.core.models import CapabilityCatalog, IdentityRef, Observation, ProbeMatrix
from chainbreak.execution._records import build_observation
from chainbreak.execution.control import calibrate_matrix
from chainbreak.execution.delegation import MaterializedGraph
from chainbreak.execution.preconditions import (
    unsatisfied_preconditions,
    verify_matrix_preconditions,
)
from chainbreak.providers.base.protocol import ProviderAdapter
from chainbreak.providers.base.types import ProbeRequest

__all__ = ["MatrixRun", "estimate_matrix_duration_s", "run_probe_matrix"]

#: F6's own conservative per-probe estimate -- deliberately generous. An
#: overestimate only makes ``delegation.needs_redelegation`` trigger more
#: eagerly, trading a few extra ``delegate()`` calls for never risking a
#: credential expiring mid-matrix; an underestimate would risk the opposite.
_ESTIMATED_SECONDS_PER_PROBE = 0.05


def estimate_matrix_duration_s(matrix: ProbeMatrix) -> float:
    """F6's own rough estimate of how long this matrix will take to run --
    used only to size the re-delegation threshold, never reported as a real
    timing measurement (which would need a real Interval, not a guess)."""
    return (
        len(matrix.identities)
        * len(matrix.capabilities)
        * matrix.trials
        * _ESTIMATED_SECONDS_PER_PROBE
    )


def _row_seed(seed: int, matrix_id: str, identity_id: str) -> int:
    """Deterministic per-(matrix, identity) shuffle seed (C-6).

    sha256-derived rather than Python's own ``hash()``, which is randomized
    per-process by default (``PYTHONHASHSEED``) and would make "replaying
    the recorded seed reproduces the order" false across two separate
    processes with the same ``--seed``.
    """
    digest = hashlib.sha256(f"{seed}:{matrix_id}:{identity_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


@dataclass(frozen=True, slots=True)
class MatrixRun:
    observations: tuple[Observation, ...]
    events: tuple[dict[str, Any], ...]
    next_sequence: int


def run_probe_matrix(
    adapter: ProviderAdapter,
    matrix: ProbeMatrix,
    materialized: MaterializedGraph,
    catalog: CapabilityCatalog,
    precondition_registry: PreconditionRegistry,
    *,
    run_id: str,
    phase: PlanPhase,
    seed: int,
    provisioning_ref: IdentityRef,
    now: datetime,
    salt: str,
    namespace: str,
    sequence_start: int = 0,
) -> MatrixRun:
    # C-2: verified once for the whole matrix, before any probe in it runs.
    precondition_results = verify_matrix_preconditions(
        precondition_registry, catalog, matrix.capabilities, provisioning_ref
    )
    failed = unsatisfied_preconditions(precondition_results)
    if failed:
        raise PreconditionFailedError(
            f"matrix {matrix.matrix_id!r}: precondition(s) not satisfied: {failed}",
            matrix_id=matrix.matrix_id,
            preconditions=list(failed),
        )

    observations: list[Observation] = []
    events: list[dict[str, Any]] = []
    sequence = sequence_start
    control_ids = {capability.id for capability in catalog.controls()}

    for identity_id in matrix.identities:
        # A matrix identity always has a materialized ref: an unreachable
        # identity is a compile-time ScenarioSemanticError ("never reached"),
        # never a compiled matrix (G-2's own reachability guarantee -- see
        # orchestrator.py's identical guard).
        if identity_id not in materialized.refs:  # pragma: no cover
            continue
        ref: IdentityRef = materialized.refs[identity_id]
        credential = materialized.credentials.get(identity_id)

        # C-1: calibration, before anything else in this identity's row.
        # Raises ControlCapabilityFailedError uncaught on failure -- the
        # caller discards this whole matrix, not just this identity's row.
        calibration = calibrate_matrix(
            adapter,
            catalog,
            ref=ref,
            identity_id=identity_id,
            run_id=run_id,
            phase=phase,
            matrix_id=matrix.matrix_id,
            sequence=sequence,
            credential=credential,
            now=now,
            salt=salt,
            namespace=namespace,
        )
        observations.extend(calibration)
        sequence += len(calibration)

        # C-6: every capability except the controls just calibrated,
        # shuffled with a recorded, deterministic-per-(matrix, identity) seed.
        row_seed = _row_seed(seed, matrix.matrix_id, identity_id)
        capability_order = [c for c in matrix.capabilities if c not in control_ids]
        random.Random(row_seed).shuffle(  # noqa: S311  # nosec B311 -- reproducibility, not security
            capability_order
        )
        events.append(
            {
                "event_id": new_event_id(),
                "sequence": sequence,
                "kind": "PROBE_ORDER_SHUFFLED",
                "matrix_id": matrix.matrix_id,
                "identity_id": identity_id,
                "seed": row_seed,
                "capability_order": capability_order,
            }
        )

        for capability_id in capability_order:
            binding = adapter.resolve_capability(capability_id)
            for trial in range(1, matrix.trials + 1):
                result = adapter.probe(
                    ProbeRequest(
                        identity_ref=ref,
                        capability_id=capability_id,
                        binding=binding,
                        namespace=namespace,
                        trial=trial,
                    )
                )
                observations.append(
                    build_observation(
                        run_id=run_id,
                        sequence=sequence,
                        phase=phase,
                        matrix_id=matrix.matrix_id,
                        identity_id=identity_id,
                        identity_ref_value=ref.value,
                        capability_id=capability_id,
                        trial=trial,
                        trial_count=matrix.trials,
                        binding=binding,
                        namespace=namespace,
                        result=result,
                        credential=credential,
                        now=now,
                        preconditions_verified=True,
                        salt=salt,
                    )
                )
                sequence += 1

    return MatrixRun(observations=tuple(observations), events=tuple(events), next_sequence=sequence)
