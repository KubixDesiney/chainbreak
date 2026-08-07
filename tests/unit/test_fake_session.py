"""providers/fake/session.py -- F3: credential lifetimes and the chained-role
duration cap.
"""

from __future__ import annotations

import pytest

from chainbreak.core.enums import DelegationMechanism, Provider
from chainbreak.core.models import AuthoritySet, IdentityRef
from chainbreak.providers.fake.session import (
    CHAINED_ROLE_DURATION_CAP_S,
    SessionStore,
    virtual_ms_to_datetime,
)

pytestmark = pytest.mark.unit


def _ref(identity_id: str) -> IdentityRef:
    return IdentityRef(
        provider=Provider.FAKE,
        kind="role",
        value=f"fake:555555555555:role/cb-abcd1234-{identity_id}",
        region="fake-region-1",
        account_ref="555555555555",
    )


class TestUncappedMechanisms:
    def test_direct_role_assumption_is_not_capped(self):
        store = SessionStore(seed=1)
        result = store.issue(
            identity_ref=_ref("agent-a"),
            target_identity_id="agent-a",
            mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
            requested_duration_s=7200,
            intended_capabilities=AuthoritySet.of("objectstore.read"),
            issued_at_ms=0,
        )
        assert result.record.granted_duration_s == 7200
        assert result.record.lifetime_capped is False

    def test_session_policy_scoped_alone_is_not_chain_capped(self):
        store = SessionStore(seed=1)
        result = store.issue(
            identity_ref=_ref("agent-a"),
            target_identity_id="agent-a",
            mechanism=DelegationMechanism.SESSION_POLICY_SCOPED,
            requested_duration_s=7200,
            intended_capabilities=AuthoritySet.of("objectstore.read"),
            issued_at_ms=0,
        )
        assert result.record.granted_duration_s == 7200


class TestChainedMechanismsAreCapped:
    def test_role_chain_capped_at_3600(self):
        store = SessionStore(seed=1)
        result = store.issue(
            identity_ref=_ref("agent-a"),
            target_identity_id="agent-a",
            mechanism=DelegationMechanism.ROLE_CHAIN,
            requested_duration_s=7200,
            intended_capabilities=AuthoritySet.of("objectstore.read"),
            issued_at_ms=0,
        )
        assert result.record.granted_duration_s == CHAINED_ROLE_DURATION_CAP_S
        assert result.record.requested_duration_s == 7200
        assert result.record.lifetime_capped is True

    def test_role_chain_with_session_policy_also_capped(self):
        store = SessionStore(seed=1)
        result = store.issue(
            identity_ref=_ref("agent-a"),
            target_identity_id="agent-a",
            mechanism=DelegationMechanism.ROLE_CHAIN_WITH_SESSION_POLICY,
            requested_duration_s=10_000,
            intended_capabilities=AuthoritySet.of("objectstore.read"),
            issued_at_ms=0,
        )
        assert result.record.granted_duration_s == CHAINED_ROLE_DURATION_CAP_S

    def test_a_chained_request_already_under_the_cap_is_not_reduced_further(self):
        store = SessionStore(seed=1)
        result = store.issue(
            identity_ref=_ref("agent-a"),
            target_identity_id="agent-a",
            mechanism=DelegationMechanism.ROLE_CHAIN,
            requested_duration_s=1800,
            intended_capabilities=AuthoritySet.of("objectstore.read"),
            issued_at_ms=0,
        )
        assert result.record.granted_duration_s == 1800
        assert result.record.lifetime_capped is False


class TestMaxSessionDurationCeiling:
    def test_direct_assumption_still_bounded_by_max_session_duration(self):
        store = SessionStore(seed=1, max_session_duration_s=3600)
        result = store.issue(
            identity_ref=_ref("agent-a"),
            target_identity_id="agent-a",
            mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
            requested_duration_s=999_999,
            intended_capabilities=AuthoritySet.of("objectstore.read"),
            issued_at_ms=0,
        )
        assert result.record.granted_duration_s == 3600


class TestLiveness:
    def test_credential_is_live_before_expiry(self):
        store = SessionStore(seed=1)
        result = store.issue(
            identity_ref=_ref("agent-a"),
            target_identity_id="agent-a",
            mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
            requested_duration_s=900,
            intended_capabilities=AuthoritySet.of("objectstore.read"),
            issued_at_ms=0,
        )
        assert store.is_live(result.record.credential_id, at_ms=899_000) is True

    def test_credential_is_not_live_after_expiry(self):
        store = SessionStore(seed=1)
        result = store.issue(
            identity_ref=_ref("agent-a"),
            target_identity_id="agent-a",
            mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
            requested_duration_s=900,
            intended_capabilities=AuthoritySet.of("objectstore.read"),
            issued_at_ms=0,
        )
        assert store.is_live(result.record.credential_id, at_ms=901_000) is False

    def test_unknown_credential_id_is_not_live(self):
        store = SessionStore(seed=1)
        assert store.is_live("no-such-credential", at_ms=0) is False

    def test_revoke_makes_a_live_credential_no_longer_live(self):
        store = SessionStore(seed=1)
        result = store.issue(
            identity_ref=_ref("agent-a"),
            target_identity_id="agent-a",
            mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
            requested_duration_s=900,
            intended_capabilities=AuthoritySet.of("objectstore.read"),
            issued_at_ms=0,
        )
        assert store.is_live(result.record.credential_id, at_ms=0) is True
        store.revoke(result.record.credential_id)
        assert store.is_live(result.record.credential_id, at_ms=0) is False

    def test_revoking_an_unknown_credential_is_not_an_error(self):
        store = SessionStore(seed=1)
        store.revoke("no-such-credential")  # must not raise


class TestDeterminism:
    def test_same_seed_and_call_sequence_produces_identical_credentials(self):
        store_a = SessionStore(seed=42)
        store_b = SessionStore(seed=42)
        result_a = store_a.issue(
            identity_ref=_ref("agent-a"),
            target_identity_id="agent-a",
            mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
            requested_duration_s=900,
            intended_capabilities=AuthoritySet.of("objectstore.read"),
            issued_at_ms=0,
        )
        result_b = store_b.issue(
            identity_ref=_ref("agent-a"),
            target_identity_id="agent-a",
            mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
            requested_duration_s=900,
            intended_capabilities=AuthoritySet.of("objectstore.read"),
            issued_at_ms=0,
        )
        assert result_a.record.credential_id == result_b.record.credential_id
        assert result_a.credential.access_key_id == result_b.credential.access_key_id
        assert result_a.credential.secret_access_key.reveal() == (
            result_b.credential.secret_access_key.reveal()
        )

    def test_no_secret_never_reads_the_system_clock(self):
        # virtual_ms_to_datetime is pure: same ms in, same datetime out,
        # regardless of when the test actually runs.
        assert virtual_ms_to_datetime(0) == virtual_ms_to_datetime(0)
