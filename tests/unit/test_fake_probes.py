"""providers/fake/probes.py -- precondition failure and denial-attribution
packaging, at the unit level (the contract suite exercises the common paths;
this covers the two branches specific to ``build_probe_outcome`` itself)."""

from __future__ import annotations

import pytest

from chainbreak.core.enums import DelegationMechanism, DenialAttribution, OutcomeClass
from chainbreak.core.models import AuthoritySet
from chainbreak.providers.base.types import DelegationRequest, ProbeRequest
from chainbreak.providers.fake.adapter import FakeProviderAdapter

pytestmark = pytest.mark.unit


class TestPreconditionFailure:
    def test_missing_marker_produces_error_infrastructure_not_a_denial(self):
        adapter = FakeProviderAdapter(seed=1, namespace="cb-abcd1234")
        adapter.markers.objectstore_marker_present = False
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
        assert result.outcome.outcome_class is OutcomeClass.ERROR_INFRASTRUCTURE
        assert result.outcome.disambiguation_path == "precondition_failed"
        # Never a denial: CAPABILITY_MODEL.md section 4 rule 3.
        assert result.outcome.outcome_class.is_denial is False


class TestSessionPolicyAttribution:
    def test_capability_the_identity_holds_but_the_session_narrowed_away(self):
        adapter = FakeProviderAdapter(seed=1, namespace="cb-abcd1234")
        principal = adapter.register_identity(
            "principal", allow=AuthoritySet.of("identity.delegate")
        )
        adapter.register_identity(
            "agent-a", allow=AuthoritySet.of("objectstore.read", "objectstore.write")
        )
        delegation = adapter.delegate(
            DelegationRequest(
                source_identity=principal,
                target_identity_id="agent-a",
                mechanism=DelegationMechanism.SESSION_POLICY_SCOPED,
                requested_duration_s=900,
                intended_capabilities=AuthoritySet.of("objectstore.read"),
            )
        )
        binding = adapter.resolve_capability("objectstore.write")
        result = adapter.probe(
            ProbeRequest(
                identity_ref=delegation.identity_ref,
                capability_id="objectstore.write",
                binding=binding,
                namespace="cb-abcd1234",
            )
        )
        assert result.outcome.outcome_class is OutcomeClass.DENIED_IMPLICIT
        assert result.outcome.denial_attribution is DenialAttribution.SESSION_POLICY
