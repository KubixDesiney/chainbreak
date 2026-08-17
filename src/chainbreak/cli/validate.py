"""`chainbreak validate` (F3): the environment sanity check.

Offline mode performs provider-agnostic checks -- config resolves; the
account allowlist is
non-empty and every entry is an explicit 12-digit id; regions are
configured; the namespace prefix is well-formed; the capability catalog
loads; every scenario in the repo passes structural validation (stages 1-3;
stage 4's binding resolution is reported informationally rather than as a
failure in offline mode); clock offset is honestly reported as unmeasured.
``--provider aws`` adds the adapter's explicit live P1-P11 validation.

Imports of the heavier packages (pydantic models, jsonschema, the compiler)
are deferred into the function bodies below rather than sitting at module
level: this module is imported by ``cli/main.py`` just to register the
command, on every single CLI invocation including ``chainbreak --help``, so
anything importable-but-unused there is pure startup latency.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess  # nosec B404 -- invokes fixed Terraform output arguments
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from chainbreak.config.settings import Settings

app = typer.Typer(help="Validate environment and configuration.")

_CLOCK_OFFSET_TOLERANCE_MS = 1000.0
_NAMESPACE_PREFIX_PATTERN = re.compile(r"^[a-z][a-z0-9]*$")
_DEFAULT_SCENARIOS_DIR: Path | None = None


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def _check_config_resolves() -> tuple[CheckResult, Settings]:
    from chainbreak.config.settings import Settings, resolve_settings

    try:
        settings = resolve_settings(repo_config_path=Path("chainbreak.toml"))
    except Exception as exc:
        return CheckResult("config resolves", False, str(exc)), Settings()
    return CheckResult("config resolves", True, "resolved"), settings


def _check_account_allowlist(settings: Settings) -> CheckResult:
    if not settings.allowed_account_ids:
        return CheckResult("account allowlist", False, "no accounts configured")
    malformed = [a for a in settings.allowed_account_ids if not (a.isdigit() and len(a) == 12)]
    if malformed:
        return CheckResult("account allowlist", False, f"not explicit 12-digit ids: {malformed}")
    return CheckResult(
        "account allowlist", True, f"{len(settings.allowed_account_ids)} account(s), explicit"
    )


def _check_regions(settings: Settings) -> CheckResult:
    if not settings.allowed_regions:
        return CheckResult("regions", False, "no regions configured")
    return CheckResult("regions", True, ", ".join(settings.allowed_regions))


def _check_namespace_prefix(settings: Settings) -> CheckResult:
    if not _NAMESPACE_PREFIX_PATTERN.match(settings.namespace_prefix):
        return CheckResult(
            "namespace prefix", False, f"{settings.namespace_prefix!r} is not well-formed"
        )
    return CheckResult("namespace prefix", True, settings.namespace_prefix)


def _check_catalog_loads() -> CheckResult:
    from chainbreak.capabilities.loader import load_catalog

    try:
        catalog = load_catalog()
    except Exception as exc:
        return CheckResult("capability catalog", False, str(exc))
    return CheckResult(
        "capability catalog", True, f"v{catalog.version}, {len(catalog.capabilities)} capabilities"
    )


def _check_scenarios_compile(directory: Path) -> CheckResult:
    from chainbreak.capabilities.loader import load_catalog
    from chainbreak.capabilities.registry import BindingRegistry
    from chainbreak.scenarios.loader import EXIT_BINDING, EXIT_VALID, validate_scenario

    paths = sorted(directory.rglob("*.yaml")) if directory.exists() else []
    if not paths:
        return CheckResult("scenarios", False, f"no scenario files found under {directory}")

    catalog = load_catalog()
    registry = BindingRegistry()
    failures = []
    for path in paths:
        result = validate_scenario(path, catalog=catalog, registry=registry)
        if result.exit_code not in (EXIT_VALID, EXIT_BINDING):
            failures.append(f"{path.name}: exit {result.exit_code}")
    if failures:
        return CheckResult("scenarios", False, "; ".join(failures))
    return CheckResult(
        "scenarios",
        True,
        f"{len(paths)} scenario(s) structurally valid "
        "(offline validation: live provider binding and infrastructure state not checked)",
    )


def _check_clock_offset() -> CheckResult:
    from chainbreak.core.clock import no_offset_estimator

    offset_ms = no_offset_estimator()
    if abs(offset_ms) > _CLOCK_OFFSET_TOLERANCE_MS:
        return CheckResult("clock offset", False, f"{offset_ms}ms exceeds tolerance")
    return CheckResult(
        "clock offset", True, "offline validation: unmeasured (no provider configured)"
    )


def _check_budget_guard(settings: Settings, env: dict[str, str] | None = None) -> CheckResult:
    """Check the budget contract before apply, without contacting AWS.

    The live budget resource cannot exist on a clean checkout before apply.  The
    pre-apply guard therefore validates the inputs that will create it; the
    post-apply ``--check-budget`` path verifies the live budget and notification.
    Both paths fail closed when their evidence is absent.
    """
    environment = os.environ if env is None else env
    raw_limit = environment.get("TF_VAR_budget_limit_usd", "").strip()
    raw_email = environment.get("TF_VAR_budget_notification_email", "").strip()
    if not raw_limit:
        return CheckResult("budget guard", False, "TF_VAR_budget_limit_usd is unset")
    if not raw_email:
        return CheckResult("budget guard", False, "TF_VAR_budget_notification_email is unset")
    try:
        limit = float(raw_limit)
    except ValueError:
        return CheckResult("budget guard", False, "TF_VAR_budget_limit_usd is not numeric")
    if limit <= 0:
        return CheckResult("budget guard", False, "budget limit must be greater than zero")
    if limit < settings.max_estimated_cost_usd:
        return CheckResult(
            "budget guard",
            False,
            f"budget limit ${limit:.2f} is below the "
            f"${settings.max_estimated_cost_usd:.2f} run ceiling",
        )
    if environment.get("TF_VAR_enable_negative_controls", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return CheckResult("budget guard", False, "negative-control infrastructure is not enabled")
    return CheckResult(
        "budget guard",
        True,
        f"planned monthly budget ${limit:.2f}; notification configured; negative controls enabled",
    )


def _check_live_budget(adapter: object) -> CheckResult:
    """Verify the namespace budget and its forecast notification in AWS."""
    try:
        outputs = adapter.outputs  # type: ignore[attr-defined]
        client = adapter.operator_session.client("budgets", region_name="us-east-1")  # type: ignore[attr-defined]
        response = client.describe_budget(
            AccountId=outputs.account_id,
            BudgetName=f"{outputs.namespace}-budget",
        )
        budget = response.get("Budget")
        if not isinstance(budget, dict):
            return CheckResult("live budget/alarm", False, "AWS Budgets returned no budget")
        limit = float(budget.get("BudgetLimit", {}).get("Amount", "0"))
        notifications = budget.get("NotificationsWithSubscribers", [])
        active_notifications = [
            item
            for item in notifications
            if item.get("Notification", {}).get("NotificationState") == "ALARM"
            and item.get("Subscribers")
        ]
        valid_shape = (
            budget.get("BudgetType") == "COST" and budget.get("TimeUnit") == "MONTHLY" and limit > 0
        )
        passed = valid_shape and bool(active_notifications)
        detail = (
            f"{outputs.namespace}-budget active; ${limit:.2f} monthly; "
            f"{len(active_notifications)} alarm notification(s)"
            if passed
            else "budget missing a positive monthly COST limit or active subscribed alarm"
        )
        return CheckResult("live budget/alarm", passed, detail)
    except Exception as exc:
        return CheckResult("live budget/alarm", False, f"unable to verify live budget: {exc}")


def _check_fresh_terraform_outputs(outputs_path: Path) -> CheckResult:
    """Refuse live validation unless captured outputs equal current state output."""
    if not outputs_path.is_file():
        return CheckResult("fresh Terraform outputs", False, f"missing outputs at {outputs_path}")
    terraform = shutil.which("terraform")
    if terraform is None:
        return CheckResult("fresh Terraform outputs", False, "terraform is not available")
    from chainbreak.core.errors import ConfigurationError
    from chainbreak.providers.aws.preflight import load_terraform_outputs, parse_terraform_outputs

    try:
        captured = load_terraform_outputs(outputs_path)
        result = subprocess.run(  # noqa: S603  # nosec B603 -- fixed Terraform argv
            [terraform, "output", "-json"],
            cwd=outputs_path.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return CheckResult("fresh Terraform outputs", False, "current Terraform output failed")
        current = parse_terraform_outputs(
            json.loads(result.stdout), path=Path("<terraform-state-output>")
        )
    except (ConfigurationError, OSError, json.JSONDecodeError) as exc:
        return CheckResult(
            "fresh Terraform outputs", False, f"could not verify current state: {exc}"
        )
    if current != captured:
        return CheckResult(
            "fresh Terraform outputs",
            False,
            "outputs.json is stale or does not match current Terraform state",
        )
    return CheckResult(
        "fresh Terraform outputs", True, f"current fingerprint {current.infrastructure_fingerprint}"
    )


def _check_live_aws(
    settings: Settings,
    outputs_path: Path,
    *,
    check_budget: bool,
    i_know_what_i_am_doing: bool = False,
) -> CheckResult:
    """Explicit live validation: the AWS adapter is the sole P1-P11 runner."""
    from chainbreak.config.settings import resolve_safety_envelope
    from chainbreak.providers.aws.factory import create_aws_provider

    adapter = None
    try:
        adapter = create_aws_provider(
            outputs_path=outputs_path,
            run_id="validation",
            i_know_what_i_am_doing=i_know_what_i_am_doing,
        )
        envelope = resolve_safety_envelope(settings, namespace=adapter.namespace)
        report = adapter.preflight(envelope)
        failed = {
            check.name: check.detail for check in report.checks if not check.passed
        }
        if not report.passed:
            return CheckResult(
                "AWS live validation (P1-P11)",
                False,
                f"failed checks: {failed}",
            )
        if check_budget:
            budget_check = _check_live_budget(adapter)
            if not budget_check.passed:
                return CheckResult(
                    "AWS live validation (P1-P11) + budget",
                    False,
                    budget_check.detail,
                )
        return CheckResult("AWS live validation (P1-P11)", True, "P1-P11 live checks passed")
    except Exception as exc:
        return CheckResult("AWS live validation (P1-P11)", False, str(exc))
    finally:
        if adapter is not None:
            close = getattr(adapter, "close", None)
            if close is not None:
                close()


@app.callback(invoke_without_command=True)
def validate(
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    scenarios_dir: Path | None = typer.Option(
        _DEFAULT_SCENARIOS_DIR, "--scenarios-dir", help="Scenario corpus root."
    ),
    provider: str = typer.Option(
        "offline", "--provider", help="Validation mode: offline (default) or aws (live P1-P11)."
    ),
    terraform_outputs: Path = typer.Option(
        Path("infra/terraform/environments/aws-sandbox/outputs.json"),
        "--terraform-outputs",
        help="Terraform outputs for --provider aws.",
    ),
    i_know_what_i_am_doing: bool = typer.Option(
        False, "--i-know-what-i-am-doing", help="Acknowledge P9's production-tag warning."
    ),
    stage: str = typer.Option(
        "live",
        "--stage",
        help="Gate stage: pre-apply (offline config/budget guard) or live (P1-P11).",
    ),
    block_id: str | None = typer.Option(
        None, "--block-id", help="Required AWS experiment block identifier."
    ),
    check_budget: bool = typer.Option(
        False,
        "--check-budget",
        help="Fail closed unless the live namespace budget has an active subscribed alarm.",
    ),
) -> None:
    if stage not in {"pre-apply", "live"}:
        typer.echo("chainbreak validate: --stage must be pre-apply or live", err=True)
        raise typer.Exit(code=2)
    if provider == "aws" and not block_id:
        typer.echo("chainbreak validate: --block-id is required with --provider aws", err=True)
        raise typer.Exit(code=2)
    config_check, settings = _check_config_resolves()
    if scenarios_dir is None:
        from chainbreak.scenarios.resources import packaged_scenarios_path

        with packaged_scenarios_path() as packaged:
            scenario_check = _check_scenarios_compile(packaged)
    else:
        scenario_check = _check_scenarios_compile(scenarios_dir)
    checks = [
        config_check,
        _check_account_allowlist(settings),
        _check_regions(settings),
        _check_namespace_prefix(settings),
        _check_catalog_loads(),
        scenario_check,
        _check_clock_offset(),
    ]
    if provider == "aws" and stage == "pre-apply":
        checks.append(_check_budget_guard(settings))
    elif provider == "aws":
        fresh_outputs = _check_fresh_terraform_outputs(terraform_outputs)
        checks.append(fresh_outputs)
        if fresh_outputs.passed:
            checks.append(
                _check_live_aws(
                    settings,
                    terraform_outputs,
                    check_budget=check_budget,
                    i_know_what_i_am_doing=i_know_what_i_am_doing,
                )
            )
        else:
            checks.append(
                CheckResult(
                    "AWS live validation (P1-P11)",
                    False,
                    "blocked because Terraform outputs are not fresh",
                )
            )
    elif provider != "offline":
        checks.append(CheckResult("validation mode", False, f"unknown provider/mode {provider!r}"))
    all_passed = all(check.passed for check in checks)

    if as_json:
        typer.echo(
            json.dumps({"passed": all_passed, "checks": [asdict(c) for c in checks]}, indent=2)
        )
    else:
        from rich.console import Console
        from rich.table import Table

        table = Table(title="chainbreak validate")
        table.add_column("Check")
        table.add_column("Result")
        table.add_column("Detail")
        for check in checks:
            table.add_row(check.name, "OK" if check.passed else "FAIL", check.detail)
        Console().print(table)

    raise typer.Exit(code=0 if all_passed else 1)
