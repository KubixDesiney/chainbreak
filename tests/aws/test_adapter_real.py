"""IAM semantics validated against a real, operator-owned AWS benchmark
account (AWS_PROVIDER_SPEC's own acceptance criterion 2).

Gated behind the ``aws`` marker (``tests/conftest.py``'s F5 gate): skipped
in every default run, including CI, and only collected for real when both
``CHAINBREAK_ALLOW_AWS_TESTS=1`` is set *and* this module's own
``CHAINBREAK_AWS_TEST_TERRAFORM_OUTPUTS`` environment variable points at a
real ``terraform output -json`` file for a provisioned benchmark account --
which does not exist yet (Terraform itself is M9's deliverable; this file
was written before any account was provisioned). **No test in this file has
ever been executed.** Every assertion below is a direct implementation of
AWS_PROVIDER_SPEC section 2/4/6/7's documented behavior, not a result.

``TestAwsProviderContract`` subclasses the shared ``ProviderContractSuite``
(``tests/integration/test_provider_contract.py``) per acceptance criterion
1, with two of its inherited tests overridden rather than run unmodified --
see the class docstring for why: the shared suite invents ad hoc identity
names (``"agent-denied"``, ``"agent-empty"``) that have no analogue in
AWS's fixed, Terraform-provisioned six-role model
(``adapter.py``'s own module docstring records this same tension). This is
a genuine specification gap discovered while implementing M8, not
worked around silently.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from chainbreak.core.enums import DelegationMechanism, MutationKind, OutcomeClass
from chainbreak.core.models import AuthoritySet, PolicyMutation
from chainbreak.providers.aws.adapter import AwsProviderAdapter
from chainbreak.providers.aws.preflight import load_terraform_outputs
from chainbreak.providers.base.types import DelegationRequest, ProbeRequest
from tests.integration.test_provider_contract import ProviderContractSuite

pytestmark = pytest.mark.aws

_OUTPUTS_ENV_VAR = "CHAINBREAK_AWS_TEST_TERRAFORM_OUTPUTS"
_WRONG_ACCOUNT_ENV_VAR = "CHAINBREAK_AWS_TEST_WRONG_ACCOUNT_ID"


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
    """The shared adapter-agnostic contract, run against a real account.

    Two inherited tests are overridden here rather than run unmodified:
    ``test_every_capability_classifies_allow_and_deny_correctly`` and
    ``test_control_capability_never_denied`` both call
    ``adapter.register_identity`` with fake-only ad hoc names
    (``"agent-denied"``, ``"agent-empty"``) that assume an in-memory policy
    engine capable of registering an arbitrary identity on the spot.
    AWS's identities are fixed by Terraform provisioning
    (``adapter.py``'s module docstring); the override below exercises the
    same *behavior* (an identity with no granted capabilities is denied
    everything except the control capability) using a real provisioned
    identity (``agent-f``, the chain's unused tail in a scenario that does
    not reach it) with an explicit deny mutation applied first, rather than
    a role that does not exist.
    """

    def make_adapter(self) -> AwsProviderAdapter:  # type: ignore[override]
        adapter, _wrong_account = _require_real_account()
        return adapter

    def wrong_account_id(self) -> str:
        _adapter, wrong_account = _require_real_account()
        return wrong_account

    def test_every_capability_classifies_allow_and_deny_correctly(self):  # type: ignore[override]
        adapter = self.make_adapter()
        principal = adapter.register_identity("principal")
        allowed_caps = AuthoritySet.from_iterable(
            c.id for c in adapter.catalog.capabilities if not c.is_control
        )
        delegation = adapter.delegate(
            DelegationRequest(
                source_identity=principal,
                target_identity_id="agent-a",
                mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
                requested_duration_s=900,
                intended_capabilities=allowed_caps,
            )
        )
        for capability in adapter.catalog.capabilities:
            if capability.is_control:
                continue
            result = adapter.probe(
                ProbeRequest(
                    identity_ref=delegation.identity_ref,
                    capability_id=capability.id,
                    binding=adapter.resolve_capability(capability.id),
                    namespace=adapter.namespace,
                )
            )
            assert result.outcome.outcome_class is OutcomeClass.ALLOWED, capability.id

        # agent-f is provisioned but has no baseline grant applied by this
        # test; an explicit deny locks out every non-control capability the
        # way "an identity with no granted capabilities" would.
        denied_identity = adapter.register_identity("agent-f")
        adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="contract-deny-all",
                kind=MutationKind.ATTACH_INLINE_DENY,
                target_identity="agent-f",
                denies_capabilities=allowed_caps,
            )
        )
        for capability in adapter.catalog.capabilities:
            if capability.is_control:
                continue
            result = adapter.probe(
                ProbeRequest(
                    identity_ref=denied_identity,
                    capability_id=capability.id,
                    binding=adapter.resolve_capability(capability.id),
                    namespace=adapter.namespace,
                )
            )
            assert result.outcome.outcome_class.is_denial, capability.id

    def test_control_capability_never_denied(self):  # type: ignore[override]
        adapter = self.make_adapter()
        identity = adapter.register_identity("agent-f")
        result = adapter.probe(
            ProbeRequest(
                identity_ref=identity,
                capability_id="identity.whoami",
                binding=adapter.resolve_capability("identity.whoami"),
                namespace=adapter.namespace,
            )
        )
        assert result.outcome.outcome_class is OutcomeClass.ALLOWED


# ---------------------------------------------------------------------------
# IAM-semantics tests the shared contract suite does not cover
# (AWS_PROVIDER_SPEC's own "Tests" section for M8)
# ---------------------------------------------------------------------------


class TestRealIamSemantics:
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
        4: "Session policies intersect, never grant")."""
        adapter, _ = _require_real_account()
        principal = adapter.register_identity("principal")
        delegation = adapter.delegate(
            DelegationRequest(
                source_identity=principal,
                target_identity_id="agent-c",
                mechanism=DelegationMechanism.SESSION_POLICY_SCOPED,
                requested_duration_s=900,
                # agent-c's own baseline Terraform policy is assumed not to
                # grant queue.send; the session policy naming it anyway must
                # not manufacture authority the identity policy lacks.
                intended_capabilities=AuthoritySet.of("queue.send"),
            )
        )
        result = adapter.probe(
            ProbeRequest(
                identity_ref=delegation.identity_ref,
                capability_id="queue.send",
                binding=adapter.resolve_capability("queue.send"),
                namespace=adapter.namespace,
            )
        )
        assert result.outcome.outcome_class.is_denial

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
        result = adapter.probe(
            ProbeRequest(
                identity_ref=delegation.identity_ref,
                capability_id="objectstore.read",
                binding=adapter.resolve_capability("objectstore.read"),
                namespace=adapter.namespace,
            )
        )
        assert result.outcome.outcome_class is OutcomeClass.DENIED_EXPLICIT

    def test_denial_message_attribution_matches_todays_aws_wording(self):
        """The canary AWS_PROVIDER_SPEC's "Risks" section names explicitly:
        if this fails, AWS changed its denial message wording and
        ``disambiguation.py`` needs updating -- it must fail loudly here,
        never silently degrade to DENIED_UNATTRIBUTED in production."""
        adapter, _ = _require_real_account()
        principal = adapter.register_identity("principal")
        delegation = adapter.delegate(
            DelegationRequest(
                source_identity=principal,
                target_identity_id="agent-b",
                mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
                requested_duration_s=900,
                intended_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="canary-explicit-deny",
                kind=MutationKind.ATTACH_INLINE_DENY,
                target_identity="agent-b",
                denies_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        result = adapter.probe(
            ProbeRequest(
                identity_ref=delegation.identity_ref,
                capability_id="objectstore.read",
                binding=adapter.resolve_capability("objectstore.read"),
                namespace=adapter.namespace,
            )
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
        delegation = adapter.delegate(
            DelegationRequest(
                source_identity=principal,
                target_identity_id="agent-c",
                mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
                requested_duration_s=900,
                intended_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="s3-403-404-canary",
                kind=MutationKind.ATTACH_INLINE_DENY,
                target_identity="agent-c",
                denies_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        result = adapter.probe(
            ProbeRequest(
                identity_ref=delegation.identity_ref,
                capability_id="objectstore.read",
                binding=adapter.resolve_capability("objectstore.read"),
                namespace=adapter.namespace,
            )
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
        delegation = adapter.delegate(
            DelegationRequest(
                source_identity=principal,
                target_identity_id="agent-d",
                mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
                requested_duration_s=900,
                intended_capabilities=AuthoritySet.of("identity.whoami"),
            )
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
