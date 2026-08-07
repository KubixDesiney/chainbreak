"""Graph invariants G-1..G-5 (ARCHITECTURE.md section 2, AUTHORIZATION_MODEL.md 2).

G-1 and G-2 are enforced by ``AuthorizationGraph`` itself and already covered
by ``tests/unit/test_domain_contract.py``; this file adds the violating
fixtures for completeness alongside G-3..G-5, which ``graph/builder.py``
enforces. Each invariant has a fixture that raises with a message naming it
(acceptance criterion 3).
"""

from __future__ import annotations

import pytest

from chainbreak.core.enums import DelegationMechanism, PlanPhase, ProbeKind, Sensitivity
from chainbreak.core.errors import ScenarioSemanticError
from chainbreak.core.models import (
    AuthoritySet,
    Capability,
    CapabilityCatalog,
    DelegationEdge,
    ExpectedAuthority,
    IdentityNode,
)
from chainbreak.graph.builder import build_graph

pytestmark = pytest.mark.unit


def _expected(*capabilities: str, declared: bool = False) -> ExpectedAuthority:
    return ExpectedAuthority(
        capabilities=AuthoritySet.of(*capabilities),
        phase=PlanPhase.POST_DELEGATION,
        derivation="DECLARED" if declared else "INHERITED_ATTENUATED",
    )


def _edge(edge_id: str, source: str, target: str, *intended: str) -> DelegationEdge:
    caps = AuthoritySet.of(*intended)
    return DelegationEdge(
        edge_id=edge_id,
        source_id=source,
        target_id=target,
        mechanism=DelegationMechanism.SESSION_POLICY_SCOPED,
        requested_capabilities=caps,
        intended_capabilities=caps,
        expected_effective=caps,
        credential_lifetime_s=900,
    )


def _capability(capability_id: str) -> Capability:
    return Capability(
        id=capability_id,
        title=capability_id,
        description="test fixture capability",
        probe_kind=ProbeKind.READ_MARKER,
        sensitivity=Sensitivity.BENIGN_READ,
    )


def _catalog(*capability_ids: str) -> CapabilityCatalog:
    return CapabilityCatalog(
        version="1.0.0", capabilities=tuple(_capability(c) for c in capability_ids)
    )


_CATALOG = _catalog("test.a", "test.b", "test.c")


def _root(capabilities: tuple[str, ...] = ("test.a",)) -> IdentityNode:
    return IdentityNode(
        identity_id="root",
        is_root=True,
        hop_index=0,
        expected_authority=_expected(*capabilities, declared=True),
    )


def _agent(identity_id: str, hop: int, parent: str, capabilities: tuple[str, ...]) -> IdentityNode:
    return IdentityNode(
        identity_id=identity_id,
        hop_index=hop,
        parent_id=parent,
        expected_authority=_expected(*capabilities),
    )


class TestG1Acyclic:
    def test_cycle_is_rejected(self):
        # A cycle between two non-root nodes, so G-1 (acyclic) is what fires
        # rather than G-2 (root must have no inbound edge).
        nodes = (
            _root(),
            _agent("a", 1, "root", ("test.a",)),
            _agent("b", 2, "a", ("test.a",)),
        )
        edges = (
            _edge("e1", "root", "a", "test.a"),
            _edge("e2", "a", "b", "test.a"),
            _edge("e3", "b", "a", "test.a"),
        )
        with pytest.raises(ScenarioSemanticError, match="G-1"):
            build_graph(nodes, edges, catalog=_CATALOG)


class TestG2SingleRoot:
    def test_two_roots_is_rejected(self):
        nodes = (
            IdentityNode(
                identity_id="root-1",
                is_root=True,
                hop_index=0,
                expected_authority=_expected("test.a", declared=True),
            ),
            IdentityNode(
                identity_id="root-2",
                is_root=True,
                hop_index=0,
                expected_authority=_expected("test.a", declared=True),
            ),
        )
        with pytest.raises(ScenarioSemanticError, match="G-2"):
            build_graph(nodes, (), catalog=_CATALOG)


class TestG3MonotoneIntent:
    def test_intent_exceeding_parent_is_rejected(self):
        nodes = (_root(("test.a",)), _agent("a", 1, "root", ("test.a", "test.b")))
        edges = (_edge("e1", "root", "a", "test.a", "test.b"),)  # test.b not in root's expected
        with pytest.raises(ScenarioSemanticError, match="G-3"):
            build_graph(nodes, edges, catalog=_CATALOG)

    def test_negative_control_downgrades_to_warning(self):
        """A declared INTENT_EXCEEDS_PARENT negative control opts out of the
        guardrail for this scenario without disabling it globally."""
        nodes = (_root(("test.a",)), _agent("a", 1, "root", ("test.a", "test.b")))
        edges = (_edge("e1", "root", "a", "test.a", "test.b"),)
        graph, warnings = build_graph(
            nodes, edges, catalog=_CATALOG, downgrade_intent_exceeds_parent=True
        )
        assert graph.node("a") is not None
        assert len(warnings) == 1
        assert "G-3" in warnings[0]

    def test_compliant_intent_produces_no_warning(self):
        nodes = (_root(("test.a", "test.b")), _agent("a", 1, "root", ("test.a",)))
        edges = (_edge("e1", "root", "a", "test.a"),)
        _graph, warnings = build_graph(nodes, edges, catalog=_CATALOG)
        assert warnings == ()


class TestG4CapabilityClosure:
    def test_unresolvable_capability_is_rejected(self):
        catalog = _catalog("test.a")  # test.z is not in this catalog
        bad_root = IdentityNode(
            identity_id="root",
            is_root=True,
            hop_index=0,
            expected_authority=_expected("test.a", "test.z", declared=True),
        )
        with pytest.raises(ScenarioSemanticError, match="G-4"):
            build_graph((bad_root,), (), catalog=catalog)

    def test_all_capabilities_resolving_passes(self):
        nodes = (_root(("test.a",)),)
        graph, warnings = build_graph(nodes, (), catalog=_CATALOG)
        assert graph is not None
        assert warnings == ()


class TestG5BoundedDepth:
    def _chain(self, depth: int) -> tuple[tuple[IdentityNode, ...], tuple[DelegationEdge, ...]]:
        nodes = [_root(("test.a",))]
        edges = []
        parent = "root"
        for hop in range(1, depth + 1):
            identity_id = f"agent-{hop}"
            nodes.append(_agent(identity_id, hop, parent, ("test.a",)))
            edges.append(_edge(f"e{hop}", parent, identity_id, "test.a"))
            parent = identity_id
        return tuple(nodes), tuple(edges)

    def test_depth_within_bound_passes(self):
        nodes, edges = self._chain(6)
        graph, _warnings = build_graph(nodes, edges, catalog=_CATALOG, max_delegation_depth=6)
        assert graph.depth == 6

    def test_depth_exceeding_bound_is_rejected(self):
        nodes, edges = self._chain(7)
        with pytest.raises(ScenarioSemanticError, match="G-5"):
            build_graph(nodes, edges, catalog=_CATALOG, max_delegation_depth=6)
