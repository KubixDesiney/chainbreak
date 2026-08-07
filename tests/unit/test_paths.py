"""graph/paths.py -- PathAnalysis (AUTHORIZATION_MODEL.md section 4.5)."""

from __future__ import annotations

import pytest

from chainbreak.core.enums import DelegationMechanism, PlanPhase
from chainbreak.core.models import (
    AuthoritySet,
    AuthorizationGraph,
    DelegationEdge,
    ExpectedAuthority,
    IdentityNode,
    ObservedAuthority,
)
from chainbreak.graph.paths import analyze_all_paths, analyze_path

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


class TestWorkedExamplePathAnalysis:
    """AUTHORIZATION_MODEL section 7: observed sets shrink monotonically down
    the chain even though hop 3 diverges from what was *expected* -- these are
    different axes and the analysis must not conflate them."""

    def test_full_path_analysis(self, worked_example_graph: AuthorizationGraph):
        path = ("principal", "agent-a", "agent-b", "agent-c", "agent-d")
        analysis = analyze_path(worked_example_graph, path)

        assert analysis.path == path
        assert analysis.first_divergence is not None
        assert analysis.first_divergence.hop_index == 3
        assert analysis.terminal_gain.sorted == ("keyvalue.read",)
        # Despite the divergence at hop 3, observed authority still shrinks
        # (or holds) monotonically all the way down the chain.
        assert analysis.attenuation_monotone_set is True
        assert analysis.attenuation_monotone_cardinality is True

    def test_analyze_all_paths_covers_the_single_path(
        self, worked_example_graph: AuthorizationGraph
    ):
        analyses = analyze_all_paths(worked_example_graph)
        assert len(analyses) == 1
        assert analyses[0].path == (
            "principal",
            "agent-a",
            "agent-b",
            "agent-c",
            "agent-d",
        )


class TestSingleNodeGraph:
    def test_trivially_monotone(self):
        root = IdentityNode(
            identity_id="root",
            is_root=True,
            hop_index=0,
            expected_authority=_expected("test.a", declared=True),
            observed_authority=_observed("test.a"),
        )
        graph = AuthorizationGraph(nodes=(root,))
        analysis = analyze_path(graph, ("root",))
        assert analysis.attenuation_monotone_set is True
        assert analysis.attenuation_monotone_cardinality is True
        assert analysis.first_divergence is None
        assert analysis.terminal_gain.is_empty()


class TestNonMonotoneChain:
    def test_cardinality_increase_breaks_cardinality_monotonicity(self):
        root = IdentityNode(
            identity_id="root",
            is_root=True,
            hop_index=0,
            expected_authority=_expected("test.a", declared=True),
            observed_authority=_observed("test.a"),
        )
        child = IdentityNode(
            identity_id="child",
            hop_index=1,
            parent_id="root",
            expected_authority=_expected("test.a"),
            # Observed MORE than the parent -- an impossible-looking but
            # detectable-in-principle non-monotone chain (SCENARIO_SPECIFICATION
            # negative control nc-non-monotone-chain).
            observed_authority=_observed("test.a", "test.b"),
        )
        graph = AuthorizationGraph(
            nodes=(root, child), edges=(_edge("e1", "root", "child", "test.a"),)
        )
        analysis = analyze_path(graph, ("root", "child"))
        assert analysis.attenuation_monotone_set is False
        assert analysis.attenuation_monotone_cardinality is False


class TestUnmeasuredNodeExcludedFromMonotonicity:
    def test_unmeasured_middle_node_does_not_break_monotonicity_check(self):
        root = IdentityNode(
            identity_id="root",
            is_root=True,
            hop_index=0,
            expected_authority=_expected("test.a", "test.b", declared=True),
            observed_authority=_observed("test.a", "test.b"),
        )
        middle = IdentityNode(
            identity_id="middle",
            hop_index=1,
            parent_id="root",
            expected_authority=_expected("test.a"),
            # unmeasured
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
        analysis = analyze_path(graph, ("root", "middle", "leaf"))
        # root(2) -> leaf(1): still monotone across the one measured pair.
        assert analysis.attenuation_monotone_set is True
        assert analysis.attenuation_monotone_cardinality is True
        assert analysis.first_divergence is not None
        assert analysis.first_divergence.identity_id == "middle"


class TestBranchingGraphAllPaths:
    def test_each_branch_analyzed_independently(self):
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
            observed_authority=_observed("test.a", "test.b"),
        )
        branch_b = IdentityNode(
            identity_id="branch-b",
            hop_index=1,
            parent_id="root",
            expected_authority=_expected("test.b"),
            observed_authority=_observed("test.b"),
        )
        graph = AuthorizationGraph(
            nodes=(root, branch_a, branch_b),
            edges=(
                _edge("e1", "root", "branch-a", "test.a"),
                _edge("e2", "root", "branch-b", "test.b"),
            ),
        )
        analyses = {a.path[-1]: a for a in analyze_all_paths(graph)}
        assert analyses["branch-a"].first_divergence is not None
        assert analyses["branch-b"].first_divergence is None
