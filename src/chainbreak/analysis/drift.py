"""F6 (M11): divergence reported as a **rate per hop**, never a raw count per
chain, with the excluded-trial count reported alongside it.

Depth and total probe count are confounded by construction: a depth-6 chain
issues more probes, runs longer, and has strictly more opportunity for a
transient fault to exclude a cell than a depth-2 chain does. Reporting a raw
divergence *count* across a depth sweep would make deeper chains look more
drift-prone for a reason that has nothing to do with delegation drift itself.
This module is the one place that comparison is made honestly: a rate,
normalized by hop count, with the exclusion rate computed the same way and
reported next to it -- and an explicit ``INCONCLUSIVE`` verdict when both
rise together, since that pattern cannot be attributed to depth alone
(RESEARCH_METHODOLOGY.md's own H8/RQ5).

Deliberately downstream of :mod:`chainbreak.analysis.pipeline`: a
:class:`DepthResult` is built from one already-analyzed bundle's
:class:`~chainbreak.analysis.pipeline.AnalysisResult` plus its populated
graph, never by re-deriving divergence itself -- that stays
``graph/divergence.py``'s and ``analysis/pipeline.py``'s job.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from chainbreak.core.enums import FindingType, PlanPhase
from chainbreak.core.models import AuthorizationGraph, Finding

__all__ = [
    "DepthResult",
    "DepthSweepReport",
    "build_depth_result",
    "depth_result_from_bundle",
    "summarize_depth_sweep",
]

_DRIFT_FINDING_TYPES = frozenset({FindingType.DELEGATION_DRIFT, FindingType.AUTHORITY_EXPANSION})


@dataclass(frozen=True, slots=True)
class DepthResult:
    """One depth's own measurement, for one phase of one compiled scenario.

    ``total_hops``/``total_cells`` count only non-root, *measured* nodes --
    the root is never a delegation hop, and an unmeasured node contributes
    to neither a divergence nor an exclusion rate (it was never probed at
    that phase at all, which coverage already reports separately).
    """

    depth: int
    scenario_id: str
    total_hops: int
    diverged_hops: int
    excluded_cells: int
    total_cells: int

    @property
    def divergence_rate_per_hop(self) -> float:
        return self.diverged_hops / self.total_hops if self.total_hops else 0.0

    @property
    def exclusion_rate(self) -> float:
        return self.excluded_cells / self.total_cells if self.total_cells else 0.0


@dataclass(frozen=True, slots=True)
class DepthSweepReport:
    """F6's own output: results ordered by depth, plus the confound verdict."""

    results: tuple[DepthResult, ...]
    inconclusive: bool
    inconclusive_reason: str = ""


def build_depth_result(
    *,
    depth: int,
    scenario_id: str,
    populated_graph: AuthorizationGraph,
    findings: Sequence[Finding],
) -> DepthResult:
    """Build one depth's :class:`DepthResult` from an already-populated graph
    (``analysis.authority.populate_observed_authority``'s output for one
    phase) and the findings already derived from it
    (``analysis.pipeline._authority_findings_for_phase``)."""
    hops = [
        node
        for node in populated_graph.nodes
        if not node.is_root and node.observed_authority is not None
    ]
    diverged_identity_ids = {
        finding.identity_id
        for finding in findings
        if finding.type in _DRIFT_FINDING_TYPES and finding.identity_id is not None
    }
    diverged_hops = sum((1 for node in hops if node.identity_id in diverged_identity_ids), 0)
    excluded_cells = 0
    total_cells = 0
    for node in hops:
        observed = node.observed_authority
        if observed is None:  # pragma: no cover -- `hops` is already filtered to exclude this
            raise AssertionError(f"{node.identity_id}: unmeasured node leaked into `hops`")
        excluded_cells += len(observed.excluded)
        total_cells += observed.attempted

    return DepthResult(
        depth=depth,
        scenario_id=scenario_id,
        total_hops=len(hops),
        diverged_hops=diverged_hops,
        excluded_cells=excluded_cells,
        total_cells=total_cells,
    )


def depth_result_from_bundle(
    run_dir: Path, *, phase: PlanPhase = PlanPhase.POST_DELEGATION
) -> DepthResult:
    """Convenience for the ``chainbreak analyze --aggregate`` CLI path:
    build one :class:`DepthResult` directly from a sealed bundle, without
    the caller needing to know about populated graphs or which phase to
    look at. ``depth`` comes from the graph itself
    (``AuthorizationGraph.depth``, the maximum ``hop_index``) rather than
    parsed from a scenario id string, so it is correct regardless of
    naming convention.
    """
    from chainbreak.analysis.authority import populate_observed_authority
    from chainbreak.analysis.pipeline import analyze_bundle
    from chainbreak.evidence.reader import read_graph, read_observations, read_scenario

    scenario = read_scenario(run_dir)
    graph = read_graph(run_dir)
    observations = list(read_observations(run_dir))
    result = analyze_bundle(run_dir)
    populated = populate_observed_authority(graph, observations, phase=phase)

    return build_depth_result(
        depth=populated.depth,
        scenario_id=scenario.scenario_id,
        populated_graph=populated,
        findings=result.findings,
    )


def summarize_depth_sweep(results: Sequence[DepthResult]) -> DepthSweepReport:
    """F6: if divergence rate per hop *and* exclusion rate both rise (never
    fall) across increasing depth, and the deepest depth's rate exceeds the
    shallowest's for both, the result is inconclusive -- a real depth effect
    cannot be distinguished from more probes simply having more opportunity
    to fail. Reported as fact, not smoothed into a single depth-trend claim.
    """
    ordered = tuple(sorted(results, key=lambda r: r.depth))
    if len(ordered) < 2:
        return DepthSweepReport(results=ordered, inconclusive=False)

    def _nondecreasing(values: Sequence[float]) -> bool:
        return all(later >= earlier for earlier, later in pairwise(values))

    divergence_rates = [r.divergence_rate_per_hop for r in ordered]
    exclusion_rates = [r.exclusion_rate for r in ordered]

    divergence_rose = (
        _nondecreasing(divergence_rates) and divergence_rates[-1] > divergence_rates[0]
    )
    exclusions_rose = _nondecreasing(exclusion_rates) and exclusion_rates[-1] > exclusion_rates[0]

    if divergence_rose and exclusions_rose:
        first, last = ordered[0], ordered[-1]
        return DepthSweepReport(
            results=ordered,
            inconclusive=True,
            inconclusive_reason=(
                "divergence rate per hop and exclusion rate both increase with depth "
                f"(depth {first.depth}: {divergence_rates[0]:.3f}/{exclusion_rates[0]:.3f} -> "
                f"depth {last.depth}: {divergence_rates[-1]:.3f}/{exclusion_rates[-1]:.3f}); "
                "the apparent depth effect is confounded with exclusions and cannot be reported "
                "as a real finding (F6)"
            ),
        )
    return DepthSweepReport(results=ordered, inconclusive=False)
