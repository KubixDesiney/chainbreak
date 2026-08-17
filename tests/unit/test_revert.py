"""``execution/revert.py`` (M12, F8/F9, S3): revert-plan construction, the
human-actionable log event shape, and the actual reversion call -- unit
level, against a real compiled graph but without going through the full
orchestrator.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreak.core.enums import MutationKind
from chainbreak.core.models import EMPTY_AUTHORITY, AuthoritySet
from chainbreak.execution.revert import build_revert_log_event, build_revert_plan, revert_mutation
from chainbreak.providers.fake.adapter import FakeProviderAdapter
from chainbreak.scenarios.loader import load_and_compile

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
INLINE_DENY = REPO_ROOT / "scenarios" / "revocation" / "inline-deny.yaml"


@pytest.fixture
def graph(synthetic_aws_registry):
    return load_and_compile(INLINE_DENY, registry=synthetic_aws_registry).graph


class TestBuildRevertPlan:
    @pytest.mark.parametrize(
        "kind",
        [
            MutationKind.ATTACH_INLINE_DENY,
            MutationKind.REMOVE_INLINE_POLICY,
            MutationKind.REPLACE_INLINE_POLICY,
        ],
    )
    def test_live_state_kinds_are_actionable(self, graph, kind):
        plan = build_revert_plan(graph, "agent-b", kind)
        assert plan.actionable is True
        assert "objectstore.read" in plan.declared_capabilities
        assert "REPLACE_INLINE_POLICY" in plan.action

    def test_revoke_older_sessions_removes_transient_policy(self, graph):
        plan = build_revert_plan(graph, "agent-b", MutationKind.REVOKE_OLDER_SESSIONS)
        assert plan.actionable is True
        assert "transient revocation policy" in plan.action

    @pytest.mark.parametrize(
        "kind", [MutationKind.DELETE_SESSION_POLICY_SCOPE]
    )
    def test_control_kinds_are_not_actionable(self, graph, kind):
        plan = build_revert_plan(graph, "agent-b", kind)
        assert plan.actionable is False
        assert "no action required" in plan.action

    def test_trust_policy_null_control_is_reverted(self, graph):
        plan = build_revert_plan(graph, "agent-b", MutationKind.UPDATE_TRUST_POLICY)
        assert plan.actionable is True
        assert "trust policy" in plan.action


class TestBuildRevertLogEvent:
    def test_event_shape_is_human_actionable(self, graph):
        plan = build_revert_plan(graph, "agent-b", MutationKind.ATTACH_INLINE_DENY)
        event = build_revert_log_event(plan, sequence=3)
        assert event["kind"] == "REVERT_LOG_WRITTEN"
        assert event["sequence"] == 3
        assert event["target_identity"] == "agent-b"
        assert event["mutation_kind"] == "ATTACH_INLINE_DENY"
        assert event["actionable"] is True
        assert isinstance(event["action"], str) and event["action"]
        assert event["declared_capabilities"] == ["identity.whoami", "objectstore.read"]


class TestRevertMutation:
    def test_actionable_plan_restores_declared_authority(self, graph):
        adapter = FakeProviderAdapter(seed=1)
        adapter.engine.register_identity("agent-b", allow=EMPTY_AUTHORITY)
        adapter.engine.apply_deny("agent-b", AuthoritySet.of("objectstore.read"))
        assert "objectstore.read" not in adapter.engine.identity_allow("agent-b")

        plan = build_revert_plan(graph, "agent-b", MutationKind.ATTACH_INLINE_DENY)
        event = revert_mutation(adapter, plan, sequence=9)

        assert event is not None
        assert event["kind"] == "MUTATION_REVERTED"
        assert event["sequence"] == 9
        assert event["original_mutation_kind"] == "ATTACH_INLINE_DENY"
        assert event["receipt"]["confirmed"] is True
        assert "objectstore.read" in adapter.engine.identity_allow("agent-b")

    def test_revoke_older_plan_returns_reversion_event(self, graph):
        adapter = FakeProviderAdapter(seed=1)
        plan = build_revert_plan(graph, "agent-b", MutationKind.REVOKE_OLDER_SESSIONS)
        event = revert_mutation(adapter, plan, sequence=9)
        assert event is not None
        assert event["kind"] == "MUTATION_REVERTED"
        assert event["receipt"]["confirmed"] is True
