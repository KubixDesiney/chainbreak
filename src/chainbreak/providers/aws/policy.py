"""``snapshot_policy_state`` (AWS_PROVIDER_SPEC section 7): fingerprints every
inline policy and the trust policy currently attached to a role, so a
before/after comparison (``PolicyStateSnapshot.differs_from``) can detect
that a mutation actually changed something on the role, independent of
whether the mutation's own read-after-write poll settled in time.

Deliberately reads *all* inline policy names on the role via
``list_role_policies`` rather than only the three this adapter's own
``mutation.py`` writes (``cb-deny``/``cb-grant``/``cb-revoke-older``):
Terraform (M9) may attach its own baseline inline policy expressing a
scenario's intended capabilities, and a snapshot that only looked at
mutation-owned policy names would miss a change to that baseline policy --
exactly the kind of blind spot AUTHORIZATION_MODEL.md's empirical-probing
philosophy (ADR-009) exists to avoid.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from chainbreak.core.enums import PolicyKind
from chainbreak.core.ids import IdentityId, digest_ref
from chainbreak.core.models import PolicyFingerprint, PolicyStateSnapshot
from chainbreak.providers.aws.mutation import role_arn_for_identity
from chainbreak.providers.aws.preflight import TerraformOutputs

_snapshot_counter = 0


def _document_fingerprint(document: dict[str, Any]) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def _has_explicit_deny(document: dict[str, Any]) -> bool:
    return any(statement.get("Effect") == "Deny" for statement in document.get("Statement", []))


def snapshot_policy_state(
    iam_client: Any,
    identity_id: IdentityId,
    *,
    outputs: TerraformOutputs,
    salt: str,
    now_ns: int,
) -> PolicyStateSnapshot:
    global _snapshot_counter
    role_arn = role_arn_for_identity(identity_id, outputs)
    role_name = role_arn.rsplit("/", 1)[-1]

    fingerprints: list[PolicyFingerprint] = []

    inline_names = iam_client.list_role_policies(RoleName=role_name)["PolicyNames"]
    for name in sorted(inline_names):
        document = iam_client.get_role_policy(RoleName=role_name, PolicyName=name)["PolicyDocument"]
        fingerprints.append(
            PolicyFingerprint(
                policy_kind=PolicyKind.IDENTITY_INLINE,
                name_hash=digest_ref(name, salt),
                document_sha256=_document_fingerprint(document),
                statement_count=len(document.get("Statement", [])),
                has_explicit_deny=_has_explicit_deny(document),
            )
        )

    trust_document = iam_client.get_role(RoleName=role_name)["Role"]["AssumeRolePolicyDocument"]
    fingerprints.append(
        PolicyFingerprint(
            policy_kind=PolicyKind.TRUST,
            name_hash=digest_ref(f"{role_name}:trust", salt),
            document_sha256=_document_fingerprint(trust_document),
            statement_count=len(trust_document.get("Statement", [])),
            has_explicit_deny=_has_explicit_deny(trust_document),
        )
    )

    _snapshot_counter += 1
    return PolicyStateSnapshot(
        snapshot_id=f"snap_aws_{outputs.namespace}_{_snapshot_counter:012d}",
        identity_id=identity_id,
        taken_at=datetime.now(UTC),
        monotonic_ns=now_ns,
        policies=tuple(fingerprints),
    )
