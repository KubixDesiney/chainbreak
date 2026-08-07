"""The fake's policy-evaluation model (F2): explicit deny > explicit allow >
implicit deny, evaluated across identity policy, session policy (intersection
semantics -- a session can only narrow), and resource policy (which can grant
*across* the intersection, a documented asymmetry -- AWS_PROVIDER_SPEC section
4). This is a real authorization engine, not a stub: every scope-attenuation
and delegation-drift scenario's correctness depends on this evaluation being
faithful to how AWS actually behaves.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from chainbreak.core.enums import OutcomeClass
from chainbreak.core.ids import CapabilityId, IdentityId
from chainbreak.core.models import EMPTY_AUTHORITY, AuthoritySet


@dataclass
class IdentityPolicyState:
    """One identity's current identity-policy grants and explicit denials.

    Mutable by design: ``PolicyEngine.apply_mutation`` (via the adapter's
    ``apply_policy_mutation``) changes this in place, which is what lets the
    fake exhibit a real before/after policy transition for the revocation
    family once the consistency model (M5) and the poller (M12) exist to
    observe it.
    """

    allow: AuthoritySet = EMPTY_AUTHORITY
    deny: AuthoritySet = EMPTY_AUTHORITY


@dataclass
class PolicyEngine:
    """Per-identity identity-policy state, plus the evaluation function.

    Session and resource policy are supplied per call (``evaluate``'s
    ``session_allow``/``resource_allow`` parameters) rather than stored here:
    a session policy is scoped to one delegated credential, not to the
    identity itself, and a resource policy is scoped to the resource a probe
    targets, not to the caller -- storing either on ``IdentityPolicyState``
    would conflate three independent axes into one.
    """

    identity_policies: dict[IdentityId, IdentityPolicyState] = field(default_factory=dict)

    def register_identity(
        self, identity_id: IdentityId, *, allow: AuthoritySet = EMPTY_AUTHORITY
    ) -> None:
        self.identity_policies[identity_id] = IdentityPolicyState(allow=allow)

    def _state(self, identity_id: IdentityId) -> IdentityPolicyState:
        try:
            return self.identity_policies[identity_id]
        except KeyError:
            raise KeyError(f"no policy state registered for identity {identity_id!r}") from None

    def identity_allow(self, identity_id: IdentityId) -> AuthoritySet:
        """The identity's own policy grant, before any session narrowing --
        used to attribute an implicit denial to the session policy rather
        than the identity policy when that is what actually excluded it."""
        return self._state(identity_id).allow

    def identity_deny(self, identity_id: IdentityId) -> AuthoritySet:
        return self._state(identity_id).deny

    def is_registered(self, identity_id: IdentityId) -> bool:
        return identity_id in self.identity_policies

    def evaluate(
        self,
        identity_id: IdentityId,
        capability_id: CapabilityId,
        *,
        session_allow: AuthoritySet | None = None,
        resource_allow: AuthoritySet | None = None,
    ) -> OutcomeClass:
        """F2's evaluation order, made explicit:

        1. Start from the identity policy's ``allow`` set.
        2. A session policy, if present, *intersects* -- it can only narrow
           what the identity policy already grants.
        3. A resource policy, if present, *unions in* -- it can grant across
           the intersection, independent of what the session narrowed to.
        4. An explicit deny on either the identity or session policy wins
           over all of the above, unconditionally.
        """
        state = self._state(identity_id)
        return self.evaluate_against(
            state.allow,
            state.deny,
            capability_id,
            session_allow=session_allow,
            resource_allow=resource_allow,
        )

    @staticmethod
    def evaluate_against(
        allow: AuthoritySet,
        deny: AuthoritySet,
        capability_id: CapabilityId,
        *,
        session_allow: AuthoritySet | None = None,
        resource_allow: AuthoritySet | None = None,
    ) -> OutcomeClass:
        """Same evaluation order as ``evaluate``, against an explicit
        (allow, deny) pair rather than a registered identity's live state --
        what lets a caller (``adapter.py``) evaluate a probe against a
        *pre-mutation* snapshot while a consistency-model transition is still
        in flight, without duplicating the evaluation order."""
        effective_allow = allow
        if session_allow is not None:
            effective_allow = effective_allow & session_allow
        if resource_allow is not None:
            effective_allow = effective_allow | resource_allow

        if capability_id in deny:
            return OutcomeClass.DENIED_EXPLICIT
        if capability_id in effective_allow:
            return OutcomeClass.ALLOWED
        return OutcomeClass.DENIED_IMPLICIT

    def apply_deny(self, identity_id: IdentityId, capabilities: AuthoritySet) -> None:
        state = self._state(identity_id)
        state.deny = state.deny | capabilities

    def remove_deny(self, identity_id: IdentityId, capabilities: AuthoritySet) -> None:
        state = self._state(identity_id)
        state.deny = state.deny - capabilities

    def apply_allow(self, identity_id: IdentityId, capabilities: AuthoritySet) -> None:
        state = self._state(identity_id)
        state.allow = state.allow | capabilities

    def remove_allow(self, identity_id: IdentityId, capabilities: AuthoritySet) -> None:
        state = self._state(identity_id)
        state.allow = state.allow - capabilities

    def replace(self, identity_id: IdentityId, *, allow: AuthoritySet, deny: AuthoritySet) -> None:
        self.identity_policies[identity_id] = IdentityPolicyState(allow=allow, deny=deny)
