"""STS delegation (AWS_PROVIDER_SPEC section 4): issuing a real, temporary
credential for each of the five supported mechanisms.

**The 3600s chaining cap is applied before calling STS, not read off its
response.** AWS_PROVIDER_SPEC's own table says a longer ``ROLE_CHAIN``
request "is rejected"; its prose says the effect is "silently satisfied with
less." Both are true from different vantage points: this module is the
thing doing the silent satisfying -- it computes ``granted_duration_s =
min(requested, 3600)`` *before* the call and requests exactly that, so STS
never sees (and never has occasion to reject) an over-long chained request.
The scenario author's requested duration and the granted one are both kept
on the resulting :class:`CredentialRecord`, so ``LIFETIME_CAPPED`` is a
comparison of two recorded numbers, not an AWS error to interpret -- exactly
the precedent ``providers/fake/session.py`` already set.

``RESOURCE_POLICY_GRANT`` mints a plain, unscoped credential like
``DIRECT_ROLE_ASSUMPTION``: what makes that mechanism interesting is a
resource-based policy granting the assumed role authority its own identity
policy would not (AWS_PROVIDER_SPEC section 4's documented asymmetry), which
a later *probe* reveals, not something delegation itself does differently.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import boto3

from chainbreak.core.enums import DelegationMechanism
from chainbreak.core.ids import CapabilityId, IdentityId, new_ulid
from chainbreak.core.models import (
    EMPTY_AUTHORITY,
    AuthoritySet,
    CredentialRecord,
    IdentityRef,
    ProviderCapabilityBinding,
)
from chainbreak.core.secrets import TemporaryCredential
from chainbreak.providers.aws.policy_synthesis import synthesize_session_policy
from chainbreak.providers.base.types import DelegationResult

#: AWS's own undocumented-in-any-API-response chained-role cap.
CHAINED_ROLE_DURATION_CAP_S = 3600

#: RoleSessionName has a 64-character hard limit; trust policies (AWS_PROVIDER_SPEC
#: section 3) require the ``cb-{ns}-*`` prefix so every session is CloudTrail-identifiable.
_MAX_SESSION_NAME_LENGTH = 64

_CHAINED_MECHANISMS = frozenset(
    {DelegationMechanism.ROLE_CHAIN, DelegationMechanism.ROLE_CHAIN_WITH_SESSION_POLICY}
)
_SCOPED_MECHANISMS = frozenset(
    {DelegationMechanism.SESSION_POLICY_SCOPED, DelegationMechanism.ROLE_CHAIN_WITH_SESSION_POLICY}
)


def build_session_name(namespace: str, target_identity_id: str) -> str:
    # ``namespace`` already carries its own "cb-" prefix (e.g. "cb-a1b2c3d4"),
    # which is what satisfies the trust policy's ``StringLike``
    # ``sts:RoleSessionName": "cb-${ns}-*"`` condition (AWS_PROVIDER_SPEC
    # section 3) -- no second, literal "cb-" is added here.
    suffix = new_ulid()[:12]
    name = f"{namespace}-{target_identity_id}-{suffix}"
    return name[:_MAX_SESSION_NAME_LENGTH]


def _policy_fingerprint(policy_json: str) -> str:
    return "sha256:" + hashlib.sha256(policy_json.encode()).hexdigest()


def assume_role(
    sts_client: Any,
    *,
    role_arn: str,
    session_name: str,
    external_id: str,
    requested_duration_s: int,
    mechanism: DelegationMechanism,
    intended_capabilities: AuthoritySet,
    bindings: Mapping[CapabilityId, ProviderCapabilityBinding],
    namespace: str,
    target_identity_id: IdentityId,
    identity_ref: IdentityRef,
    credential_id: str,
    salt: str,
) -> DelegationResult:
    """Call ``sts:AssumeRole`` for one delegation edge and return a
    :class:`DelegationResult` carrying the live credential plus its
    metadata-only :class:`CredentialRecord` (EV-1: no secret in the record).
    """
    granted_duration_s = requested_duration_s
    if mechanism in _CHAINED_MECHANISMS:
        granted_duration_s = min(granted_duration_s, CHAINED_ROLE_DURATION_CAP_S)

    kwargs: dict[str, Any] = {
        "RoleArn": role_arn,
        "RoleSessionName": session_name,
        "DurationSeconds": granted_duration_s,
        "ExternalId": external_id,
    }

    session_policy_fingerprint: str | None = None
    scope_capabilities = EMPTY_AUTHORITY
    if mechanism in _SCOPED_MECHANISMS:
        policy_json = synthesize_session_policy(
            intended_capabilities, bindings, namespace=namespace
        )
        kwargs["Policy"] = policy_json
        session_policy_fingerprint = _policy_fingerprint(policy_json)
        scope_capabilities = intended_capabilities

    response = sts_client.assume_role(**kwargs)
    creds = response["Credentials"]
    expiration: datetime = creds["Expiration"]
    if expiration.tzinfo is None:  # pragma: no cover -- defensive; botocore always returns tz-aware
        expiration = expiration.replace(tzinfo=UTC)

    credential = TemporaryCredential(
        access_key_id=creds["AccessKeyId"],
        secret_access_key=creds["SecretAccessKey"],
        session_token=creds["SessionToken"],
        credential_id=credential_id,
    )

    record = CredentialRecord(
        credential_id=credential_id,
        identity_id=target_identity_id,
        mechanism=mechanism,
        issued_at=datetime.now(UTC),
        expires_at=expiration,
        requested_duration_s=requested_duration_s,
        granted_duration_s=granted_duration_s,
        session_name_hash=credential.access_key_id_digest(salt + "session:"),
        access_key_id_hash=credential.access_key_id_digest(salt + "akid:"),
        session_policy_fingerprint=session_policy_fingerprint,
        scope_capabilities=scope_capabilities,
    )
    return DelegationResult(
        identity_ref=identity_ref,
        credential=credential,
        record=record,
        granted_capabilities=intended_capabilities,
    )


def boto3_session_from_credential(credential: TemporaryCredential, *, region: str) -> boto3.Session:
    """The one authorized call site (with ``TemporaryCredential.__init__``
    itself) that ever calls ``.reveal()`` on secret material (SI-1 --
    ``core/secrets.py``'s own docstring names "the AWS and fake session
    builders" as the exhaustive list): a live ``boto3.Session`` is the only
    thing the adapter can hand the *next* hop's own calls, and boto3's own
    API requires the raw strings at this one boundary. The session object
    itself is never serialized, logged, or written to evidence."""
    return boto3.Session(
        aws_access_key_id=credential.access_key_id,
        aws_secret_access_key=credential.secret_access_key.reveal(),
        aws_session_token=credential.session_token.reveal(),
        region_name=region,
    )
