"""The ten capability probes (AWS_PROVIDER_SPEC section 6.2) and the
precondition verifiers that guard the two capabilities the 403/404 problem
would otherwise make unmeasurable (section 6.1).

Every probe function takes an already-constructed, already-hooked boto3
client (the agent's own session -- ``adapter.py``'s job to build) and
returns the **success-path** :class:`ProbeOutcome` only, letting
``botocore.exceptions.ClientError`` propagate uncaught. This is deliberate,
not an oversight: retry policy (``retry.py``) must wrap the *raw* AWS call
so a transient fault gets retried before anything is classified, and
:func:`classify_denial` (denial/error classification, applied once a final,
non-retryable exception is in hand) must run *after* retries are exhausted
-- if a probe function caught its own ``ClientError`` and returned an
``ERROR_INFRASTRUCTURE`` outcome internally, ``call_with_retry`` would never
see an exception to retry on at all, silently defeating retry for every
transient AWS fault. ``adapter.py`` is therefore the one place that wraps
each call with :func:`chainbreak.providers.aws.retry.call_with_retry` and
then, only on the final exception, calls :func:`classify_denial`.

``identity.whoami``'s probe needs no special casing under this structure --
it already lets its exception propagate like everything else. What is
special is what ``adapter.py`` does with that final exception: ordinary
failed ``GetCallerIdentity`` calls are not denials (IAM cannot deny them),
but an ``ExpiredToken`` is the expected expired-credential outcome in the
post-expiry stale-authority scenario, including its whoami control. Other
apparatus failures -- credentials, network, or endpoint faults -- still
abort rather than reporting a false denial, as required by
AWS_PROVIDER_SPEC section 6.2.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from botocore.exceptions import ClientError

from chainbreak.capabilities.preconditions import PreconditionRegistry
from chainbreak.core.enums import OutcomeClass
from chainbreak.core.models import IdentityRef, ProbeOutcome
from chainbreak.providers.aws import disambiguation
from chainbreak.providers.aws.preflight import TerraformOutputs
from chainbreak.providers.aws.retry import error_code, http_status

_AWS_ARN_RE = re.compile(r"arn:aws[a-zA-Z0-9-]*:[^\s]+")
_ACCOUNT_ID_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")


def _redact_aws_identifier_message(text: str) -> str:
    """Redact AWS identifiers before the evidence secret gate sees them."""
    text = _AWS_ARN_RE.sub("<REDACTED_ARN>", text)
    return _ACCOUNT_ID_RE.sub("<REDACTED_ACCOUNT>", text)


def classify_denial(exc: ClientError, *, path: str) -> ProbeOutcome:
    """Shared denial/error classification, applied by ``adapter.py`` to the
    final (post-retry) exception from any probe below.

    Not every ``ClientError`` is a denial (a name-not-found or malformed-
    request error is an infrastructure fault, not an authorization signal);
    only a recognized access-denied code goes through message-shape
    classification at all.
    """
    code = error_code(exc)
    status = http_status(exc)
    message = str(exc.response.get("Error", {}).get("Message", ""))

    if disambiguation.is_s3_object_missing(code, http_status=status):
        return ProbeOutcome(
            outcome_class=OutcomeClass.ERROR_INFRASTRUCTURE,
            provider_status_code=status,
            provider_error_code=code,
            message_redacted="object reported missing after precondition confirmed it exists",
            disambiguation_path=f"{path}:unexpected_missing_after_precondition",
        )
    if not disambiguation.is_access_denied_code(code):
        return ProbeOutcome(
            outcome_class=OutcomeClass.ERROR_INFRASTRUCTURE,
            provider_status_code=status,
            provider_error_code=code,
            message_redacted=_redact_aws_identifier_message(message),
            disambiguation_path=f"{path}:unexpected_error",
        )

    outcome_class, attribution = disambiguation.classify_denial_message(message)
    return ProbeOutcome(
        outcome_class=outcome_class,
        provider_status_code=status,
        provider_error_code=code,
        denial_attribution=attribution,
        message_redacted=_redact_aws_identifier_message(message),
        disambiguation_path=f"{path}:{outcome_class.value.lower()}",
    )


# ---------------------------------------------------------------------------
# Object storage
# ---------------------------------------------------------------------------


def probe_objectstore_read(s3_client: Any, *, outputs: TerraformOutputs) -> ProbeOutcome:
    response = s3_client.get_object(
        Bucket=outputs.objectstore_bucket, Key=outputs.objectstore_marker_key
    )
    body = response["Body"].read()
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    if digest == outputs.objectstore_marker_sha256:
        return ProbeOutcome(
            outcome_class=OutcomeClass.ALLOWED, disambiguation_path="content_verified"
        )
    return ProbeOutcome(
        outcome_class=OutcomeClass.ERROR_INFRASTRUCTURE,
        message_redacted="marker body digest did not match the expected value",
        disambiguation_path="objectstore.read:content_mismatch",
    )


def probe_objectstore_write(
    s3_client: Any, *, outputs: TerraformOutputs, run_id: str, probe_id: str, nonce: str
) -> ProbeOutcome:
    key = f"{outputs.namespace}/scratch/{run_id}/{probe_id}"
    s3_client.put_object(Bucket=outputs.objectstore_bucket, Key=key, Body=nonce.encode())
    s3_client.head_object(Bucket=outputs.objectstore_bucket, Key=key)
    return ProbeOutcome(outcome_class=OutcomeClass.ALLOWED, disambiguation_path="write_confirmed")


def probe_objectstore_list(s3_client: Any, *, outputs: TerraformOutputs) -> ProbeOutcome:
    prefix = f"{outputs.namespace}/markers/"
    response = s3_client.list_objects_v2(Bucket=outputs.objectstore_bucket, Prefix=prefix)
    if response.get("KeyCount", len(response.get("Contents", []))) >= 1:
        return ProbeOutcome(
            outcome_class=OutcomeClass.ALLOWED, disambiguation_path="prefix_nonempty"
        )
    return ProbeOutcome(
        outcome_class=OutcomeClass.ERROR_INFRASTRUCTURE,
        message_redacted="listing succeeded but returned zero keys despite the marker precondition",
        disambiguation_path="objectstore.list:unexpected_empty_after_precondition",
    )


# ---------------------------------------------------------------------------
# Key/value
# ---------------------------------------------------------------------------


def probe_keyvalue_read(dynamodb_client: Any, *, outputs: TerraformOutputs) -> ProbeOutcome:
    response = dynamodb_client.get_item(
        TableName=outputs.keyvalue_table,
        Key={"pk": {"S": outputs.keyvalue_marker_pk}},
        ConsistentRead=True,
    )
    item = response.get("Item")
    if item is None:
        return ProbeOutcome(
            outcome_class=OutcomeClass.ERROR_INFRASTRUCTURE,
            message_redacted="marker item missing despite the marker precondition",
            disambiguation_path="keyvalue.read:unexpected_missing_after_precondition",
        )
    digest = item.get("digest", {}).get("S")
    if digest == outputs.keyvalue_marker_sha256:
        return ProbeOutcome(
            outcome_class=OutcomeClass.ALLOWED, disambiguation_path="content_verified"
        )
    return ProbeOutcome(
        outcome_class=OutcomeClass.ERROR_INFRASTRUCTURE,
        message_redacted="marker item digest did not match the expected value",
        disambiguation_path="keyvalue.read:content_mismatch",
    )


def probe_keyvalue_write(
    dynamodb_client: Any, *, outputs: TerraformOutputs, run_id: str, probe_id: str, nonce: str
) -> ProbeOutcome:
    pk = f"cb-scratch#{run_id}#{probe_id}"
    dynamodb_client.put_item(
        TableName=outputs.keyvalue_table, Item={"pk": {"S": pk}, "value": {"S": nonce}}
    )
    dynamodb_client.get_item(
        TableName=outputs.keyvalue_table, Key={"pk": {"S": pk}}, ConsistentRead=True
    )
    return ProbeOutcome(outcome_class=OutcomeClass.ALLOWED, disambiguation_path="write_confirmed")


# ---------------------------------------------------------------------------
# Compute / queue
# ---------------------------------------------------------------------------


def probe_function_invoke(lambda_client: Any, *, outputs: TerraformOutputs) -> ProbeOutcome:
    """The deployed function performs no work and returns a **fixed** payload
    (``{"ok": true, "nonce": <namespace>}`` -- the capability catalog's own
    description, ``capabilities/catalog.yaml``'s ``function.invoke`` entry:
    "returns a fixed payload containing a nonce", and
    ``infra/terraform/modules/resources/CONTRACT.md`` names the namespace as
    that fixed value). The probe sends no meaningful payload and does not
    echo one back -- there is nothing per-call to echo."""
    response = lambda_client.invoke(
        FunctionName=outputs.function_name, InvocationType="RequestResponse", Payload=b"{}"
    )
    if disambiguation.is_lambda_function_fault(response.get("FunctionError")):
        return ProbeOutcome(
            outcome_class=OutcomeClass.ERROR_INFRASTRUCTURE,
            message_redacted="invoked function raised (FunctionError set) -- a fault, not a denial",
            disambiguation_path="function.invoke:function_fault",
        )
    payload = json.loads(response["Payload"].read())
    if payload.get("ok") is True and payload.get("nonce") == outputs.namespace:
        return ProbeOutcome(
            outcome_class=OutcomeClass.ALLOWED, disambiguation_path="payload_verified"
        )
    return ProbeOutcome(
        outcome_class=OutcomeClass.ERROR_INFRASTRUCTURE,
        message_redacted="function returned an unexpected payload shape",
        disambiguation_path="function.invoke:unexpected_payload",
    )


def probe_queue_send(sqs_client: Any, *, outputs: TerraformOutputs, nonce: str) -> ProbeOutcome:
    response = sqs_client.send_message(QueueUrl=outputs.queue_url, MessageBody=nonce)
    if response.get("MessageId"):
        return ProbeOutcome(
            outcome_class=OutcomeClass.ALLOWED, disambiguation_path="message_id_returned"
        )
    return ProbeOutcome(  # pragma: no cover -- SQS always returns MessageId on success
        outcome_class=OutcomeClass.ERROR_INFRASTRUCTURE,
        message_redacted="send succeeded but returned no MessageId",
        disambiguation_path="queue.send:missing_message_id",
    )


def probe_queue_receive(sqs_client: Any, *, outputs: TerraformOutputs) -> ProbeOutcome:
    sqs_client.receive_message(
        QueueUrl=outputs.queue_url, VisibilityTimeout=0, MaxNumberOfMessages=1
    )
    # An empty receive still proves authority (AWS_PROVIDER_SPEC section 6.2)
    # -- the API call itself succeeding is the whole signal. Do not require
    # a message to be present.
    return ProbeOutcome(outcome_class=OutcomeClass.ALLOWED, disambiguation_path="receive_succeeded")


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def probe_identity_whoami(sts_client: Any) -> ProbeOutcome:
    response = sts_client.get_caller_identity()
    return ProbeOutcome(
        outcome_class=OutcomeClass.ALLOWED,
        disambiguation_path="control_capability",
        message_redacted=_redact_aws_identifier_message(response["Arn"]),
    )


def probe_identity_delegate(
    sts_client: Any, *, next_hop_role_arn: str | None, external_id: str, session_name: str
) -> ProbeOutcome:
    if next_hop_role_arn is None:
        return ProbeOutcome(
            outcome_class=OutcomeClass.ERROR_INFRASTRUCTURE,
            message_redacted="no further hop in the fixed six-role agent chain to probe against",
            disambiguation_path="identity.delegate:no_next_hop",
        )
    # ``session_name`` must satisfy the next hop's trust-policy
    # ``StringLike: sts:RoleSessionName = "${namespace}-*"`` condition
    # (identities/main.tf) -- a literal, non-namespaced name is refused at
    # the trust-policy layer before the identity policy is even consulted,
    # confirmed empirically against a real account: caller
    # (``adapter.py``) must build this with ``session.build_session_name``,
    # the same helper every other AssumeRole call site already uses.
    sts_client.assume_role(
        RoleArn=next_hop_role_arn,
        RoleSessionName=session_name,
        DurationSeconds=900,
        ExternalId=external_id,
    )
    return ProbeOutcome(
        outcome_class=OutcomeClass.ALLOWED, disambiguation_path="assume_role_succeeded"
    )


# ---------------------------------------------------------------------------
# Preconditions (AWS_PROVIDER_SPEC section 6.1, F6)
# ---------------------------------------------------------------------------


def _object_marker_present(s3_client: Any, outputs: TerraformOutputs) -> bool:
    try:
        s3_client.head_object(Bucket=outputs.objectstore_bucket, Key=outputs.objectstore_marker_key)
    except ClientError:
        return False
    return True


def _keyvalue_marker_present(dynamodb_client: Any, outputs: TerraformOutputs) -> bool:
    try:
        response = dynamodb_client.get_item(
            TableName=outputs.keyvalue_table,
            Key={"pk": {"S": outputs.keyvalue_marker_pk}},
            ConsistentRead=True,
        )
    except ClientError:
        return False
    return "Item" in response


def _function_alive(lambda_client: Any, outputs: TerraformOutputs) -> bool:
    try:
        lambda_client.get_function(FunctionName=outputs.function_name)
    except ClientError:
        return False
    return True


def _queue_present(sqs_client: Any, outputs: TerraformOutputs) -> bool:
    try:
        sqs_client.get_queue_attributes(QueueUrl=outputs.queue_url, AttributeNames=["QueueArn"])
    except ClientError:
        return False
    return True


def build_aws_preconditions(
    *,
    s3_client: Any,
    dynamodb_client: Any,
    lambda_client: Any,
    sqs_client: Any,
    outputs: TerraformOutputs,
) -> PreconditionRegistry:
    """All four verifiers are called with the **bootstrap** identity's own
    clients (F6) -- the caller (``adapter.py``) is responsible for that;
    this function has no opinion on whose credentials the clients hold."""
    registry = PreconditionRegistry()
    registry.register(
        "objectstore.marker_present",
        lambda _ref: _object_marker_present(s3_client, outputs),
    )
    registry.register(
        "keyvalue.marker_present",
        lambda _ref: _keyvalue_marker_present(dynamodb_client, outputs),
    )
    registry.register("function.alive", lambda _ref: _function_alive(lambda_client, outputs))
    registry.register("queue.present", lambda _ref: _queue_present(sqs_client, outputs))
    return registry


def verify_all_preconditions(
    registry: PreconditionRegistry, provisioning_identity: IdentityRef
) -> Mapping[str, bool]:
    return registry.verify_all(
        (
            "objectstore.marker_present",
            "keyvalue.marker_present",
            "function.alive",
            "queue.present",
        ),
        provisioning_identity,
    )
