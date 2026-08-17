"""``AwsProviderAdapter``: wires preflight, session issuance, the ten probes,
the mutation choke point and policy snapshotting behind the
``ProviderAdapter`` Protocol (AWS_PROVIDER_SPEC.md).

**Identity model.** AWS's real identities are fixed by Terraform
provisioning (``bootstrap``, ``principal``, ``agent-a``..``agent-f`` --
section 3), unlike the fake's in-memory ``PolicyEngine``, which can register
an arbitrary named identity on the spot. ``register_identity`` therefore
recognizes exactly those seven names and raises for anything else. The shared
provider contract supplies provider-specific setup hooks for fixed-role test
fixtures, so its behavioral assertions remain common without inventing
placeholder IAM roles.

**The botocore before-call hook** (SI-2's independent check, SI-3's
``OperationAllowlist``) is installed once per boto3 client at construction
time, reading from a small mutable ``_AllowlistHookState`` the adapter flips
around each probe's own ``with OperationAllowlist(binding)`` block -- the
hook itself has no notion of "which probe is this," only "is an allowlist
currently open."
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from botocore.exceptions import ClientError

from chainbreak.capabilities.guard import OperationAllowlist
from chainbreak.capabilities.loader import load_catalog
from chainbreak.core.enums import Provider
from chainbreak.core.errors import CapabilityResolutionError, ChainbreakError, DelegationError
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
from chainbreak.providers.aws.namespace import assert_aws_reference, assert_outbound_parameters
from chainbreak.providers.aws.preflight import TerraformOutputs
from chainbreak.providers.aws.retry import RetryOutcome, call_with_retry, error_code
from chainbreak.providers.base.types import (
    DelegationRequest,
    DelegationResult,
    EnvironmentDescriptor,
    PreflightCheck,
    PreflightReport,
    ProbeRequest,
    ProbeResult,
)

ADAPTER_VERSION = "0.1.0"

_RECOGNIZED_IDENTITIES = frozenset(
    {"bootstrap", "principal", "agent-a", "agent-b", "agent-c", "agent-d", "agent-e", "agent-f"}
)

#: The real chain topology ``delegation/main.tf`` provisions ``sts:AssumeRole``
#: for: operator -> principal -> agent-a -> agent-b -> ... -> agent-f. Neither
#: the operator nor bootstrap has a granted ``sts:AssumeRole`` path onto any
#: agent role beyond what this chain expresses (bootstrap is *trusted* by every
#: agent role but was never granted the action itself -- see
#: ``register_identity``'s docstring).
_AGENT_CHAIN = ("principal", "agent-a", "agent-b", "agent-c", "agent-d", "agent-e", "agent-f")


def _identity_chain(identity_id: str) -> tuple[str, ...]:
    """Ordered hops from the operator session to ``identity_id``, inclusive.

    ``bootstrap`` and ``principal`` are one hop (operator trusts both
    directly); each agent is reached by walking ``_AGENT_CHAIN`` up to and
    including it.
    """
    if identity_id in ("bootstrap", "principal"):
        return (identity_id,)
    return _AGENT_CHAIN[: _AGENT_CHAIN.index(identity_id) + 1]


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
    account_id: str | None = None
    namespace: str | None = None
    exact_parameters: dict[str, str] = field(default_factory=dict)
    allowed_parameters: dict[str, frozenset[str]] = field(default_factory=dict)


def _install_allowlist_hook(client: Any, state: _AllowlistHookState) -> None:
    service_name = client.meta.service_model.service_name

    def _before_call(**kwargs: Any) -> None:
        if state.account_id is not None and state.namespace is not None:
            params = kwargs.get("params", {})
            if isinstance(params, Mapping):
                assert_outbound_parameters(
                    params,
                    account_id=state.account_id,
                    namespace=state.namespace,
                    exact_parameters=state.exact_parameters,
                    allowed_parameters=state.allowed_parameters,
                )
        if state.current is None:
            return
        model = kwargs.get("model")
        if model is not None:
            state.current.record(_iam_action(service_name, model.name))

    client.meta.events.register("before-call.*.*", _before_call)


@dataclass(frozen=True, slots=True)
class _Clients:
    iam: Any
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
    i_know_what_i_am_doing: bool = False
    protected_identities: frozenset[str] = field(
        default_factory=lambda: frozenset({"bootstrap", "principal"})
    )

    name: str = field(default="aws", init=False)
    adapter_version: str = field(default=ADAPTER_VERSION, init=False)

    catalog: CapabilityCatalog = field(init=False, repr=False)
    bindings: dict[str, ProviderCapabilityBinding] = field(init=False, repr=False)

    _ref_to_identity_id: dict[str, IdentityId] = field(init=False, default_factory=dict, repr=False)
    _identity_output_bindings: dict[IdentityId, str] = field(
        init=False, default_factory=dict, repr=False
    )
    _identity_sessions: dict[str, Any] = field(init=False, default_factory=dict, repr=False)
    _clients_cache: dict[str, _Clients] = field(init=False, default_factory=dict, repr=False)
    _allowlist_states: dict[str, _AllowlistHookState] = field(
        init=False, default_factory=dict, repr=False
    )
    _bootstrap_session_cache: Any = field(init=False, default=None, repr=False)
    _credentials: list[Any] = field(init=False, default_factory=list, repr=False)
    _closed: bool = field(init=False, default=False, repr=False)
    _bootstrap_refresh_skew_s: int = field(default=60, repr=False)

    def __post_init__(self) -> None:
        self.catalog = load_catalog()
        self.bindings = {
            b.capability_id: b
            for b in build_aws_bindings(
                self.catalog, account_id=self.outputs.account_id, region=self.outputs.region
            )
        }

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("AWS provider adapter is closed")

    def _hook_state(self, ref_value: str) -> _AllowlistHookState:
        state = self._allowlist_states.get(ref_value)
        if state is None:
            state = _AllowlistHookState(
                account_id=self.outputs.account_id,
                namespace=self.outputs.namespace,
                exact_parameters={
                    "Bucket": self.outputs.objectstore_bucket,
                    "TableName": self.outputs.keyvalue_table,
                    "FunctionName": self.outputs.function_name,
                    "QueueUrl": self.outputs.queue_url,
                },
                allowed_parameters={
                    "RoleName": frozenset(
                        arn.rsplit("/", 1)[-1]
                        for arn in self.outputs.all_resource_arns()
                        if ":role/" in arn
                    )
                },
            )
            self._allowlist_states[ref_value] = state
        return state

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
        client = session.client(
            "sts", region_name=self.region, endpoint_url=f"https://sts.{self.region}.amazonaws.com"
        )
        _install_allowlist_hook(client, self._hook_state("operator"))
        return client

    def _clients_for(self, ref_value: str, boto_session: Any) -> _Clients:
        cached = self._clients_cache.get(ref_value)
        if cached is not None:
            return cached
        state = self._hook_state(ref_value)
        clients = _Clients(
            iam=boto_session.client("iam", region_name=self.region),
            s3=boto_session.client("s3", region_name=self.region),
            dynamodb=boto_session.client("dynamodb", region_name=self.region),
            lambda_=boto_session.client("lambda", region_name=self.region),
            sqs=boto_session.client("sqs", region_name=self.region),
            sts=self._sts_client(boto_session),
        )
        for client in (
            clients.iam,
            clients.s3,
            clients.dynamodb,
            clients.lambda_,
            clients.sqs,
            clients.sts,
        ):
            _install_allowlist_hook(client, state)
        self._clients_cache[ref_value] = clients
        return clients

    def _bootstrap_session(self) -> Any:
        self._ensure_open()
        now = datetime.now(UTC)
        if self._bootstrap_session_cache is not None:
            cached_session, expires_at, _credential = self._bootstrap_session_cache
            if now + timedelta(seconds=self._bootstrap_refresh_skew_s) < expires_at:
                return cached_session
            self._bootstrap_session_cache = None
            _credential.scrub()
            self._clients_cache.pop(self.outputs.bootstrap_role_arn, None)

        sts = self._sts_client(self.operator_session)
        response = sts.assume_role(
            RoleArn=self.outputs.bootstrap_role_arn,
            RoleSessionName=session_mod.build_session_name(self.namespace, "bootstrap"),
            DurationSeconds=3600,
            ExternalId=self.outputs.external_id,
        )
        credential = _credential_from_sts_response(response, credential_id=new_credential_id())
        expiration = response["Credentials"].get("Expiration")
        if not isinstance(expiration, datetime):
            raise DelegationError("bootstrap AssumeRole response did not include an expiration")
        if expiration.tzinfo is None:
            expiration = expiration.replace(tzinfo=UTC)
        session = session_mod.boto3_session_from_credential(credential, region=self.region)
        self._credentials.append(credential)
        self._bootstrap_session_cache = (session, expiration, credential)
        return session

    # -- setup, not part of the Protocol -------------------------------------

    def register_identity(
        self,
        identity_id: str,
        *,
        allow: Any = None,
        provider_binding: str | None = None,
    ) -> IdentityRef:
        """Assume the corresponding real, Terraform-provisioned role. See
        the module docstring for why this only recognizes the seven fixed
        AWS_PROVIDER_SPEC identity names -- ``allow`` is accepted for
        surface compatibility with the fake adapter's convenience method but
        is otherwise ignored: AWS's identity policies come from Terraform
        provisioning (M9), not from a runtime call.

        Only ``bootstrap`` and ``principal`` are directly assumable from the
        operator session (``identities/main.tf``'s ``trust_policy_operator``).
        Every agent role's trust policy names only its chain predecessor plus
        ``bootstrap`` (``identities/main.tf``'s per-agent ``Principal`` block),
        and -- confirmed empirically against the real account -- bootstrap's
        own identity policy grants IAM mutation actions on the agent roles but
        never ``sts:AssumeRole``, so being *trusted* by every agent role does
        not make bootstrap able to *assume* any of them. The only granted
        ``sts:AssumeRole`` path onto an agent role is the chain itself
        (``delegation/main.tf``'s per-hop ``CbAllowIdentityDelegate`` statement,
        agent-N -> agent-N+1). Reaching ``agent-c`` for direct test setup
        therefore means walking operator -> principal -> agent-a -> agent-b ->
        agent-c for real, one hop at a time, exactly as a scenario's own
        delegation chain would."""
        if identity_id not in _RECOGNIZED_IDENTITIES:
            raise DelegationError(
                f"{identity_id!r} is not a Terraform-provisioned AWS identity; "
                "AWS_PROVIDER_SPEC section 3 provisions exactly bootstrap, principal "
                "and agent-a..agent-f",
                identity_id=identity_id,
            )

        chain = _identity_chain(identity_id)
        session = self.operator_session
        role_arn = ""
        for hop_id in chain:
            role_arn = (
                self.outputs.role_arn_for_output(provider_binding)
                if provider_binding is not None and hop_id == identity_id
                else mutation_mod.role_arn_for_identity(hop_id, self.outputs)
            )
            session_name = session_mod.build_session_name(self.namespace, hop_id)
            sts = self._sts_client(session)
            response = sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName=session_name,
                DurationSeconds=3600,
                ExternalId=self.outputs.external_id,
            )
            credential = _credential_from_sts_response(response, credential_id=new_credential_id())
            self._credentials.append(credential)
            session = session_mod.boto3_session_from_credential(credential, region=self.region)

        ref = self._make_ref(role_arn)
        self._identity_sessions[ref.value] = session
        self._ref_to_identity_id[ref.value] = identity_id
        if provider_binding is not None:
            self._identity_output_bindings[identity_id] = provider_binding
        return ref

    # -- ProviderAdapter Protocol ---------------------------------------------

    def preflight(self, envelope: SafetyEnvelope) -> PreflightReport:
        self._ensure_open()
        sts = self._sts_client(self.operator_session)
        tagging = self.operator_session.client("resourcegroupstaggingapi", region_name=self.region)
        iam = self.operator_session.client("iam", region_name=self.region)
        _install_allowlist_hook(tagging, self._hook_state("operator"))
        _install_allowlist_hook(iam, self._hook_state("operator"))

        def precondition_results() -> dict[str, bool]:
            # This callback is evaluated only after P1/P2/P3/P4/P5/P6/P7 have
            # passed.  In particular, wrong-account preflight has exactly one
            # AWS call: the operator STS GetCallerIdentity.
            bootstrap = self._bootstrap_session()
            clients = self._clients_for(self.outputs.bootstrap_role_arn, bootstrap)
            registry = probes_mod.build_aws_preconditions(
                s3_client=clients.s3,
                dynamodb_client=clients.dynamodb,
                lambda_client=clients.lambda_,
                sqs_client=clients.sqs,
                outputs=self.outputs,
            )
            return dict(
                probes_mod.verify_all_preconditions(
                    registry, self._make_ref(self.outputs.bootstrap_role_arn)
                )
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
        # ``run_preflight`` raises per-check (pinned by test_adapter_moto.py,
        # which calls it directly and asserts on the specific exception type
        # for P2/P3/P4/P6/P7/P9/P10) -- but the ``ProviderAdapter`` Protocol
        # this method implements returns a ``PreflightReport`` and never
        # raises (``providers/fake/adapter.py::preflight`` never does, and
        # the shared M5 contract suite's ``test_preflight_rejects_wrong_account``
        # asserts ``report.passed is False`` with no ``pytest.raises`` around
        # it). Converting here, rather than changing ``run_preflight`` itself,
        # keeps both the low-level abort-fast semantics AWS_PROVIDER_SPEC
        # section 2 describes (P1/P2 make no AWS call beyond
        # GetCallerIdentity -- SI-6) and the Protocol's own contract intact.
        try:
            return preflight_mod.run_preflight(
                sts_client=sts,
                resourcegroupstaggingapi_client=tagging,
                iam_client=iam,
                envelope=envelope,
                terraform_outputs=self.outputs,
                precondition_results=precondition_results,
                cost_estimate=cost_estimate,
                clock_offset_ms=None,
                i_know_what_i_am_doing=self.i_know_what_i_am_doing,
            )
        except ChainbreakError as exc:
            return PreflightReport(
                passed=False,
                checks=(PreflightCheck(name=exc.machine_reason, passed=False, detail=exc.message),),
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
            sts_endpoint=self.sts_endpoint,
        )

    @property
    def sts_endpoint(self) -> str:
        return f"https://sts.{self.region}.amazonaws.com"

    def build_precondition_registry(self) -> Any:
        """Return lazy, bootstrap-attributed matrix preconditions.

        The callbacks do not assume the bootstrap role until the orchestrator
        has completed P1-P11.  This keeps preflight's abort-fast account gate
        ahead of all marker/resource calls.
        """
        from chainbreak.capabilities.preconditions import PreconditionRegistry

        registry = PreconditionRegistry()

        def verify(name: str, _ref: Any) -> bool:
            bootstrap = self._bootstrap_session()
            clients = self._clients_for(self.outputs.bootstrap_role_arn, bootstrap)
            checks = probes_mod.build_aws_preconditions(
                s3_client=clients.s3,
                dynamodb_client=clients.dynamodb,
                lambda_client=clients.lambda_,
                sqs_client=clients.sqs,
                outputs=self.outputs,
            )
            return checks.resolve(name)(_ref)

        for name in (
            "objectstore.marker_present",
            "keyvalue.marker_present",
            "function.alive",
            "queue.present",
        ):

            def verifier(ref: Any, check: str = name) -> bool:
                return verify(check, ref)

            registry.register(name, verifier)
        return registry

    def verify_output_marker(
        self,
        provisioning_ref: IdentityRef,
        *,
        run_id: str,
        task_id: str,
        output_capability: str | None = None,
    ) -> bool:
        """Verify a task side effect with a bootstrap-owned read.

        The worker never supplies a marker claim to this method.  The key is
        derived from the same run-scoped write shape used by the production
        probe, and the client is always created from the bootstrap session.
        """
        if provisioning_ref.value != self.outputs.bootstrap_role_arn:
            raise DelegationError("output-marker verification requires the bootstrap identity")
        bootstrap = self._bootstrap_session()
        clients = self._clients_for(self.outputs.bootstrap_role_arn, bootstrap)
        try:
            if output_capability == "objectstore.write":
                clients.s3.head_object(
                    Bucket=self.outputs.objectstore_bucket,
                    Key=f"{self.outputs.namespace}/scratch/{run_id}/{task_id}/objectstore.write",
                )
                return True
            if output_capability == "keyvalue.write":
                response = clients.dynamodb.get_item(
                    TableName=self.outputs.keyvalue_table,
                    Key={"pk": {"S": f"cb-scratch#{run_id}#{task_id}/keyvalue.write"}},
                    ConsistentRead=True,
                )
                return "Item" in response
        except ClientError:
            return False
        return False

    def delegate(self, request: DelegationRequest) -> DelegationResult:
        self._ensure_open()
        assert_aws_reference(
            request.source_identity.value, account_id=self.account_ref, namespace=self.namespace
        )
        source_session = self._identity_sessions.get(request.source_identity.value)
        if source_session is None:
            raise DelegationError(
                f"no live session for source identity ref {request.source_identity.value!r}; "
                "call register_identity or delegate to it first",
                source_ref=request.source_identity.value,
            )
        sts_client = self._sts_client(source_session)

        role_arn = (
            self.outputs.role_arn_for_output(request.target_provider_binding)
            if request.target_provider_binding is not None
            else mutation_mod.role_arn_for_identity(request.target_identity_id, self.outputs)
        )
        assert_aws_reference(role_arn, account_id=self.account_ref, namespace=self.namespace)
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
        self._credentials.append(result.credential)
        boto_session = session_mod.boto3_session_from_credential(
            result.credential, region=self.region
        )
        self._identity_sessions[result.identity_ref.value] = boto_session
        self._ref_to_identity_id[result.identity_ref.value] = request.target_identity_id
        if request.target_provider_binding is not None:
            self._identity_output_bindings[request.target_identity_id] = (
                request.target_provider_binding
            )
        return result

    def probe(self, request: ProbeRequest) -> ProbeResult:
        self._ensure_open()
        assert_aws_reference(
            request.identity_ref.value, account_id=self.account_ref, namespace=self.namespace
        )
        target_ref = request.binding.resource_template.format(namespace=request.namespace)
        assert_aws_reference(target_ref, account_id=self.account_ref, namespace=self.namespace)

        identity_id = self._ref_to_identity_id[request.identity_ref.value]
        boto_session = self._identity_sessions[request.identity_ref.value]
        clients = self._clients_for(request.identity_ref.value, boto_session)
        state = self._allowlist_states[request.identity_ref.value]

        run_id = self.run_id
        probe_id = request.operation_id or f"{request.capability_id}-{request.trial}"
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
                next_hop = self._next_hop_role_arn(identity_id)
                return lambda: probes_mod.probe_identity_delegate(
                    clients.sts,
                    next_hop_role_arn=next_hop,
                    external_id=outputs.external_id,
                    session_name=session_mod.build_session_name(self.namespace, "probe-delegate"),
                )
            case _:
                raise CapabilityResolutionError(
                    f"no AWS probe implementation for {capability_id}",
                    provider="aws",
                    capability_id=capability_id,
                )

    def _next_hop_role_arn(self, identity_id: str) -> str | None:
        standard = next_hop_role_arn(
            identity_id, account_id=self.outputs.account_id, namespace=self.namespace
        )
        if standard is None:
            return None
        if identity_id == "principal":
            target_id = "agent-a"
        elif identity_id.startswith("agent-"):
            try:
                target_id = f"agent-{chr(ord(identity_id[-1]) + 1)}"
            except (IndexError, TypeError):
                return standard
        else:
            return standard
        binding = self._identity_output_bindings.get(target_id)
        return self.outputs.role_arn_for_output(binding) if binding is not None else standard

    def _call_and_classify(self, call: Any, *, path: str) -> tuple[ProbeOutcome, RetryOutcome]:
        result, exc, retry_outcome = call_with_retry(call)
        if exc is None:
            if result is None:  # pragma: no cover -- call_with_retry's own contract
                raise AssertionError("call_with_retry returned neither a result nor an exception")
            return result, retry_outcome
        # ExpiredToken is the expected expired-credential outcome in the
        # post-expiry stale-authority scenario, including its whoami control.
        # Other whoami failures remain apparatus faults rather than denials.
        if path == "identity.whoami" and not (
            isinstance(exc, ClientError) and error_code(exc) == "ExpiredToken"
        ):
            # Apparatus fault, not a denial (AWS_PROVIDER_SPEC section 6.2):
            # the run aborts rather than reporting a false denial.
            raise exc
        if not isinstance(exc, ClientError):
            raise exc
        return probes_mod.classify_denial(exc, path=path), retry_outcome

    def apply_policy_mutation(self, mutation: PolicyMutation) -> MutationReceipt:
        self._ensure_open()
        bootstrap = self._bootstrap_session()
        iam_client = self._clients_for(self.outputs.bootstrap_role_arn, bootstrap).iam
        return mutation_mod.apply_mutation(
            iam_client,
            mutation,
            outputs=self.outputs,
            bindings=self.bindings,
            namespace=self.namespace,
        )

    def restore_declared_policy(
        self, target_identity: str, declared_capabilities: Any
    ) -> MutationReceipt:
        del declared_capabilities  # Terraform's managed ceiling is the source of truth.
        self._ensure_open()
        bootstrap = self._bootstrap_session()
        iam_client = self._clients_for(self.outputs.bootstrap_role_arn, bootstrap).iam
        return mutation_mod.restore_declared_policy(
            iam_client,
            target_identity=target_identity,
            outputs=self.outputs,
            namespace=self.namespace,
        )

    def restore_trust_policy(self, target_identity: str) -> MutationReceipt:
        self._ensure_open()
        bootstrap = self._bootstrap_session()
        iam_client = self._clients_for(self.outputs.bootstrap_role_arn, bootstrap).iam
        return mutation_mod.restore_trust_policy(
            iam_client,
            target_identity=target_identity,
            outputs=self.outputs,
            namespace=self.namespace,
        )

    def snapshot_policy_state(self, identity_ref: IdentityRef) -> PolicyStateSnapshot:
        self._ensure_open()
        identity_id = self._ref_to_identity_id[identity_ref.value]
        bootstrap = self._bootstrap_session()
        iam_client = self._clients_for(self.outputs.bootstrap_role_arn, bootstrap).iam
        return policy_mod.snapshot_policy_state(
            iam_client,
            identity_id,
            outputs=self.outputs,
            salt=self._salt(),
            now_ns=time.monotonic_ns(),
        )

    def clear_caches(self) -> None:
        """Drop client/session indexes deterministically without touching AWS."""
        self._clients_cache.clear()
        self._allowlist_states.clear()
        self._identity_sessions.clear()
        self._ref_to_identity_id.clear()
        self._identity_output_bindings.clear()
        self._bootstrap_session_cache = None

    def close(self) -> None:
        """Scrub live credentials and clear all adapter-held session state."""
        if self._closed:
            return
        for credential in self._credentials:
            credential.scrub()
        self._credentials.clear()
        self.clear_caches()
        self._closed = True

    def __enter__(self) -> AwsProviderAdapter:
        self._ensure_open()
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.close()


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
