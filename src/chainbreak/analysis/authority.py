"""Observations -> ``ProbeCellResult`` -> ``ObservedAuthority`` (AUTH-1, ADR-012).

Pure functions: no I/O, no clock reads, no provider knowledge. A cell is
resolved by **unanimity** (ADR-012) -- ``ProbeCellResult.resolved``
(``core/models.py``) already implements that rule; this module's job is
grouping raw observations into cells and turning resolved cells into the
``ObservedAuthority`` AUTH-1 requires: only ``ALLOWED`` cells contribute to
``capabilities``, every other outcome is either a denial (a real negative
measurement, simply absent from the set) or an exclusion (recorded in
``excluded`` with a reason -- never both, never neither).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping

from chainbreak.core.enums import ExclusionReason, OutcomeClass, PlanPhase
from chainbreak.core.ids import CapabilityId, IdentityId
from chainbreak.core.models import (
    AuthoritySet,
    AuthorizationGraph,
    Observation,
    ObservedAuthority,
    ProbeCellResult,
)

CellKey = tuple[IdentityId, CapabilityId, PlanPhase]

#: Maps a resolved (post-unanimity) outcome that is neither ALLOWED nor a
#: denial onto the reason it could not be classified. Every ``OutcomeClass``
#: member appears exactly once across this table and the denial/allowed
#: cases handled directly in :func:`resolve_cell`.
_EXCLUSION_BY_OUTCOME: Mapping[OutcomeClass, ExclusionReason] = {
    OutcomeClass.INDETERMINATE: ExclusionReason.TRIALS_DISAGREED,
    OutcomeClass.ERROR_TRANSIENT: ExclusionReason.TRANSIENT_ERRORS_EXHAUSTED,
    OutcomeClass.ERROR_INFRASTRUCTURE: ExclusionReason.INFRASTRUCTURE_ERROR,
    OutcomeClass.ERROR_RESOURCE_MISSING: ExclusionReason.INFRASTRUCTURE_ERROR,
}


def resolve_cell(cell: ProbeCellResult) -> tuple[OutcomeClass, ExclusionReason | None]:
    """Unanimity-resolve one cell (F1). Returns ``(resolved, exclusion)``;
    ``exclusion`` is ``None`` for both ``ALLOWED`` and every denial -- a
    denial is a real negative measurement, not a classification failure."""
    resolved = cell.resolved
    if resolved is OutcomeClass.ALLOWED or resolved.is_denial:
        return resolved, None
    return resolved, _EXCLUSION_BY_OUTCOME[resolved]


def aggregate_observations(
    observations: Iterable[Observation],
) -> dict[CellKey, ProbeCellResult]:
    """Group raw observations into one ``ProbeCellResult`` per
    ``(identity_id, capability_id, phase)``, trials ordered by trial number."""
    grouped: dict[CellKey, list[Observation]] = defaultdict(list)
    for observation in observations:
        key = (observation.identity_id, observation.capability_id, observation.phase)
        grouped[key].append(observation)

    cells: dict[CellKey, ProbeCellResult] = {}
    for key, obs_list in grouped.items():
        ordered = sorted(obs_list, key=lambda o: o.trial)
        identity_id, capability_id, phase = key
        cells[key] = ProbeCellResult(
            identity_id=identity_id,
            capability_id=capability_id,
            phase=phase,
            trials=tuple(o.outcome.outcome_class for o in ordered),
            observation_ids=tuple(o.observation_id for o in ordered),
        )
    return cells


def build_observed_authority(
    identity_id: IdentityId,
    phase: PlanPhase,
    probe_matrix_id: str,
    universe: AuthoritySet,
    cells_by_capability: Mapping[CapabilityId, ProbeCellResult],
) -> ObservedAuthority:
    """``universe`` is every capability this identity was probed against at
    this phase -- not only the ones it is expected to hold (F3 in M3): that
    is what makes authority expansion detectable at all. A capability in
    ``universe`` absent from ``cells_by_capability`` was never actually
    probed (``NOT_PROBED``) despite being in scope."""
    capabilities: set[str] = set()
    excluded: dict[str, ExclusionReason] = {}
    classified = 0

    for capability_id in universe:
        cell = cells_by_capability.get(capability_id)
        if cell is None:
            excluded[capability_id] = ExclusionReason.NOT_PROBED
            continue
        resolved, reason = resolve_cell(cell)
        if resolved is OutcomeClass.ALLOWED:
            capabilities.add(capability_id)
            classified += 1
        elif reason is None:  # a denial: classified, but not held
            classified += 1
        else:
            excluded[capability_id] = reason

    return ObservedAuthority(
        capabilities=AuthoritySet.from_iterable(capabilities),
        excluded=excluded,
        phase=phase,
        probe_matrix_id=probe_matrix_id,
        attempted=len(universe),
        classified=classified,
    )


def populate_observed_authority(
    graph: AuthorizationGraph,
    observations: Iterable[Observation],
    *,
    phase: PlanPhase,
) -> AuthorizationGraph:
    """Return a new graph with ``observed_authority`` populated on every node
    that was probed at ``phase``, derived entirely from ``observations``.
    Nodes with no observations at this phase are returned unchanged (graph
    nodes are frozen; this never mutates the input).
    """
    cells = aggregate_observations(o for o in observations if o.phase is phase)

    by_identity: dict[IdentityId, dict[CapabilityId, ProbeCellResult]] = defaultdict(dict)
    matrix_id_by_identity: dict[IdentityId, str] = {}
    for (identity_id, capability_id, _phase), cell in cells.items():
        by_identity[identity_id][capability_id] = cell
    for observation in observations:
        if observation.phase is phase and observation.identity_id not in matrix_id_by_identity:
            matrix_id_by_identity[observation.identity_id] = observation.probe_matrix_id

    new_nodes = []
    for node in graph.nodes:
        identity_cells = by_identity.get(node.identity_id)
        if not identity_cells:
            new_nodes.append(node)
            continue
        universe = AuthoritySet.from_iterable(identity_cells)
        observed = build_observed_authority(
            node.identity_id,
            phase,
            matrix_id_by_identity[node.identity_id],
            universe,
            identity_cells,
        )
        new_nodes.append(node.model_copy(update={"observed_authority": observed}))

    return graph.model_copy(update={"nodes": tuple(new_nodes)})
