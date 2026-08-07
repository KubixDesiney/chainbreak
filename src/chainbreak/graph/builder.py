"""Graph construction, enforcing G-1..G-5 (ARCHITECTURE.md, AUTHORIZATION_MODEL.md 2).

G-1 (acyclic) and G-2 (single root) are enforced by ``AuthorizationGraph``'s
own validator in ``core/models.py`` -- they need no context beyond the nodes
and edges themselves. The remaining three need context that must not leak
into ``core/`` (ARCH-1: core imports nothing from chainbreak), so they are
dependency-injected here rather than looked up:

- **G-3** (monotone intent) needs to know whether this is a declared
  negative control, which only the scenario compiler (M3) knows.
- **G-4** (capability closure) needs the capability catalog. Only the
  catalog half -- "every capability resolves in the loaded catalog" -- is
  checked here. The other half, "has a binding in the active provider",
  needs ``capabilities.loader.resolve_bindings``, which lives outside
  ``graph/`` and is out of scope for this module; PROJECT_STATUS.md tracks
  full G-4 enforcement moving to the scenario compiler at M3.
- **G-5** (bounded depth) needs the configured ceiling.
"""

from __future__ import annotations

from chainbreak.core.errors import ScenarioSemanticError
from chainbreak.core.models import (
    AuthorizationGraph,
    CapabilityCatalog,
    DelegationEdge,
    IdentityNode,
)


def build_graph(
    nodes: tuple[IdentityNode, ...],
    edges: tuple[DelegationEdge, ...] = (),
    *,
    catalog: CapabilityCatalog,
    max_delegation_depth: int = 6,
    downgrade_intent_exceeds_parent: bool = False,
) -> tuple[AuthorizationGraph, tuple[str, ...]]:
    """Construct an ``AuthorizationGraph`` and enforce G-1..G-5.

    Returns the graph plus any warnings recorded by a downgraded invariant
    (currently only G-3's negative-control opt-out). An empty tuple means no
    invariant was downgraded during construction.
    """
    graph = AuthorizationGraph(nodes=nodes, edges=edges)  # G-1, G-2

    warnings = _check_g3_monotone_intent(graph, downgrade=downgrade_intent_exceeds_parent)
    _check_g4_capability_closure(graph, catalog)
    _check_g5_bounded_depth(graph, max_delegation_depth)

    return graph, tuple(warnings)


def _check_g3_monotone_intent(graph: AuthorizationGraph, *, downgrade: bool) -> list[str]:
    """G-3: every edge's intended_capabilities must be a subset of the source's expected.

    A negative control declaring ``INTENT_EXCEEDS_PARENT`` downgrades a
    violation to a recorded warning instead of a compile error -- this is how
    that specific defect gets injected on purpose without disabling the
    guardrail for every other scenario.
    """
    warnings: list[str] = []
    for edge in graph.edges:
        source = graph.node(edge.source_id)
        excess = edge.intended_capabilities - source.expected_authority.capabilities
        if not excess:
            continue
        message = (
            f"G-3: edge {edge.edge_id} intends {sorted(excess)} beyond "
            f"{source.identity_id}'s expected authority"
        )
        if downgrade:
            warnings.append(message)
        else:
            raise ScenarioSemanticError(message, edge_id=edge.edge_id, excess=sorted(excess))
    return warnings


def _check_g4_capability_closure(graph: AuthorizationGraph, catalog: CapabilityCatalog) -> None:
    """G-4 (catalog half only): every capability named anywhere resolves in the catalog."""
    known = set(catalog.ids())
    referenced: set[str] = set()

    for node in graph.nodes:
        referenced |= set(node.expected_authority.capabilities)
        if node.observed_authority is not None:
            referenced |= set(node.observed_authority.capabilities)

    for edge in graph.edges:
        referenced |= set(edge.requested_capabilities)
        referenced |= set(edge.intended_capabilities)
        referenced |= set(edge.expected_effective)

    unresolved = referenced - known
    if unresolved:
        raise ScenarioSemanticError(
            f"G-4: capabilities not in catalog {catalog.version}: {sorted(unresolved)}",
            unresolved=sorted(unresolved),
        )


def _check_g5_bounded_depth(graph: AuthorizationGraph, max_delegation_depth: int) -> None:
    """G-5: depth <= the configured ceiling. Long chains are a variable, not an accident."""
    if graph.depth > max_delegation_depth:
        raise ScenarioSemanticError(
            f"G-5: depth {graph.depth} exceeds max_delegation_depth {max_delegation_depth}",
            depth=graph.depth,
            max_delegation_depth=max_delegation_depth,
        )
