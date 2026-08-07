"""The shared provider contract suite (ARCHITECTURE.md section 3.8).

``ProviderContractSuite`` is adapter-agnostic: it exercises only the
``ProviderAdapter`` Protocol surface, never anything fake-specific. The AWS
adapter (M8) is expected to subclass it too, supplying a real-account
``make_adapter``/``envelope`` pair gated behind the ``aws`` marker -- "both
adapters run it unmodified" is the actual point of this file existing
separately from ``tests/unit/``.
"""

from __future__ import annotations

import pytest

from chainbreak.core.enums import DelegationMechanism, MutationKind, OutcomeClass
from chainbreak.core.errors import MutationTargetForbiddenError, NamespaceViolationError
from chainbreak.core.models import (
    AuthoritySet,
    IdentityRef,
    PolicyMutation,
    Provider,
    SafetyEnvelope,
)
from chainbreak.providers.base.types import DelegationRequest, ProbeRequest
from chainbreak.providers.fake.adapter import FakeProviderAdapter

pytestmark = pytest.mark.integration


class ProviderContractSuite:
    """Subclasses provide ``make_adapter()`` and ``foreign_envelope()``."""

    def make_adapter(self) -> FakeProviderAdapter:
        raise NotImplementedError

    def wrong_account_id(self) -> str:
        raise NotImplementedError

    def _envelope(self, adapter: FakeProviderAdapter, *, account_ref: str | None = None):
        return SafetyEnvelope(
            allowed_account_ids=(account_ref or adapter.account_ref,),
            allowed_regions=(adapter.region,),
            namespace=adapter.namespace,
            namespace_pattern=f"^{adapter.namespace}$",
        )

    # -- preflight ----------------------------------------------------

    def test_preflight_passes_with_correct_account(self):
        adapter = self.make_adapter()
        report = adapter.preflight(self._envelope(adapter))
        assert report.passed is True

    def test_preflight_rejects_wrong_account(self):
        adapter = self.make_adapter()
        report = adapter.preflight(self._envelope(adapter, account_ref=self.wrong_account_id()))
        assert report.passed is False

    # -- namespace (SI-2) -----------------------------------------------

    def test_out_of_namespace_probe_refused_before_any_evaluation(self):
        adapter = self.make_adapter()
        principal = adapter.register_identity(
            "principal", allow=AuthoritySet.of("objectstore.read")
        )
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

    def test_out_of_namespace_delegation_refused(self):
        adapter = self.make_adapter()
        foreign = IdentityRef(
            provider=Provider.FAKE,
            kind="role",
            value="fake:000000000000:role/cb-ffffffff-someone",
            region=adapter.region,
            account_ref="000000000000",
        )
        with pytest.raises(NamespaceViolationError):
            adapter.delegate(
                DelegationRequest(
                    source_identity=foreign,
                    target_identity_id="agent-a",
                    mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
                    requested_duration_s=900,
                    intended_capabilities=AuthoritySet.of("objectstore.read"),
                )
            )

    # -- capability classification --------------------------------------

    def test_every_capability_classifies_allow_and_deny_correctly(self):
        adapter = self.make_adapter()
        allowed_caps = AuthoritySet.from_iterable(
            c.id for c in adapter.catalog.capabilities if not c.is_control
        )
        principal = adapter.register_identity("principal", allow=allowed_caps)

        for capability in adapter.catalog.capabilities:
            if capability.is_control:
                continue
            binding = adapter.resolve_capability(capability.id)
            allowed_result = adapter.probe(
                ProbeRequest(
                    identity_ref=principal,
                    capability_id=capability.id,
                    binding=binding,
                    namespace=adapter.namespace,
                )
            )
            assert allowed_result.outcome.outcome_class is OutcomeClass.ALLOWED, capability.id

        denied_identity = adapter.register_identity("agent-denied")
        for capability in adapter.catalog.capabilities:
            if capability.is_control:
                continue
            binding = adapter.resolve_capability(capability.id)
            denied_result = adapter.probe(
                ProbeRequest(
                    identity_ref=denied_identity,
                    capability_id=capability.id,
                    binding=binding,
                    namespace=adapter.namespace,
                )
            )
            assert denied_result.outcome.outcome_class.is_denial, capability.id

    def test_control_capability_never_denied(self):
        adapter = self.make_adapter()
        # No capabilities granted at all -- identity.whoami must still pass.
        identity = adapter.register_identity("agent-empty")
        binding = adapter.resolve_capability("identity.whoami")
        result = adapter.probe(
            ProbeRequest(
                identity_ref=identity,
                capability_id="identity.whoami",
                binding=binding,
                namespace=adapter.namespace,
            )
        )
        assert result.outcome.outcome_class is OutcomeClass.ALLOWED

    # -- delegation -------------------------------------------------------

    def test_delegation_returns_metadata_with_no_secret_in_the_record(self):
        adapter = self.make_adapter()
        principal = adapter.register_identity(
            "principal", allow=AuthoritySet.of("identity.delegate")
        )
        result = adapter.delegate(
            DelegationRequest(
                source_identity=principal,
                target_identity_id="agent-a",
                mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
                requested_duration_s=900,
                intended_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        # CredentialRecord is metadata-only by construction (EV-1) -- the
        # secret exists (reveal() returns real material)...
        assert len(result.credential.secret_access_key.reveal()) > 0
        # ...but the record that's safe to serialize contains none of it:
        # round-tripping through canonical JSON must not raise, and the
        # actual secret string must not appear anywhere in the output.
        from chainbreak.core.canonical import dumps

        dumped = dumps(result.record)
        assert result.credential.secret_access_key.reveal() not in dumped
        assert result.credential.session_token.reveal() not in dumped

    # -- mutation -----------------------------------------------------------

    def test_mutation_returns_a_confirmed_receipt(self):
        adapter = self.make_adapter()
        adapter.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        receipt = adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="m1",
                kind=MutationKind.ATTACH_INLINE_DENY,
                target_identity="agent-a",
                denies_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        assert receipt.confirmed is True

    def test_mutation_refuses_to_target_a_protected_identity(self):
        adapter = self.make_adapter()
        with pytest.raises(MutationTargetForbiddenError):
            adapter.apply_policy_mutation(
                PolicyMutation(
                    mutation_id="m2",
                    kind=MutationKind.ATTACH_INLINE_DENY,
                    target_identity="principal",
                    denies_capabilities=AuthoritySet.of("objectstore.read"),
                )
            )

    # -- lifetime capping ---------------------------------------------------

    def test_chained_role_lifetime_is_capped_and_reported(self):
        adapter = self.make_adapter()
        principal = adapter.register_identity(
            "principal", allow=AuthoritySet.of("identity.delegate")
        )
        result = adapter.delegate(
            DelegationRequest(
                source_identity=principal,
                target_identity_id="agent-a",
                mechanism=DelegationMechanism.ROLE_CHAIN,
                requested_duration_s=7200,
                intended_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        assert result.record.lifetime_capped is True
        assert result.record.granted_duration_s == 3600

    # -- snapshot -------------------------------------------------------

    def test_snapshot_returns_stable_fingerprints(self):
        adapter = self.make_adapter()
        principal = adapter.register_identity(
            "principal", allow=AuthoritySet.of("objectstore.read")
        )
        first = adapter.snapshot_policy_state(principal)
        second = adapter.snapshot_policy_state(principal)
        assert first.policies[0].document_sha256 == second.policies[0].document_sha256

    def test_snapshot_changes_after_a_mutation(self):
        adapter = self.make_adapter()
        principal = adapter.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        before = adapter.snapshot_policy_state(principal)
        adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="m3",
                kind=MutationKind.ATTACH_INLINE_DENY,
                target_identity="agent-a",
                denies_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        after = adapter.snapshot_policy_state(principal)
        assert before.policies[0].document_sha256 != after.policies[0].document_sha256


class TestFakeProviderContract(ProviderContractSuite):
    def make_adapter(self) -> FakeProviderAdapter:
        return FakeProviderAdapter(seed=1, namespace="cb-abcd1234")

    def wrong_account_id(self) -> str:
        return "000000000000"
