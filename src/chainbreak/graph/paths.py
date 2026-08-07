"""Root-to-leaf path enumeration and per-path analysis (AUTHORIZATION_MODEL.md 4.5).

``AuthorizationGraph.paths()`` (core/models.py) already enumerates every
root-to-leaf path; this module turns one path into a :class:`PathAnalysis`.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise

from chainbreak.core.models import AuthorizationGraph, PathAnalysis
from chainbreak.graph.divergence import first_divergence


def analyze_path(graph: AuthorizationGraph, path: Sequence[str]) -> PathAnalysis:
    """Analyze one root-to-leaf path.

    Cardinality- and set-monotonicity are computed only over consecutive
    *measured* pairs: an unmeasured node in the middle of an otherwise fully
    measured path should not silently fail monotonicity just because there is
    nothing to compare it against.
    """
    nodes = [graph.node(identity_id) for identity_id in path]
    measured = [n for n in nodes if n.observed_authority is not None]

    monotone_set = True
    monotone_cardinality = True
    for earlier, later in pairwise(measured):
        later_caps = later.observed_authority.capabilities  # type: ignore[union-attr]
        earlier_caps = earlier.observed_authority.capabilities  # type: ignore[union-attr]
        if not later_caps.is_subset_of(earlier_caps):
            monotone_set = False
        if len(later_caps) > len(earlier_caps):
            monotone_cardinality = False

    return PathAnalysis(
        path=tuple(path),
        first_divergence=first_divergence(graph, path),
        attenuation_monotone_set=monotone_set,
        attenuation_monotone_cardinality=monotone_cardinality,
        terminal_gain=nodes[-1].unexpected_gain,
    )


def analyze_all_paths(graph: AuthorizationGraph) -> tuple[PathAnalysis, ...]:
    """Every root-to-leaf path, analyzed independently (branching graphs)."""
    return tuple(analyze_path(graph, path) for path in graph.paths())
