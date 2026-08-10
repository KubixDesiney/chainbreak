"""``analysis/drift.py`` (M11 F6): divergence reported as a rate per hop,
never a raw per-chain count, with the exclusion rate alongside it, and an
explicit ``INCONCLUSIVE`` verdict when both rise together across depth.
"""

from __future__ import annotations

import pytest

from chainbreak.analysis.drift import DepthResult, build_depth_result, summarize_depth_sweep
from chainbreak.core.enums import DelegationMechanism, ExclusionReason, FindingType, PlanPhase
from chainbreak.core.models import (
    AuthoritySet,
    AuthorizationGraph,
    DelegationEdge,
    ExpectedAuthority,
    Finding,
    IdentityNode,
    ObservedAuthority,
)

pytestmark = pytest.mark.unit


def _finding(*, identity_id: str, finding_type: FindingType) -> Finding:
    from chainbreak.core.enums import Confidence, SeverityHint

    return Finding(
        finding_id=f"fnd_{identity_id}_{finding_type.value}",
        type=finding_type,
        severity_hint=SeverityHint.REVIEW,
        confidence=Confidence.HIGH,
        subject_kind="identity",
        observation="test fixture",
        identity_id=identity_id,
    )


def _observed(
    *, allowed: tuple[str, ...] = (), excluded: dict[str, ExclusionReason] | None = None
) -> ObservedAuthority:
    excluded = excluded or {}
    attempted = len(allowed) + len(excluded)
    return ObservedAuthority(
        capabilities=AuthoritySet.of(*allowed),
        excluded=excluded,
        phase=PlanPhase.POST_DELEGATION,
        probe_matrix_id="pm-1",
        attempted=attempted,
        classified=len(allowed),
    )


def _three_hop_graph(*, agent_b_diverged: bool) -> AuthorizationGraph:
    root = IdentityNode(
        identity_id="principal",
        is_root=True,
        hop_index=0,
        expected_authority=ExpectedAuthority(
            capabilities=AuthoritySet.of("objectstore.read"),
            phase=PlanPhase.BASELINE,
            derivation="DECLARED",
        ),
        observed_authority=_observed(allowed=("objectstore.read",)),
    )
    agent_a = IdentityNode(
        identity_id="agent-a",
        hop_index=1,
        parent_id="principal",
        expected_authority=ExpectedAuthority(
            capabilities=AuthoritySet.of("objectstore.read"),
            phase=PlanPhase.POST_DELEGATION,
            derivation="INHERITED_ATTENUATED",
        ),
        observed_authority=_observed(allowed=("objectstore.read",)),
    )
    agent_b = IdentityNode(
        identity_id="agent-b",
        hop_index=2,
        parent_id="agent-a",
        expected_authority=ExpectedAuthority(
            capabilities=AuthoritySet.of("objectstore.read"),
            phase=PlanPhase.POST_DELEGATION,
            derivation="INHERITED_ATTENUATED",
        ),
        observed_authority=_observed(
            allowed=("objectstore.read", "keyvalue.read")
            if agent_b_diverged
            else ("objectstore.read",),
            excluded={"function.invoke": ExclusionReason.TRIALS_DISAGREED}
            if agent_b_diverged
            else {},
        ),
    )
    edges = (
        DelegationEdge(
            edge_id="e1",
            source_id="principal",
            target_id="agent-a",
            mechanism=DelegationMechanism.ROLE_CHAIN,
            requested_capabilities=AuthoritySet.of("objectstore.read"),
            intended_capabilities=AuthoritySet.of("objectstore.read"),
            expected_effective=AuthoritySet.of("objectstore.read"),
            credential_lifetime_s=900,
        ),
        DelegationEdge(
            edge_id="e2",
            source_id="agent-a",
            target_id="agent-b",
            mechanism=DelegationMechanism.ROLE_CHAIN,
            requested_capabilities=AuthoritySet.of("objectstore.read"),
            intended_capabilities=AuthoritySet.of("objectstore.read"),
            expected_effective=AuthoritySet.of("objectstore.read"),
            credential_lifetime_s=900,
        ),
    )
    return AuthorizationGraph(nodes=(root, agent_a, agent_b), edges=edges)


class TestBuildDepthResult:
    def test_counts_hops_and_divergence_correctly(self) -> None:
        graph = _three_hop_graph(agent_b_diverged=True)
        findings = [_finding(identity_id="agent-b", finding_type=FindingType.AUTHORITY_EXPANSION)]

        result = build_depth_result(
            depth=2,
            scenario_id="delegation-drift-two-hop",
            populated_graph=graph,
            findings=findings,
        )

        assert result.total_hops == 2  # agent-a, agent-b -- root excluded
        assert result.diverged_hops == 1  # only agent-b has a drift-family finding
        assert result.excluded_cells == 1  # agent-b's one TRIALS_DISAGREED exclusion
        assert (
            result.total_cells == 4
        )  # agent-a: 1 attempted, agent-b: 3 attempted (2 allowed + 1 excluded)

    def test_clean_chain_has_zero_divergence_and_zero_exclusions(self) -> None:
        graph = _three_hop_graph(agent_b_diverged=False)
        result = build_depth_result(
            depth=2, scenario_id="delegation-drift-two-hop", populated_graph=graph, findings=()
        )
        assert result.diverged_hops == 0
        assert result.excluded_cells == 0
        assert result.divergence_rate_per_hop == 0.0
        assert result.exclusion_rate == 0.0

    def test_root_never_counted_as_a_hop(self) -> None:
        graph = _three_hop_graph(agent_b_diverged=False)
        findings = [_finding(identity_id="principal", finding_type=FindingType.AUTHORITY_EXPANSION)]
        result = build_depth_result(
            depth=2, scenario_id="x", populated_graph=graph, findings=findings
        )
        # A (hypothetical) root-attributed finding must not count as a diverged hop.
        assert result.diverged_hops == 0


class TestDepthResultRates:
    def test_rate_properties_guard_against_division_by_zero(self) -> None:
        result = DepthResult(
            depth=2, scenario_id="x", total_hops=0, diverged_hops=0, excluded_cells=0, total_cells=0
        )
        assert result.divergence_rate_per_hop == 0.0
        assert result.exclusion_rate == 0.0


class TestSummarizeDepthSweep:
    def test_fewer_than_two_results_is_never_inconclusive(self) -> None:
        report = summarize_depth_sweep(
            [
                DepthResult(
                    depth=2,
                    scenario_id="x",
                    total_hops=2,
                    diverged_hops=1,
                    excluded_cells=0,
                    total_cells=2,
                )
            ]
        )
        assert report.inconclusive is False

    def test_stable_divergence_rate_across_depth_is_not_inconclusive(self) -> None:
        results = [
            DepthResult(
                depth=d,
                scenario_id="x",
                total_hops=d,
                diverged_hops=1,
                excluded_cells=0,
                total_cells=d * 2,
            )
            for d in (2, 3, 4)
        ]
        report = summarize_depth_sweep(results)
        assert report.inconclusive is False

    def test_divergence_rising_without_exclusions_rising_is_not_inconclusive(self) -> None:
        results = [
            DepthResult(
                depth=2,
                scenario_id="x",
                total_hops=2,
                diverged_hops=0,
                excluded_cells=1,
                total_cells=10,
            ),
            DepthResult(
                depth=4,
                scenario_id="x",
                total_hops=4,
                diverged_hops=2,
                excluded_cells=1,
                total_cells=10,
            ),
        ]
        report = summarize_depth_sweep(results)
        assert report.inconclusive is False

    def test_both_rising_together_is_inconclusive_and_names_why(self) -> None:
        results = [
            DepthResult(
                depth=2,
                scenario_id="x",
                total_hops=2,
                diverged_hops=0,
                excluded_cells=0,
                total_cells=10,
            ),
            DepthResult(
                depth=4,
                scenario_id="x",
                total_hops=4,
                diverged_hops=1,
                excluded_cells=2,
                total_cells=10,
            ),
            DepthResult(
                depth=6,
                scenario_id="x",
                total_hops=6,
                diverged_hops=3,
                excluded_cells=5,
                total_cells=10,
            ),
        ]
        report = summarize_depth_sweep(results)
        assert report.inconclusive is True
        assert "confounded" in report.inconclusive_reason
        assert "F6" in report.inconclusive_reason

    def test_results_are_ordered_by_depth_regardless_of_input_order(self) -> None:
        results = [
            DepthResult(
                depth=6,
                scenario_id="x",
                total_hops=6,
                diverged_hops=0,
                excluded_cells=0,
                total_cells=6,
            ),
            DepthResult(
                depth=2,
                scenario_id="x",
                total_hops=2,
                diverged_hops=0,
                excluded_cells=0,
                total_cells=2,
            ),
        ]
        report = summarize_depth_sweep(results)
        assert [r.depth for r in report.results] == [2, 6]
