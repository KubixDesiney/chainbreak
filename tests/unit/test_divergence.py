"""Divergence algorithm tests (AUTHORIZATION_MODEL.md section 4).

Table-driven over hand-computed cases, plus the section 7 worked example
reproduced exactly (acceptance criteria 1 and 2).
"""

from __future__ import annotations

import pytest

from chainbreak.core.enums import DelegationMechanism, DivergenceKind, DriftClass, PlanPhase
from chainbreak.core.models import (
    AuthoritySet,
    AuthorizationGraph,
    DelegationEdge,
    EdgeDivergence,
    ExpectedAuthority,
    IdentityNode,
    ObservedAuthority,
)
from chainbreak.graph.divergence import classify_drift, edge_divergence, first_divergence

pytestmark = pytest.mark.unit


def _expected(*capabilities: str, declared: bool = False) -> ExpectedAuthority:
    return ExpectedAuthority(
        capabilities=AuthoritySet.of(*capabilities),
        phase=PlanPhase.POST_DELEGATION,
        derivation="DECLARED" if declared else "INHERITED_ATTENUATED",
    )


def _observed(*capabilities: str) -> ObservedAuthority:
    return ObservedAuthority(
        capabilities=AuthoritySet.of(*capabilities),
        phase=PlanPhase.POST_DELEGATION,
        probe_matrix_id="pm-test",
        attempted=len(capabilities),
        classified=len(capabilities),
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


# ---------------------------------------------------------------------------
# Worked example (AUTHORIZATION_MODEL section 7) -- reproduced exactly.
# ---------------------------------------------------------------------------


class TestWorkedExample:
    def test_expected_and_observed_cardinalities(self, worked_example_graph: AuthorizationGraph):
        expected_counts = {
            "principal": 6,
            "agent-a": 5,
            "agent-b": 2,
            "agent-c": 1,
            "agent-d": 1,
        }
        observed_counts = {
            "principal": 6,
            "agent-a": 5,
            "agent-b": 2,
            "agent-c": 2,
            "agent-d": 2,
        }
        for identity_id, expected_count in expected_counts.items():
            node = worked_example_graph.node(identity_id)
            assert len(node.expected_authority.capabilities) == expected_count
            assert node.observed_authority is not None
            assert len(node.observed_authority.capabilities) == observed_counts[identity_id]

    def test_gain_and_loss_per_node(self, worked_example_graph: AuthorizationGraph):
        for identity_id in ("principal", "agent-a", "agent-b"):
            node = worked_example_graph.node(identity_id)
            assert node.unexpected_gain.is_empty()
            assert node.unexpected_loss.is_empty()

        agent_c = worked_example_graph.node("agent-c")
        assert agent_c.unexpected_gain.sorted == ("keyvalue.read",)
        assert agent_c.unexpected_loss.is_empty()

        agent_d = worked_example_graph.node("agent-d")
        assert agent_d.unexpected_gain.sorted == ("keyvalue.read",)
        assert agent_d.unexpected_loss.is_empty()

    def test_first_divergence_is_hop_3_expansion(self, worked_example_graph: AuthorizationGraph):
        path = ("principal", "agent-a", "agent-b", "agent-c", "agent-d")
        point = first_divergence(worked_example_graph, path)
        assert point is not None
        assert point.hop_index == 3
        assert point.identity_id == "agent-c"
        assert point.kind is DivergenceKind.EXPANSION
        assert point.gain.sorted == ("keyvalue.read",)
        assert point.loss.is_empty()

    def test_drift_classification(self, worked_example_graph: AuthorizationGraph):
        node = lambda i: worked_example_graph.node(i)  # noqa: E731
        assert classify_drift(node("principal"), None) is None
        assert classify_drift(node("agent-a"), node("principal")) is None
        assert classify_drift(node("agent-b"), node("agent-a")) is None
        assert classify_drift(node("agent-c"), node("agent-b")) is DriftClass.ORIGINATED
        assert classify_drift(node("agent-d"), node("agent-c")) is DriftClass.PROPAGATED

    def test_edge_divergence_hop_3_and_hop_4(self, worked_example_graph: AuthorizationGraph):
        hop3 = next(e for e in worked_example_graph.edges if e.edge_id == "hop-3")
        div3 = edge_divergence(worked_example_graph, hop3)
        assert div3.expected_at_target_observed.sorted == ("objectstore.read",)
        assert div3.attenuation_correct is False
        assert div3.survived_incorrectly.sorted == ("keyvalue.read",)
        assert div3.dropped_incorrectly.is_empty()

        hop4 = next(e for e in worked_example_graph.edges if e.edge_id == "hop-4")
        div4 = edge_divergence(worked_example_graph, hop4)
        assert div4.expected_at_target_observed.sorted == ("objectstore.read",)
        assert div4.attenuation_correct is False
        assert div4.survived_incorrectly.sorted == ("keyvalue.read",)
        assert div4.dropped_incorrectly.is_empty()

    def test_edges_before_divergence_are_correct(self, worked_example_graph: AuthorizationGraph):
        for edge_id in ("hop-1", "hop-2"):
            edge = next(e for e in worked_example_graph.edges if e.edge_id == edge_id)
            divergence = edge_divergence(worked_example_graph, edge)
            assert divergence.attenuation_correct is True
            assert divergence.survived_incorrectly.is_empty()
            assert divergence.dropped_incorrectly.is_empty()


# ---------------------------------------------------------------------------
# classify_drift -- table-driven, including CORRECTED (the case a naive
# implementation misclassifies as PROPAGATED).
# ---------------------------------------------------------------------------


def _node_with_gain(identity_id: str, *, hop: int, parent: str | None, gain: tuple[str, ...]):
    base = ("objectstore.read",)
    expected = _expected(*base)
    observed = _observed(*base, *gain)
    return IdentityNode(
        identity_id=identity_id,
        is_root=(parent is None),
        hop_index=hop,
        parent_id=parent,
        expected_authority=expected,
        observed_authority=observed,
    )


class TestClassifyDriftTable:
    def test_no_divergence_anywhere_is_none(self):
        parent = _node_with_gain("p", hop=0, parent=None, gain=())
        child = _node_with_gain("c", hop=1, parent="p", gain=())
        assert classify_drift(child, parent) is None

    def test_root_with_no_parent_and_no_gain_is_none(self):
        root = _node_with_gain("root", hop=0, parent=None, gain=())
        assert classify_drift(root, None) is None

    def test_originated_when_parent_clean(self):
        parent = _node_with_gain("p", hop=0, parent=None, gain=())
        child = _node_with_gain("c", hop=1, parent="p", gain=("keyvalue.read",))
        assert classify_drift(child, parent) is DriftClass.ORIGINATED

    def test_propagated_when_gain_equals_parent_gain(self):
        parent = _node_with_gain("p", hop=0, parent=None, gain=("keyvalue.read",))
        child = _node_with_gain("c", hop=1, parent="p", gain=("keyvalue.read",))
        assert classify_drift(child, parent) is DriftClass.PROPAGATED

    def test_propagated_when_gain_is_proper_subset_of_parent_gain(self):
        parent = _node_with_gain("p", hop=0, parent=None, gain=("keyvalue.read", "queue.send"))
        child = _node_with_gain("c", hop=1, parent="p", gain=("keyvalue.read",))
        assert classify_drift(child, parent) is DriftClass.PROPAGATED

    def test_amplified_when_gain_is_proper_superset_of_parent_gain(self):
        parent = _node_with_gain("p", hop=0, parent=None, gain=("keyvalue.read",))
        child = _node_with_gain("c", hop=1, parent="p", gain=("keyvalue.read", "queue.send"))
        assert classify_drift(child, parent) is DriftClass.AMPLIFIED

    def test_corrected_when_node_clean_but_parent_diverged(self):
        """The case a naive implementation misclassifies as PROPAGATED.

        This is the difference between reporting a working defense-in-depth
        control as a failure and reporting it correctly.
        """
        parent = _node_with_gain("p", hop=0, parent=None, gain=("keyvalue.read",))
        child = _node_with_gain("c", hop=1, parent="p", gain=())
        assert classify_drift(child, parent) is DriftClass.CORRECTED

    def test_originated_when_gains_are_incomparable(self):
        parent = _node_with_gain("p", hop=0, parent=None, gain=("keyvalue.read",))
        child = _node_with_gain("c", hop=1, parent="p", gain=("queue.send",))
        assert classify_drift(child, parent) is DriftClass.ORIGINATED


# ---------------------------------------------------------------------------
# edge_divergence -- requires both endpoints measured.
# ---------------------------------------------------------------------------


class TestEdgeDivergenceGuards:
    def test_raises_when_source_unmeasured(self):
        source = IdentityNode(
            identity_id="s", is_root=True, hop_index=0, expected_authority=_expected("test.a")
        )
        target = IdentityNode(
            identity_id="t",
            hop_index=1,
            parent_id="s",
            expected_authority=_expected("test.a"),
            observed_authority=_observed("test.a"),
        )
        graph = AuthorizationGraph(nodes=(source, target), edges=(_edge("e1", "s", "t", "test.a"),))
        with pytest.raises(ValueError, match="unmeasured"):
            edge_divergence(graph, graph.edges[0])

    def test_raises_when_target_unmeasured(self):
        source = IdentityNode(
            identity_id="s",
            is_root=True,
            hop_index=0,
            expected_authority=_expected("test.a"),
            observed_authority=_observed("test.a"),
        )
        target = IdentityNode(
            identity_id="t", hop_index=1, parent_id="s", expected_authority=_expected("test.a")
        )
        graph = AuthorizationGraph(nodes=(source, target), edges=(_edge("e1", "s", "t", "test.a"),))
        with pytest.raises(ValueError, match="unmeasured"):
            edge_divergence(graph, graph.edges[0])

    def test_expected_based_variant_differs_from_observed_based(self):
        """dropped_incorrectly has two baselines; they can legitimately differ."""
        source = IdentityNode(
            identity_id="s",
            is_root=True,
            hop_index=0,
            expected_authority=_expected("test.a", "test.b"),
            # Source under-observed relative to its own expectation.
            observed_authority=_observed("test.a"),
        )
        target = IdentityNode(
            identity_id="t",
            hop_index=1,
            parent_id="s",
            expected_authority=_expected("test.a", "test.b"),
            observed_authority=_observed("test.a", "test.b"),
        )
        edge = _edge("e1", "s", "t", "test.a", "test.b")
        graph = AuthorizationGraph(nodes=(source, target), edges=(edge,))
        divergence = edge_divergence(graph, edge)

        assert isinstance(divergence, EdgeDivergence)
        # Observed baseline: src_obs={a} & intended={a,b} = {a}; dst_obs={a,b} != {a}.
        assert divergence.expected_at_target_observed.sorted == ("test.a",)
        assert divergence.attenuation_correct is False
        # Expected baseline: src_expected={a,b} & intended={a,b} = {a,b}; dst_obs={a,b} == {a,b}.
        assert divergence.expected_at_target_intended.sorted == ("test.a", "test.b")
        assert divergence.attenuation_correct_vs_intent is True
