"""The mutation choke point (AWS_PROVIDER_SPEC section 7): every controlled
policy change passes through :func:`apply_mutation`, in this exact order --
namespace assert, benchmark-agent assert, snapshot, send, read-after-write,
receipt. ``assert_role_is_benchmark_agent`` refuses ``bootstrap`` and
``principal`` (SI-12): a benchmark that can revoke its own ability to
observe produces garbage, the same invariant
``providers/fake/adapter.py::apply_policy_mutation`` already enforces for
the fake.

One named inline policy per purpose (``cb-deny`` for
attach/replace/session-oscillation, ``cb-grant`` for the baseline grant
Terraform (M9) provisions and this module's ``REMOVE_INLINE_POLICY`` deletes,
``cb-revoke-older`` for the token-issue-time pattern) rather than a
freshly-generated name per call, so ``ATTACH_INLINE_DENY`` followed by
another ``ATTACH_INLINE_DENY`` overwrites the same statement instead of
accumulating orphaned policies on the role.

``DELETE_SESSION_POLICY_SCOPE`` makes no AWS call at all (AWS_PROVIDER_SPEC
section 4's own table: "n/a -- re-delegate without the scope") -- the
harness-level behavior change of the *next* delegation is
``session.py``/``adapter.py``'s concern, not a policy mutation on the role
itself. Its receipt uses ``confirmation_method="api_ack_only"`` because
there is nothing to read back.
"""

from __future__ import annotations

import contextlib
import json
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import ClientError

from chainbreak.core.enums import MutationKind
from chainbreak.core.errors import MutationTargetForbiddenError
from chainbreak.core.ids import CapabilityId, IdentityId
from chainbreak.core.models import (
    AuthoritySet,
    MutationReceipt,
    PolicyMutation,
    ProviderCapabilityBinding,
)
from chainbreak.providers.aws.namespace import assert_aws_reference
from chainbreak.providers.aws.preflight import TerraformOutputs

DENY_POLICY_NAME = "cb-deny"
GRANT_POLICY_NAME = "cb-grant"
REVOKE_OLDER_POLICY_NAME = "cb-revoke-older"

_PROTECTED_ROLE_NAME_FRAGMENTS = ("bootstrap", "principal")

_READ_AFTER_WRITE_TIMEOUT_S = 10.0
_READ_AFTER_WRITE_INTERVAL_S = 0.5


def role_arn_for_identity(identity_id: IdentityId, outputs: TerraformOutputs) -> str:
    if identity_id == "principal":
        return outputs.principal_role_arn
    if identity_id == "bootstrap":
        return outputs.bootstrap_role_arn
    letter = identity_id.rsplit("-", 1)[-1]
    try:
        return outputs.agent_role_arns[letter]
    except KeyError:
        raise MutationTargetForbiddenError(
            f"unknown benchmark identity {identity_id!r}: no provisioned role",
            identity_id=identity_id,
        ) from None


def assert_role_is_benchmark_agent(role_arn: str) -> None:
    role_name = role_arn.rsplit("/", 1)[-1]
    for fragment in _PROTECTED_ROLE_NAME_FRAGMENTS:
        if fragment in role_name:
            raise MutationTargetForbiddenError(
                f"refuses to mutate protected identity role {role_name!r} (SI-12)",
                target_role=role_name,
            )


def _statement(
    *,
    sid: str,
    effect: str,
    actions: list[str],
    resources: list[str] | None = None,
    condition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """``resources=None`` omits the ``Resource`` field entirely -- required
    for trust-policy statements, which IAM rejects
    (``MalformedPolicyDocumentException: Has prohibited field Resource``) if
    one is present at all; identity/inline-policy statements always pass an
    explicit list."""
    statement: dict[str, Any] = {"Sid": sid, "Effect": effect, "Action": actions}
    if resources is not None:
        statement["Resource"] = resources
    if condition:
        statement["Condition"] = condition
    return statement


def _deny_document(
    denies: AuthoritySet, bindings: Mapping[CapabilityId, ProviderCapabilityBinding], namespace: str
) -> str:
    statements = [
        _statement(
            sid="CbDeny" if index == 0 else f"CbDeny{index}",
            effect="Deny",
            actions=list(bindings[cap_id].actions),
            resources=[bindings[cap_id].resource_template.format(namespace=namespace)],
        )
        for index, cap_id in enumerate(denies.sorted)
    ]
    return json.dumps({"Version": "2012-10-17", "Statement": statements}, separators=(",", ":"))


def _grant_document(
    grants: AuthoritySet, bindings: Mapping[CapabilityId, ProviderCapabilityBinding], namespace: str
) -> str:
    statements = [
        _statement(
            sid="CbGrant" if index == 0 else f"CbGrant{index}",
            effect="Allow",
            actions=list(bindings[cap_id].actions),
            resources=[bindings[cap_id].resource_template.format(namespace=namespace)],
        )
        for index, cap_id in enumerate(grants.sorted)
    ]
    return json.dumps({"Version": "2012-10-17", "Statement": statements}, separators=(",", ":"))


def _revoke_older_document(*, token_issue_cutoff: datetime) -> str:
    """The documented AWS session-revocation pattern (AWS_PROVIDER_SPEC
    section 4): deny everything to sessions whose token was issued before
    ``token_issue_cutoff`` -- existing sessions only, since a session issued
    after this mutation is applied has a later ``TokenIssueTime``."""
    statements = [
        _statement(
            sid="CbRevokeOlderSessions",
            effect="Deny",
            actions=["*"],
            resources=["*"],
            condition={"DateLessThan": {"aws:TokenIssueTime": token_issue_cutoff.isoformat()}},
        )
    ]
    return json.dumps({"Version": "2012-10-17", "Statement": statements}, separators=(",", ":"))


def _poll_until(
    fetch: Callable[[], Any],
    predicate: Callable[[Any], bool],
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[bool, float]:
    start = time.monotonic()
    while True:
        try:
            value = fetch()
        except ClientError:
            value = None
        if predicate(value):
            return True, (time.monotonic() - start) * 1000
        if time.monotonic() - start >= _READ_AFTER_WRITE_TIMEOUT_S:
            return False, (time.monotonic() - start) * 1000
        sleep(_READ_AFTER_WRITE_INTERVAL_S)


def apply_mutation(
    iam_client: Any,
    mutation: PolicyMutation,
    *,
    outputs: TerraformOutputs,
    bindings: Mapping[CapabilityId, ProviderCapabilityBinding],
    namespace: str,
    sleep: Callable[[float], None] = time.sleep,
) -> MutationReceipt:
    role_arn = role_arn_for_identity(mutation.target_identity, outputs)
    assert_aws_reference(role_arn, account_id=outputs.account_id, namespace=namespace)
    assert_role_is_benchmark_agent(role_arn)
    role_name = role_arn.rsplit("/", 1)[-1]

    monotonic_sent_ns = time.monotonic_ns()
    wall_sent = datetime.now(UTC)

    match mutation.kind:
        case MutationKind.ATTACH_INLINE_DENY:
            document = _deny_document(mutation.denies_capabilities, bindings, namespace)
            iam_client.put_role_policy(
                RoleName=role_name, PolicyName=DENY_POLICY_NAME, PolicyDocument=document
            )
            confirmed, latency_ms = _poll_until(
                lambda: iam_client.get_role_policy(RoleName=role_name, PolicyName=DENY_POLICY_NAME)[
                    "PolicyDocument"
                ],
                lambda doc: (
                    doc is not None
                    and json.dumps(doc, sort_keys=True)
                    == json.dumps(json.loads(document), sort_keys=True)
                ),
                sleep=sleep,
            )
        case MutationKind.REPLACE_INLINE_POLICY:
            document = _deny_document(mutation.denies_capabilities, bindings, namespace)
            if not mutation.grants_capabilities.is_empty():
                grant_doc = json.loads(
                    _grant_document(mutation.grants_capabilities, bindings, namespace)
                )
                document = json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [*json.loads(document)["Statement"], *grant_doc["Statement"]],
                    },
                    separators=(",", ":"),
                )
            iam_client.put_role_policy(
                RoleName=role_name, PolicyName=DENY_POLICY_NAME, PolicyDocument=document
            )
            confirmed, latency_ms = _poll_until(
                lambda: iam_client.get_role_policy(RoleName=role_name, PolicyName=DENY_POLICY_NAME)[
                    "PolicyDocument"
                ],
                lambda doc: doc is not None,
                sleep=sleep,
            )
        case MutationKind.REMOVE_INLINE_POLICY:
            # Already absent -- removing a grant that never existed is a
            # harmless no-op.
            with contextlib.suppress(ClientError):
                iam_client.delete_role_policy(RoleName=role_name, PolicyName=GRANT_POLICY_NAME)
            confirmed, latency_ms = _poll_until(
                lambda: _try_get_role_policy(iam_client, role_name, GRANT_POLICY_NAME),
                lambda doc: doc is None,
                sleep=sleep,
            )
        case MutationKind.UPDATE_TRUST_POLICY:
            current = iam_client.get_role(RoleName=role_name)["Role"]["AssumeRolePolicyDocument"]
            updated = {
                "Version": current.get("Version", "2012-10-17"),
                "Statement": [
                    *current.get("Statement", []),
                    _statement(
                        sid="CbRevokeFutureAssumeRole",
                        effect="Deny",
                        actions=["sts:AssumeRole"],
                    ),
                ],
            }
            iam_client.update_assume_role_policy(
                RoleName=role_name, PolicyDocument=json.dumps(updated, separators=(",", ":"))
            )
            confirmed, latency_ms = _poll_until(
                lambda: iam_client.get_role(RoleName=role_name)["Role"]["AssumeRolePolicyDocument"],
                lambda doc: (
                    doc is not None
                    and any(
                        s.get("Sid") == "CbRevokeFutureAssumeRole" for s in doc.get("Statement", [])
                    )
                ),
                sleep=sleep,
            )
        case MutationKind.REVOKE_OLDER_SESSIONS:
            document = _revoke_older_document(token_issue_cutoff=wall_sent)
            iam_client.put_role_policy(
                RoleName=role_name, PolicyName=REVOKE_OLDER_POLICY_NAME, PolicyDocument=document
            )
            confirmed, latency_ms = _poll_until(
                lambda: iam_client.get_role_policy(
                    RoleName=role_name, PolicyName=REVOKE_OLDER_POLICY_NAME
                )["PolicyDocument"],
                lambda doc: doc is not None,
                sleep=sleep,
            )
        case MutationKind.DELETE_SESSION_POLICY_SCOPE:
            return MutationReceipt(
                confirmed=True,
                confirmation_method="api_ack_only",
                confirmation_latency_ms=0.0,
                monotonic_sent_ns=monotonic_sent_ns,
                wall_sent=wall_sent,
            )

    return MutationReceipt(
        confirmed=confirmed,
        confirmation_method="read_after_write",
        confirmation_latency_ms=latency_ms,
        monotonic_sent_ns=monotonic_sent_ns,
        wall_sent=wall_sent,
    )


def _try_get_role_policy(iam_client: Any, role_name: str, policy_name: str) -> Any:
    try:
        return iam_client.get_role_policy(RoleName=role_name, PolicyName=policy_name)[
            "PolicyDocument"
        ]
    except ClientError:
        return None
