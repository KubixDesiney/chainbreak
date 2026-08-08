"""``analysis/rules.py``: one rule per finding type (F4), acceptance
criterion 1 -- every finding type has a rule and a test here."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from chainbreak.analysis import rules
from chainbreak.core.enums import (
    Confidence,
    DelegationMechanism,
    DriftClass,
    FindingType,
    MutationKind,
    OutcomeClass,
    PlanPhase,
    StaleAuthorityClass,
    TaskStatus,
)
from chainbreak.core.models import (
    AuthoritySet,
    CredentialRecord,
    DelegationEdge,
    EdgeDivergence,
    ExpectedAuthority,
    IdentityNode,
    Interval,
    ObservedAuthority,
    ProbeCellResult,
    RevocationMeasurement,
    StaleAuthorityMeasurement,
    TaskOutcome,
)

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _cell(capability: str, *trials: OutcomeClass, identity: str = "agent-b") -> ProbeCellResult:
    return ProbeCellResult(
        identity_id=identity, capability_id=capability, phase=PlanPhase.BASELINE, trials=trials
    )


def _node(
    identity_id: str,
    expected: tuple[str, ...],
    observed: tuple[str, ...],
    *,
    hop_index: int = 1,
    parent_id: str | None = "principal",
) -> IdentityNode:
    return IdentityNode(
        identity_id=identity_id,
        hop_index=hop_index,
        parent_id=parent_id,
        is_root=(hop_index == 0),
        expected_authority=ExpectedAuthority(
            capabilities=AuthoritySet.of(*expected), phase=PlanPhase.BASELINE, derivation="DECLARED"
        ),
        observed_authority=ObservedAuthority(
            capabilities=AuthoritySet.of(*observed),
            phase=PlanPhase.BASELINE,
            probe_matrix_id="pm1",
            attempted=len(set(expected) | set(observed)) or 1,
            classified=len(set(expected) | set(observed)) or 1,
        ),
    )


def _cells_for(
    *capabilities: str, identity: str = "agent-b", unanimous: bool = True
) -> dict[str, ProbeCellResult]:
    trials = (
        (OutcomeClass.ALLOWED,) * 3
        if unanimous
        else (OutcomeClass.ALLOWED, OutcomeClass.DENIED_EXPLICIT, OutcomeClass.ALLOWED)
    )
    return {c: _cell(c, *trials, identity=identity) for c in capabilities}


class TestExpectedBehavior:
    def test_fires_when_no_divergence(self):
        node = _node("agent-b", ("objectstore.read",), ("objectstore.read",))
        cells = _cells_for("objectstore.read")
        finding = rules.rule_expected_behavior(node, cells)
        assert finding is not None
        assert finding.type is FindingType.EXPECTED_BEHAVIOR
        assert finding.severity_hint.value == "INFORMATIONAL"

    def test_none_when_diverged(self):
        node = _node("agent-b", ("objectstore.read",), ("objectstore.read", "keyvalue.read"))
        finding = rules.rule_expected_behavior(
            node, _cells_for("objectstore.read", "keyvalue.read")
        )
        assert finding is None


class TestAuthorityExpansion:
    def test_fires_on_unexpected_gain_origin(self):
        node = _node("agent-b", ("objectstore.read",), ("objectstore.read", "keyvalue.read"))
        cells = _cells_for("objectstore.read", "keyvalue.read")
        finding = rules.rule_authority_expansion(node, DriftClass.ORIGINATED, cells)
        assert finding is not None
        assert finding.type is FindingType.AUTHORITY_EXPANSION
        assert finding.delta == {"unexpected_gain": ["keyvalue.read"], "unexpected_loss": []}

    def test_fires_when_drift_class_none(self):
        node = _node("agent-b", ("objectstore.read",), ("objectstore.read", "keyvalue.read"))
        finding = rules.rule_authority_expansion(
            node, None, _cells_for("objectstore.read", "keyvalue.read")
        )
        assert finding is not None

    def test_none_when_no_gain(self):
        node = _node("agent-b", ("objectstore.read",), ("objectstore.read",))
        assert rules.rule_authority_expansion(node, None, _cells_for("objectstore.read")) is None

    def test_none_when_propagated_not_origin(self):
        node = _node("agent-c", ("objectstore.read",), ("objectstore.read", "keyvalue.read"))
        finding = rules.rule_authority_expansion(
            node,
            DriftClass.PROPAGATED,
            _cells_for("objectstore.read", "keyvalue.read", identity="agent-c"),
        )
        assert finding is None

    def test_low_coverage_downgrades_to_inconclusive(self):
        node = _node("agent-b", ("objectstore.read",), ("objectstore.read", "keyvalue.read"))
        finding = rules.rule_authority_expansion(node, DriftClass.ORIGINATED, {})
        assert finding is not None
        assert finding.type is FindingType.INCONCLUSIVE
        assert finding.confidence is Confidence.INSUFFICIENT


class TestAuthorityNarrowing:
    def test_fires_on_unexpected_loss(self):
        node = _node("agent-b", ("objectstore.read", "keyvalue.read"), ("objectstore.read",))
        finding = rules.rule_authority_narrowing(
            node, _cells_for("objectstore.read", "keyvalue.read")
        )
        assert finding is not None
        assert finding.type is FindingType.AUTHORITY_NARROWING
        assert finding.delta == {"unexpected_gain": [], "unexpected_loss": ["keyvalue.read"]}

    def test_none_when_no_loss(self):
        node = _node("agent-b", ("objectstore.read",), ("objectstore.read",))
        assert rules.rule_authority_narrowing(node, _cells_for("objectstore.read")) is None


class TestDelegationDrift:
    def test_fires_for_origin_alongside_expansion(self):
        node = _node(
            "agent-c", ("objectstore.read",), ("objectstore.read", "keyvalue.write"), hop_index=3
        )
        cells = _cells_for("objectstore.read", "keyvalue.write", identity="agent-c")
        finding = rules.rule_delegation_drift(node, DriftClass.ORIGINATED, None, cells)
        assert finding is not None
        assert finding.type is FindingType.DELEGATION_DRIFT
        assert finding.drift_class is DriftClass.ORIGINATED

    def test_fires_for_propagated_downstream(self):
        node = _node(
            "agent-d", ("objectstore.read",), ("objectstore.read", "keyvalue.write"), hop_index=4
        )
        cells = _cells_for("objectstore.read", "keyvalue.write", identity="agent-d")
        finding = rules.rule_delegation_drift(node, DriftClass.PROPAGATED, "fnd_origin123", cells)
        assert finding is not None
        assert "fnd_origin123" in finding.security_interpretation

    def test_none_for_root_hop(self):
        node = _node(
            "principal",
            ("objectstore.read",),
            ("objectstore.read", "keyvalue.write"),
            hop_index=0,
            parent_id=None,
        )
        finding = rules.rule_delegation_drift(
            node,
            DriftClass.ORIGINATED,
            None,
            _cells_for("objectstore.read", "keyvalue.write", identity="principal"),
        )
        assert finding is None

    def test_none_for_corrected(self):
        node = _node("agent-d", ("objectstore.read",), ("objectstore.read",), hop_index=4)
        finding = rules.rule_delegation_drift(
            node, DriftClass.CORRECTED, None, _cells_for("objectstore.read", identity="agent-d")
        )
        assert finding is None

    def test_none_when_drift_class_is_none(self):
        node = _node(
            "agent-c", ("objectstore.read",), ("objectstore.read", "keyvalue.write"), hop_index=3
        )
        finding = rules.rule_delegation_drift(
            node, None, None, _cells_for("objectstore.read", "keyvalue.write", identity="agent-c")
        )
        assert finding is None


class TestAuthoritySurvival:
    def _edge(self) -> DelegationEdge:
        return DelegationEdge(
            edge_id="hop-2",
            source_id="agent-a",
            target_id="agent-b",
            mechanism=DelegationMechanism.ROLE_CHAIN,
            requested_capabilities=AuthoritySet.of("objectstore.read"),
            intended_capabilities=AuthoritySet.of("objectstore.read"),
            expected_effective=AuthoritySet.of("objectstore.read"),
            credential_lifetime_s=3600,
        )

    def test_fires_when_capability_survives(self):
        edge = self._edge()
        div = EdgeDivergence(
            edge_id="hop-2",
            expected_at_target_observed=AuthoritySet.of("objectstore.read"),
            expected_at_target_intended=AuthoritySet.of("objectstore.read"),
            attenuation_correct=False,
            attenuation_correct_vs_intent=False,
            survived_incorrectly=AuthoritySet.of("function.invoke"),
        )
        finding = rules.rule_authority_survival(edge, div, _cells_for("function.invoke"))
        assert finding is not None
        assert finding.type is FindingType.AUTHORITY_SURVIVAL
        assert finding.edge_id == "hop-2"
        assert finding.identity_id == "agent-b"

    def test_none_when_nothing_survived(self):
        edge = self._edge()
        div = EdgeDivergence(
            edge_id="hop-2",
            expected_at_target_observed=AuthoritySet.of("objectstore.read"),
            expected_at_target_intended=AuthoritySet.of("objectstore.read"),
            attenuation_correct=True,
            attenuation_correct_vs_intent=True,
        )
        assert rules.rule_authority_survival(edge, div, {}) is None


class TestNoTransitionObserved:
    def test_fires_when_not_observed(self):
        measurement = RevocationMeasurement(
            identity_id="agent-b",
            capability_id="objectstore.read",
            mutation_kind=MutationKind.ATTACH_INLINE_DENY,
            transition_observed=False,
            poll_interval_ms=500,
            poll_count=5,
            window_length_s=2.5,
            mutation_receipt_confirmed=True,
        )
        finding = rules.rule_no_transition_observed(measurement)
        assert finding is not None
        assert finding.type is FindingType.NO_TRANSITION_OBSERVED
        assert finding.confidence is Confidence.HIGH  # poll_count=5

    def test_none_when_observed(self):
        measurement = RevocationMeasurement(
            identity_id="agent-b",
            capability_id="objectstore.read",
            mutation_kind=MutationKind.ATTACH_INLINE_DENY,
            transition_observed=True,
            transition_window=Interval(low=0.5, point=1.0, high=1.5),
            poll_interval_ms=500,
            poll_count=5,
            window_length_s=2.5,
            mutation_receipt_confirmed=True,
        )
        assert rules.rule_no_transition_observed(measurement) is None

    def test_low_poll_count_yields_inconclusive(self):
        measurement = RevocationMeasurement(
            identity_id="agent-b",
            capability_id="objectstore.read",
            mutation_kind=MutationKind.ATTACH_INLINE_DENY,
            transition_observed=False,
            poll_interval_ms=500,
            poll_count=0,
            window_length_s=0.0,
            mutation_receipt_confirmed=True,
        )
        finding = rules.rule_no_transition_observed(measurement)
        assert finding.type is FindingType.INCONCLUSIVE


class TestRevocationDelay:
    from chainbreak.core.models import CompiledExpectation

    def _measurement(self, low: float, high: float) -> RevocationMeasurement:
        return RevocationMeasurement(
            identity_id="agent-b",
            capability_id="objectstore.read",
            mutation_kind=MutationKind.ATTACH_INLINE_DENY,
            transition_observed=True,
            transition_window=Interval(low=low, point=(low + high) / 2, high=high),
            poll_interval_ms=500,
            poll_count=5,
            window_length_s=high,
            mutation_receipt_confirmed=True,
        )

    def test_fires_when_assertive_threshold_exceeded(self):
        expectation = self.CompiledExpectation(
            kind="revocation_within",
            identity_id="agent-b",
            capability_id="objectstore.read",
            max_seconds=60.0,
            severity="assertive",
            justification="a" * 25,
        )
        finding = rules.rule_revocation_delay(self._measurement(70.0, 75.0), expectation)
        assert finding is not None
        assert finding.type is FindingType.REVOCATION_DELAY

    def test_none_when_informational(self):
        expectation = self.CompiledExpectation(
            kind="revocation_within",
            identity_id="agent-b",
            capability_id="objectstore.read",
            max_seconds=60.0,
            severity="informational",
        )
        assert rules.rule_revocation_delay(self._measurement(70.0, 75.0), expectation) is None

    def test_none_when_no_expectation(self):
        assert rules.rule_revocation_delay(self._measurement(70.0, 75.0), None) is None

    def test_none_when_within_threshold(self):
        expectation = self.CompiledExpectation(
            kind="revocation_within",
            identity_id="agent-b",
            capability_id="objectstore.read",
            max_seconds=60.0,
            severity="assertive",
            justification="a" * 25,
        )
        assert rules.rule_revocation_delay(self._measurement(1.0, 2.0), expectation) is None


class TestStaleAuthority:
    def _measurement(self, classification: StaleAuthorityClass) -> StaleAuthorityMeasurement:
        return StaleAuthorityMeasurement(
            identity_id="agent-c",
            capability_id="objectstore.read",
            classification=classification,
            deferral_seconds=600.0,
            credential_expired_at_execution=False,
        )

    @pytest.mark.parametrize(
        "cls",
        [
            StaleAuthorityClass.STALE_AUTHORITY_LIVE_CREDENTIAL,
            StaleAuthorityClass.SESSION_SCOPE_CACHED,
        ],
    )
    def test_fires_for_stale_classes(self, cls):
        finding = rules.rule_stale_authority(self._measurement(cls))
        assert finding is not None
        assert finding.type is FindingType.STALE_AUTHORITY
        assert finding.confidence is Confidence.MEDIUM

    def test_none_for_current_authority(self):
        assert (
            rules.rule_stale_authority(self._measurement(StaleAuthorityClass.CURRENT_AUTHORITY))
            is None
        )


class TestExpiredCredentialAccepted:
    def test_fires(self):
        measurement = StaleAuthorityMeasurement(
            identity_id="agent-c",
            capability_id="objectstore.read",
            classification=StaleAuthorityClass.EXPIRED_CREDENTIAL_HONORED,
            deferral_seconds=3700.0,
            credential_expired_at_execution=True,
        )
        finding = rules.rule_expired_credential_accepted(measurement)
        assert finding is not None
        assert finding.type is FindingType.EXPIRED_CREDENTIAL_ACCEPTED
        assert finding.confidence is Confidence.HIGH

    def test_none_otherwise(self):
        measurement = StaleAuthorityMeasurement(
            identity_id="agent-c",
            capability_id="objectstore.read",
            classification=StaleAuthorityClass.CURRENT_AUTHORITY,
            deferral_seconds=1.0,
            credential_expired_at_execution=False,
        )
        assert rules.rule_expired_credential_accepted(measurement) is None


class TestSilentNarrowing:
    def test_fires_when_claims_complete_but_is_not(self):
        task = TaskOutcome(
            task_id="task_01",
            identity_id="agent-b",
            worker="always-complete",
            status=TaskStatus.COMPLETE,
            steps_total=3,
            steps_attempted=3,
            steps_succeeded=1,
            reported_insufficient_authority=False,
            output_marker_written=True,
            output_marker_verified_independently=True,
        )
        finding = rules.rule_silent_narrowing(task)
        assert finding is not None
        assert finding.type is FindingType.SILENT_NARROWING
        assert finding.confidence is Confidence.HIGH

    def test_fires_when_output_marker_missing(self):
        task = TaskOutcome(
            task_id="task_01",
            identity_id="agent-b",
            worker="always-complete",
            status=TaskStatus.COMPLETE,
            steps_total=1,
            steps_attempted=1,
            steps_succeeded=1,
            reported_insufficient_authority=False,
            output_marker_written=True,
            output_marker_verified_independently=False,
        )
        assert rules.rule_silent_narrowing(task) is not None

    def test_none_for_honest_worker(self):
        task = TaskOutcome(
            task_id="task_01",
            identity_id="agent-b",
            worker="sequential",
            status=TaskStatus.COMPLETE,
            steps_total=3,
            steps_attempted=3,
            steps_succeeded=3,
            reported_insufficient_authority=False,
            output_marker_written=True,
            output_marker_verified_independently=True,
        )
        assert rules.rule_silent_narrowing(task) is None


class TestLifetimeCapped:
    def _credential(self, requested: int, granted: int) -> CredentialRecord:
        return CredentialRecord(
            credential_id="cred_01",
            identity_id="agent-b",
            mechanism=DelegationMechanism.ROLE_CHAIN,
            issued_at=_NOW,
            expires_at=_NOW.replace(hour=1),
            requested_duration_s=requested,
            granted_duration_s=granted,
            session_name_hash="sha256:" + "a" * 64,
            access_key_id_hash="sha256:" + "b" * 64,
        )

    def test_fires_when_capped(self):
        finding = rules.rule_lifetime_capped(self._credential(3600, 900))
        assert finding is not None
        assert finding.type is FindingType.LIFETIME_CAPPED
        assert finding.confidence is Confidence.HIGH

    def test_none_when_not_capped(self):
        assert rules.rule_lifetime_capped(self._credential(900, 900)) is None


class TestExecutionError:
    def test_fires_on_aborted_error(self):
        finding = rules.rule_execution_error("ABORTED_ERROR")
        assert finding is not None
        assert finding.type is FindingType.EXECUTION_ERROR
        assert finding.subject_kind == "run"
        assert finding.confidence is Confidence.HIGH

    def test_none_when_completed(self):
        assert rules.rule_execution_error("COMPLETED") is None


class TestConfigurationError:
    def test_always_returns_a_finding(self):
        finding = rules.rule_configuration_error("agent-b", "identity.whoami", "no response")
        assert finding.type is FindingType.CONFIGURATION_ERROR
        assert finding.confidence is Confidence.HIGH
        assert finding.identity_id == "agent-b"


def test_finding_id_is_deterministic_across_repeated_calls():
    node = _node("agent-b", ("objectstore.read",), ("objectstore.read", "keyvalue.read"))
    cells = _cells_for("objectstore.read", "keyvalue.read")
    first = rules.rule_authority_expansion(node, DriftClass.ORIGINATED, cells)
    second = rules.rule_authority_expansion(node, DriftClass.ORIGINATED, cells)
    assert first.finding_id == second.finding_id


def test_security_interpretation_and_observation_are_separate_fields():
    """ADR-006: never merged into prose."""
    node = _node("agent-b", ("objectstore.read",), ("objectstore.read", "keyvalue.read"))
    finding = rules.rule_authority_expansion(
        node, DriftClass.ORIGINATED, _cells_for("objectstore.read", "keyvalue.read")
    )
    assert finding.observation != finding.security_interpretation
    assert finding.observation
    assert finding.security_interpretation
