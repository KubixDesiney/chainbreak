"""Apply the M1 graph algorithms to an analysis-time (fully observed) graph.

``graph/divergence.py`` and ``graph/paths.py`` already implement per-edge
divergence, first-divergence-per-path and drift classification as pure
functions over :class:`AuthorizationGraph`; this module is the thin
orchestration layer M07-analysis-findings.md's F name describes -- it does
not re-derive any of those algorithms, only sequences them and pairs each
node with its parent for :func:`classify_drift`.
"""

from __future__ import annotations

from dataclasses import dataclass

from chainbreak.core.enums import DriftClass
from chainbreak.core.ids import IdentityId
from chainbreak.core.models import AuthorizationGraph, EdgeDivergence, PathAnalysis
from chainbreak.graph.divergence import classify_drift, edge_divergence
from chainbreak.graph.paths import analyze_all_paths


@dataclass(frozen=True, slots=True)
class GraphAnalysis:
    """Every M1 divergence algorithm applied to one graph, once."""

    edges: tuple[EdgeDivergence, ...]
    paths: tuple[PathAnalysis, ...]
    drift: dict[IdentityId, DriftClass | None]


def analyze_graph(graph: AuthorizationGraph) -> GraphAnalysis:
    """Both endpoints of an edge must be measured for
    :func:`~chainbreak.graph.divergence.edge_divergence` to apply (it raises
    otherwise); edges with an unmeasured endpoint are simply omitted rather
    than raising here, since "some nodes weren't probed" is itself a
    coverage fact, not an analysis failure.
    """
    edges = tuple(
        edge_divergence(graph, edge)
        for edge in graph.edges
        if graph.node(edge.source_id).observed_authority is not None
        and graph.node(edge.target_id).observed_authority is not None
    )
    paths = analyze_all_paths(graph)

    drift: dict[IdentityId, DriftClass | None] = {}
    for node in graph.nodes:
        if node.observed_authority is None:
            continue
        parent = graph.node(node.parent_id) if node.parent_id is not None else None
        drift[node.identity_id] = classify_drift(node, parent)

    return GraphAnalysis(edges=edges, paths=paths, drift=drift)
