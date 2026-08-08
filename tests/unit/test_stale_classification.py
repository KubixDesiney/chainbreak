"""``analysis/timing.py``'s stale-authority classification (AUTHORIZATION_MODEL.md
section 5.2's six-row table), and its paired-fresh-credential disambiguation
(M13's design element)."""

from __future__ import annotations

import pytest

from chainbreak.analysis.timing import classify_stale_authority
from chainbreak.core.enums import OutcomeClass, StaleAuthorityClass

pytestmark = pytest.mark.unit


class TestSixRowTable:
    def test_denied_consistent_with_post_mutation_policy(self):
        result = classify_stale_authority(
            deferred_outcome=OutcomeClass.DENIED_EXPLICIT, credential_expired_at_execution=False
        )
        assert result is StaleAuthorityClass.CURRENT_AUTHORITY

    def test_allowed_credential_unexpired_fresh_would_be_denied(self):
        result = classify_stale_authority(
            deferred_outcome=OutcomeClass.ALLOWED,
            credential_expired_at_execution=False,
            fresh_outcome=OutcomeClass.DENIED_EXPLICIT,
        )
        assert result is StaleAuthorityClass.STALE_AUTHORITY_LIVE_CREDENTIAL

    def test_allowed_credential_past_expiry(self):
        result = classify_stale_authority(
            deferred_outcome=OutcomeClass.ALLOWED, credential_expired_at_execution=True
        )
        assert result is StaleAuthorityClass.EXPIRED_CREDENTIAL_HONORED

    def test_denied_with_expiry(self):
        result = classify_stale_authority(
            deferred_outcome=OutcomeClass.DENIED_IMPLICIT, credential_expired_at_execution=True
        )
        assert result is StaleAuthorityClass.CREDENTIAL_EXPIRED

    def test_allowed_but_session_scope_removed(self):
        result = classify_stale_authority(
            deferred_outcome=OutcomeClass.ALLOWED,
            credential_expired_at_execution=False,
            session_scope_removed=True,
        )
        assert result is StaleAuthorityClass.SESSION_SCOPE_CACHED

    def test_other_combination_is_indeterminate(self):
        result = classify_stale_authority(
            deferred_outcome=OutcomeClass.INDETERMINATE, credential_expired_at_execution=False
        )
        assert result is StaleAuthorityClass.INDETERMINATE


class TestPairedFreshCredentialDisambiguation:
    def test_ambiguous_case_not_propagated_is_indeterminate_not_stale(self):
        """The change hasn't propagated anywhere -- both the pinned and a
        freshly-minted credential still see the old policy. This must NOT be
        reported as STALE_AUTHORITY_LIVE_CREDENTIAL (M13's own explicit
        requirement: 'assert the classification is not propagated, NOT
        stale authority')."""
        result = classify_stale_authority(
            deferred_outcome=OutcomeClass.ALLOWED,
            credential_expired_at_execution=False,
            fresh_outcome=OutcomeClass.ALLOWED,
        )
        assert result is StaleAuthorityClass.INDETERMINATE
        assert result is not StaleAuthorityClass.STALE_AUTHORITY_LIVE_CREDENTIAL

    def test_no_fresh_outcome_supplied_defaults_to_stale(self):
        """Without a fresh-credential pairing there is no way to
        disambiguate; the deferral itself (ALLOWED, unexpired, no session
        scope removal) is still reported as the documented stale-bearer-
        token behavior."""
        result = classify_stale_authority(
            deferred_outcome=OutcomeClass.ALLOWED, credential_expired_at_execution=False
        )
        assert result is StaleAuthorityClass.STALE_AUTHORITY_LIVE_CREDENTIAL

    def test_session_scope_removed_takes_priority_over_fresh_outcome(self):
        result = classify_stale_authority(
            deferred_outcome=OutcomeClass.ALLOWED,
            credential_expired_at_execution=False,
            session_scope_removed=True,
            fresh_outcome=OutcomeClass.ALLOWED,
        )
        assert result is StaleAuthorityClass.SESSION_SCOPE_CACHED
