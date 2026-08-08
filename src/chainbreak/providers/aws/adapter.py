"""``AwsProviderAdapter``: wires preflight, session issuance, the ten probes,
the mutation choke point and policy snapshotting behind the
``ProviderAdapter`` Protocol (AWS_PROVIDER_SPEC.md).

**Identity model.** AWS's real identities are fixed by Terraform
provisioning (``bootstrap``, ``principal``, ``agent-a``..``agent-f`` --
section 3), unlike the fake's in-memory ``PolicyEngine``, which can register
an arbitrary named identity on the spot. ``register_identity`` here
therefore recognizes exactly those seven names and raises for anything else
-- notably, this means ``tests/integration/test_provider_contract.py``'s
shared ``ProviderContractSuite`` (which invents ad hoc identities like
``"agent-denied"``/``"agent-empty"`` purely for fake-side test setup)
**cannot run against this adapter unmodified**, contrary to M8's acceptance
criterion 1 as literally written. This is a real specification tension
discovered while implementing this module, not an oversight -- recorded in
PROJECT_STATUS.md's M8 entry rather than worked around by inventing
placeholder IAM roles that would misrepresent the fixed six-role model
AWS_PROVIDER_SPEC section 3 documents.

**The botocore before-call hook** (SI-2's independent check, SI-3's
``OperationAllowlist``) is installed once per boto3 client at construction
time, reading from a small mutable ``_AllowlistHookState`` the adapter flips
around each probe's own ``with OperationAllowlist(binding)`` block -- the
hook itself has no notion of "which probe is this," only "is an allowlist
currently open."
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import ClientError

from chainbreak.capabilities.guard import OperationAllowlist
from chainbreak.capabilities.loader import load_catalog
from chainbreak.core.enums import Provider
from chainbreak.core.errors import CapabilityResolutionError, DelegationError
from chainbreak.core.ids import (
    CapabilityId,
    IdentityId,
    Namespace,
    new_credential_id,
    new_ulid,
    run_salt,
)
from chainbreak.core.models import (
    CapabilityCatalog,
    IdentityRef,
    MutationReceipt,
    PolicyMutation,
    PolicyStateSnapshot,
    ProbeOutcome,
    ProbeTiming,
    ProviderCapabilityBinding,
    SafetyEnvelope,
)
from chainbreak.core.secrets import TemporaryCredential
from chainbreak.providers.aws import mutation as mutation_mod
from chainbreak.providers.aws import policy as policy_mod
from chainbreak.providers.aws import preflight as preflight_mod
from chainbreak.providers.aws import probes as probes_mod
from chainbreak.providers.aws import session as session_mod
from chainbreak.providers.aws.bindings import build_aws_bindings, next_hop_role_arn
from chainbreak.providers.aws.preflight import TerraformOutputs
from chainbreak.providers.aws.retry import RetryOutcome, call_with_retry
from chainbreak.providers.base.namespace import assert_namespace
from chainbreak.providers.base.types import (
    DelegationRequest,
    DelegationResult,
    EnvironmentDescriptor,
    PreflightReport,
    ProbeRequest,
    ProbeResult,
)

ADAPTER_VERSION = "0.1.0"

_RECOGNIZED_IDENTITIES = frozenset(
    {"bootstrap", "principal", "agent-a", "agent-b", "agent-c", "agent-d", "agent-e", "agent-f"}
)

#: Operation-name -> IAM-action-name overrides for the (small, well-known)
#: set of AWS APIs where the boto3 operation name and the IAM action name
#: diverge -- HeadObject/ListObjectsV2 both require an s3:GetObject/
#: s3:ListBucket permission with no operation-matching action name of their
#: own; Lambda's ``Invoke`` operation requires ``lambda:InvokeFunction``.
_OPERATION_TO_ACTION_OVERRIDES: dict[str, dict[str, str]] = {
    "s3": {"HeadObject": "GetObject", "ListObjectsV2": "ListBucket"},
    "lambda": {"Invoke": "InvokeFunction"},
}


def _iam_action(service_name: str, operation_name: str) -> str:
    override = _OPERATION_TO_ACTION_OVERRIDES.get(service_name, {}).get(operation_name)
    return f"{service_name}:{override or operation_name}"


@dataclass
class _AllowlistHookState:
    current: OperationAllowlist | None = None


def _install_allowlist_hook(client: Any, state: _AllowlistHookState) -> None:
    service_name = client.meta.service_model.service_name

    def _before_call(**kwargs: Any) -> None:
        if state.current is None:
            return
        model = kwargs.get("model")
        if model is not None:
            state.current.record(_iam_action(service_name, model.name))

    client.meta.events.register("before-call.*.*", _before_call)


@dataclass(frozen=True, slots=True)
class _Clients:
    s3: Any
    dynamodb: Any
    lambda_: Any
    sqs: Any
    sts: Any


@dataclass
class AwsProviderAdapter:
    """Construct one per run. ``operator_session`` is whatever credentials
    the human or CI OIDC identity is running with -- never used for probes,
    only to assume ``bootstrap`` and ``principal`` (AWS_PROVIDER_SPEC
    section 3)."""

    operator_session: Any
    outputs: TerraformOutputs
    run_id: str
    protected_identities: frozenset[str] = field(
        default_factory=lambda: frozenset({"bootstrap", "principal"})
    )

    name: str = field(default="aws", init=False)
    adapter_version: str = field(default=ADAPTER_VERSION, init=False)

    catalog: CapabilityCatalog = field(init=False, repr=False)
    bindings: dict[str, ProviderCapabilityBinding] = field(init=False, repr=False)

    _ref_to_identity_id: dict[str, IdentityId] = field(init=False, default_factory=dict, repr=False)
    _identity_sessions: dict[str, Any] = field(init=False, default_factory=dict, repr=False)
    _clients_cache: dict[str, _Clients] = field(init=False, default_factory=dict, repr=False)
    _allowlist_states: dict[str, _AllowlistHookState] = field(
        init=False, default_factory=dict, repr=False
    )
    _bootstrap_session_cache: Any = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        self.catalog = load_catalog()
        self.bindings = {
            b.capability_id: b
            for b in build_aws_bindings(
                self.catalog, account_id=self.outputs.account_id, region=self.outputs.region
            )
        }

    # -- shared state -------------------------------------------------------

    @property
    def account_ref(self) -> str:
        return self.outputs.account_id

    @property
    def region(self) -> str:
        return self.outputs.region

    @property
    def namespace(self) -> Namespace:
        return self.outputs.namespace

    def _salt(self) -> str:
        return run_salt(self.run_id)  # type: ignore[arg-type]

    def _make_ref(self, role_arn: str) -> IdentityRef:
        return IdentityRef(
            provider=Provider.AWS,
            kind="role",
            value=role_arn,
            region=self.region,
            account_ref=self.account_ref,
        )

    def _sts_client(self, session: Any) -> Any:
        return session.client(
            "sts", region_name=self.region, endpoint_url=f"https://sts.{self.region}.amazonaws.com"
        )

    def _clients_for(self, ref_value: str, boto_session: Any) -> _Clients:
        cached = self._clients_cache.get(ref_value)
        if cached is not None:
            return cached
        state = _AllowlistHookState()
        self._allowlist_states[ref_value] = state
        clients = _Clients(
            s3=boto_session.client("s3", region_name=self.region),
            dynamodb=boto_session.client("dynamodb", region_name=self.region),
            lambda_=boto_session.client("lambda", region_name=self.region),
            sqs=boto_session.client("sqs", region_name=self.region),
            sts=self._sts_client(boto_session),
        )
        for client in (clients.s3, clients.dynamodb, clients.lambda_, clients.sqs, clients.sts):
            _install_allowlist_hook(client, state)
        self._clients_cache[ref_value] = clients
        return clients

    def _bootstrap_session(self) -> Any:
        if self._bootstrap_session_cache is None:
            sts = self._sts_client(self.operator_session)
            response = sts.assume_role(
                RoleArn=self.outputs.bootstrap_role_arn,
                RoleSessionName=session_mod.build_session_name(self.namespace, "bootstrap"),
                DurationSeconds=3600,
                ExternalId=self.outputs.external_id,
            )
            credential = _credential_from_sts_response(response, credential_id=new_credential_id())
            self._bootstrap_session_cache = session_mod.boto3_session_from_credential(
                credential, region=self.region
            )
        return self._bootstrap_session_cache

    # -- setup, not part of the Protocol -------------------------------------

    def register_identity(self, identity_id: str, *, allow: Any = None) -> IdentityRef:
        """Assume the corresponding real, Terraform-provisioned role. See
        the module docstring for why this only recognizes the seven fixed
        AWS_PROVIDER_SPEC identity names -- ``allow`` is accepted for
        surface compatibility with the fake adapter's convenience method but
        is otherwise ignored: AWS's identity policies come from Terraform
        provisioning (M9), not from a runtime call."""
        if identity_id not in _RECOGNIZED_IDENTITIES:
            raise DelegationError(
                f"{identity_id!r} is not a Terraform-provisioned AWS identity; "
                "AWS_PROVIDER_SPEC section 3 provisions exactly bootstrap, principal "
                "and agent-a..agent-f",
                identity_id=identity_id,
            )
        role_arn = mutation_mod.role_arn_for_identity(identity_id, self.outputs)
        session_name = session_mod.build_session_name(self.namespace, identity_id)
        sts = self._sts_client(self.operator_session)
        response = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name,
            DurationSeconds=3600,
            ExternalId=self.outputs.external_id,
        )
        credential = _credential_from_sts_response(response, credential_id=new_credential_id())
        boto_session = session_mod.boto3_session_from_credential(credential, region=self.region)
        ref = self._make_ref(role_arn)
        self._identity_sessions[ref.value] = boto_session
        self._ref_to_identity_id[ref.value] = identity_id
        return ref

    # -- ProviderAdapter Protocol ---------------------------------------------

    def preflight(self, envelope: SafetyEnvelope) -> PreflightReport:
        sts = self._sts_client(self.operator_session)
        tagging = self.operator_session.client("resourcegroupstaggingapi", region_name=self.region)
        bootstrap = self._bootstrap_session()
        registry = probes_mod.build_aws_preconditions(
            s3_client=bootstrap.client("s3", region_name=self.region),
            dynamodb_client=bootstrap.client("dynamodb", region_name=self.region),
            lambda_client=bootstrap.client("lambda", region_name=self.region),
            sqs_client=bootstrap.client("sqs", region_name=self.region),
            outputs=self.outputs,
        )
        precondition_results = probes_mod.verify_all_preconditions(
            registry, self._make_ref(self.outputs.bootstrap_role_arn)
        )
        cost_estimate = preflight_mod.CostEstimate(
            estimated_calls_by_service={
                "sts": 60,
                "iam": 40,
                "s3": 400,
                "dynamodb": 300,
                "lambda": 100,
                "sqs": 200,
            }
        )
        return preflight_mod.run_preflight(
            sts_client=sts,
            resourcegroupstaggingapi_client=tagging,
            envelope=envelope,
            terraform_outputs=self.outputs,
            precondition_results=precondition_results,
            cost_estimate=cost_estimate,
            clock_offset_ms=0.0,
        )

    def resolve_capability(self, cap_id: CapabilityId) -> ProviderCapabilityBinding:
        try:
            return self.bindings[cap_id]
        except KeyError:
            raise CapabilityResolutionError(
                f"no AWS binding registered for {cap_id}", provider="aws", capability_id=cap_id
            ) from None

    def describe_environment(self) -> EnvironmentDescriptor:
        return EnvironmentDescriptor(
            provider=Provider.AWS,
            adapter_version=self.adapter_version,
            account_ref=self.account_ref,
            region=self.region,
            namespace=self.namespace,
        )

    def delegate(self, request: DelegationRequest) -> DelegationResult:
        assert_namespace(request.source_identity.value, self.namespace)
        source_session = self._identity_sessions.get(request.source_identity.value)
        if source_session is None:
            raise DelegationError(
                f"no live session for source identity ref {request.source_identity.value!r}; "
                "call register_identity or delegate to it first",
                source_ref=request.source_identity.value,
            )
        sts_client = self._sts_client(source_session)

        role_arn = mutation_mod.role_arn_for_identity(request.target_identity_id, self.outputs)
        assert_namespace(role_arn, self.namespace)
        session_name = session_mod.build_session_name(self.namespace, request.target_identity_id)

        result = session_mod.assume_role(
            sts_client,
            role_arn=role_arn,
            session_name=session_name,
            external_id=self.outputs.external_id,
            requested_duration_s=request.requested_duration_s,
            mechanism=request.mechanism,
            intended_capabilities=request.intended_capabilities,
            bindings=self.bindings,
            namespace=self.namespace,
            target_identity_id=request.target_identity_id,
            identity_ref=self._make_ref(role_arn),
            credential_id=new_credential_id(),
            salt=self._salt(),
        )
        boto_session = session_mod.boto3_session_from_credential(
            result.credential, region=self.region
        )
        self._identity_sessions[result.identity_ref.value] = boto_session
        self._ref_to_identity_id[result.identity_ref.value] = request.target_identity_id
        return result

    def probe(self, request: ProbeRequest) -> ProbeResult:
        assert_namespace(request.identity_ref.value, self.namespace)
        target_ref = request.binding.resource_template.format(namespace=request.namespace)
        assert_namespace(target_ref, self.namespace)

        identity_id = self._ref_to_identity_id[request.identity_ref.value]
        boto_session = self._identity_sessions[request.identity_ref.value]
        clients = self._clients_for(request.identity_ref.value, boto_session)
        state = self._allowlist_states[request.identity_ref.value]

        run_id = self.run_id
        probe_id = f"{request.capability_id}-{request.trial}"
        nonce = new_ulid()[:16]
        call = self._build_call(
            request.capability_id, clients, identity_id, run_id, probe_id, nonce
        )

        start_ns = time.monotonic_ns()
        wall_start = datetime.now(UTC)
        with OperationAllowlist(request.binding) as allowlist:
            state.current = allowlist
            try:
                outcome, retry_outcome = self._call_and_classify(call, path=request.capability_id)
            finally:
                state.current = None
        end_ns = time.monotonic_ns()

        timing = ProbeTiming(
            monotonic_start_ns=start_ns,
            monotonic_end_ns=end_ns,
            wall_start=wall_start,
            attempt_number=retry_outcome.attempt_number,
            retries=retry_outcome.retries,
        )
        return ProbeResult(outcome=outcome, timing=timing)

    def _build_call(
        self,
        capability_id: str,
        clients: _Clients,
        identity_id: str,
        run_id: str,
        probe_id: str,
        nonce: str,
    ) -> Any:
        outputs = self.outputs
        match capability_id:
            case "objectstore.read":
                return lambda: probes_mod.probe_objectstore_read(clients.s3, outputs=outputs)
            case "objectstore.write":
                return lambda: probes_mod.probe_objectstore_write(
                    clients.s3, outputs=outputs, run_id=run_id, probe_id=probe_id, nonce=nonce
                )
            case "objectstore.list":
                return lambda: probes_mod.probe_objectstore_list(clients.s3, outputs=outputs)
            case "keyvalue.read":
                return lambda: probes_mod.probe_keyvalue_read(clients.dynamodb, outputs=outputs)
            case "keyvalue.write":
                return lambda: probes_mod.probe_keyvalue_write(
                    clients.dynamodb, outputs=outputs, run_id=run_id, probe_id=probe_id, nonce=nonce
                )
            case "function.invoke":
                return lambda: probes_mod.probe_function_invoke(clients.lambda_, outputs=outputs)
            case "queue.send":
                return lambda: probes_mod.probe_queue_send(
                    clients.sqs, outputs=outputs, nonce=nonce
                )
            case "queue.receive":
                return lambda: probes_mod.probe_queue_receive(clients.sqs, outputs=outputs)
            case "identity.whoami":
                return lambda: probes_mod.probe_identity_whoami(clients.sts)
            case "identity.delegate":
                next_hop = next_hop_role_arn(
                    identity_id, account_id=outputs.account_id, namespace=self.namespace
                )
                return lambda: probes_mod.probe_identity_delegate(
                    clients.sts, next_hop_role_arn=next_hop, external_id=outputs.external_id
                )
            case _:
                raise CapabilityResolutionError(
                    f"no AWS probe implementation for {capability_id}",
                    provider="aws",
                    capability_id=capability_id,
                )

    def _call_and_classify(self, call: Any, *, path: str) -> tuple[ProbeOutcome, RetryOutcome]:
        result, exc, retry_outcome = call_with_retry(call)
        if exc is None:
            if result is None:  # pragma: no cover -- call_with_retry's own contract
                raise AssertionError("call_with_retry returned neither a result nor an exception")
            return result, retry_outcome
        if path == "identity.whoami":
            # Apparatus fault, not a denial (AWS_PROVIDER_SPEC section 6.2):
            # the run aborts rather than reporting a false denial.
            raise exc
        if not isinstance(exc, ClientError):
            raise exc
        return probes_mod.classify_denial(exc, path=path), retry_outcome

    def apply_policy_mutation(self, mutation: PolicyMutation) -> MutationReceipt:
        bootstrap = self._bootstrap_session()
        iam_client = bootstrap.client("iam", region_name=self.region)
        return mutation_mod.apply_mutation(
            iam_client,
            mutation,
            outputs=self.outputs,
            bindings=self.bindings,
            namespace=self.namespace,
        )

    def snapshot_policy_state(self, identity_ref: IdentityRef) -> PolicyStateSnapshot:
        identity_id = self._ref_to_identity_id[identity_ref.value]
        bootstrap = self._bootstrap_session()
        iam_client = bootstrap.client("iam", region_name=self.region)
        return policy_mod.snapshot_policy_state(
            iam_client,
            identity_id,
            outputs=self.outputs,
            salt=self._salt(),
            now_ns=time.monotonic_ns(),
        )


def _credential_from_sts_response(
    response: dict[str, Any], *, credential_id: str
) -> TemporaryCredential:
    creds = response["Credentials"]
    return TemporaryCredential(
        access_key_id=creds["AccessKeyId"],
        secret_access_key=creds["SecretAccessKey"],
        session_token=creds["SessionToken"],
        credential_id=credential_id,
    )
