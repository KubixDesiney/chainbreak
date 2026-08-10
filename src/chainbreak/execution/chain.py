"""Family B's own entry point over multi-hop delegation (delegation drift).

``execution/delegation.py``'s ``materialize_graph`` already walks a compiled
graph's edges in hop order and issues one delegation per edge -- a bounded
loop over ``graph.edges`` with no hardcoded hop count, so a depth-6 chain is
exercised through the exact same code path M10 already built and tested for
two hops (F1). S2's credential scrubbing lives there too (every delegation
scrubs its raw secret immediately after extracting the safe
``CredentialRecord``, not only chain ones -- see ``materialize_graph``'s own
docstring). This module adds nothing that duplicates that walk; it is the
delegation-drift family's named entry point plus one thing genuinely
specific to depth as an experimental variable (S1): a redundant,
execution-layer depth check.
"""

from __future__ import annotations

from chainbreak.core.errors import ExecutionError
from chainbreak.core.models import AuthorizationGraph
from chainbreak.execution.delegation import MaterializedGraph, materialize_graph
from chainbreak.providers.base.protocol import ProviderAdapter

__all__ = ["materialize_chain"]


def materialize_chain(
    adapter: ProviderAdapter, graph: AuthorizationGraph, *, max_delegation_depth: int
) -> MaterializedGraph:
    """S1: depth bounded by ``SafetyEnvelope.max_delegation_depth``.

    The graph builder (``graph/builder.py``, G-5) already refuses to
    *compile* a chain deeper than ``max_delegation_depth`` -- exceeding it is
    a compile-time error, per M11's own security requirement. The check here
    is deliberately redundant: belt-and-suspenders at the point execution
    actually begins, so a graph that reached this function by some path other
    than the normal compiler (a hand-built test fixture, a future caller)
    still cannot be executed past the bound, rather than trusting that
    whoever constructed it already enforced G-5.
    """
    if graph.depth > max_delegation_depth:
        raise ExecutionError(
            f"chain depth {graph.depth} exceeds max_delegation_depth "
            f"{max_delegation_depth} -- this should already have been refused at compile "
            "time (G-5); refusing to execute",
            depth=graph.depth,
            max_delegation_depth=max_delegation_depth,
        )
    return materialize_graph(adapter, graph)
