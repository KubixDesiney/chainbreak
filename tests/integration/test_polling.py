"""``execution/polling.py`` (M12, F2/F3): serial polling with stability
detection, exercised directly against a real compiled graph and a real
``FakeProviderAdapter`` rather than through the full orchestrator.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.enums import PlanPhase
from chainbreak.core.errors import ExecutionError
from chainbreak.core.models import PollPlan
from chainbreak.execution import chain
from chainbreak.execution.delegation import MaterializedGraph
from chainbreak.execution.polling import run_poll_phase
from chainbreak.providers.fake.adapter import FakeProviderAdapter
from chainbreak.providers.fake.session import virtual_ms_to_datetime
from chainbreak.scenarios.loader import load_and_compile

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
INLINE_DENY = REPO_ROOT / "scenarios" / "revocation" / "inline-deny.yaml"


def _materialize(registry: BindingRegistry, adapter: FakeProviderAdapter):
    compiled = load_and_compile(INLINE_DENY, registry=registry)
    return compiled, chain.materialize_chain(adapter, compiled.graph, max_delegation_depth=6)


def _now(adapter: FakeProviderAdapter):
    return virtual_ms_to_datetime(adapter.clock.now_ms)


class TestNamespaceGuard:
    def test_target_not_materialized_is_rejected(self) -> None:
        adapter = FakeProviderAdapter(seed=1)
        plan = PollPlan(
            phase_name="poll-transition",
            target_identity="agent-b",
            capability_id="objectstore.read",
        )
        with pytest.raises(ExecutionError, match="not a materialized identity") as excinfo:
            run_poll_phase(
                adapter,
                MaterializedGraph(),
                plan,
                run_id="run-poll-missing",
                matrix_id="pm-poll-transition",
                now=lambda: _now(adapter),
                salt="salt",
                namespace=adapter.namespace,
                sequence_start=0,
            )
        assert excinfo.value.context["target_identity"] == "agent-b"


class TestStableAllow:
    def test_warm_baseline_stops_on_stable_allow(
        self, synthetic_aws_registry: BindingRegistry
    ) -> None:
        adapter = FakeProviderAdapter(seed=1)
        _, materialized = _materialize(synthetic_aws_registry, adapter)
        plan = PollPlan(
            phase_name="warm-baseline",
            target_identity="agent-b",
            capability_id="objectstore.read",
            interval_ms=500,
            max_duration_seconds=30,
            stop_on="STABLE_ALLOW",
            stability_count=3,
        )
        run = run_poll_phase(
            adapter,
            materialized,
            plan,
            run_id="run-poll-allow",
            matrix_id="pm-poll-warm-baseline",
            now=lambda: _now(adapter),
            salt="salt",
            namespace=adapter.namespace,
            sequence_start=0,
        )
        assert run.stop_reason == "STABLE_ALLOW"
        assert run.poll_count == 3
        assert all(o.outcome.outcome_class.value == "ALLOWED" for o in run.observations)
        assert all(o.phase is PlanPhase.POST_MUTATION for o in run.observations)
        assert all(o.identity_id == "agent-b" for o in run.observations)
        assert all(o.capability_id == "objectstore.read" for o in run.observations)


class TestStableDenial:
    def test_stops_on_stable_denial_after_a_mutation(
        self, synthetic_aws_registry: BindingRegistry
    ) -> None:
        from chainbreak.core.models import PolicyMutation

        adapter = FakeProviderAdapter(seed=1)
        _, materialized = _materialize(synthetic_aws_registry, adapter)
        adapter.apply_policy_mutation(
            PolicyMutation(
                mutation_id="mut-1",
                kind="ATTACH_INLINE_DENY",
                target_identity="agent-b",
                denies_capabilities=["objectstore.read"],
            )
        )
        plan = PollPlan(
            phase_name="poll-transition",
            target_identity="agent-b",
            capability_id="objectstore.read",
            interval_ms=500,
            max_duration_seconds=300,
            stop_on="STABLE_DENIAL",
            stability_count=3,
        )
        run = run_poll_phase(
            adapter,
            materialized,
            plan,
            run_id="run-poll-deny",
            matrix_id="pm-poll-transition",
            now=lambda: _now(adapter),
            salt="salt",
            namespace=adapter.namespace,
            sequence_start=0,
        )
        assert run.stop_reason == "STABLE_DENIAL"
        assert run.poll_count == 3
        assert all(o.outcome.outcome_class.value.startswith("DENIED") for o in run.observations)


class TestTimeout:
    def test_stops_on_timeout_when_the_target_never_stabilizes(
        self, synthetic_aws_registry: BindingRegistry
    ) -> None:
        adapter = FakeProviderAdapter(seed=1)
        _, materialized = _materialize(synthetic_aws_registry, adapter)
        # Never mutated: polling for a denial that will never happen.
        plan = PollPlan(
            phase_name="poll-transition",
            target_identity="agent-b",
            capability_id="objectstore.read",
            interval_ms=500,
            max_duration_seconds=2,
            stop_on="STABLE_DENIAL",
            stability_count=3,
        )
        run = run_poll_phase(
            adapter,
            materialized,
            plan,
            run_id="run-poll-timeout",
            matrix_id="pm-poll-transition",
            now=lambda: _now(adapter),
            salt="salt",
            namespace=adapter.namespace,
            sequence_start=0,
        )
        assert run.stop_reason == "TIMEOUT"
        # 2000ms budget / 500ms interval == 4 polls before the loop gives up.
        assert run.poll_count == 4
        assert all(o.outcome.outcome_class.value == "ALLOWED" for o in run.observations)

    def test_stop_on_timeout_itself_never_stabilizes_early(
        self, synthetic_aws_registry: BindingRegistry
    ) -> None:
        """A ``stop_on: TIMEOUT`` phase (the null-condition scenarios' own
        convention) always runs its full budget, even though every poll
        happens to be ALLOWED (which would satisfy STABLE_ALLOW immediately
        if that were the target)."""
        adapter = FakeProviderAdapter(seed=1)
        _, materialized = _materialize(synthetic_aws_registry, adapter)
        plan = PollPlan(
            phase_name="poll-transition",
            target_identity="agent-b",
            capability_id="objectstore.read",
            interval_ms=700,
            max_duration_seconds=2,
            stop_on="TIMEOUT",
            stability_count=1,
        )
        run = run_poll_phase(
            adapter,
            materialized,
            plan,
            run_id="run-poll-explicit-timeout",
            matrix_id="pm-poll-transition",
            now=lambda: _now(adapter),
            salt="salt",
            namespace=adapter.namespace,
            sequence_start=0,
        )
        assert run.stop_reason == "TIMEOUT"
        assert run.poll_count == 3
