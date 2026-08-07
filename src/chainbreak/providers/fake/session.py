"""Simulated credential issuance (F3): lifetimes, expiry, and the chained-role
duration cap that makes ``LIFETIME_CAPPED`` exercisable offline.

AWS_PROVIDER_SPEC.md section 4: a ``ROLE_CHAIN`` (or
``ROLE_CHAIN_WITH_SESSION_POLICY``) ``AssumeRole`` -- one using credentials
that are themselves already temporary -- is capped by AWS at 3600 seconds
regardless of what duration is requested. A scenario that requests more on a
chained hop is *silently satisfied with less* unless the caller compares
requested vs. granted; ``SessionStore.issue`` always returns both
(``CredentialRecord.requested_duration_s``/``granted_duration_s``), so
``CredentialRecord.lifetime_capped`` (already defined in ``core/models.py``)
reports it correctly.

Session state and credential ids are drawn from a seeded RNG local to this
module, never from ``core.ids.new_ulid()`` (real wall time) -- required for
F6's "same seed => identical run, byte-for-byte" guarantee.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from chainbreak.core.enums import DelegationMechanism
from chainbreak.core.ids import IdentityId
from chainbreak.core.models import AuthoritySet, CredentialRecord, IdentityRef
from chainbreak.core.secrets import TemporaryCredential
from chainbreak.providers.base.types import DelegationResult

#: Arbitrary fixed epoch the virtual clock's millisecond offsets are measured
#: from. Never read from the system clock -- see module docstring.
_VIRTUAL_EPOCH = datetime(2024, 1, 1, tzinfo=UTC)

#: AWS's real, undocumented-in-any-API-response chained-role cap.
CHAINED_ROLE_DURATION_CAP_S = 3600

#: Mechanisms whose granted duration is capped regardless of request.
_CHAINED_MECHANISMS = frozenset(
    {DelegationMechanism.ROLE_CHAIN, DelegationMechanism.ROLE_CHAIN_WITH_SESSION_POLICY}
)


def virtual_ms_to_datetime(ms: int) -> datetime:
    return _VIRTUAL_EPOCH + timedelta(milliseconds=ms)


@dataclass
class SessionStore:
    """Issues fake credentials and tracks them for
    ``snapshot_policy_state``/mutation-driven revocation.
    """

    seed: int = 0
    max_session_duration_s: int = 43_200
    _rng: random.Random = field(init=False, repr=False)
    _counter: int = field(init=False, default=0, repr=False)
    _live: dict[str, datetime] = field(init=False, default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)  # noqa: S311  # nosec B311 -- deterministic sim, not crypto

    def _next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}_fake_{self.seed}_{self._counter:012d}"

    def issue(
        self,
        *,
        identity_ref: IdentityRef,
        target_identity_id: IdentityId,
        mechanism: DelegationMechanism,
        requested_duration_s: int,
        intended_capabilities: AuthoritySet,
        issued_at_ms: int,
    ) -> DelegationResult:
        """``identity_ref`` is built by the caller (``adapter._make_ref``),
        not here: the adapter is the single source of truth for what a
        namespaced reference looks like (SI-2) -- this store has no opinion
        on namespace at all."""
        granted_duration_s = requested_duration_s
        if mechanism in _CHAINED_MECHANISMS:
            granted_duration_s = min(granted_duration_s, CHAINED_ROLE_DURATION_CAP_S)
        granted_duration_s = min(granted_duration_s, self.max_session_duration_s)

        credential_id = self._next_id("cred")
        access_key_id = self._next_id("AKFAKE")
        secret = "".join(self._rng.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=40))
        token = "".join(self._rng.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=80))
        credential = TemporaryCredential(
            access_key_id=access_key_id,
            secret_access_key=secret,
            session_token=token,
            credential_id=credential_id,
        )

        issued_at = virtual_ms_to_datetime(issued_at_ms)
        expires_at = issued_at + timedelta(seconds=granted_duration_s)
        self._live[credential_id] = expires_at

        salt = f"fake-session:{self.seed}:"
        record = CredentialRecord(
            credential_id=credential_id,
            identity_id=target_identity_id,
            mechanism=mechanism,
            issued_at=issued_at,
            expires_at=expires_at,
            requested_duration_s=requested_duration_s,
            granted_duration_s=granted_duration_s,
            session_name_hash=credential.access_key_id_digest(salt + "session:"),
            access_key_id_hash=credential.access_key_id_digest(salt + "akid:"),
            scope_capabilities=intended_capabilities,
        )
        return DelegationResult(
            identity_ref=identity_ref,
            credential=credential,
            record=record,
            granted_capabilities=intended_capabilities,
        )

    def is_live(self, credential_id: str, *, at_ms: int) -> bool:
        expires_at = self._live.get(credential_id)
        if expires_at is None:
            return False
        return virtual_ms_to_datetime(at_ms) < expires_at

    def revoke(self, credential_id: str) -> None:
        self._live.pop(credential_id, None)
