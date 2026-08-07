"""providers/fake/engine.py -- F2's policy evaluation model: explicit deny >
explicit allow > implicit deny, across identity/session/resource policy.
"""

from __future__ import annotations

import pytest

from chainbreak.core.enums import OutcomeClass
from chainbreak.core.models import AuthoritySet
from chainbreak.providers.fake.engine import PolicyEngine

pytestmark = pytest.mark.unit


class TestIdentityPolicyAlone:
    def test_granted_capability_is_allowed(self):
        engine = PolicyEngine()
        engine.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        assert engine.evaluate("agent-a", "objectstore.read") is OutcomeClass.ALLOWED

    def test_ungranted_capability_is_implicitly_denied(self):
        engine = PolicyEngine()
        engine.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        assert engine.evaluate("agent-a", "keyvalue.read") is OutcomeClass.DENIED_IMPLICIT

    def test_unregistered_identity_raises(self):
        engine = PolicyEngine()
        with pytest.raises(KeyError):
            engine.evaluate("nobody", "objectstore.read")


class TestExplicitDenyWinsOverAllow:
    def test_explicit_deny_beats_identity_allow(self):
        engine = PolicyEngine()
        engine.register_identity(
            "agent-a", allow=AuthoritySet.of("objectstore.read", "objectstore.write")
        )
        engine.apply_deny("agent-a", AuthoritySet.of("objectstore.write"))
        assert engine.evaluate("agent-a", "objectstore.write") is OutcomeClass.DENIED_EXPLICIT
        assert engine.evaluate("agent-a", "objectstore.read") is OutcomeClass.ALLOWED

    def test_explicit_deny_beats_a_session_policy_that_would_otherwise_allow(self):
        engine = PolicyEngine()
        engine.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        engine.apply_deny("agent-a", AuthoritySet.of("objectstore.read"))
        result = engine.evaluate(
            "agent-a", "objectstore.read", session_allow=AuthoritySet.of("objectstore.read")
        )
        assert result is OutcomeClass.DENIED_EXPLICIT

    def test_removing_a_deny_restores_the_allow(self):
        engine = PolicyEngine()
        engine.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        engine.apply_deny("agent-a", AuthoritySet.of("objectstore.read"))
        engine.remove_deny("agent-a", AuthoritySet.of("objectstore.read"))
        assert engine.evaluate("agent-a", "objectstore.read") is OutcomeClass.ALLOWED


class TestSessionPolicyIntersectsNeverGrants:
    def test_session_narrower_than_identity_policy_excludes_the_capability(self):
        engine = PolicyEngine()
        engine.register_identity(
            "agent-a", allow=AuthoritySet.of("objectstore.read", "objectstore.write")
        )
        result = engine.evaluate(
            "agent-a", "objectstore.write", session_allow=AuthoritySet.of("objectstore.read")
        )
        assert result is OutcomeClass.DENIED_IMPLICIT

    def test_session_cannot_grant_beyond_the_identity_policy(self):
        # The whole point of intersection semantics: a session policy naming
        # a capability the identity policy never granted must not produce
        # ALLOWED. This is the property AWS_PROVIDER_SPEC section 4 calls out
        # as the correct primary attenuation mechanism.
        engine = PolicyEngine()
        engine.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        result = engine.evaluate(
            "agent-a", "objectstore.write", session_allow=AuthoritySet.of("objectstore.write")
        )
        assert result is OutcomeClass.DENIED_IMPLICIT

    def test_session_covering_everything_the_identity_grants_changes_nothing(self):
        engine = PolicyEngine()
        engine.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        result = engine.evaluate(
            "agent-a", "objectstore.read", session_allow=AuthoritySet.of("objectstore.read")
        )
        assert result is OutcomeClass.ALLOWED


class TestResourcePolicyCanGrantAcrossTheIntersection:
    def test_resource_policy_grants_a_capability_the_identity_never_had(self):
        # Documented asymmetry (AWS_PROVIDER_SPEC section 4): unlike a
        # session policy, a resource policy can grant across the
        # intersection.
        engine = PolicyEngine()
        engine.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        result = engine.evaluate(
            "agent-a", "keyvalue.read", resource_allow=AuthoritySet.of("keyvalue.read")
        )
        assert result is OutcomeClass.ALLOWED

    def test_explicit_deny_still_wins_over_a_resource_policy_grant(self):
        engine = PolicyEngine()
        engine.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        engine.apply_deny("agent-a", AuthoritySet.of("keyvalue.read"))
        result = engine.evaluate(
            "agent-a", "keyvalue.read", resource_allow=AuthoritySet.of("keyvalue.read")
        )
        assert result is OutcomeClass.DENIED_EXPLICIT


class TestMutationHelpers:
    def test_apply_and_remove_allow(self):
        engine = PolicyEngine()
        engine.register_identity("agent-a")
        engine.apply_allow("agent-a", AuthoritySet.of("objectstore.read"))
        assert engine.evaluate("agent-a", "objectstore.read") is OutcomeClass.ALLOWED
        engine.remove_allow("agent-a", AuthoritySet.of("objectstore.read"))
        assert engine.evaluate("agent-a", "objectstore.read") is OutcomeClass.DENIED_IMPLICIT

    def test_replace_sets_both_allow_and_deny_atomically(self):
        engine = PolicyEngine()
        engine.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        engine.replace(
            "agent-a",
            allow=AuthoritySet.of("keyvalue.read"),
            deny=AuthoritySet.of("keyvalue.write"),
        )
        assert engine.evaluate("agent-a", "objectstore.read") is OutcomeClass.DENIED_IMPLICIT
        assert engine.evaluate("agent-a", "keyvalue.read") is OutcomeClass.ALLOWED
        assert engine.evaluate("agent-a", "keyvalue.write") is OutcomeClass.DENIED_EXPLICIT

    def test_is_registered(self):
        engine = PolicyEngine()
        assert engine.is_registered("agent-a") is False
        engine.register_identity("agent-a")
        assert engine.is_registered("agent-a") is True


class TestEvaluateAgainstExplicitSnapshot:
    """The static entry point ``adapter.py`` uses to evaluate against a
    pre-mutation snapshot while a consistency-model transition is in flight,
    without touching (or even requiring) a registered identity."""

    def test_matches_evaluate_for_an_equivalent_registered_identity(self):
        engine = PolicyEngine()
        engine.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        via_evaluate = engine.evaluate("agent-a", "objectstore.read")
        via_snapshot = PolicyEngine.evaluate_against(
            AuthoritySet.of("objectstore.read"), AuthoritySet(), "objectstore.read"
        )
        assert via_evaluate is via_snapshot is OutcomeClass.ALLOWED

    def test_works_with_no_registered_identity_at_all(self):
        result = PolicyEngine.evaluate_against(
            AuthoritySet(), AuthoritySet.of("objectstore.read"), "objectstore.read"
        )
        assert result is OutcomeClass.DENIED_EXPLICIT
