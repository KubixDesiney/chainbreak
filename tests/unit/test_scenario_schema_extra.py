"""scenarios/schema.py -- validator failure branches not exercised by
tests/scenarios/test_scenario_corpus.py (which only ever sees *valid*
scenarios) or tests/unit/test_scenario_loader.py's four documented exit-code
fixtures.

Not part of M3's own required-files list, but M3's coverage acceptance
criterion (``scenarios/`` >= 90%, TESTING.md) is a hard bar on the whole
package, and this module -- structural layer of the whole five-stage
pipeline -- predates M3 and had roughly thirty untested validator branches.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from chainbreak.scenarios.schema import (
    DelegationSpec,
    Execution,
    ExpectationSpec,
    IdentitySpec,
    PhaseSpec,
    ScenarioDocument,
    SessionPolicySpec,
)

pytestmark = pytest.mark.unit


class TestExecution:
    def test_timing_sensitive_requires_serial_concurrency(self):
        with pytest.raises(ValidationError, match="concurrency: 1"):
            Execution(timing_sensitive=True, concurrency=4)

    def test_timing_sensitive_with_serial_concurrency_is_accepted(self):
        Execution(timing_sensitive=True, concurrency=1)


class TestIdentitySpec:
    def test_root_without_capabilities_rejected(self):
        with pytest.raises(ValidationError, match="root identity must declare"):
            IdentitySpec(
                id="principal",
                role="root",
                provider_binding={"terraform_output": "principal_role_arn"},
            )

    def test_agent_with_capabilities_rejected(self):
        with pytest.raises(ValidationError, match="authority is derived from its inbound edge"):
            IdentitySpec(
                id="agent-a",
                role="agent",
                provider_binding={"terraform_output": "agent_a_role_arn"},
                capabilities=("objectstore.read",),
            )

    def test_agent_with_expect_capabilities_is_accepted(self):
        IdentitySpec(
            id="agent-a",
            role="agent",
            provider_binding={"terraform_output": "agent_a_role_arn"},
            expect_capabilities=("objectstore.read",),
        )


class TestSessionPolicySpec:
    def test_neither_source_rejected(self):
        with pytest.raises(ValidationError, match="exactly one of"):
            SessionPolicySpec(derive_from=None, inline_ref=None)

    def test_both_sources_rejected(self):
        with pytest.raises(ValidationError, match="exactly one of"):
            SessionPolicySpec(derive_from="intended_capabilities", inline_ref="ref-1")


class TestDelegationSpec:
    def _kwargs(self, **overrides):
        base = {
            "id": "hop-1",
            "from": "principal",
            "to": "agent-a",
            "mechanism": "ROLE_CHAIN",
            "intended_capabilities": ("objectstore.read",),
        }
        base.update(overrides)
        return base

    def test_reserved_mechanism_rejected(self):
        with pytest.raises(ValidationError, match="reserved for a future version"):
            DelegationSpec(**self._kwargs(mechanism="FEDERATED_TOKEN"))

    def test_self_delegation_rejected(self):
        with pytest.raises(ValidationError, match="self-delegation"):
            DelegationSpec(**self._kwargs(**{"from": "agent-a", "to": "agent-a"}))

    def test_scoped_mechanism_requires_session_policy(self):
        with pytest.raises(ValidationError, match="requires a session_policy block"):
            DelegationSpec(**self._kwargs(mechanism="SESSION_POLICY_SCOPED"))

    def test_scoped_mechanism_with_session_policy_is_accepted(self):
        DelegationSpec(
            **self._kwargs(
                mechanism="SESSION_POLICY_SCOPED",
                session_policy={"derive_from": "intended_capabilities"},
            )
        )


class TestPhaseSpecKindRequirements:
    def test_probe_requires_targets(self):
        with pytest.raises(ValidationError, match="PROBE requires targets"):
            PhaseSpec(name="p1", kind="PROBE", targets=())

    def test_mutate_requires_mutation_block(self):
        with pytest.raises(ValidationError, match="MUTATE requires a mutation block"):
            PhaseSpec(name="p1", kind="MUTATE")

    def test_poll_requires_target_identity_and_capability(self):
        with pytest.raises(ValidationError, match="POLL requires"):
            PhaseSpec(name="p1", kind="POLL")

    def test_deferred_execution_requires_credential_source(self):
        with pytest.raises(ValidationError, match="DEFERRED_EXECUTION requires"):
            PhaseSpec(name="p1", kind="DEFERRED_EXECUTION")

    def test_deferred_execution_requires_target_identity(self):
        with pytest.raises(ValidationError, match="DEFERRED_EXECUTION requires target_identity"):
            PhaseSpec(name="p1", kind="DEFERRED_EXECUTION", credential_source="phase:baseline")

    def test_wait_requires_positive_wait_seconds(self):
        with pytest.raises(ValidationError, match="WAIT requires a positive wait_seconds"):
            PhaseSpec(name="p1", kind="WAIT", wait_seconds=0)

    def test_task_requires_a_task_reference(self):
        with pytest.raises(ValidationError, match="TASK requires a task reference"):
            PhaseSpec(name="p1", kind="TASK")


class TestExpectationSpecKindRequirements:
    def test_node_authority_requires_identity(self):
        with pytest.raises(ValidationError, match="node_authority requires an identity"):
            ExpectationSpec(kind="node_authority", deny=("objectstore.write",))

    def test_node_authority_requires_nonempty_deny(self):
        with pytest.raises(ValidationError, match="non-empty deny list"):
            ExpectationSpec(kind="node_authority", identity="agent-a")

    def test_node_authority_allow_deny_overlap_rejected(self):
        with pytest.raises(ValidationError, match="both allow and deny"):
            ExpectationSpec(
                kind="node_authority",
                identity="agent-a",
                allow=("objectstore.read",),
                deny=("objectstore.read",),
            )

    def test_attenuation_monotone_requires_path_of_two(self):
        with pytest.raises(ValidationError, match="path of at least two"):
            ExpectationSpec(kind="attenuation_monotone", path=("agent-a",))

    def test_no_first_divergence_requires_path_of_two(self):
        with pytest.raises(ValidationError, match="path of at least two"):
            ExpectationSpec(kind="no_first_divergence", path=())

    def test_revocation_within_requires_identity_capability_and_max_seconds(self):
        with pytest.raises(ValidationError, match="revocation_within requires"):
            ExpectationSpec(kind="revocation_within")

    def test_revocation_within_assertive_requires_justification(self):
        with pytest.raises(ValidationError, match="requires a justification"):
            ExpectationSpec(
                kind="revocation_within",
                identity="agent-a",
                capability="objectstore.read",
                max_seconds=5.0,
                severity="assertive",
                justification="too short",
            )

    def test_revocation_within_assertive_with_justification_is_accepted(self):
        ExpectationSpec(
            kind="revocation_within",
            identity="agent-a",
            capability="objectstore.read",
            max_seconds=5.0,
            severity="assertive",
            justification="a sufficiently long justification for an assertive threshold",
        )

    def test_task_contract_requires_task_reference(self):
        with pytest.raises(ValidationError, match="task_contract requires a task"):
            ExpectationSpec(kind="task_contract")


def _minimal_document(**spec_overrides):
    spec = {
        "provider": "aws",
        "identities": [
            {
                "id": "principal",
                "role": "root",
                "provider_binding": {"terraform_output": "principal_role_arn"},
                "capabilities": ["objectstore.read"],
            },
        ],
        "phases": [{"name": "baseline", "kind": "PROBE", "targets": ["principal"]}],
    }
    spec.update(spec_overrides)
    return {
        "apiVersion": "chainbreak.dev/v1alpha1",
        "kind": "Scenario",
        "metadata": {
            "id": "referential-integrity-test",
            "version": "1.0.0",
            "family": "scope-attenuation",
            "title": "Referential integrity fixture",
            "description": "Exercises ScenarioSpec._referential_integrity branches.",
            "authors": ["operator"],
        },
        "spec": spec,
    }


class TestScenarioSpecReferentialIntegrity:
    def test_duplicate_identity_ids_rejected(self):
        raw = _minimal_document(
            identities=[
                {
                    "id": "principal",
                    "role": "root",
                    "provider_binding": {"terraform_output": "a"},
                    "capabilities": ["objectstore.read"],
                },
                {
                    "id": "principal",
                    "role": "agent",
                    "provider_binding": {"terraform_output": "b"},
                },
            ]
        )
        with pytest.raises(ValidationError, match="duplicate identity ids"):
            ScenarioDocument(**raw)

    def test_not_exactly_one_root_rejected(self):
        raw = _minimal_document(
            identities=[
                {
                    "id": "root-1",
                    "role": "root",
                    "provider_binding": {"terraform_output": "a"},
                    "capabilities": ["objectstore.read"],
                },
                {
                    "id": "root-2",
                    "role": "root",
                    "provider_binding": {"terraform_output": "b"},
                    "capabilities": ["objectstore.read"],
                },
            ]
        )
        with pytest.raises(ValidationError, match="exactly one root identity"):
            ScenarioDocument(**raw)

    def test_delegation_references_unknown_identity_rejected(self):
        raw = _minimal_document(
            delegations=[
                {
                    "id": "hop-1",
                    "from": "principal",
                    "to": "ghost",
                    "mechanism": "ROLE_CHAIN",
                    "intended_capabilities": ["objectstore.read"],
                }
            ]
        )
        with pytest.raises(ValidationError, match="references unknown"):
            ScenarioDocument(**raw)

    def test_duplicate_phase_names_rejected(self):
        raw = _minimal_document(
            phases=[
                {"name": "baseline", "kind": "PROBE", "targets": ["principal"]},
                {"name": "baseline", "kind": "PROBE", "targets": ["principal"]},
            ]
        )
        with pytest.raises(ValidationError, match="duplicate phase names"):
            ScenarioDocument(**raw)

    def test_phase_targets_unknown_identity_rejected(self):
        raw = _minimal_document(
            phases=[{"name": "baseline", "kind": "PROBE", "targets": ["ghost"]}]
        )
        with pytest.raises(ValidationError, match="targets unknown identity"):
            ScenarioDocument(**raw)

    def test_phase_target_identity_unknown_rejected(self):
        raw = _minimal_document(
            phases=[
                {
                    "name": "poll-1",
                    "kind": "POLL",
                    "target_identity": "ghost",
                    "capability": "objectstore.read",
                }
            ]
        )
        with pytest.raises(ValidationError, match="targets unknown identity"):
            ScenarioDocument(**raw)

    def test_phase_mutation_target_unknown_rejected(self):
        raw = _minimal_document(
            phases=[
                {
                    "name": "mutate-1",
                    "kind": "MUTATE",
                    "mutation": {"target_identity": "ghost", "kind": "ATTACH_INLINE_DENY"},
                }
            ]
        )
        with pytest.raises(ValidationError, match="mutates unknown identity"):
            ScenarioDocument(**raw)

    def test_phase_task_reference_unknown_rejected(self):
        raw = _minimal_document(phases=[{"name": "task-1", "kind": "TASK", "task": "ghost-task"}])
        with pytest.raises(ValidationError, match="references unknown task"):
            ScenarioDocument(**raw)

    def test_phase_credential_source_unknown_rejected(self):
        raw = _minimal_document(
            phases=[
                {
                    "name": "deferred-1",
                    "kind": "DEFERRED_EXECUTION",
                    "targets": ["principal"],
                    "target_identity": "principal",
                    "credential_source": "phase:ghost-phase",
                }
            ]
        )
        with pytest.raises(ValidationError, match="references unknown phase"):
            ScenarioDocument(**raw)

    def test_task_references_unknown_identity_rejected(self):
        raw = _minimal_document(
            tasks=[
                {
                    "id": "task-1",
                    "identity": "ghost",
                    "requires_capabilities": ["objectstore.read"],
                    "steps": [{"use": "objectstore.read"}],
                }
            ]
        )
        with pytest.raises(ValidationError, match="references unknown identity"):
            ScenarioDocument(**raw)

    def test_expectation_references_unknown_identity_rejected(self):
        raw = _minimal_document(
            expectations=[
                {
                    "kind": "node_authority",
                    "identity": "ghost",
                    "deny": ["objectstore.write"],
                }
            ]
        )
        with pytest.raises(ValidationError, match="references unknown identity"):
            ScenarioDocument(**raw)

    def test_expectation_path_references_unknown_identity_rejected(self):
        raw = _minimal_document(
            expectations=[{"kind": "attenuation_monotone", "path": ["principal", "ghost"]}]
        )
        with pytest.raises(ValidationError, match="path references unknown identity"):
            ScenarioDocument(**raw)

    def test_expectation_references_unknown_task_rejected(self):
        raw = _minimal_document(expectations=[{"kind": "task_contract", "task": "ghost-task"}])
        with pytest.raises(ValidationError, match="references unknown task"):
            ScenarioDocument(**raw)


class TestNegativeControlMarking:
    def test_negative_control_without_nc_prefix_rejected(self):
        raw = _minimal_document()
        raw["metadata"]["id"] = "not-marked"
        raw["spec"]["negative_control"] = {
            "kind": "INTENT_EXCEEDS_PARENT",
            "rationale": "a rationale long enough to pass the forty-character minimum length",
            "expect_finding": {"type": "AUTHORITY_EXPANSION"},
        }
        with pytest.raises(ValidationError, match="must use an id beginning with 'nc-'"):
            ScenarioDocument(**raw)

    def test_nc_prefixed_id_without_negative_control_rejected(self):
        raw = _minimal_document()
        raw["metadata"]["id"] = "nc-not-actually-a-control"
        with pytest.raises(ValidationError, match="declares no negative_control"):
            ScenarioDocument(**raw)
