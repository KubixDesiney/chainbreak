"""first_divergence() -- AUTHORIZATION_MODEL.md section 4.3.

Covers unmeasured nodes, branching graphs, single-node graphs, and the
negative controls named in the M1 milestone spec.
"""

from __future__ import annotations

import pytest

from chainbreak.core.enums import DelegationMechanism, DivergenceKind, DriftClass, PlanPhase
from chainbreak.core.models import (
    AuthoritySet,
    AuthorizationGraph,
    DelegationEdge,
    ExpectedAuthority,
    IdentityNode,
    ObservedAuthority,
)
from chainbreak.graph.divergence import classify_drift, first_divergence

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


class TestSingleNodeGraph:
    def test_no_divergence_returns_none(self):
        root = IdentityNode(
            identity_id="root",
            is_root=True,
            hop_index=0,
            expected_authority=_expected("test.a", declared=True),
            observed_authority=_observed("test.a"),
        )
        graph = AuthorizationGraph(nodes=(root,))
        assert first_divergence(graph, ("root",)) is None

    def test_divergence_at_root(self):
        root = IdentityNode(
            identity_id="root",
            is_root=True,
            hop_index=0,
            expected_authority=_expected("test.a", declared=True),
            observed_authority=_observed("test.a", "test.b"),
        )
        graph = AuthorizationGraph(nodes=(root,))
        point = first_divergence(graph, ("root",))
        assert point is not None
        assert point.hop_index == 0
        assert point.kind is DivergenceKind.EXPANSION
        assert point.gain.sorted == ("test.b",)

    def test_unmeasured_root(self):
        root = IdentityNode(
            identity_id="root",
            is_root=True,
            hop_index=0,
            expected_authority=_expected("test.a", declared=True),
        )
        graph = AuthorizationGraph(nodes=(root,))
        point = first_divergence(graph, ("root",))
        assert point is not None
        assert point.kind is DivergenceKind.UNMEASURED
        assert point.hop_index == 0


class TestUnmeasuredNodeMidPath:
    def test_unmeasured_node_is_reported_not_skipped(self):
        """An unmeasured gap must not be silently passed over in favour of a
        later, measured, agreeing node."""
        root = IdentityNode(
            identity_id="root",
            is_root=True,
            hop_index=0,
            expected_authority=_expected("test.a", declared=True),
            observed_authority=_observed("test.a"),
        )
        middle = IdentityNode(
            identity_id="middle",
            hop_index=1,
            parent_id="root",
            expected_authority=_expected("test.a"),
            # deliberately unmeasured
        )
        leaf = IdentityNode(
            identity_id="leaf",
            hop_index=2,
            parent_id="middle",
            expected_authority=_expected("test.a"),
            observed_authority=_observed("test.a"),
        )
        graph = AuthorizationGraph(
            nodes=(root, middle, leaf),
            edges=(
                _edge("e1", "root", "middle", "test.a"),
                _edge("e2", "middle", "leaf", "test.a"),
            ),
        )
        point = first_divergence(graph, ("root", "middle", "leaf"))
        assert point is not None
        assert point.identity_id == "middle"
        assert point.kind is DivergenceKind.UNMEASURED


class TestMixedDivergence:
    def test_gain_and_loss_together_is_mixed(self):
        root = IdentityNode(
            identity_id="root",
            is_root=True,
            hop_index=0,
            expected_authority=_expected("test.a", "test.b", declared=True),
            observed_authority=_observed("test.b", "test.c"),
        )
        graph = AuthorizationGraph(nodes=(root,))
        point = first_divergence(graph, ("root",))
        assert point is not None
        assert point.kind is DivergenceKind.MIXED
        assert point.gain.sorted == ("test.c",)
        assert point.loss.sorted == ("test.a",)


class TestBranchingGraph:
    """A principal delegating to two independent agents: each path analyzed independently."""

    def _branching_graph(self, *, branch_a_gain: bool, branch_b_gain: bool) -> AuthorizationGraph:
        root = IdentityNode(
            identity_id="root",
            is_root=True,
            hop_index=0,
            expected_authority=_expected("test.a", "test.b", declared=True),
            observed_authority=_observed("test.a", "test.b"),
        )
        branch_a = IdentityNode(
            identity_id="branch-a",
            hop_index=1,
            parent_id="root",
            expected_authority=_expected("test.a"),
            observed_authority=(
                _observed("test.a", "test.b") if branch_a_gain else _observed("test.a")
            ),
        )
        branch_b = IdentityNode(
            identity_id="branch-b",
            hop_index=1,
            parent_id="root",
            expected_authority=_expected("test.b"),
            observed_authority=(
                _observed("test.a", "test.b") if branch_b_gain else _observed("test.b")
            ),
        )
        return AuthorizationGraph(
            nodes=(root, branch_a, branch_b),
            edges=(
                _edge("e1", "root", "branch-a", "test.a"),
                _edge("e2", "root", "branch-b", "test.b"),
            ),
        )

    def test_paths_are_enumerated_independently(self):
        graph = self._branching_graph(branch_a_gain=True, branch_b_gain=False)
        paths = graph.paths()
        assert set(paths) == {("root", "branch-a"), ("root", "branch-b")}

    def test_one_branch_diverges_the_other_does_not(self):
        graph = self._branching_graph(branch_a_gain=True, branch_b_gain=False)

        point_a = first_divergence(graph, ("root", "branch-a"))
        assert point_a is not None
        assert point_a.identity_id == "branch-a"
        assert point_a.kind is DivergenceKind.EXPANSION

        point_b = first_divergence(graph, ("root", "branch-b"))
        assert point_b is None

    def test_both_branches_diverge_independently(self):
        graph = self._branching_graph(branch_a_gain=True, branch_b_gain=True)
        assert first_divergence(graph, ("root", "branch-a")) is not None
        assert first_divergence(graph, ("root", "branch-b")) is not None


# ---------------------------------------------------------------------------
# Negative controls named explicitly in the M1 milestone spec.
# ---------------------------------------------------------------------------


class TestNegativeControls:
    def _five_hop_chain(self, *, agent_d_drops_gain: bool) -> AuthorizationGraph:
        """principal -> a -> b -> c -> d, c gains keyvalue.read unexpectedly.

        When ``agent_d_drops_gain`` is True, d's observed authority excludes
        the gain: the hop corrected the upstream drift instead of inheriting it.
        """
        nodes = [
            IdentityNode(
                identity_id="principal",
                is_root=True,
                hop_index=0,
                expected_authority=_expected("os.read", "kv.read", declared=True),
                observed_authority=_observed("os.read", "kv.read"),
            ),
            IdentityNode(
                identity_id="agent-a",
                hop_index=1,
                parent_id="principal",
                expected_authority=_expected("os.read", "kv.read"),
                observed_authority=_observed("os.read", "kv.read"),
            ),
            IdentityNode(
                identity_id="agent-b",
                hop_index=2,
                parent_id="agent-a",
                expected_authority=_expected("os.read"),
                observed_authority=_observed("os.read"),
            ),
            IdentityNode(
                identity_id="agent-c",
                hop_index=3,
                parent_id="agent-b",
                expected_authority=_expected("os.read"),
                # Gains kv.read unexpectedly.
                observed_authority=_observed("os.read", "kv.read"),
            ),
            IdentityNode(
                identity_id="agent-d",
                hop_index=4,
                parent_id="agent-c",
                expected_authority=_expected("os.read"),
                observed_authority=(
                    _observed("os.read") if agent_d_drops_gain else _observed("os.read", "kv.read")
                ),
            ),
        ]
        edges = (
            _edge("e1", "principal", "agent-a", "os.read", "kv.read"),
            _edge("e2", "agent-a", "agent-b", "os.read"),
            _edge("e3", "agent-b", "agent-c", "os.read"),
            _edge("e4", "agent-c", "agent-d", "os.read"),
        )
        return AuthorizationGraph(nodes=tuple(nodes), edges=edges)

    def test_hop_3_gain_propagates_to_hop_4(self):
        """Feed a graph where hop 3 gains a capability: first_divergence.hop_index == 3
        and hop 4 classifies PROPAGATED, not ORIGINATED."""
        graph = self._five_hop_chain(agent_d_drops_gain=False)
        path = ("principal", "agent-a", "agent-b", "agent-c", "agent-d")

        point = first_divergence(graph, path)
        assert point is not None
        assert point.hop_index == 3
        assert point.identity_id == "agent-c"

        drift = classify_drift(graph.node("agent-d"), graph.node("agent-c"))
        assert drift is DriftClass.PROPAGATED

    def test_hop_4_corrects_hop_3s_gain(self):
        """Feed a graph where hop 3 gains and hop 4 drops it: hop 4 is CORRECTED."""
        graph = self._five_hop_chain(agent_d_drops_gain=True)

        drift = classify_drift(graph.node("agent-d"), graph.node("agent-c"))
        assert drift is DriftClass.CORRECTED
