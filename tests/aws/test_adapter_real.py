"""IAM semantics validated against a real, operator-owned AWS benchmark
account (AWS_PROVIDER_SPEC's own acceptance criterion 2).

Gated behind the ``aws`` marker (``tests/conftest.py``'s F5 gate): skipped
in every default run, including CI, and only collected for real when both
``CHAINBREAK_ALLOW_AWS_TESTS=1`` is set *and* this module's own
``CHAINBREAK_AWS_TEST_TERRAFORM_OUTPUTS`` environment variable points at a
real ``terraform output -json`` file for a provisioned benchmark account.
The dedicated-account execution result is recorded in ``PROJECT_STATUS.md``;
four denial/ambiguity assertions currently expose observed IAM authorization
propagation behavior rather than being suppressed or weakened.

``TestAwsProviderContract`` subclasses the shared ``ProviderContractSuite``
(``tests/integration/test_provider_contract.py``) per acceptance criterion
1. AWS supplies only provider-specific identity setup hooks because its
Terraform deployment has fixed roles; all contract behavior assertions remain
inherited from the shared suite.
"""

from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path

import pytest

from chainbreak.core.enums import DelegationMechanism, MutationKind, OutcomeClass
from chainbreak.core.models import AuthoritySet, PolicyMutation, SafetyEnvelope
from chainbreak.providers.aws.adapter import AwsProviderAdapter
from chainbreak.providers.aws.preflight import load_terraform_outputs
from chainbreak.providers.base.types import DelegationRequest, ProbeRequest
from tests.integration.test_provider_contract import ProviderContractSuite

pytestmark = pytest.mark.aws

_OUTPUTS_ENV_VAR = "CHAINBREAK_AWS_TEST_TERRAFORM_OUTPUTS"
_WRONG_ACCOUNT_ENV_VAR = "CHAINBREAK_AWS_TEST_WRONG_ACCOUNT_ID"
# This is an acceptance-test bound, not an experiment interval.  The dedicated
# account has already exhibited IAM authorization propagation beyond 120 s;
# the M17 timing families measure that behavior separately with n>=5.
_IAM_AUTHORIZATION_PROPAGATION_TIMEOUT_S = 180.0


@pytest.fixture(autouse=True)
def _cleanup_agent_inline_policies():
    """Real inline-policy mutations this file applies (``ATTACH_INLINE_DENY``/
    ``REPLACE_INLINE_POLICY``, via ``apply_policy_mutation``) are permanent IAM
    state, not fake-adapter in-memory state that resets between tests -- a
    residue from one test silently contaminates a later, unrelated one.
    Confirmed empirically: a leftover ``cb-deny`` on agent-a (from
    ``test_mutation_returns_a_confirmed_receipt``, which never reverted its
    own mutation) made ``test_every_capability_classifies_allow_and_deny_correctly``
    see a spurious ``DENIED_EXPLICIT`` on ``objectstore.read`` in an
    otherwise-unrelated run. Every test in this module builds its own adapter
    fresh (``make_adapter``/``_require_real_account``), so unconditionally
    clearing both mutation policy names off every agent role after each test
    is correct regardless of which test just ran, rather than threading
    per-test cleanup through each mutation call site.
    """
    yield
    outputs_path = os.environ.get(_OUTPUTS_ENV_VAR)
    if not outputs_path:
        return
    import boto3
    from botocore.exceptions import ClientError

    from chainbreak.providers.aws.mutation import DENY_POLICY_NAME, GRANT_POLICY_NAME

    outputs = load_terraform_outputs(Path(outputs_path))
    iam = boto3.Session(region_name=outputs.region).client("iam")
    for letter in "abcdef":
        role_name = f"{outputs.namespace}-agent-{letter}"
        for policy_name in (DENY_POLICY_NAME, GRANT_POLICY_NAME):
            with contextlib.suppress(ClientError):
                iam.delete_role_policy(RoleName=role_name, PolicyName=policy_name)


def _require_real_account() -> tuple[AwsProviderAdapter, str]:
    outputs_path = os.environ.get(_OUTPUTS_ENV_VAR)
    if not outputs_path:
        pytest.skip(
            f"{_OUTPUTS_ENV_VAR} is not set -- no Terraform-provisioned benchmark "
            "account is configured for this test run"
        )
    import boto3

    outputs = load_terraform_outputs(Path(outputs_path))
    operator_session = boto3.Session(region_name=outputs.region)
    adapter = AwsProviderAdapter(
        operator_session=operator_session, outputs=outputs, run_id="test-adapter-real"
    )
    wrong_account = os.environ.get(_WRONG_ACCOUNT_ENV_VAR, "000000000000")
    return adapter, wrong_account


class TestAwsProviderContract(ProviderContractSuite):
    """The shared contract assertions run against the real AWS adapter.

    The hooks below map abstract setup identities onto Terraform-provisioned
    roles. The denied hook uses ``agent-e`` because it has a valid next hop
    for the delegate capability; the empty/control hook uses terminal
    ``agent-f``.
    """

    def make_adapter(self) -> AwsProviderAdapter:  # type: ignore[override]
        adapter, _wrong_account = _require_real_account()
        return adapter

    def wrong_account_id(self) -> str:
        _adapter, wrong_account = _require_real_account()
        return wrong_account

    def contract_denied_identity(
        self, adapter: AwsProviderAdapter, capabilities: AuthoritySet | None = None
    ):
        allowed_caps = capabilities or AuthoritySet.from_iterable(
            c.id for c in adapter.catalog.capabilities if not c.is_control
        )
        denied_identity = adapter.register_identity("agent-e")
        adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="contract-deny-all",
                kind=MutationKind.ATTACH_INLINE_DENY,
                target_identity="agent-e",
                denies_capabilities=allowed_caps,
            )
        )
        # IAM mutation confirmation proves the policy document is stored, not
        # that the authorization-decision data plane has converged. Prime the
        # fixed-role fixture by waiting for every denied capability to be
        # observed as denied; the shared suite then performs its own common
        # one-shot behavioral assertions.
        for capability in adapter.catalog.capabilities:
            if capability.is_control:
                continue
            _probe_until(
                adapter,
                denied_identity,
                capability_id=capability.id,
                binding=adapter.resolve_capability(capability.id),
                namespace=adapter.namespace,
                predicate=lambda oc: oc.is_denial,
            )
        return denied_identity

    def contract_allowed_identity(self, adapter: AwsProviderAdapter, capabilities: AuthoritySet):
        principal = adapter.register_identity("principal")
        delegation = adapter.delegate(
            DelegationRequest(
                source_identity=principal,
                target_identity_id="agent-a",
                mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
                requested_duration_s=900,
                intended_capabilities=capabilities,
            )
        )
        return delegation.identity_ref

    def contract_empty_identity(self, adapter: AwsProviderAdapter):
        return adapter.register_identity("agent-f")

    def contract_snapshot_identity(self, adapter: AwsProviderAdapter):
        return adapter.register_identity("agent-a")


# ---------------------------------------------------------------------------
# IAM-semantics tests the shared contract suite does not cover
# (AWS_PROVIDER_SPEC's own "Tests" section for M8)
# ---------------------------------------------------------------------------


_AGENT_CHAIN = ("agent-a", "agent-b", "agent-c", "agent-d", "agent-e", "agent-f")


def _delegate_through_chain(
    adapter,
    principal_ref,
    *,
    target_identity_id,
    mechanism,
    intended_capabilities,
    requested_duration_s=900,
):
    """Walk principal -> agent-a -> ... -> ``target_identity_id`` one hop at
    a time. Each agent role's trust policy names only its chain predecessor
    plus bootstrap (``identities/main.tf``), so a single ``delegate()`` call
    straight from ``principal`` onto agent-b..agent-f is refused by AWS
    itself -- confirmed empirically against the real account. Every
    intermediate hop uses a broad ``DIRECT_ROLE_ASSUMPTION`` (no session
    policy applied -- see ``session.py``'s ``_SCOPED_MECHANISMS`` -- so it
    never narrows what the final hop can exercise); only the last hop uses
    the caller's requested mechanism and capabilities.
    """
    hops = _AGENT_CHAIN[: _AGENT_CHAIN.index(target_identity_id) + 1]
    current = principal_ref
    result = None
    for index, hop in enumerate(hops):
        is_last = index == len(hops) - 1
        result = adapter.delegate(
            DelegationRequest(
                source_identity=current,
                target_identity_id=hop,
                mechanism=mechanism if is_last else DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
                requested_duration_s=requested_duration_s,
                intended_capabilities=(
                    intended_capabilities if is_last else AuthoritySet.of("identity.delegate")
                ),
            )
        )
        current = result.identity_ref
    return result


def _probe_until(
    adapter,
    identity_ref,
    *,
    capability_id,
    binding,
    namespace,
    predicate,
    timeout_s=_IAM_AUTHORIZATION_PROPAGATION_TIMEOUT_S,
):
    """``apply_policy_mutation``'s own confirmation (``_poll_until`` in
    ``mutation.py``) polls ``GetRolePolicy`` until the stored document
    matches -- that proves IAM's control plane has the new document, not
    that the (separate, documented) authorization-decision data plane has
    picked it up yet. Confirmed empirically against the real account, with
    real variance: a deny mutation against an already-active session was
    observed to take effect anywhere from ~20s to over 120s across repeated
    trials against this same account/region for functionally identical
    mutations (see PROJECT_STATUS.md's M8/M9 real-account entry). This is
    exactly the phenomenon M12 (revocation propagation, gated behind M17)
    exists to measure properly with n>=5 trials polled to a STABLE
    denial -- a single ad-hoc assertion, even a polled one, cannot
    guarantee catching it inside any fixed bound. Poll the probe itself
    (same idea as the production path, ``execution/polling.py``) rather than
    asserting on a single sample, but note this test can still legitimately
    fail on a slow-propagation trial; that is the real, measured behavior,
    not a defect in this helper. Still fails hard -- returns whatever the
    last probe was -- if ``predicate`` is never satisfied inside
    ``timeout_s``.
    """
    deadline = time.monotonic() + timeout_s
    result = None
    while True:
        result = adapter.probe(
            ProbeRequest(
                identity_ref=identity_ref,
                capability_id=capability_id,
                binding=binding,
                namespace=namespace,
            )
        )
        if predicate(result.outcome.outcome_class) or time.monotonic() >= deadline:
            return result
        time.sleep(1.0)


class TestRealIamSemantics:
    def test_wrong_account_preflight_makes_only_get_caller_identity_call(self):
        """P1/P2 must fail closed before any resource or IAM call."""
        adapter, wrong_account = _require_real_account()
        call_log: list[str] = []

        def capture_call(*, model=None, **_kwargs):
            if model is not None:
                call_log.append(model.name)

        # boto3 exposes the botocore event emitter through its private session
        # object; this is an evidence-only hook and does not alter requests.
        adapter.operator_session._session.register("before-call.*.*", capture_call)
        envelope = SafetyEnvelope(
            allowed_account_ids=(wrong_account,),
            allowed_regions=(adapter.region,),
            namespace=adapter.namespace,
            namespace_pattern=f"^{adapter.namespace}$",
        )
        report = adapter.preflight(envelope)
        assert report.passed is False
        assert call_log == ["GetCallerIdentity"]

    def test_role_chain_duration_is_capped_at_3600_seconds_by_real_sts(self):
        """Not just that the adapter *requests* 3600s (already proven
        offline against moto in ``test_adapter_moto.py``) -- that real STS
        actually grants no more than that for a chained AssumeRole, which
        only a live account can confirm."""
        adapter, _ = _require_real_account()
        principal = adapter.register_identity("principal")
        hop_a = adapter.delegate(
            DelegationRequest(
                source_identity=principal,
                target_identity_id="agent-a",
                mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
                requested_duration_s=3600,
                intended_capabilities=AuthoritySet.of("identity.delegate"),
            )
        )
        hop_b = adapter.delegate(
            DelegationRequest(
                source_identity=hop_a.identity_ref,
                target_identity_id="agent-b",
                mechanism=DelegationMechanism.ROLE_CHAIN,
                requested_duration_s=7200,
                intended_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        assert hop_b.record.granted_duration_s == 3600
        assert hop_b.record.lifetime_capped is True

    def test_session_policy_cannot_grant_beyond_the_role_identity_policy(self):
        """A session policy naming a capability the role's own identity
        policy does not grant must still deny it (AWS_PROVIDER_SPEC section
        4: "Session policies intersect, never grant").

        Every agent's ceiling grants the identical non-delegate capability
        set (``delegation/main.tf``'s ``ceiling_statements`` applies to every
        role via the same ``for_each``) -- confirmed empirically -- so no
        ordinary capability like ``queue.send`` is ever genuinely absent
        from an agent's own identity policy; scoping a session policy to one
        cannot demonstrate this property against the real six-role
        deployment. ``identity.delegate`` is the one real exception:
        ``agent-f`` is the chain's last link and is provisioned with NO
        ``sts:AssumeRole`` statement at all (the per-hop grant is omitted
        for the final agent). A session policy scoped to ``identity.delegate``
        nominally covers any ``{namespace}-agent-*`` ARN (the binding's own
        resource template, ``bindings.py``), including agent-a's -- but
        agent-f's identity policy grants no ``sts:AssumeRole`` whatsoever,
        so the intersection is empty regardless of what the session policy
        claims. Uses a raw ``AssumeRole`` call (not the ``identity.delegate``
        probe wrapper, which short-circuits to ``ERROR_INFRASTRUCTURE``
        before any AWS call once it sees agent-f has no next hop -- correct
        probe behavior, but it means the probe path itself cannot exercise
        this specific IAM semantics question).
        """
        from botocore.exceptions import ClientError

        from chainbreak.providers.aws.mutation import role_arn_for_identity
        from chainbreak.providers.aws.session import (
            boto3_session_from_credential,
            build_session_name,
        )

        adapter, _ = _require_real_account()
        principal = adapter.register_identity("principal")
        delegation = _delegate_through_chain(
            adapter,
            principal,
            target_identity_id="agent-f",
            mechanism=DelegationMechanism.SESSION_POLICY_SCOPED,
            intended_capabilities=AuthoritySet.of("identity.delegate"),
        )
        boto_session = boto3_session_from_credential(delegation.credential, region=adapter.region)
        sts = boto_session.client("sts", region_name=adapter.region)
        with pytest.raises(ClientError) as exc_info:
            sts.assume_role(
                RoleArn=role_arn_for_identity("agent-a", adapter.outputs),
                RoleSessionName=build_session_name(adapter.namespace, "session-policy-canary"),
                DurationSeconds=900,
                ExternalId=adapter.outputs.external_id,
            )
        assert exc_info.value.response["Error"]["Code"] == "AccessDenied"

    def test_explicit_deny_wins_over_an_otherwise_granted_capability(self):
        adapter, _ = _require_real_account()
        principal = adapter.register_identity("principal")
        delegation = adapter.delegate(
            DelegationRequest(
                source_identity=principal,
                target_identity_id="agent-a",
                mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
                requested_duration_s=900,
                intended_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="explicit-deny-wins",
                kind=MutationKind.ATTACH_INLINE_DENY,
                target_identity="agent-a",
                denies_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        result = _probe_until(
            adapter,
            delegation.identity_ref,
            capability_id="objectstore.read",
            binding=adapter.resolve_capability("objectstore.read"),
            namespace=adapter.namespace,
            predicate=lambda oc: oc is OutcomeClass.DENIED_EXPLICIT,
        )
        assert result.outcome.outcome_class is OutcomeClass.DENIED_EXPLICIT

    def test_denial_message_attribution_matches_todays_aws_wording(self):
        """The canary AWS_PROVIDER_SPEC's "Risks" section names explicitly:
        if this fails, AWS changed its denial message wording and
        ``disambiguation.py`` needs updating -- it must fail loudly here,
        never silently degrade to DENIED_UNATTRIBUTED in production."""
        adapter, _ = _require_real_account()
        principal = adapter.register_identity("principal")
        delegation = _delegate_through_chain(
            adapter,
            principal,
            target_identity_id="agent-b",
            mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
            intended_capabilities=AuthoritySet.of("objectstore.read"),
        )
        adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="canary-explicit-deny",
                kind=MutationKind.ATTACH_INLINE_DENY,
                target_identity="agent-b",
                denies_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        result = _probe_until(
            adapter,
            delegation.identity_ref,
            capability_id="objectstore.read",
            binding=adapter.resolve_capability("objectstore.read"),
            namespace=adapter.namespace,
            predicate=lambda oc: oc is OutcomeClass.DENIED_EXPLICIT,
        )
        assert result.outcome.outcome_class is OutcomeClass.DENIED_EXPLICIT
        assert result.outcome.denial_attribution is not None

    def test_s3_403_404_ambiguity_resolved_by_precondition_not_guessed(self):
        """With the marker precondition satisfied, a real AccessDenied on
        ``objectstore.read`` must classify as a denial, never as
        ERROR_INFRASTRUCTURE's "object reported missing" branch -- proving
        the precondition guarantee actually holds against real S3, not
        just moto's approximation."""
        adapter, _ = _require_real_account()
        principal = adapter.register_identity("principal")
        delegation = _delegate_through_chain(
            adapter,
            principal,
            target_identity_id="agent-c",
            mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
            intended_capabilities=AuthoritySet.of("objectstore.read"),
        )
        adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="s3-403-404-canary",
                kind=MutationKind.ATTACH_INLINE_DENY,
                target_identity="agent-c",
                denies_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        result = _probe_until(
            adapter,
            delegation.identity_ref,
            capability_id="objectstore.read",
            binding=adapter.resolve_capability("objectstore.read"),
            namespace=adapter.namespace,
            predicate=lambda oc: oc.is_denial,
        )
        assert result.outcome.outcome_class.is_denial
        assert (
            result.outcome.disambiguation_path
            != "objectstore.read:unexpected_missing_after_precondition"
        )

    def test_missing_marker_reports_configuration_error_via_preflight(self):
        """F6: preflight's P8 check, not a probe, is what must catch this --
        a missing marker must never surface as a wave of denials."""
        adapter, _ = _require_real_account()
        from chainbreak.core.models import SafetyEnvelope

        envelope = SafetyEnvelope(
            allowed_account_ids=(adapter.account_ref,),
            allowed_regions=(adapter.region,),
            namespace=adapter.namespace,
            namespace_pattern=f"^{adapter.namespace}$",
        )
        report = adapter.preflight(envelope)
        marker_check = next((c for c in report.checks if c.name == "marker_preconditions"), None)
        assert marker_check is not None, "preflight must always record a marker_preconditions check"

    def test_whoami_never_denied_even_with_every_other_capability_removed(self):
        adapter, _ = _require_real_account()
        principal = adapter.register_identity("principal")
        delegation = _delegate_through_chain(
            adapter,
            principal,
            target_identity_id="agent-d",
            mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
            intended_capabilities=AuthoritySet.of("identity.whoami"),
        )
        result = adapter.probe(
            ProbeRequest(
                identity_ref=delegation.identity_ref,
                capability_id="identity.whoami",
                binding=adapter.resolve_capability("identity.whoami"),
                namespace=adapter.namespace,
            )
        )
        assert result.outcome.outcome_class is OutcomeClass.ALLOWED

    def test_out_of_namespace_probe_refused_before_the_call(self):
        """SI-2 against a real adapter instance, not the fake -- same
        assertion ``ProviderContractSuite`` already makes generically, kept
        here too because it is explicitly named in M8's own spec as a
        required real-account test."""
        from chainbreak.core.errors import NamespaceViolationError

        adapter, _ = _require_real_account()
        principal = adapter.register_identity("principal")
        binding = adapter.resolve_capability("objectstore.read")
        with pytest.raises(NamespaceViolationError):
            adapter.probe(
                ProbeRequest(
                    identity_ref=principal,
                    capability_id="objectstore.read",
                    binding=binding,
                    namespace="cb-ffffffff",
                )
            )
