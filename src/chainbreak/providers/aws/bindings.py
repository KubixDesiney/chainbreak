"""Real AWS bindings for every catalog capability (AWS_PROVIDER_SPEC section
6.2's probe table). Mirrors ``providers/fake/bindings.py``'s one-binding-per-
capability shape, but ``resource_template`` here is a real ARN with the
account id and region already baked in from Terraform outputs at
construction time -- only the literal substring ``{namespace}`` survives for
the later ``.format(namespace=...)`` call every adapter (fake or AWS) makes
in ``probe()`` (SI-2).

``objectstore.write``/``keyvalue.write`` each declare **two** actions
(``PutObject``+``HeadObject``, ``PutItem``+``GetItem``) because
AWS_PROVIDER_SPEC's probe table requires content confirmation after the
write, and ``OperationAllowlist`` (SI-3) must see both calls as
binding-declared, not a broadening.

The fixed physical agent chain (``agent-a`` through ``agent-f``, section 3:
"Six are provisioned so scenarios up to depth 6 need no re-apply") is a
property of the *provisioned infrastructure*, not any one scenario's logical
graph -- ``identity.delegate``'s real probe target (the next hop's role ARN)
is therefore resolved from this static chain, not from ``resource_template``,
which stays a namespace-scoped wildcard here since the concrete ARN depends
on which identity is being probed (``probes.py::next_hop_role_arn``).
"""

from __future__ import annotations

from chainbreak.core.enums import Provider
from chainbreak.core.models import CapabilityCatalog, ProviderCapabilityBinding

#: The physical Terraform-provisioned agent role chain (AWS_PROVIDER_SPEC
#: section 3). Independent of any scenario's logical identity graph.
AGENT_CHAIN: tuple[str, ...] = ("agent-a", "agent-b", "agent-c", "agent-d", "agent-e", "agent-f")

_ACTIONS: dict[str, tuple[str, ...]] = {
    "objectstore.read": ("s3:GetObject",),
    # HeadObject (the write-confirmation call) requires the *same* IAM
    # action as GetObject -- S3 defines no separate s3:HeadObject action.
    "objectstore.write": ("s3:PutObject", "s3:GetObject"),
    # ListObjectsV2 (the operation) requires s3:ListBucket (the IAM
    # action) -- S3's operation and IAM action names diverge here.
    "objectstore.list": ("s3:ListBucket",),
    "keyvalue.read": ("dynamodb:GetItem",),
    "keyvalue.write": ("dynamodb:PutItem", "dynamodb:GetItem"),
    "function.invoke": ("lambda:InvokeFunction",),
    "queue.send": ("sqs:SendMessage",),
    "queue.receive": ("sqs:ReceiveMessage",),
    "identity.whoami": ("sts:GetCallerIdentity",),
    "identity.delegate": ("sts:AssumeRole",),
}


def _resource_template(capability_id: str, *, account_id: str, region: str) -> str:
    # ``{namespace}`` (later substituted from a real ``Namespace``-typed
    # value, e.g. "cb-a1b2c3d4") already carries its own "cb-" prefix --
    # AWS_PROVIDER_SPEC section 8's own namespace generation bakes it in
    # (``namespace = "cb-" + substr(...)``). None of these templates add a
    # second, literal "cb-" of their own.
    match capability_id:
        case "objectstore.read":
            return "arn:aws:s3:::{namespace}-objectstore/{namespace}/markers/marker.json"
        case "objectstore.write":
            return "arn:aws:s3:::{namespace}-objectstore/{namespace}/scratch/*"
        case "objectstore.list":
            return "arn:aws:s3:::{namespace}-objectstore"
        case "keyvalue.read" | "keyvalue.write":
            return f"arn:aws:dynamodb:{region}:{account_id}:table/{{namespace}}-keyvalue"
        case "function.invoke":
            return f"arn:aws:lambda:{region}:{account_id}:function:{{namespace}}-noop"
        case "queue.send" | "queue.receive":
            return f"arn:aws:sqs:{region}:{account_id}:{{namespace}}-queue"
        case "identity.whoami":
            # No specific resource -- sts:GetCallerIdentity is never denied by
            # an identity policy (the control capability). Namespace-scoped so
            # SI-2's assertion still has a substring to find.
            return f"arn:aws:iam::{account_id}:role/{{namespace}}-*"
        case "identity.delegate":
            # The concrete target (next hop's role ARN) depends on which
            # identity is being probed -- resolved dynamically by
            # ``probes.py::next_hop_role_arn``, not by this template.
            return f"arn:aws:iam::{account_id}:role/{{namespace}}-agent-*"
        case _:  # pragma: no cover -- defensive; every catalog id is handled above
            raise KeyError(f"no AWS resource template for {capability_id!r}")


def build_aws_bindings(
    catalog: CapabilityCatalog, *, account_id: str, region: str
) -> tuple[ProviderCapabilityBinding, ...]:
    return tuple(
        ProviderCapabilityBinding(
            capability_id=capability.id,
            provider=Provider.AWS,
            actions=_ACTIONS[capability.id],
            resource_template=_resource_template(
                capability.id, account_id=account_id, region=region
            ),
            probe_kind=capability.probe_kind,
            preconditions=capability.requires_precondition,
        )
        for capability in catalog.capabilities
    )


def next_hop_role_arn(identity_id: str, *, account_id: str, namespace: str) -> str | None:
    """The next role in the fixed physical agent chain, or ``None`` if
    ``identity_id`` is ``principal`` (whose next hop is ``agent-a``),
    ``bootstrap`` (never a chain member), or the chain's final link
    (``agent-f`` has no further hop to probe -- a real, documented
    limitation of the six-role provisioning, not a bug)."""
    if identity_id == "principal":
        return f"arn:aws:iam::{account_id}:role/{namespace}-agent-a"
    if identity_id not in AGENT_CHAIN:
        return None
    index = AGENT_CHAIN.index(identity_id)
    if index + 1 >= len(AGENT_CHAIN):
        return None
    return f"arn:aws:iam::{account_id}:role/{namespace}-{AGENT_CHAIN[index + 1]}"
