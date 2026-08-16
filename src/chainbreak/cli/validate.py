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
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from chainbreak.config.settings import Settings

app = typer.Typer(help="Validate environment and configuration.")

_CLOCK_OFFSET_TOLERANCE_MS = 1000.0
_NAMESPACE_PREFIX_PATTERN = re.compile(r"^[a-z][a-z0-9]*$")
_DEFAULT_SCENARIOS_DIR = Path("scenarios")


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


def _check_live_aws(
    settings: Settings, outputs_path: Path, *, i_know_what_i_am_doing: bool = False
) -> CheckResult:
    """Explicit live validation: the AWS adapter is the sole P1-P11 runner."""
    from chainbreak.config.settings import resolve_safety_envelope
    from chainbreak.providers.aws.factory import create_aws_provider

    try:
        adapter = create_aws_provider(
            outputs_path=outputs_path,
            run_id="validation",
            i_know_what_i_am_doing=i_know_what_i_am_doing,
        )
        envelope = resolve_safety_envelope(settings, namespace=adapter.namespace)
        report = adapter.preflight(envelope)
    except Exception as exc:
        return CheckResult("AWS live validation (P1-P11)", False, str(exc))
    finally:
        if "adapter" in locals():
            close = getattr(adapter, "close", None)
            if close is not None:
                close()
    failed = [check.name for check in report.checks if not check.passed]
    detail = "P1-P11 live checks passed" if report.passed else f"failed checks: {failed}"
    return CheckResult("AWS live validation (P1-P11)", report.passed, detail)


@app.callback(invoke_without_command=True)
def validate(
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    scenarios_dir: Path = typer.Option(
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
) -> None:
    config_check, settings = _check_config_resolves()
    checks = [
        config_check,
        _check_account_allowlist(settings),
        _check_regions(settings),
        _check_namespace_prefix(settings),
        _check_catalog_loads(),
        _check_scenarios_compile(scenarios_dir),
        _check_clock_offset(),
    ]
    if provider == "aws":
        checks.append(
            _check_live_aws(
                settings,
                terraform_outputs,
                i_know_what_i_am_doing=i_know_what_i_am_doing,
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
