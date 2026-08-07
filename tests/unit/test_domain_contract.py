"""Contract tests for the CHAINBREAK domain model.

These are the tests that prove the *design* holds together. Claude Code will
add the full unit suite described in TESTING.md; this file is the executable
core of the specification and must keep passing.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from chainbreak.capabilities.loader import load_catalog, resolve_bindings, validate_binding
from chainbreak.core.enums import (
    Confidence,
    DelegationMechanism,
    OutcomeClass,
    PlanPhase,
    ProbeKind,
    Provider,
    Sensitivity,
)
from chainbreak.core.errors import (
    CapabilityResolutionError,
    ScenarioSafetyError,
    ScenarioSemanticError,
    SecretSerializationError,
)
from chainbreak.core.ids import is_ulid, new_run_id, run_salt
from chainbreak.core.models import (
    AuthoritySet,
    AuthorizationGraph,
    CredentialRecord,
    DelegationEdge,
    ExpectedAuthority,
    IdentityNode,
    Interval,
    ObservedAuthority,
    ProviderCapabilityBinding,
    SafetyEnvelope,
    min_confidence,
)
from chainbreak.core.secrets import SecretMaterial, TemporaryCredential
from chainbreak.scenarios.safety import assert_no_literal_infrastructure

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# AuthoritySet -- the basis of every divergence computation
# --------------------------------------------------------------------------


def test_authority_set_algebra() -> None:
    a = AuthoritySet.of("objectstore.read", "objectstore.write", "keyvalue.read")
    b = AuthoritySet.of("objectstore.read")

    assert (a - b).sorted == ("keyvalue.read", "objectstore.write")
    assert (a & b).sorted == ("objectstore.read",)
    assert b.is_subset_of(a)
    assert not a.is_subset_of(b)
    assert len(a) == 3


def test_authority_set_ordering_is_canonical() -> None:
    """Serialized evidence must be diffable, so ordering cannot depend on hashing."""
    forward = AuthoritySet.of("queue.send", "identity.whoami", "objectstore.read")
    reverse = AuthoritySet.of("objectstore.read", "identity.whoami", "queue.send")
    assert (
        forward.sorted
        == reverse.sorted
        == (
            "identity.whoami",
            "objectstore.read",
            "queue.send",
        )
    )


# --------------------------------------------------------------------------
# SI-1 -- secrets must be unrenderable
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "render",
    [
        str,
        repr,
        lambda s: f"{s}",
        lambda s: "{}".format(s),  # noqa: UP032 - exercising the format path deliberately
        bytes,
    ],
)
def test_secret_material_refuses_every_render_path(render) -> None:  # type: ignore[no-untyped-def]
    secret = SecretMaterial("ASIAEXAMPLEEXAMPLE00", "session_token")
    with pytest.raises(SecretSerializationError):
        render(secret)


def test_secret_digest_is_stable_and_salted() -> None:
    secret = SecretMaterial("value", "test")
    assert secret.digest("salt-a") == secret.digest("salt-a")
    assert secret.digest("salt-a") != secret.digest("salt-b")
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", secret.digest())


def test_temporary_credential_repr_discloses_nothing() -> None:
    credential = TemporaryCredential(
        access_key_id="ASIAEXAMPLEEXAMPLE00",
        secret_access_key="super-secret-value",
        session_token="token-value",
        credential_id="cred_test",
    )
    rendered = repr(credential)
    assert "super-secret-value" not in rendered
    assert "token-value" not in rendered
    assert "cred_test" in rendered


# --------------------------------------------------------------------------
# SI-6 -- the account allowlist admits no wildcard
# --------------------------------------------------------------------------


@pytest.mark.parametrize("account", ["*", "any", "ALL", "", "12345", "not-an-account"])
def test_safety_envelope_rejects_non_explicit_accounts(account: str) -> None:
    with pytest.raises(ValueError, match="account"):
        SafetyEnvelope(
            allowed_account_ids=(account,),
            allowed_regions=("region-a",),
            namespace="cb-0123abcd",
            namespace_pattern="^cb-0123abcd",
        )


def test_safety_envelope_duration_ceiling() -> None:
    with pytest.raises(ValueError, match="14400"):
        SafetyEnvelope(
            allowed_account_ids=("123456789012",),
            allowed_regions=("region-a",),
            namespace="cb-0123abcd",
            namespace_pattern="^cb-0123abcd",
            max_run_duration_seconds=20_000,
        )


# --------------------------------------------------------------------------
# Graph invariants G-1, G-2
# --------------------------------------------------------------------------


def _node(identity: str, *, root: bool = False, hop: int = 0, parent: str | None = None):  # type: ignore[no-untyped-def]
    return IdentityNode(
        identity_id=identity,
        is_root=root,
        hop_index=hop,
        parent_id=parent,
        expected_authority=ExpectedAuthority(
            capabilities=AuthoritySet.of("objectstore.read"),
            phase=PlanPhase.POST_DELEGATION,
            derivation="DECLARED" if root else "INHERITED_ATTENUATED",
        ),
    )


def _edge(edge_id: str, source: str, target: str) -> DelegationEdge:
    caps = AuthoritySet.of("objectstore.read")
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


def test_graph_accepts_a_valid_chain() -> None:
    graph = AuthorizationGraph(
        nodes=(
            _node("principal", root=True),
            _node("agent-a", hop=1, parent="principal"),
            _node("agent-b", hop=2, parent="agent-a"),
        ),
        edges=(_edge("hop-1", "principal", "agent-a"), _edge("hop-2", "agent-a", "agent-b")),
    )
    assert graph.depth == 2
    assert graph.paths() == (("principal", "agent-a", "agent-b"),)


def test_graph_rejects_a_cycle() -> None:
    """G-1: a cycle makes hop index and 'first divergence' meaningless."""
    with pytest.raises(ScenarioSemanticError, match="cycle"):
        AuthorizationGraph(
            nodes=(
                _node("principal", root=True),
                _node("agent-a", hop=1, parent="principal"),
                _node("agent-b", hop=2, parent="agent-a"),
            ),
            edges=(
                _edge("hop-1", "principal", "agent-a"),
                _edge("hop-2", "agent-a", "agent-b"),
                _edge("hop-3", "agent-b", "agent-a"),
            ),
        )


def test_graph_requires_exactly_one_root() -> None:
    with pytest.raises(ScenarioSemanticError, match="one root"):
        AuthorizationGraph(
            nodes=(_node("principal", root=True), _node("other", root=True)),
            edges=(),
        )


# --------------------------------------------------------------------------
# Divergence -- AUTHORIZATION_MODEL 4.1
# --------------------------------------------------------------------------


def test_node_divergence_detects_expansion_and_narrowing() -> None:
    node = IdentityNode(
        identity_id="agent-c",
        hop_index=3,
        parent_id="agent-b",
        expected_authority=ExpectedAuthority(
            capabilities=AuthoritySet.of("objectstore.read"),
            phase=PlanPhase.POST_DELEGATION,
            derivation="INHERITED_ATTENUATED",
        ),
        observed_authority=ObservedAuthority(
            capabilities=AuthoritySet.of("keyvalue.read", "objectstore.read"),
            phase=PlanPhase.POST_DELEGATION,
            probe_matrix_id="pm_03",
            attempted=6,
            classified=6,
        ),
    )
    assert node.unexpected_gain.sorted == ("keyvalue.read",)
    assert node.unexpected_loss.is_empty()
    assert node.diverged
    assert node.observed_authority is not None
    assert node.observed_authority.coverage == 1.0


def test_unmeasured_node_reports_no_divergence_rather_than_a_false_one() -> None:
    node = _node("agent-a", hop=1, parent="principal")
    assert node.observed_authority is None
    assert node.unexpected_gain.is_empty()
    assert node.unexpected_loss.is_empty()
    assert not node.diverged


# --------------------------------------------------------------------------
# Outcome classification -- AUTH-1
# --------------------------------------------------------------------------


def test_only_allowed_counts_as_authority() -> None:
    assert OutcomeClass.ALLOWED.counts_as_authority
    for outcome in OutcomeClass:
        if outcome is not OutcomeClass.ALLOWED:
            assert not outcome.counts_as_authority


def test_errors_are_neither_allow_nor_deny() -> None:
    for outcome in (
        OutcomeClass.ERROR_RESOURCE_MISSING,
        OutcomeClass.ERROR_TRANSIENT,
        OutcomeClass.ERROR_INFRASTRUCTURE,
    ):
        assert outcome.is_error
        assert not outcome.is_denial
        assert not outcome.counts_as_authority


# --------------------------------------------------------------------------
# Measurements
# --------------------------------------------------------------------------


def test_interval_requires_ordering() -> None:
    with pytest.raises(ValueError, match="not ordered"):
        Interval(low=5.0, point=1.0, high=2.0)


def test_interval_from_bounds() -> None:
    interval = Interval.from_bounds(37.2, 39.0)
    assert interval.point == pytest.approx(38.1)
    assert interval.half_width == pytest.approx(0.9)


def test_confidence_aggregates_by_minimum_not_mean() -> None:
    assert min_confidence([Confidence.HIGH, Confidence.HIGH, Confidence.LOW]) is Confidence.LOW
    assert min_confidence([]) is Confidence.INSUFFICIENT


def test_credential_lifetime_cap_is_detected() -> None:
    """H7: AWS silently grants less than requested on a chained hop."""
    issued = datetime.now(UTC)
    record = CredentialRecord(
        credential_id="cred_x",
        identity_id="agent-b",
        mechanism=DelegationMechanism.ROLE_CHAIN,
        issued_at=issued,
        expires_at=issued + timedelta(seconds=3600),
        requested_duration_s=7200,
        granted_duration_s=3600,
        session_name_hash="sha256:" + "0" * 64,
        access_key_id_hash="sha256:" + "1" * 64,
    )
    assert record.lifetime_capped


# --------------------------------------------------------------------------
# Capability catalog
# --------------------------------------------------------------------------


def test_shipped_catalog_loads_and_is_safe() -> None:
    catalog = load_catalog()
    assert catalog.version == "1.0.0"
    assert len(catalog.capabilities) == 10
    assert catalog.dangerous() == (), "SI-9: the default catalog must contain no DANGEROUS entries"
    assert [c.id for c in catalog.controls()] == ["identity.whoami"]


def test_catalog_ids_match_the_documented_set() -> None:
    expected = {
        "objectstore.read",
        "objectstore.write",
        "objectstore.list",
        "keyvalue.read",
        "keyvalue.write",
        "function.invoke",
        "queue.send",
        "queue.receive",
        "identity.whoami",
        "identity.delegate",
    }
    assert set(load_catalog().ids().sorted) == expected


def test_unresolvable_capability_raises_rather_than_skipping() -> None:
    """CAP-1: a silent skip would let a scenario appear to pass untested."""
    catalog = load_catalog()
    with pytest.raises(CapabilityResolutionError, match=re.escape("objectstore.read")):
        resolve_bindings(catalog, AuthoritySet.of("objectstore.read"), {}, Provider.FAKE)


def test_binding_probe_kind_must_match_capability() -> None:
    catalog = load_catalog()
    capability = catalog.get("objectstore.read")
    wrong = ProviderCapabilityBinding(
        capability_id="objectstore.read",
        provider=Provider.FAKE,
        actions=("fake:ReadMarker",),
        resource_template="fake://{namespace}/markers/marker",
        probe_kind=ProbeKind.WRITE_SCRATCH,
        preconditions=("objectstore.marker_present",),
    )
    with pytest.raises(Exception, match="probe_kind"):
        validate_binding(capability, wrong, Provider.FAKE)


def test_binding_must_declare_capability_preconditions() -> None:
    catalog = load_catalog()
    capability = catalog.get("objectstore.read")
    missing = ProviderCapabilityBinding(
        capability_id="objectstore.read",
        provider=Provider.FAKE,
        actions=("fake:ReadMarker",),
        resource_template="fake://{namespace}/markers/marker",
        probe_kind=ProbeKind.READ_MARKER,
    )
    with pytest.raises(Exception, match="precondition"):
        validate_binding(capability, missing, Provider.FAKE)


def test_write_capability_must_declare_that_it_mutates() -> None:
    from chainbreak.core.models import Capability

    with pytest.raises(ValueError, match="mutates_state"):
        Capability(
            id="objectstore.badwrite",
            title="Bad write",
            description="A write capability that claims not to mutate state.",
            probe_kind=ProbeKind.WRITE_SCRATCH,
            sensitivity=Sensitivity.BENIGN_WRITE,
            mutates_state=False,
        )


# --------------------------------------------------------------------------
# SI-11 -- scenarios must not name real infrastructure
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "resource: arn:aws:s3:::my-real-bucket/key",
        "account: 123456789012",
        "region: us-east-1",
        "endpoint: https://internal.corp.example.net/",
    ],
)
def test_literal_infrastructure_is_rejected(text: str) -> None:
    with pytest.raises(ScenarioSafetyError):
        assert_no_literal_infrastructure(text, source="test")


def test_comments_may_mention_infrastructure() -> None:
    """Rejecting comments would make it impossible to explain the rule in a scenario file."""
    assert_no_literal_infrastructure(
        "identities: []  # never write arn:aws:iam::123456789012:role/x here",
        source="test",
    )


def test_shipped_scenarios_contain_no_literal_infrastructure() -> None:
    scenario_dir = REPO_ROOT / "scenarios"
    files = sorted(scenario_dir.rglob("*.yaml"))
    assert files, "no scenarios found -- the guard would pass vacuously"
    for path in files:
        assert_no_literal_infrastructure(path.read_text(encoding="utf-8"), source=str(path))


# --------------------------------------------------------------------------
# Identifiers
# --------------------------------------------------------------------------


def test_run_ids_are_ulids_and_sort_by_creation_time() -> None:
    """Monotonicity must hold even for IDs minted inside the same millisecond."""
    ids = [new_run_id() for _ in range(1000)]
    assert all(is_ulid(value) for value in ids)
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_run_salt_is_derived_from_the_run_id() -> None:
    run_id = new_run_id()
    assert run_salt(run_id) == f"chainbreak:{run_id}:"
