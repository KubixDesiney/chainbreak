"""core/models.py -- coverage for validators and properties not exercised by
tests/unit/test_domain_contract.py.

Not part of M1's own scope (these models mostly belong to M6/M7/M14/M15),
but they were built ahead of schedule during pre-M0 design verification and
M1's coverage acceptance criterion (``core/`` >= 95%, TESTING.md) is a hard
bar on the whole package. Each of these is a small, pure Pydantic validator
or property -- exactly what TESTING.md calls "cheap to test".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from chainbreak.core.enums import (
    Confidence,
    DelegationMechanism,
    DenialAttribution,
    OutcomeClass,
    PlanPhase,
    PolicyKind,
    ProbeKind,
    Provider,
    ScoringCategory,
    Sensitivity,
    TaskStatus,
)
from chainbreak.core.errors import ScenarioSemanticError
from chainbreak.core.models import (
    AuthoritySet,
    Capability,
    CapabilityCatalog,
    CategoryResult,
    CategoryStatus,
    CredentialRecord,
    DelegationEdge,
    ExpectedAuthority,
    IdentityNode,
    Interval,
    Observation,
    ObservedAuthority,
    PolicyFingerprint,
    PolicyStateSnapshot,
    ProbeCellResult,
    ProbeOutcome,
    ProbeRequestRecord,
    ProbeTiming,
    ProviderCapabilityBinding,
    RevocationMeasurement,
    TaskOutcome,
)
from chainbreak.core.models import AuthorizationGraph as Graph

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# AuthoritySet
# ---------------------------------------------------------------------------


def test_authority_set_contains():
    authority = AuthoritySet.of("a.read", "a.write")
    assert "a.read" in authority
    assert "b.read" not in authority


def test_authority_set_union():
    a = AuthoritySet.of("a.read")
    b = AuthoritySet.of("b.read")
    assert (a | b).sorted == ("a.read", "b.read")


# ---------------------------------------------------------------------------
# Capability
# ---------------------------------------------------------------------------


def test_capability_benign_write_must_mutate():
    with pytest.raises(ValidationError, match="BENIGN_WRITE"):
        Capability(
            id="test.write",
            title="t",
            description="d",
            probe_kind=ProbeKind.WRITE_SCRATCH,
            sensitivity=Sensitivity.BENIGN_WRITE,
            mutates_state=False,
        )


def test_capability_benign_read_must_not_mutate():
    with pytest.raises(ValidationError, match="BENIGN_READ"):
        Capability(
            id="test.read",
            title="t",
            description="d",
            probe_kind=ProbeKind.READ_MARKER,
            sensitivity=Sensitivity.BENIGN_READ,
            mutates_state=True,
        )


def _capability(capability_id: str) -> Capability:
    return Capability(
        id=capability_id,
        title=capability_id,
        description="test fixture",
        probe_kind=ProbeKind.READ_MARKER,
        sensitivity=Sensitivity.BENIGN_READ,
    )


def test_catalog_rejects_duplicate_ids():
    with pytest.raises(ValidationError, match="duplicate"):
        CapabilityCatalog(
            version="1.0.0", capabilities=(_capability("test.a"), _capability("test.a"))
        )


def test_catalog_get_missing_raises_keyerror():
    catalog = CapabilityCatalog(version="1.0.0", capabilities=(_capability("test.a"),))
    with pytest.raises(KeyError):
        catalog.get("test.missing")


def test_provider_capability_binding_rejects_duplicate_actions():
    with pytest.raises(ValidationError, match="unique"):
        ProviderCapabilityBinding(
            capability_id="test.a",
            provider=Provider.FAKE,
            actions=("fake:Get", "fake:Get"),
            resource_template="fake://{namespace}",
            probe_kind=ProbeKind.READ_MARKER,
        )


# ---------------------------------------------------------------------------
# CredentialRecord
# ---------------------------------------------------------------------------


def _credential_kwargs(**overrides: object) -> dict[str, object]:
    now = datetime.now(UTC)
    base = {
        "credential_id": "cred_test",
        "identity_id": "agent-a",
        "mechanism": DelegationMechanism.ROLE_CHAIN,
        "issued_at": now,
        "expires_at": now + timedelta(hours=1),
        "requested_duration_s": 3600,
        "granted_duration_s": 3600,
        "session_name_hash": "sha256:" + "0" * 64,
        "access_key_id_hash": "sha256:" + "0" * 64,
    }
    base.update(overrides)
    return base


def test_credential_record_rejects_naive_issued_at():
    with pytest.raises(ValidationError, match="timezone-aware"):
        CredentialRecord(
            **_credential_kwargs(issued_at=datetime(2026, 1, 1))  # noqa: DTZ001
        )


def test_credential_record_rejects_naive_expires_at():
    with pytest.raises(ValidationError, match="timezone-aware"):
        CredentialRecord(
            **_credential_kwargs(expires_at=datetime(2026, 1, 1))  # noqa: DTZ001
        )


def test_credential_record_rejects_expiry_before_issuance():
    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="expires_at must be after issued_at"):
        CredentialRecord(**_credential_kwargs(issued_at=now, expires_at=now - timedelta(seconds=1)))


def test_credential_record_lifetime_capped():
    credential = CredentialRecord(
        **_credential_kwargs(requested_duration_s=3600, granted_duration_s=3599)
    )
    assert credential.lifetime_capped is True


# ---------------------------------------------------------------------------
# PolicyStateSnapshot
# ---------------------------------------------------------------------------


def _fingerprint(digest_suffix: str) -> PolicyFingerprint:
    return PolicyFingerprint(
        policy_kind=PolicyKind.IDENTITY_INLINE,
        name_hash="sha256:" + "0" * 64,
        document_sha256="sha256:" + digest_suffix.rjust(64, "0"),
        statement_count=1,
        has_explicit_deny=False,
    )


def test_policy_snapshot_differs_from():
    a = PolicyStateSnapshot(
        snapshot_id="s1",
        identity_id="agent-a",
        taken_at=datetime.now(UTC),
        monotonic_ns=1,
        policies=(_fingerprint("1"),),
    )
    b = PolicyStateSnapshot(
        snapshot_id="s2",
        identity_id="agent-a",
        taken_at=datetime.now(UTC),
        monotonic_ns=2,
        policies=(_fingerprint("2"),),
    )
    assert a.differs_from(b) is True
    assert a.differs_from(a) is False


# ---------------------------------------------------------------------------
# ObservedAuthority
# ---------------------------------------------------------------------------


def test_observed_authority_coverage_zero_attempted():
    observed = ObservedAuthority(
        capabilities=AuthoritySet.of(),
        phase=PlanPhase.POST_DELEGATION,
        probe_matrix_id="pm",
        attempted=0,
        classified=0,
    )
    assert observed.coverage == 0.0


def test_observed_authority_classified_exceeds_attempted_rejected():
    with pytest.raises(ValidationError, match="classified cannot exceed attempted"):
        ObservedAuthority(
            capabilities=AuthoritySet.of(),
            phase=PlanPhase.POST_DELEGATION,
            probe_matrix_id="pm",
            attempted=1,
            classified=2,
        )


# ---------------------------------------------------------------------------
# DelegationEdge / IdentityNode
# ---------------------------------------------------------------------------


def test_delegation_edge_rejects_self_delegation():
    caps = AuthoritySet.of("test.a")
    with pytest.raises(ValidationError, match="self-delegation"):
        DelegationEdge(
            edge_id="e1",
            source_id="agent-a",
            target_id="agent-a",
            mechanism=DelegationMechanism.ROLE_CHAIN,
            requested_capabilities=caps,
            intended_capabilities=caps,
            expected_effective=caps,
            credential_lifetime_s=900,
        )


def _expected(*capabilities: str, declared: bool = False) -> ExpectedAuthority:
    return ExpectedAuthority(
        capabilities=AuthoritySet.of(*capabilities),
        phase=PlanPhase.POST_DELEGATION,
        derivation="DECLARED" if declared else "INHERITED_ATTENUATED",
    )


def test_root_node_rejects_parent_id():
    with pytest.raises(ValidationError, match="root node must not have a parent"):
        IdentityNode(
            identity_id="root",
            is_root=True,
            hop_index=0,
            parent_id="someone",
            expected_authority=_expected("test.a", declared=True),
        )


def test_root_node_rejects_nonzero_hop_index():
    with pytest.raises(ValidationError, match="root node must have hop_index 0"):
        IdentityNode(
            identity_id="root",
            is_root=True,
            hop_index=1,
            expected_authority=_expected("test.a", declared=True),
        )


def test_non_root_node_requires_parent():
    with pytest.raises(ValidationError, match="requires a parent"):
        IdentityNode(
            identity_id="agent-a",
            is_root=False,
            hop_index=1,
            expected_authority=_expected("test.a"),
        )


def test_node_agreement_property():
    node = IdentityNode(
        identity_id="agent-a",
        hop_index=1,
        parent_id="root",
        expected_authority=_expected("test.a", "test.b"),
        observed_authority=ObservedAuthority(
            capabilities=AuthoritySet.of("test.b", "test.c"),
            phase=PlanPhase.POST_DELEGATION,
            probe_matrix_id="pm",
            attempted=2,
            classified=2,
        ),
    )
    assert node.agreement.sorted == ("test.b",)


def test_node_agreement_unmeasured_is_empty():
    node = IdentityNode(
        identity_id="agent-a", hop_index=1, parent_id="root", expected_authority=_expected("test.a")
    )
    assert node.agreement.is_empty()


# ---------------------------------------------------------------------------
# AuthorizationGraph
# ---------------------------------------------------------------------------


def test_graph_rejects_duplicate_identity_ids():
    root = IdentityNode(
        identity_id="dup",
        is_root=True,
        hop_index=0,
        expected_authority=_expected("test.a", declared=True),
    )
    other = IdentityNode(
        identity_id="dup",
        is_root=False,
        hop_index=1,
        parent_id="dup",
        expected_authority=_expected("test.a"),
    )
    with pytest.raises(ScenarioSemanticError, match="duplicate identity ids"):
        Graph(nodes=(root, other))


def test_graph_rejects_edge_referencing_unknown_identity():
    root = IdentityNode(
        identity_id="root",
        is_root=True,
        hop_index=0,
        expected_authority=_expected("test.a", declared=True),
    )
    caps = AuthoritySet.of("test.a")
    ghost_edge = DelegationEdge(
        edge_id="e1",
        source_id="root",
        target_id="ghost",
        mechanism=DelegationMechanism.ROLE_CHAIN,
        requested_capabilities=caps,
        intended_capabilities=caps,
        expected_effective=caps,
        credential_lifetime_s=900,
    )
    with pytest.raises(ScenarioSemanticError, match="unknown identity"):
        Graph(nodes=(root,), edges=(ghost_edge,))


def test_graph_node_lookup_missing_raises_keyerror():
    root = IdentityNode(
        identity_id="root",
        is_root=True,
        hop_index=0,
        expected_authority=_expected("test.a", declared=True),
    )
    graph = Graph(nodes=(root,))
    with pytest.raises(KeyError):
        graph.node("missing")


def test_graph_edge_into():
    root = IdentityNode(
        identity_id="root",
        is_root=True,
        hop_index=0,
        expected_authority=_expected("test.a", declared=True),
    )
    child = IdentityNode(
        identity_id="child", hop_index=1, parent_id="root", expected_authority=_expected("test.a")
    )
    caps = AuthoritySet.of("test.a")
    edge = DelegationEdge(
        edge_id="e1",
        source_id="root",
        target_id="child",
        mechanism=DelegationMechanism.ROLE_CHAIN,
        requested_capabilities=caps,
        intended_capabilities=caps,
        expected_effective=caps,
        credential_lifetime_s=900,
    )
    graph = Graph(nodes=(root, child), edges=(edge,))
    assert graph.edge_into("child") is edge
    assert graph.edge_into("root") is None


# ---------------------------------------------------------------------------
# ProbeTiming / ProbeOutcome / Observation
# ---------------------------------------------------------------------------


def test_probe_timing_duration_and_ordering():
    timing = ProbeTiming(
        monotonic_start_ns=1_000_000_000,
        monotonic_end_ns=1_500_000_000,
        wall_start=datetime.now(UTC),
    )
    assert timing.duration_ms == pytest.approx(500.0)


def test_probe_timing_rejects_end_before_start():
    with pytest.raises(ValidationError, match="precedes"):
        ProbeTiming(
            monotonic_start_ns=2_000_000_000,
            monotonic_end_ns=1_000_000_000,
            wall_start=datetime.now(UTC),
        )


def test_probe_outcome_rejects_attribution_on_non_denial():
    with pytest.raises(ValidationError, match="denial_attribution"):
        ProbeOutcome(
            outcome_class=OutcomeClass.ALLOWED, denial_attribution=DenialAttribution.EXPLICIT_DENY
        )


def _probe_request() -> ProbeRequestRecord:
    return ProbeRequestRecord(
        probe_kind=ProbeKind.READ_MARKER,
        binding_actions=("fake:Get",),
        target_ref_hash="sha256:" + "0" * 64,
        target_namespace="cb-01234567",
        parameters_fingerprint="sha256:" + "0" * 64,
    )


def test_observation_rejects_trial_exceeding_trial_count():
    with pytest.raises(ValidationError, match="trial exceeds trial_count"):
        Observation(
            observation_id="obs_1",
            run_id="run_1",
            sequence=0,
            phase=PlanPhase.POST_DELEGATION,
            probe_matrix_id="pm",
            identity_id="agent-a",
            identity_ref_hash="sha256:" + "0" * 64,
            capability_id="test.a",
            trial=2,
            trial_count=1,
            request=_probe_request(),
            timing=ProbeTiming(
                monotonic_start_ns=0, monotonic_end_ns=1, wall_start=datetime.now(UTC)
            ),
            outcome=ProbeOutcome(outcome_class=OutcomeClass.ALLOWED),
            preconditions_verified=True,
        )


class TestProbeCellResultResolved:
    def test_all_allowed(self):
        cell = ProbeCellResult(
            identity_id="a",
            capability_id="test.a",
            phase=PlanPhase.POST_DELEGATION,
            trials=(OutcomeClass.ALLOWED, OutcomeClass.ALLOWED),
        )
        assert cell.resolved is OutcomeClass.ALLOWED
        assert cell.unanimous is True

    def test_all_denied_same_kind(self):
        cell = ProbeCellResult(
            identity_id="a",
            capability_id="test.a",
            phase=PlanPhase.POST_DELEGATION,
            trials=(OutcomeClass.DENIED_EXPLICIT, OutcomeClass.DENIED_EXPLICIT),
        )
        assert cell.resolved is OutcomeClass.DENIED_EXPLICIT
        assert cell.unanimous is True

    def test_denied_mixed_kind_reports_unattributed(self):
        cell = ProbeCellResult(
            identity_id="a",
            capability_id="test.a",
            phase=PlanPhase.POST_DELEGATION,
            trials=(OutcomeClass.DENIED_EXPLICIT, OutcomeClass.DENIED_IMPLICIT),
        )
        assert cell.resolved is OutcomeClass.DENIED_UNATTRIBUTED
        assert cell.unanimous is False

    def test_all_error_reports_first(self):
        cell = ProbeCellResult(
            identity_id="a",
            capability_id="test.a",
            phase=PlanPhase.POST_DELEGATION,
            trials=(OutcomeClass.ERROR_TRANSIENT, OutcomeClass.ERROR_TRANSIENT),
        )
        assert cell.resolved is OutcomeClass.ERROR_TRANSIENT

    def test_mixed_allow_and_deny_is_indeterminate(self):
        cell = ProbeCellResult(
            identity_id="a",
            capability_id="test.a",
            phase=PlanPhase.POST_DELEGATION,
            trials=(OutcomeClass.ALLOWED, OutcomeClass.DENIED_EXPLICIT),
        )
        assert cell.resolved is OutcomeClass.INDETERMINATE


# ---------------------------------------------------------------------------
# RevocationMeasurement
# ---------------------------------------------------------------------------


def test_revocation_measurement_requires_window_when_observed():
    with pytest.raises(ValidationError, match="requires a transition_window"):
        RevocationMeasurement(
            identity_id="a",
            capability_id="test.a",
            mutation_kind="ATTACH_INLINE_DENY",
            transition_observed=True,
            poll_interval_ms=500,
            poll_count=3,
            window_length_s=1.5,
            mutation_receipt_confirmed=True,
        )


def test_revocation_measurement_rejects_window_when_not_observed():
    with pytest.raises(ValidationError, match="without an observed transition"):
        RevocationMeasurement(
            identity_id="a",
            capability_id="test.a",
            mutation_kind="ATTACH_INLINE_DENY",
            transition_observed=False,
            transition_window=Interval.from_bounds(0.1, 0.2),
            poll_interval_ms=500,
            poll_count=3,
            window_length_s=1.5,
            mutation_receipt_confirmed=True,
        )


# ---------------------------------------------------------------------------
# TaskOutcome
# ---------------------------------------------------------------------------


def test_task_outcome_claims_complete_but_is_not():
    task = TaskOutcome(
        task_id="t1",
        identity_id="a",
        worker="w",
        status=TaskStatus.COMPLETE,
        steps_total=3,
        steps_attempted=3,
        steps_succeeded=2,
        reported_insufficient_authority=False,
        output_marker_written=True,
        output_marker_verified_independently=True,
    )
    assert task.claims_complete_but_is_not is True


def test_task_outcome_claims_output_that_does_not_exist():
    task = TaskOutcome(
        task_id="t1",
        identity_id="a",
        worker="w",
        status=TaskStatus.COMPLETE,
        steps_total=1,
        steps_attempted=1,
        steps_succeeded=1,
        reported_insufficient_authority=False,
        output_marker_written=True,
        output_marker_verified_independently=False,
    )
    assert task.claims_output_that_does_not_exist is True


# ---------------------------------------------------------------------------
# CategoryResult
# ---------------------------------------------------------------------------


def test_category_result_low_coverage_must_be_partial():
    with pytest.raises(ValidationError, match="must be reported as PARTIAL"):
        CategoryResult(
            category=ScoringCategory.SCOPE_ATTENUATION,
            status=CategoryStatus.CONSISTENT,
            coverage=0.5,
            confidence=Confidence.LOW,
        )


def test_category_result_low_coverage_as_partial_is_accepted():
    result = CategoryResult(
        category=ScoringCategory.SCOPE_ATTENUATION,
        status=CategoryStatus.PARTIAL,
        coverage=0.5,
        confidence=Confidence.LOW,
    )
    assert result.status is CategoryStatus.PARTIAL
