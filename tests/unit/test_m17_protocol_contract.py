"""Offline contract tests for the M17 two-stage AWS workflow."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "aws-experiment.yml"
PROTOCOL = REPO_ROOT / "EXPERIMENT_PROTOCOL.md"
MILESTONE = REPO_ROOT / "docs" / "implementation" / "milestones" / "M17-aws-experiment-suite.md"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _normalized_commands(text: str) -> list[str]:
    compact = re.sub(r"\\\n\s*", " ", text)
    return [line.strip() for line in compact.splitlines() if "chainbreak " in line]


def test_workflow_is_valid_yaml_and_manual_only() -> None:
    document = yaml.safe_load(_workflow_text())
    assert document is not None
    assert "workflow_dispatch:" in _workflow_text()
    assert not re.search(r"^\s*pull_request\s*:", _workflow_text(), re.MULTILINE)
    assert not re.search(r"^\s*push\s*:", _workflow_text(), re.MULTILINE)


def test_workflow_has_two_gates_in_safe_order() -> None:
    text = _workflow_text()
    stage_a = text.index("Stage A - pre-apply clean gate")
    apply = text.index("chainbreak infra apply")
    stage_b = text.index("Stage B - post-apply live gate")
    live_validate = text.index("--stage live")
    assert stage_a < apply < stage_b < live_validate
    assert text.index("name: Destroy twice and verify the exact namespace") > live_validate
    assert "destroyed sandbox" in text.lower() or "destroyed" in PROTOCOL.read_text().lower()
    assert "stale" in PROTOCOL.read_text(encoding="utf-8").lower()


def test_apply_and_destroy_are_separate_reviewed_jobs() -> None:
    text = _workflow_text()
    assert "preflight:" in text
    assert "experiment:" in text
    assert "destroy:" in text
    assert text.count("environment: aws-benchmark") >= 3
    assert "needs: preflight" in text
    assert "needs: [preflight, experiment]" in text
    assert "state.enc" in text
    assert "openssl enc -aes-256-cbc" in text


def test_no_fake_default_or_removed_cli_options_in_m17() -> None:
    text = _workflow_text()
    assert "--latest" not in text
    assert "runs list --json" not in text
    assert "chainbreak validate --json" not in text
    for command in _normalized_commands(text):
        if command.startswith("chainbreak run "):
            assert "--provider aws" in command
            assert '--block-id "$BLOCK_ID"' in command
        if command.startswith("chainbreak validate "):
            assert "--provider aws" in command
            assert '--block-id "$BLOCK_ID"' in command
        if command.startswith("chainbreak analyze "):
            assert "--provider aws" in command
            assert '--block-id "$BLOCK_ID"' in command
        if command.startswith("chainbreak evidence export "):
            assert "--provider aws" in command
            assert '--block-id "$BLOCK_ID"' in command


def test_invoked_cli_options_are_present_and_removed_options_are_absent() -> None:
    from typer.testing import CliRunner

    from chainbreak.cli.main import app

    runner = CliRunner()
    help_commands = [
        ["validate", "--help"],
        ["infra", "namespace", "--help"],
        ["infra", "status", "--help"],
        ["infra", "apply", "--help"],
        ["infra", "destroy", "--help"],
        ["infra", "verify-clean", "--help"],
        ["run", "--help"],
        ["analyze", "--help"],
        ["evidence", "export", "--help"],
    ]
    results = [runner.invoke(app, command) for command in help_commands]
    for result in results:
        assert result.exit_code == 0, result.output
        assert "--latest" not in result.output
    for command, result in zip(help_commands, results, strict=True):
        if command[0] in {"validate", "run", "analyze", "evidence"}:
            assert "--provider" in result.output
            assert "--block-id" in result.output


def test_environment_contract_is_complete_and_negative_controls_are_real() -> None:
    text = _workflow_text()
    required = {
        "CHAINBREAK_ACCOUNT_ID",
        "CHAINBREAK_REGION",
        "CHAINBREAK_BUDGET_LIMIT_USD",
        "CHAINBREAK_BENCHMARK_ROLE_ARN",
        "CHAINBREAK_NAMESPACE_SALT",
        "CHAINBREAK_OPERATOR_PRINCIPAL_ARNS",
        "CHAINBREAK_BUDGET_NOTIFICATION_EMAIL",
    }
    for name in required:
        assert name in text
    assert 'TF_VAR_enable_negative_controls: "true"' in text
    assert "default: suite" in text
    assert "find scenarios -type f -name '*.yaml'" in text
    assert "for variable_name in" in text
    assert "TF_VAR_namespace_salt" in text


def test_namespace_is_captured_before_destroy_and_reused_for_exact_cleanup() -> None:
    text = _workflow_text()
    capture = text.index("--capture-namespace artifacts/namespace.txt")
    destroy = text.index("name: Destroy twice and verify the exact namespace")
    cleanup = text.index('--namespace "$namespace"')
    assert capture < destroy < cleanup
    assert "artifacts/namespace-derived.txt" in text
    assert "cmp --silent artifacts/namespace-derived.txt artifacts/namespace.txt" in text
    assert 'namespace="$(< destroy-input/namespace.txt)"' in text


def test_concurrency_and_artifact_contract() -> None:
    text = _workflow_text()
    assert "concurrency:" in text
    assert "cancel-in-progress: false" in text
    assert "path: artifacts/" in text
    assert "state.enc" in text
    assert "path: destroy-input/" in text
    assert "path: infra/terraform/environments/aws-sandbox/terraform.tfstate" not in text
    assert ".terraform" not in text
    assert re.search(r"uses: [^@\s]+@[0-9a-f]{40}(?:\s|#|$)", text)
    assert not re.search(r"uses: [^@\s]+@v\d", text)


def test_protocol_names_fail_closed_live_budget_command() -> None:
    protocol = PROTOCOL.read_text(encoding="utf-8")
    milestone = MILESTONE.read_text(encoding="utf-8")
    assert "--provider aws --stage pre-apply --check-budget --block-id" in protocol
    assert "--provider aws --stage live --check-budget --block-id" in protocol
    assert "active subscribed alarm notification" in protocol
    assert "chainbreak validate --provider aws --stage live --check-budget" in milestone


def test_budget_guard_fails_closed_without_environment_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from chainbreak.cli.validate import _check_budget_guard
    from chainbreak.config.settings import Settings

    monkeypatch.delenv("TF_VAR_budget_limit_usd", raising=False)
    monkeypatch.delenv("TF_VAR_budget_notification_email", raising=False)
    monkeypatch.delenv("TF_VAR_enable_negative_controls", raising=False)
    result = _check_budget_guard(Settings(max_estimated_cost_usd=1.0), env={})
    assert result.passed is False
    assert "unset" in result.detail


def test_live_budget_check_requires_an_active_subscribed_alarm() -> None:
    from chainbreak.cli.validate import _check_live_budget

    class BudgetClient:
        def describe_budget(self, **_: object) -> dict[str, object]:
            return {
                "Budget": {
                    "BudgetType": "COST",
                    "TimeUnit": "MONTHLY",
                    "BudgetLimit": {"Amount": "5", "Unit": "USD"},
                    "NotificationsWithSubscribers": [
                        {
                            "Notification": {"NotificationState": "OK"},
                            "Subscribers": [{"SubscriptionType": "EMAIL"}],
                        }
                    ],
                }
            }

    class Session:
        def client(self, *_: object, **__: object) -> BudgetClient:
            return BudgetClient()

    adapter = SimpleNamespace(
        outputs=SimpleNamespace(account_id="123456789012", namespace="cb-a1b2c3d4"),
        operator_session=Session(),
    )
    assert _check_live_budget(adapter).passed is True


def test_live_budget_check_reconstructs_sns_subscriber_projection() -> None:
    from chainbreak.cli.validate import _check_live_budget

    class BudgetClient:
        def describe_budget(self, **_: object) -> dict[str, object]:
            return {
                "Budget": {
                    "BudgetType": "COST",
                    "TimeUnit": "MONTHLY",
                    "BudgetLimit": {"Amount": "5", "Unit": "USD"},
                    "NotificationsWithSubscribers": None,
                }
            }

        def describe_notifications_for_budget(self, **_: object) -> dict[str, object]:
            return {
                "Notifications": [
                    {
                        "NotificationType": "ACTUAL",
                        "ComparisonOperator": "GREATER_THAN",
                        "Threshold": 80,
                        "ThresholdType": "PERCENTAGE",
                        "NotificationState": "OK",
                    }
                ]
            }

        def describe_subscribers_for_notification(self, **_: object) -> dict[str, object]:
            return {"Subscribers": [{"SubscriptionType": "SNS"}]}

    class Session:
        def client(self, *_: object, **__: object) -> BudgetClient:
            return BudgetClient()

    adapter = SimpleNamespace(
        outputs=SimpleNamespace(account_id="123456789012", namespace="cb-a1b2c3d4"),
        operator_session=Session(),
    )
    assert _check_live_budget(adapter).passed is True


def test_live_gate_fails_closed_when_outputs_are_missing(tmp_path: Path) -> None:
    from chainbreak.cli.validate import _check_fresh_terraform_outputs

    result = _check_fresh_terraform_outputs(tmp_path / "outputs.json")
    assert result.passed is False
    assert "missing outputs" in result.detail
