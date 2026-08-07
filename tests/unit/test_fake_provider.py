"""providers/fake/adapter.py -- FakeProviderAdapter-specific behavior not
already exercised by the adapter-agnostic contract suite
(tests/integration/test_provider_contract.py): preflight failure modes,
fault injection, all six MutationKind branches, the pending-transition
lifecycle (in-flight, settled, re-mutated-before-settling), and the
negative controls M05-fake-provider.md names.
"""

from __future__ import annotations

import pytest

from chainbreak.core.enums import DelegationMechanism, MutationKind, OutcomeClass
from chainbreak.core.errors import CapabilityResolutionError
from chainbreak.core.models import AuthoritySet, PolicyMutation, SafetyEnvelope
from chainbreak.providers.base.protocol import ProviderAdapter
from chainbreak.providers.base.types import DelegationRequest, ProbeRequest
from chainbreak.providers.fake.adapter import FakeProviderAdapter

pytestmark = pytest.mark.unit


def _envelope(adapter: FakeProviderAdapter, **overrides: object) -> SafetyEnvelope:
    fields: dict[str, object] = {
        "allowed_account_ids": (adapter.account_ref,),
        "allowed_regions": (adapter.region,),
        "namespace": adapter.namespace,
        "namespace_pattern": f"^{adapter.namespace}$",
    }
    fields.update(overrides)
    return SafetyEnvelope(**fields)  # type: ignore[arg-type]


class TestSatisfiesTheProtocolStructurally:
    def test_isinstance_check(self):
        assert isinstance(FakeProviderAdapter(), ProviderAdapter)


class TestAdvanceClock:
    def test_advances_the_virtual_clock(self):
        adapter = FakeProviderAdapter(seed=1)
        assert adapter.clock.now_ms == 0
        adapter.advance_clock(1500)
        assert adapter.clock.now_ms == 1500


class TestPreflight:
    def test_wrong_region_fails(self):
        adapter = FakeProviderAdapter(seed=1)
        report = adapter.preflight(_envelope(adapter, allowed_regions=("other-region",)))
        assert report.passed is False
        region_check = next(c for c in report.checks if c.name == "region")
        assert region_check.passed is False

    def test_wrong_namespace_fails(self):
        adapter = FakeProviderAdapter(seed=1, namespace="cb-abcd1234")
        report = adapter.preflight(_envelope(adapter, namespace="cb-11111111"))
        assert report.passed is False


class TestResolveCapability:
    def test_unknown_capability_raises(self):
        adapter = FakeProviderAdapter(seed=1)
        with pytest.raises(CapabilityResolutionError):
            adapter.resolve_capability("no.such.capability")


class TestDescribeEnvironment:
    def test_reflects_construction_parameters(self):
        adapter = FakeProviderAdapter(
            seed=1, namespace="cb-abcd1234", account_ref="111111111111", region="fake-region-2"
        )
        env = adapter.describe_environment()
        assert env.account_ref == "111111111111"
        assert env.region == "fake-region-2"
        assert env.namespace == "cb-abcd1234"
        assert env.adapter_version == adapter.adapter_version


class TestFaultInjection:
    def test_throttle_after_n_calls(self):
        adapter = FakeProviderAdapter(seed=1, namespace="cb-abcd1234", throttle_after_n_calls=1)
        identity = adapter.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        binding = adapter.resolve_capability("objectstore.read")
        request = ProbeRequest(
            identity_ref=identity,
            capability_id="objectstore.read",
            binding=binding,
            namespace="cb-abcd1234",
        )
        first = adapter.probe(request)
        assert first.outcome.outcome_class is OutcomeClass.ALLOWED
        second = adapter.probe(request)
        assert second.outcome.outcome_class is OutcomeClass.ERROR_TRANSIENT
        assert second.outcome.disambiguation_path == "fault_injection_throttle"

    def test_transient_error_rate_of_one_always_faults(self):
        adapter = FakeProviderAdapter(seed=1, namespace="cb-abcd1234", transient_error_rate=1.0)
        identity = adapter.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        binding = adapter.resolve_capability("objectstore.read")
        result = adapter.probe(
            ProbeRequest(
                identity_ref=identity,
                capability_id="objectstore.read",
                binding=binding,
                namespace="cb-abcd1234",
            )
        )
        assert result.outcome.outcome_class is OutcomeClass.ERROR_TRANSIENT
        assert result.outcome.disambiguation_path == "fault_injection_transient"

    def test_transient_error_rate_of_zero_never_faults(self):
        adapter = FakeProviderAdapter(seed=1, namespace="cb-abcd1234", transient_error_rate=0.0)
        identity = adapter.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        binding = adapter.resolve_capability("objectstore.read")
        for _ in range(20):
            result = adapter.probe(
                ProbeRequest(
                    identity_ref=identity,
                    capability_id="objectstore.read",
                    binding=binding,
                    namespace="cb-abcd1234",
                )
            )
            assert result.outcome.outcome_class is not OutcomeClass.ERROR_TRANSIENT


class TestRevokedSession:
    def test_probe_with_a_revoked_credential_is_denied(self):
        adapter = FakeProviderAdapter(seed=1, namespace="cb-abcd1234")
        principal = adapter.register_identity(
            "principal", allow=AuthoritySet.of("identity.delegate")
        )
        adapter.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
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
                mutation_id="m1",
                kind=MutationKind.REVOKE_OLDER_SESSIONS,
                target_identity="agent-a",
            )
        )
        binding = adapter.resolve_capability("objectstore.read")
        result = adapter.probe(
            ProbeRequest(
                identity_ref=delegation.identity_ref,
                capability_id="objectstore.read",
                binding=binding,
                namespace="cb-abcd1234",
            )
        )
        assert result.outcome.outcome_class is OutcomeClass.DENIED_IMPLICIT
        assert result.outcome.disambiguation_path == "session_revoked"


class TestMutationKinds:
    def _adapter_with_agent(self, **allow: str) -> tuple[FakeProviderAdapter, object]:
        adapter = FakeProviderAdapter(seed=1, namespace="cb-abcd1234")
        identity = adapter.register_identity(
            "agent-a", allow=AuthoritySet.of("objectstore.read", "objectstore.write")
        )
        return adapter, identity

    def _probe(self, adapter: FakeProviderAdapter, identity, capability_id: str):
        binding = adapter.resolve_capability(capability_id)
        return adapter.probe(
            ProbeRequest(
                identity_ref=identity,
                capability_id=capability_id,
                binding=binding,
                namespace="cb-abcd1234",
            )
        )

    def test_mutation_on_an_unregistered_identity_auto_registers_it(self):
        adapter = FakeProviderAdapter(seed=1, namespace="cb-abcd1234")
        receipt = adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="m1",
                kind=MutationKind.ATTACH_INLINE_DENY,
                target_identity="agent-never-seen",
                denies_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        assert receipt.confirmed is True
        assert adapter.engine.is_registered("agent-never-seen") is True

    def test_remove_inline_policy_produces_an_implicit_denial(self):
        adapter, identity = self._adapter_with_agent()
        adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="m1",
                kind=MutationKind.REMOVE_INLINE_POLICY,
                target_identity="agent-a",
                denies_capabilities=AuthoritySet.of("objectstore.write"),
            )
        )
        result = self._probe(adapter, identity, "objectstore.write")
        assert result.outcome.outcome_class is OutcomeClass.DENIED_IMPLICIT

    def test_replace_inline_policy_replaces_allow_and_deny_atomically(self):
        adapter, identity = self._adapter_with_agent()
        adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="m1",
                kind=MutationKind.REPLACE_INLINE_POLICY,
                target_identity="agent-a",
                grants_capabilities=AuthoritySet.of("keyvalue.read"),
                denies_capabilities=AuthoritySet.of("keyvalue.write"),
            )
        )
        assert self._probe(adapter, identity, "objectstore.read").outcome.outcome_class.is_denial
        assert self._probe(adapter, identity, "keyvalue.read").outcome.outcome_class is (
            OutcomeClass.ALLOWED
        )
        assert (
            self._probe(adapter, identity, "keyvalue.write").outcome.outcome_class
            is OutcomeClass.DENIED_EXPLICIT
        )

    def test_update_trust_policy_does_not_affect_a_live_session(self):
        # Built-in negative control (AWS_PROVIDER_SPEC section 4): must NOT
        # revoke anything.
        adapter, identity = self._adapter_with_agent()
        before = self._probe(adapter, identity, "objectstore.read").outcome.outcome_class
        adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="m1", kind=MutationKind.UPDATE_TRUST_POLICY, target_identity="agent-a"
            )
        )
        after = self._probe(adapter, identity, "objectstore.read").outcome.outcome_class
        assert before is after is OutcomeClass.ALLOWED

    def test_delete_session_policy_scope_does_not_affect_a_live_session(self):
        adapter, identity = self._adapter_with_agent()
        before = self._probe(adapter, identity, "objectstore.read").outcome.outcome_class
        adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="m1",
                kind=MutationKind.DELETE_SESSION_POLICY_SCOPE,
                target_identity="agent-a",
            )
        )
        after = self._probe(adapter, identity, "objectstore.read").outcome.outcome_class
        assert before is after is OutcomeClass.ALLOWED


class TestPendingTransitionLifecycle:
    def test_probe_during_the_pending_window_still_sees_pre_mutation_state(self):
        adapter = FakeProviderAdapter(seed=1, namespace="cb-abcd1234", propagation_delay_ms=2000)
        identity = adapter.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="m1",
                kind=MutationKind.ATTACH_INLINE_DENY,
                target_identity="agent-a",
                denies_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        adapter.advance_clock(500)  # still inside the 2000ms window
        binding = adapter.resolve_capability("objectstore.read")
        result = adapter.probe(
            ProbeRequest(
                identity_ref=identity,
                capability_id="objectstore.read",
                binding=binding,
                namespace="cb-abcd1234",
            )
        )
        assert result.outcome.outcome_class is OutcomeClass.ALLOWED
        assert "agent-a" in adapter._pending

    def test_probe_after_settling_uses_authoritative_state_and_clears_pending(self):
        adapter = FakeProviderAdapter(seed=1, namespace="cb-abcd1234", propagation_delay_ms=1000)
        identity = adapter.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="m1",
                kind=MutationKind.ATTACH_INLINE_DENY,
                target_identity="agent-a",
                denies_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        assert "agent-a" in adapter._pending
        adapter.advance_clock(1000)
        binding = adapter.resolve_capability("objectstore.read")
        result = adapter.probe(
            ProbeRequest(
                identity_ref=identity,
                capability_id="objectstore.read",
                binding=binding,
                namespace="cb-abcd1234",
            )
        )
        assert result.outcome.outcome_class is OutcomeClass.DENIED_EXPLICIT
        assert "agent-a" not in adapter._pending

    def test_a_second_mutation_before_the_first_settles_folds_it_in(self):
        adapter = FakeProviderAdapter(seed=1, namespace="cb-abcd1234", propagation_delay_ms=5000)
        adapter.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="m1",
                kind=MutationKind.ATTACH_INLINE_DENY,
                target_identity="agent-a",
                denies_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        # A second mutation arrives before the first has settled -- must not
        # raise, and must replace the first's pending transition.
        adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="m2",
                kind=MutationKind.REMOVE_INLINE_POLICY,
                target_identity="agent-a",
                denies_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        assert "agent-a" in adapter._pending


class TestNegativeControlMechanisms:
    """M05-fake-provider.md's own negative controls, verified at the level
    that actually exists at M5: the fake's mechanism, not the full
    scenario -> analysis pipeline (M7 classifies AUTHORITY_EXPANSION; M12's
    poller classifies NON_MONOTONIC_TRANSITION). What M5 owes is that the
    fake is *capable* of producing the raw behavior those future classifiers
    will act on -- proven here directly against the adapter."""

    def test_over_grant_produces_an_allowed_result_outside_the_intended_set(self):
        # "Configure the fake to grant a capability the scenario does not
        # intend" -- an over-broad identity policy (a misconfiguration
        # injected at the identity-policy level, matching how
        # AWS_PROVIDER_SPEC section 4 says the scope-attenuation negative
        # control is actually injected, not via a session policy that could
        # never grant beyond the intersection).
        adapter = FakeProviderAdapter(seed=1, namespace="cb-abcd1234")
        intended = AuthoritySet.of("objectstore.read")
        over_broad = intended | AuthoritySet.of("objectstore.write")
        identity = adapter.register_identity("agent-a", allow=over_broad)

        binding = adapter.resolve_capability("objectstore.write")
        result = adapter.probe(
            ProbeRequest(
                identity_ref=identity,
                capability_id="objectstore.write",
                binding=binding,
                namespace="cb-abcd1234",
            )
        )
        assert result.outcome.outcome_class is OutcomeClass.ALLOWED
        assert "objectstore.write" not in intended  # this is the expansion

    def test_propagation_delay_produces_a_measurable_transition_window(self):
        adapter = FakeProviderAdapter(seed=1, namespace="cb-abcd1234", propagation_delay_ms=2000)
        identity = adapter.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="m1",
                kind=MutationKind.ATTACH_INLINE_DENY,
                target_identity="agent-a",
                denies_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        binding = adapter.resolve_capability("objectstore.read")

        def _probe_at(ms: int) -> OutcomeClass:
            adapter.clock.advance(ms - adapter.clock.now_ms)
            return adapter.probe(
                ProbeRequest(
                    identity_ref=identity,
                    capability_id="objectstore.read",
                    binding=binding,
                    namespace="cb-abcd1234",
                )
            ).outcome.outcome_class

        # Bracket the transition down to 1ms: the last still-allowed sample
        # and the first denied sample are exactly 2000ms apart, matching the
        # configured propagation_delay_ms.
        assert _probe_at(1999) is OutcomeClass.ALLOWED
        assert _probe_at(2000) is OutcomeClass.DENIED_EXPLICIT

    def test_oscillation_flags_a_genuinely_non_monotonic_sequence(self):
        adapter = FakeProviderAdapter(
            seed=3,
            namespace="cb-abcd1234",
            propagation_delay_ms=2000,
            oscillate=True,
        )
        identity = adapter.register_identity("agent-a", allow=AuthoritySet.of("objectstore.read"))
        adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="m1",
                kind=MutationKind.ATTACH_INLINE_DENY,
                target_identity="agent-a",
                denies_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        binding = adapter.resolve_capability("objectstore.read")

        # Sample exactly at (and 1ms either side of) each scheduled flip
        # point, read from the transition the mutation actually scheduled --
        # deterministic regardless of seed, rather than hoping a fixed grid
        # happens to land inside a randomly placed flip window.
        flips = adapter._pending["agent-a"].visibility.oscillation_flips_ms
        assert len(flips) > 0
        sample_points = sorted({0, *flips, *(f - 1 for f in flips), *(f + 1 for f in flips), 2000})

        sequence = []
        last_ms = 0
        for ms in sample_points:
            adapter.clock.advance(ms - last_ms)
            last_ms = ms
            result = adapter.probe(
                ProbeRequest(
                    identity_ref=identity,
                    capability_id="objectstore.read",
                    binding=binding,
                    namespace="cb-abcd1234",
                )
            )
            sequence.append(result.outcome.outcome_class)

        # Non-monotonic: at least one ALLOWED reappears after a DENIED, which
        # a naive "first transition wins" poller would get wrong.
        seen_denied = False
        allowed_after_denied = False
        for outcome_class in sequence:
            if outcome_class is not OutcomeClass.ALLOWED:
                seen_denied = True
            elif seen_denied:
                allowed_after_denied = True
        assert allowed_after_denied
