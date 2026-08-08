"""``analysis/authority.py``: observations -> ``ProbeCellResult`` -> ``ObservedAuthority``
(F1, F2, AUTH-1, ADR-012)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from chainbreak.analysis.authority import (
    aggregate_observations,
    build_observed_authority,
    populate_observed_authority,
    resolve_cell,
)
from chainbreak.core.enums import ExclusionReason, OutcomeClass, PlanPhase, ProbeKind
from chainbreak.core.models import (
    AuthoritySet,
    AuthorizationGraph,
    ExpectedAuthority,
    IdentityNode,
    Observation,
    ProbeCellResult,
    ProbeOutcome,
    ProbeRequestRecord,
    ProbeTiming,
)

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _observation(
    identity: str, capability: str, trial: int, outcome: OutcomeClass, *, obs_id: str | None = None
) -> Observation:
    return Observation(
        observation_id=obs_id or f"obs_{identity}_{capability}_{trial}",
        run_id="run1",
        sequence=trial,
        phase=PlanPhase.BASELINE,
        probe_matrix_id="pm1",
        identity_id=identity,
        identity_ref_hash="sha256:" + "a" * 64,
        capability_id=capability,
        trial=trial,
        trial_count=3,
        request=ProbeRequestRecord(
            probe_kind=ProbeKind.READ_MARKER,
            binding_actions=("fake:read",),
            target_ref_hash="sha256:" + "b" * 64,
            target_namespace="cb-01234567",
            parameters_fingerprint="sha256:" + "c" * 64,
        ),
        timing=ProbeTiming(monotonic_start_ns=0, monotonic_end_ns=1, wall_start=_NOW),
        outcome=ProbeOutcome(outcome_class=outcome),
        preconditions_verified=True,
    )


class TestResolveCell:
    def test_unanimous_allowed(self):
        cell = ProbeCellResult(
            identity_id="a",
            capability_id="objectstore.read",
            phase=PlanPhase.BASELINE,
            trials=(OutcomeClass.ALLOWED, OutcomeClass.ALLOWED, OutcomeClass.ALLOWED),
        )
        assert resolve_cell(cell) == (OutcomeClass.ALLOWED, None)

    def test_unanimous_denial_no_exclusion(self):
        cell = ProbeCellResult(
            identity_id="a",
            capability_id="objectstore.read",
            phase=PlanPhase.BASELINE,
            trials=(OutcomeClass.DENIED_EXPLICIT,) * 3,
        )
        assert resolve_cell(cell) == (OutcomeClass.DENIED_EXPLICIT, None)

    def test_mixed_denials_become_unattributed_no_exclusion(self):
        cell = ProbeCellResult(
            identity_id="a",
            capability_id="objectstore.read",
            phase=PlanPhase.BASELINE,
            trials=(
                OutcomeClass.DENIED_EXPLICIT,
                OutcomeClass.DENIED_IMPLICIT,
                OutcomeClass.DENIED_EXPLICIT,
            ),
        )
        resolved, reason = resolve_cell(cell)
        assert resolved is OutcomeClass.DENIED_UNATTRIBUTED
        assert reason is None

    @pytest.mark.parametrize(
        "trials,expected_reason",
        [
            (
                (OutcomeClass.ALLOWED, OutcomeClass.DENIED_EXPLICIT, OutcomeClass.ALLOWED),
                ExclusionReason.TRIALS_DISAGREED,
            ),
            ((OutcomeClass.ERROR_TRANSIENT,) * 3, ExclusionReason.TRANSIENT_ERRORS_EXHAUSTED),
            ((OutcomeClass.ERROR_INFRASTRUCTURE,) * 3, ExclusionReason.INFRASTRUCTURE_ERROR),
            ((OutcomeClass.ERROR_RESOURCE_MISSING,) * 3, ExclusionReason.INFRASTRUCTURE_ERROR),
        ],
    )
    def test_excluded_outcomes(self, trials, expected_reason):
        cell = ProbeCellResult(
            identity_id="a",
            capability_id="objectstore.read",
            phase=PlanPhase.BASELINE,
            trials=trials,
        )
        _resolved, reason = resolve_cell(cell)
        assert reason is expected_reason


class TestAggregateObservations:
    def test_groups_by_identity_capability_phase(self):
        observations = [
            _observation("agent-a", "objectstore.read", 1, OutcomeClass.ALLOWED),
            _observation("agent-a", "objectstore.read", 2, OutcomeClass.ALLOWED),
            _observation("agent-a", "keyvalue.read", 1, OutcomeClass.DENIED_EXPLICIT),
        ]
        cells = aggregate_observations(observations)
        assert len(cells) == 2
        key = ("agent-a", "objectstore.read", PlanPhase.BASELINE)
        assert cells[key].trials == (OutcomeClass.ALLOWED, OutcomeClass.ALLOWED)

    def test_trials_ordered_by_trial_number_not_insertion(self):
        observations = [
            _observation("agent-a", "objectstore.read", 3, OutcomeClass.DENIED_EXPLICIT),
            _observation("agent-a", "objectstore.read", 1, OutcomeClass.ALLOWED),
            _observation("agent-a", "objectstore.read", 2, OutcomeClass.ALLOWED),
        ]
        cells = aggregate_observations(observations)
        cell = cells[("agent-a", "objectstore.read", PlanPhase.BASELINE)]
        assert cell.trials == (
            OutcomeClass.ALLOWED,
            OutcomeClass.ALLOWED,
            OutcomeClass.DENIED_EXPLICIT,
        )


class TestBuildObservedAuthority:
    def test_allowed_capability_included(self):
        cells = {
            "objectstore.read": ProbeCellResult(
                identity_id="a",
                capability_id="objectstore.read",
                phase=PlanPhase.BASELINE,
                trials=(OutcomeClass.ALLOWED,) * 3,
            )
        }
        observed = build_observed_authority(
            "a", PlanPhase.BASELINE, "pm1", AuthoritySet.of("objectstore.read"), cells
        )
        assert observed.capabilities == AuthoritySet.of("objectstore.read")
        assert observed.coverage == 1.0
        assert observed.excluded == {}

    def test_denial_excluded_from_capabilities_but_classified(self):
        cells = {
            "objectstore.read": ProbeCellResult(
                identity_id="a",
                capability_id="objectstore.read",
                phase=PlanPhase.BASELINE,
                trials=(OutcomeClass.DENIED_EXPLICIT,) * 3,
            )
        }
        observed = build_observed_authority(
            "a", PlanPhase.BASELINE, "pm1", AuthoritySet.of("objectstore.read"), cells
        )
        assert observed.capabilities.is_empty()
        assert observed.excluded == {}
        assert observed.coverage == 1.0

    def test_never_probed_capability_is_not_probed_exclusion(self):
        observed = build_observed_authority(
            "a", PlanPhase.BASELINE, "pm1", AuthoritySet.of("objectstore.read"), {}
        )
        assert observed.excluded == {"objectstore.read": ExclusionReason.NOT_PROBED}
        assert observed.coverage == 0.0

    def test_error_outcome_excluded(self):
        cells = {
            "objectstore.read": ProbeCellResult(
                identity_id="a",
                capability_id="objectstore.read",
                phase=PlanPhase.BASELINE,
                trials=(OutcomeClass.ERROR_INFRASTRUCTURE,) * 3,
            )
        }
        observed = build_observed_authority(
            "a", PlanPhase.BASELINE, "pm1", AuthoritySet.of("objectstore.read"), cells
        )
        assert observed.excluded == {"objectstore.read": ExclusionReason.INFRASTRUCTURE_ERROR}
        assert observed.coverage == 0.0


class TestPopulateObservedAuthority:
    def _graph(self) -> AuthorizationGraph:
        return AuthorizationGraph(
            nodes=(
                IdentityNode(
                    identity_id="agent-a",
                    is_root=True,
                    expected_authority=ExpectedAuthority(
                        capabilities=AuthoritySet.of("objectstore.read"),
                        phase=PlanPhase.BASELINE,
                        derivation="DECLARED",
                    ),
                ),
            )
        )

    def test_populates_observed_authority_from_observations(self):
        graph = self._graph()
        observations = [
            _observation("agent-a", "objectstore.read", 1, OutcomeClass.ALLOWED),
            _observation("agent-a", "objectstore.read", 2, OutcomeClass.ALLOWED),
            _observation("agent-a", "objectstore.read", 3, OutcomeClass.ALLOWED),
        ]
        populated = populate_observed_authority(graph, observations, phase=PlanPhase.BASELINE)
        node = populated.node("agent-a")
        assert node.observed_authority is not None
        assert node.observed_authority.capabilities == AuthoritySet.of("objectstore.read")
        assert node.unexpected_gain.is_empty()

    def test_node_with_no_observations_at_phase_is_unchanged(self):
        graph = self._graph()
        populated = populate_observed_authority(graph, [], phase=PlanPhase.BASELINE)
        assert populated.node("agent-a").observed_authority is None
        # Frozen graph: nothing was mutated in place.
        assert populated.node("agent-a") is graph.node("agent-a")

    def test_wrong_phase_observations_are_ignored(self):
        graph = self._graph()
        observations = [
            Observation(
                **{
                    **_observation(
                        "agent-a", "objectstore.read", 1, OutcomeClass.ALLOWED
                    ).model_dump(),
                    "phase": PlanPhase.POST_MUTATION,
                }
            )
        ]
        populated = populate_observed_authority(graph, observations, phase=PlanPhase.BASELINE)
        assert populated.node("agent-a").observed_authority is None

    def test_expansion_detected(self):
        graph = self._graph()
        observations = [
            _observation("agent-a", "objectstore.read", t, OutcomeClass.ALLOWED) for t in (1, 2, 3)
        ] + [_observation("agent-a", "keyvalue.read", t, OutcomeClass.ALLOWED) for t in (1, 2, 3)]
        populated = populate_observed_authority(graph, observations, phase=PlanPhase.BASELINE)
        node = populated.node("agent-a")
        assert node.unexpected_gain == AuthoritySet.of("keyvalue.read")
