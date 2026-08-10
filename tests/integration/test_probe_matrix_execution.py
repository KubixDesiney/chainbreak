"""``execution/matrix.py`` and ``execution/preconditions.py`` and ``execution/
delegation.py``'s F6 re-delegation, exercised directly rather than only
through the full orchestrator: trial repetition, C-2 precondition discard,
and the credential-lifetime re-delegation threshold.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from chainbreak.capabilities.loader import load_catalog
from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.enums import DelegationMechanism, PlanPhase
from chainbreak.core.errors import PreconditionFailedError
from chainbreak.core.ids import digest_ref
from chainbreak.core.models import CredentialRecord
from chainbreak.execution import delegation, matrix
from chainbreak.providers.base.types import DelegationRequest
from chainbreak.providers.fake.adapter import FakeProviderAdapter
from chainbreak.providers.fake.probes import build_fake_preconditions
from chainbreak.providers.fake.session import virtual_ms_to_datetime
from chainbreak.scenarios.loader import load_and_compile

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
BASIC_SCENARIO = REPO_ROOT / "scenarios" / "scope-attenuation" / "basic.yaml"


def _materialized(registry: BindingRegistry, *, seed: int = 1):
    compiled = load_and_compile(BASIC_SCENARIO, registry=registry)
    adapter = FakeProviderAdapter(seed=seed)
    return compiled, adapter, delegation.materialize_graph(adapter, compiled.graph)


class TestTrialRepetition:
    def test_every_capability_gets_exactly_matrix_trials_observations(
        self, synthetic_aws_registry: BindingRegistry
    ) -> None:
        compiled, adapter, materialized = _materialized(synthetic_aws_registry)
        catalog = load_catalog()
        after_delegation = next(
            m for m in compiled.probe_matrices if m.phase_name == "after-delegation"
        )
        provisioning_ref = adapter.register_identity("bootstrap")

        run = matrix.run_probe_matrix(
            adapter,
            after_delegation,
            materialized,
            catalog,
            build_fake_preconditions(adapter.markers),
            run_id="run-trials-1",
            phase=PlanPhase.POST_DELEGATION,
            seed=1,
            provisioning_ref=provisioning_ref,
            now=datetime.now(UTC),
            salt="test-salt:",
            namespace=adapter.namespace,
        )

        non_control = [c for c in after_delegation.capabilities if c != "identity.whoami"]
        for identity_id in after_delegation.identities:
            for capability_id in non_control:
                trials = [
                    o
                    for o in run.observations
                    if o.identity_id == identity_id and o.capability_id == capability_id
                ]
                assert len(trials) == after_delegation.trials
                assert {t.trial for t in trials} == set(range(1, after_delegation.trials + 1))


class TestShuffleOrderIsReproducible:
    def test_same_seed_same_matrix_same_identity_reproduces_the_order(
        self, synthetic_aws_registry: BindingRegistry
    ) -> None:
        compiled, adapter, materialized = _materialized(synthetic_aws_registry)
        catalog = load_catalog()
        after_delegation = next(
            m for m in compiled.probe_matrices if m.phase_name == "after-delegation"
        )
        provisioning_ref = adapter.register_identity("bootstrap")

        def _orders(seed: int) -> list[tuple[str, ...]]:
            run = matrix.run_probe_matrix(
                adapter,
                after_delegation,
                materialized,
                catalog,
                build_fake_preconditions(adapter.markers),
                run_id="run-shuffle",
                phase=PlanPhase.POST_DELEGATION,
                seed=seed,
                provisioning_ref=provisioning_ref,
                now=datetime.now(UTC),
                salt="test-salt:",
                namespace=adapter.namespace,
            )
            return [tuple(e["capability_order"]) for e in run.events]

        assert _orders(1) == _orders(1)
        assert _orders(1) != _orders(2)


class TestPreconditionFailureDiscardsTheWholeMatrix:
    def test_missing_marker_raises_before_any_probe_in_the_matrix(
        self, synthetic_aws_registry: BindingRegistry
    ) -> None:
        compiled, adapter, materialized = _materialized(synthetic_aws_registry)
        catalog = load_catalog()
        after_delegation = next(
            m for m in compiled.probe_matrices if m.phase_name == "after-delegation"
        )
        provisioning_ref = adapter.register_identity("bootstrap")

        adapter.markers.objectstore_marker_present = False

        with pytest.raises(PreconditionFailedError) as excinfo:
            matrix.run_probe_matrix(
                adapter,
                after_delegation,
                materialized,
                catalog,
                build_fake_preconditions(adapter.markers),
                run_id="run-precondition-1",
                phase=PlanPhase.POST_DELEGATION,
                seed=1,
                provisioning_ref=provisioning_ref,
                now=datetime.now(UTC),
                salt="test-salt:",
                namespace=adapter.namespace,
            )
        assert "objectstore.marker_present" in excinfo.value.context["preconditions"]

    def test_all_markers_present_the_matrix_runs_to_completion(
        self, synthetic_aws_registry: BindingRegistry
    ) -> None:
        """`scope-attenuation/basic.yaml`'s `probe_universe: scenario` gives
        every matrix the same, full capability set (verified separately),
        so there is no matrix in *this* scenario genuinely unaffected by the
        objectstore precondition -- what this asserts instead is the
        complementary case: with every fake marker present (the default),
        the precondition check passes and the matrix is not discarded."""
        compiled, adapter, materialized = _materialized(synthetic_aws_registry)
        catalog = load_catalog()
        baseline = next(m for m in compiled.probe_matrices if m.phase_name == "baseline")
        provisioning_ref = adapter.register_identity("bootstrap")

        run = matrix.run_probe_matrix(
            adapter,
            baseline,
            materialized,
            catalog,
            build_fake_preconditions(adapter.markers),
            run_id="run-precondition-2",
            phase=PlanPhase.BASELINE,
            seed=1,
            provisioning_ref=provisioning_ref,
            now=datetime.now(UTC),
            salt="test-salt:",
            namespace=adapter.namespace,
        )
        assert run.observations
        assert all(o.preconditions_verified for o in run.observations)


class TestCredentialLifetimeReDelegation:
    """F6: credential lifetime checked before each matrix; re-delegate if
    remaining lifetime is under 2x the estimated matrix duration."""

    def _credential(self, *, now: datetime, remaining_s: float) -> CredentialRecord:
        return CredentialRecord(
            credential_id="cred_old",
            identity_id="agent-a",
            mechanism=DelegationMechanism.ROLE_CHAIN,
            issued_at=now - timedelta(hours=1),
            expires_at=now + timedelta(seconds=remaining_s),
            requested_duration_s=3600,
            granted_duration_s=3600,
            session_name_hash=digest_ref("session", "salt:"),
            access_key_id_hash=digest_ref("key", "salt:"),
        )

    def test_needs_redelegation_below_the_2x_threshold(self) -> None:
        now = datetime.now(UTC)
        credential = self._credential(now=now, remaining_s=5.0)
        assert delegation.needs_redelegation(credential, now=now, estimated_matrix_duration_s=10.0)
        assert not delegation.needs_redelegation(
            credential, now=now, estimated_matrix_duration_s=2.0
        )

    def test_ensure_fresh_credential_redelegates_and_records_an_event(
        self, synthetic_aws_registry: BindingRegistry
    ) -> None:
        compiled = load_and_compile(BASIC_SCENARIO, registry=synthetic_aws_registry)
        adapter = FakeProviderAdapter(seed=1)
        materialized = delegation.materialize_graph(adapter, compiled.graph)

        now = datetime.now(UTC)
        stale = self._credential(now=now, remaining_s=1.0)
        materialized.credentials["agent-a"] = stale
        original_ref = materialized.refs["agent-a"]

        new_ref, new_credential, event = delegation.ensure_fresh_credential(
            adapter,
            materialized,
            "agent-a",
            now=now,
            estimated_matrix_duration_s=10.0,
            sequence=0,
        )

        assert event is not None
        assert event["kind"] == "CREDENTIAL_REDELEGATED"
        assert event["previous_credential_id"] == "cred_old"
        assert new_credential is not None
        assert new_credential.credential_id != "cred_old"
        # The fake's IdentityRef is keyed by identity name, not by session/
        # credential -- re-delegating the same identity_id yields the same
        # ref even though the credential behind it changed.
        assert new_ref == original_ref
        assert materialized.refs["agent-a"] == new_ref
        assert materialized.credentials["agent-a"] == new_credential

    def test_ensure_fresh_credential_is_a_no_op_for_a_healthy_credential(
        self, synthetic_aws_registry: BindingRegistry
    ) -> None:
        compiled = load_and_compile(BASIC_SCENARIO, registry=synthetic_aws_registry)
        adapter = FakeProviderAdapter(seed=1)
        materialized = delegation.materialize_graph(adapter, compiled.graph)

        # The real (non-synthetic) credential's timestamps live on the
        # adapter's own virtual clock -- comparing against real wall time
        # here would read it as already expired regardless of duration.
        now = virtual_ms_to_datetime(adapter.clock.now_ms)
        original_credential = materialized.credentials["agent-a"]
        original_ref = materialized.refs["agent-a"]

        new_ref, new_credential, event = delegation.ensure_fresh_credential(
            adapter,
            materialized,
            "agent-a",
            now=now,
            estimated_matrix_duration_s=0.01,
            sequence=0,
        )

        assert event is None
        assert new_ref == original_ref
        assert new_credential == original_credential

    def test_root_identity_is_never_redelegated(
        self, synthetic_aws_registry: BindingRegistry
    ) -> None:
        compiled = load_and_compile(BASIC_SCENARIO, registry=synthetic_aws_registry)
        adapter = FakeProviderAdapter(seed=1)
        materialized = delegation.materialize_graph(adapter, compiled.graph)

        now = virtual_ms_to_datetime(adapter.clock.now_ms)
        new_ref, new_credential, event = delegation.ensure_fresh_credential(
            adapter,
            materialized,
            compiled.graph.root.identity_id,
            now=now,
            estimated_matrix_duration_s=1_000_000.0,
            sequence=0,
        )
        assert event is None
        assert new_credential is None
        assert new_ref == materialized.refs[compiled.graph.root.identity_id]


class TestMaterializeGraphDirectDelegateStillWorks:
    """Sanity: `delegation.materialize_graph`'s own delegate calls use the
    same `DelegationRequest` shape the rest of the providers layer expects
    (regression guard for a signature drift between execution/ and
    providers/base/types.py)."""

    def test_delegate_request_round_trips_through_the_fake_adapter(self) -> None:
        adapter = FakeProviderAdapter(seed=1)
        ref = adapter.register_identity("principal")
        from chainbreak.core.models import AuthoritySet

        result = adapter.delegate(
            DelegationRequest(
                source_identity=ref,
                target_identity_id="agent-a",
                mechanism=DelegationMechanism.ROLE_CHAIN,
                requested_duration_s=900,
                intended_capabilities=AuthoritySet.of("identity.whoami"),
            )
        )
        assert result.identity_ref != ref
