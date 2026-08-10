"""``reporting/figures.py``: each figure builder's not-applicable and
applicable branches, driven directly against hand-built evidence objects
rather than a full orchestrated run (``test_report_generation.py`` already
covers the end-to-end path for the two families a delegation-drift bundle
naturally exercises -- authorization graph and per-hop authority -- this
file's job is the remaining five, plus the not-applicable path for all
seven).
"""

from __future__ import annotations

import pytest

from chainbreak.analysis.divergence import analyze_graph
from chainbreak.core.enums import MutationKind, OutcomeClass, Provider, StaleAuthorityClass
from chainbreak.core.ids import CapabilityId, IdentityId
from chainbreak.core.models import (
    AuthorizationGraph,
    Interval,
    RevocationMeasurement,
    StaleAuthorityMeasurement,
)
from chainbreak.reporting.figures import (
    authorization_graph_figure,
    gain_loss_per_hop_figure,
    per_hop_authority_figure,
    repeatability_figure,
    revocation_timeline_figure,
    scenario_comparison_figure,
    stale_authority_window_figure,
)

pytestmark = pytest.mark.unit


class TestAuthorizationGraphFigure:
    def test_none_graph_is_not_applicable(self) -> None:
        figure = authorization_graph_figure(None, provider=Provider.FAKE)
        assert not figure.applicable
        assert "FAKE-PROVIDER" in figure.caption

    def test_real_graph_is_applicable_and_stamps_fake_provider(
        self, worked_example_graph: AuthorizationGraph
    ) -> None:
        figure = authorization_graph_figure(worked_example_graph, provider=Provider.FAKE)
        assert figure.applicable
        assert "<svg" in figure.svg
        assert "FAKE-PROVIDER" in figure.caption

    def test_aws_provider_is_not_stamped(self, worked_example_graph: AuthorizationGraph) -> None:
        figure = authorization_graph_figure(worked_example_graph, provider=Provider.AWS)
        assert "FAKE-PROVIDER" not in figure.caption


class TestPerHopAuthorityFigure:
    def test_none_graph_is_not_applicable(self) -> None:
        assert not per_hop_authority_figure(None, provider=Provider.FAKE).applicable

    def test_a_graph_with_no_observed_authority_is_not_applicable(self) -> None:
        from chainbreak.core.enums import PlanPhase
        from chainbreak.core.models import AuthoritySet, ExpectedAuthority, IdentityNode

        node = IdentityNode(
            identity_id=IdentityId("principal"),
            is_root=True,
            hop_index=0,
            expected_authority=ExpectedAuthority(
                capabilities=AuthoritySet.of("objectstore.read"),
                phase=PlanPhase.POST_DELEGATION,
                derivation="DECLARED",
            ),
        )
        graph = AuthorizationGraph(nodes=(node,))
        figure = per_hop_authority_figure(graph, provider=Provider.FAKE)
        assert not figure.applicable
        assert "no node" in figure.caption.lower()

    def test_real_graph_is_applicable(self, worked_example_graph: AuthorizationGraph) -> None:
        figure = per_hop_authority_figure(worked_example_graph, provider=Provider.FAKE)
        assert figure.applicable
        assert "principal" in figure.svg


class TestGainLossPerHopFigure:
    def test_no_edges_is_not_applicable(self) -> None:
        assert gain_loss_per_hop_figure((), provider=Provider.FAKE).applicable is False

    def test_a_real_survival_defect_appears_as_excess(
        self, worked_example_graph: AuthorizationGraph
    ) -> None:
        # agent-c is observed to hold keyvalue.read despite hop-3 never
        # intending it -- exactly the injected divergence the fixture's own
        # docstring names.
        edge_divergences = analyze_graph(worked_example_graph).edges
        figure = gain_loss_per_hop_figure(edge_divergences, provider=Provider.FAKE)
        assert figure.applicable
        assert "hop-3" in figure.svg


class TestRevocationTimelineFigure:
    def test_no_measurements_is_not_applicable(self) -> None:
        figure = revocation_timeline_figure((), provider=Provider.FAKE)
        assert not figure.applicable

    def test_a_transition_window_renders_as_shaded_range(self) -> None:
        measurement = RevocationMeasurement(
            identity_id=IdentityId("agent-b"),
            capability_id=CapabilityId("objectstore.read"),
            mutation_kind=MutationKind.ATTACH_INLINE_DENY,
            transition_window=Interval(low=2.0, point=2.25, high=2.5),
            transition_observed=True,
            non_monotonic=False,
            poll_interval_ms=100,
            poll_count=10,
            window_length_s=5.0,
            mutation_receipt_confirmed=True,
        )
        figure = revocation_timeline_figure((measurement,), provider=Provider.FAKE)
        assert figure.applicable
        assert "agent-b" in figure.svg
        assert "monotonic" in figure.svg

    def test_a_non_monotonic_transition_is_labeled(self) -> None:
        measurement = RevocationMeasurement(
            identity_id=IdentityId("agent-b"),
            capability_id=CapabilityId("objectstore.read"),
            mutation_kind=MutationKind.UPDATE_TRUST_POLICY,
            transition_window=Interval(low=1.0, point=1.5, high=2.0),
            transition_observed=True,
            non_monotonic=True,
            poll_interval_ms=100,
            poll_count=8,
            window_length_s=5.0,
            mutation_receipt_confirmed=True,
        )
        figure = revocation_timeline_figure((measurement,), provider=Provider.FAKE)
        assert "non-monotonic" in figure.svg


class TestStaleAuthorityWindowFigure:
    def test_no_populated_window_is_not_applicable(self) -> None:
        measurement = StaleAuthorityMeasurement(
            identity_id=IdentityId("agent-a"),
            capability_id=CapabilityId("objectstore.read"),
            classification=StaleAuthorityClass.CURRENT_AUTHORITY,
            deferral_seconds=5.0,
            stale_window_seconds=None,
            credential_expired_at_execution=False,
        )
        figure = stale_authority_window_figure((measurement,), provider=Provider.FAKE)
        assert not figure.applicable
        assert "not populated" in figure.caption

    def test_a_populated_window_is_applicable(self) -> None:
        measurement = StaleAuthorityMeasurement(
            identity_id=IdentityId("agent-a"),
            capability_id=CapabilityId("objectstore.read"),
            classification=StaleAuthorityClass.STALE_AUTHORITY_LIVE_CREDENTIAL,
            deferral_seconds=5.0,
            stale_window_seconds=3.2,
            credential_expired_at_execution=False,
        )
        figure = stale_authority_window_figure((measurement,), provider=Provider.FAKE)
        assert figure.applicable
        assert "agent-a" in figure.svg


class TestRepeatabilityFigure:
    def test_no_multi_trial_cells_is_not_applicable(self) -> None:
        cells = {("principal", "objectstore.read"): (OutcomeClass.ALLOWED,)}
        assert not repeatability_figure(cells, provider=Provider.FAKE).applicable

    def test_unanimous_trials_show_full_agreement(self) -> None:
        cells = {
            ("principal", "objectstore.read"): (
                OutcomeClass.ALLOWED,
                OutcomeClass.ALLOWED,
                OutcomeClass.ALLOWED,
            )
        }
        figure = repeatability_figure(cells, provider=Provider.FAKE)
        assert figure.applicable
        assert "3/3" in figure.caption

    def test_disagreement_shows_partial_agreement(self) -> None:
        cells = {
            ("principal", "objectstore.read"): (
                OutcomeClass.ALLOWED,
                OutcomeClass.ALLOWED,
                OutcomeClass.DENIED_EXPLICIT,
            )
        }
        figure = repeatability_figure(cells, provider=Provider.FAKE)
        assert "2/3" in figure.caption


class TestScenarioComparisonFigure:
    def test_no_comparison_is_not_applicable(self) -> None:
        assert not scenario_comparison_figure(None, provider=Provider.FAKE).applicable

    def test_a_comparison_mapping_is_applicable(self) -> None:
        figure = scenario_comparison_figure(
            {"DELEGATION_INTEGRITY": 1.0, "SCOPE_ATTENUATION": 0.5},
            provider=Provider.FAKE,
            denominator=5,
        )
        assert figure.applicable
        assert "of 5 run(s)" in figure.caption
        assert "DELEGATION_INTEGRITY" in figure.svg
