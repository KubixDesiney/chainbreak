"""`chainbreak run` (M10): compile a scenario and execute it against a
provider, producing a sealed evidence bundle.

A plain function registered directly on the root app (``cli/main.py``), the
same fix ``cli/analyze.py`` already documents and applies: a sub-``Typer``
app's ``@app.callback(invoke_without_command=True)`` misparses a *required*
positional argument once an option follows it on the command line -- exactly
the shape this milestone's own verification command has (``chainbreak run
scenarios/scope-attenuation/basic.yaml --provider fake --seed 11``).

Thin CLI adapter over ``execution/orchestrator.py`` (ARCHITECTURE.md section
3.1): this module resolves configuration, builds the provider adapter and
the evidence sink, and delegates; no orchestration logic lives here.

``--provider aws`` uses the validated Terraform-output factory and the same
production orchestrator as the fake path. Live AWS validation remains
explicit: the adapter's P1-P11 preflight is performed before any benchmark
mutation or probe.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404 -- fixed-argv Git provenance lookup
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer

if TYPE_CHECKING:
    from chainbreak.capabilities.registry import BindingRegistry
    from chainbreak.core.models import CapabilityCatalog

_DEFAULT_RUNS_ROOT = Path("runs")

#: Placeholder account/region ``build_aws_bindings`` needs to construct
#: structurally valid resource-template strings at compile time. Every
#: shipped scenario declares ``provider: aws`` (compiled bindings validate
#: capability resolution, CAP-1), but a ``--provider fake`` run never
#: actually dereferences these values -- the fake adapter resolves its own
#: bindings independently at probe time (``providers/fake/bindings.py``).
_SYNTHETIC_AWS_ACCOUNT_ID = "000000000000"
_SYNTHETIC_AWS_REGION = "us-east-1"


def _build_registry(
    catalog: CapabilityCatalog,
    *,
    account_id: str = _SYNTHETIC_AWS_ACCOUNT_ID,
    region: str = _SYNTHETIC_AWS_REGION,
) -> BindingRegistry:
    from chainbreak.capabilities.registry import BindingRegistry
    from chainbreak.providers.aws.bindings import build_aws_bindings

    registry = BindingRegistry()
    registry.register_all(build_aws_bindings(catalog, account_id=account_id, region=region))
    return registry


def run(
    scenario_path: Path = typer.Argument(..., help="Path to a scenario file."),
    provider: str = typer.Option(
        "fake", "--provider", help="Provider to execute against: fake or aws."
    ),
    seed: int = typer.Option(
        0, "--seed", help="Seed for probe-order shuffling and the fake provider's determinism."
    ),
    fake_profile: str = typer.Option(
        "deterministic",
        "--fake-profile",
        help="Fake provider profile: deterministic, eventual or hostile. "
        "Ignored for --provider aws.",
    ),
    runs_root: Path = typer.Option(
        _DEFAULT_RUNS_ROOT, "--runs-root", help="Directory to write the evidence bundle under."
    ),
    terraform_outputs: Path = typer.Option(
        Path("infra/terraform/environments/aws-sandbox/outputs.json"),
        "--terraform-outputs",
        help="Validated Terraform output JSON for --provider aws.",
    ),
    block_id: str | None = typer.Option(
        None, "--block-id", help="Experiment block identifier (required for AWS provenance)."
    ),
    i_know_what_i_am_doing: bool = typer.Option(
        False,
        "--i-know-what-i-am-doing",
        help="Acknowledge P9's production-tag warning; never bypasses other checks.",
    ),
    run_id_file: Path | None = typer.Option(
        None,
        "--run-id-file",
        help="Append the sealed run id to this file for deterministic downstream analysis.",
    ),
) -> None:
    """Execute a compiled scenario against a provider, producing a sealed
    evidence bundle under ``<runs-root>/<run-id>/``."""
    if provider not in {"fake", "aws"}:
        typer.echo(
            f"chainbreak run: unknown provider {provider!r} (expected fake or aws)", err=True
        )
        raise typer.Exit(code=2)

    if provider == "aws" and not block_id:
        typer.echo("chainbreak run: --block-id is required with --provider aws", err=True)
        raise typer.Exit(code=2)

    if not scenario_path.is_file():
        typer.echo(f"chainbreak run: no such scenario file {scenario_path}", err=True)
        raise typer.Exit(code=2)

    if provider == "fake" and fake_profile not in {"deterministic", "eventual", "hostile"}:
        typer.echo(
            f"chainbreak run: unknown --fake-profile {fake_profile!r} "
            "(expected deterministic, eventual or hostile)",
            err=True,
        )
        raise typer.Exit(code=2)

    from chainbreak.capabilities.loader import catalog_bytes, load_catalog
    from chainbreak.config.fingerprint import fingerprint_settings
    from chainbreak.config.settings import resolve_safety_envelope, resolve_settings
    from chainbreak.core.errors import ChainbreakError
    from chainbreak.core.ids import new_run_id
    from chainbreak.evidence.manifest import hash_bytes
    from chainbreak.evidence.writer import BundleWriter
    from chainbreak.execution.orchestrator import orchestrate
    from chainbreak.providers.fake.probes import build_fake_preconditions
    from chainbreak.providers.fake.profiles import (
        deterministic_profile,
        eventual_profile,
        hostile_profile,
    )
    from chainbreak.providers.fake.session import virtual_ms_to_datetime
    from chainbreak.scenarios.loader import load_and_compile
    from chainbreak.scenarios.safety import load_scenario_yaml
    from chainbreak.scenarios.schema import ScenarioDocument

    catalog = load_catalog()
    run_id = str(new_run_id())
    settings = resolve_settings(repo_config_path=Path("chainbreak.toml"))

    adapter: Any
    if provider == "aws":
        from chainbreak.providers.aws.factory import create_aws_provider

        try:
            adapter = create_aws_provider(
                outputs_path=terraform_outputs,
                run_id=run_id,
                i_know_what_i_am_doing=i_know_what_i_am_doing,
            )
        except ChainbreakError as exc:
            typer.echo(f"chainbreak run: {exc.message}", err=True)
            raise typer.Exit(code=1) from exc
        registry = _build_registry(catalog, account_id=adapter.account_ref, region=adapter.region)
    else:
        _fake_profiles = {
            "deterministic": deterministic_profile,
            "eventual": eventual_profile,
            "hostile": hostile_profile,
        }
        adapter = _fake_profiles[fake_profile](seed=seed)
        registry = _build_registry(catalog)

    try:
        # load_and_compile (scenarios/loader.py) is the five-stage pipeline
        # that turns every failure mode -- YAML syntax, Pydantic structural
        # errors, semantic/graph errors, binding resolution -- into a single
        # ChainbreakError, never a raw pydantic.ValidationError reaching here.
        compiled = load_and_compile(scenario_path, catalog=catalog, registry=registry)
        document = ScenarioDocument(**load_scenario_yaml(scenario_path))
    except ChainbreakError as exc:
        typer.echo(f"chainbreak run: {exc.message}", err=True)
        raise typer.Exit(code=1) from exc

    # "fake" needs no AWS account (chainbreak.example.toml's own stated
    # design) -- fall back to the fake adapter's own synthetic account/region
    # only when the operator has not configured real ones, so an AWS run
    # never silently defaults (SI-6) but a fake run works with zero config.
    cli_overrides: dict[str, object] = {}
    if not settings.allowed_account_ids:
        cli_overrides["allowed_account_ids"] = (adapter.account_ref,)
    if not settings.allowed_regions:
        cli_overrides["allowed_regions"] = (adapter.region,)
    if cli_overrides:
        settings = resolve_settings(
            repo_config_path=Path("chainbreak.toml"), cli_overrides=cli_overrides
        )

    try:
        envelope = resolve_safety_envelope(settings, namespace=adapter.namespace)
    except ChainbreakError as exc:
        typer.echo(f"chainbreak run: {exc.message}", err=True)
        raise typer.Exit(code=1) from exc

    environment = adapter.describe_environment()
    effective_block_id = block_id
    if provider == "aws":
        effective_block_id = block_id
    git_commit, git_dirty = _git_provenance()
    writer = BundleWriter(
        runs_root,
        run_id,
        scenario_ref={
            "id": compiled.scenario_id,
            "version": compiled.scenario_version,
            "family": document.metadata.family.value,
            "api_version": document.api_version,
            "compiled_hash": compiled.compiled_hash,
        },
        provenance={
            "chainbreak_version": _chainbreak_version(),
            "capability_catalog_version": compiled.catalog_version,
            "capability_catalog_fingerprint": hash_bytes(catalog_bytes()),
            "provider": adapter.name,
            "provider_adapter_version": compiled.adapter_version,
            "python_version": _python_version(),
            "config_fingerprint": fingerprint_settings(settings),
            "region": environment.region,
            "infrastructure_fingerprint": (
                getattr(getattr(adapter, "outputs", None), "infrastructure_fingerprint", None)
            ),
            "sts_endpoint": environment.sts_endpoint,
            "git_commit": git_commit,
            "git_dirty": git_dirty,
            "seed": seed,
        },
        block_id=effective_block_id,
    )

    # The fake adapter's CredentialRecord timestamps are computed from its
    # own virtual clock (an arbitrary fixed epoch, never real wall time --
    # see providers/fake/session.py), so F6's remaining-lifetime check must
    # be measured against that same virtual "now", not datetime.now(UTC) --
    # comparing a virtual-epoch expiry against real wall-clock time would
    # read every credential as already expired and re-delegate every matrix.
    def _now() -> datetime:
        if provider == "fake":
            return virtual_ms_to_datetime(adapter.clock.now_ms)
        return datetime.now(UTC)

    try:
        with writer as sink:
            preconditions = (
                adapter.build_precondition_registry()
                if provider == "aws"
                else build_fake_preconditions(adapter.markers)
            )
            cost_table = (
                {
                    "__default__": 0.0001,
                    "identity.whoami": 0.0,
                    "identity.delegate": 0.0,
                    "function.invoke": 0.0,
                    "queue.send": 0.0,
                    "queue.receive": 0.0,
                }
                if provider == "aws"
                else None
            )
            result = orchestrate(
                compiled,
                adapter,
                sink,
                preconditions,
                run_id=run_id,
                envelope=envelope,
                seed=seed,
                max_duration_seconds=settings.max_run_duration_seconds,
                now=_now,
                cost_table=cost_table,
            )
    except ChainbreakError as exc:
        typer.echo(f"chainbreak run: {exc.message}", err=True)
        typer.echo(f"chainbreak run: partial evidence left at {writer.run_dir}", err=True)
        raise typer.Exit(code=1) from exc
    finally:
        close = getattr(adapter, "close", None)
        if close is not None:
            close()

    run_dir = runs_root / run_id
    if run_id_file is not None:
        try:
            run_id_file.parent.mkdir(parents=True, exist_ok=True)
            with run_id_file.open("a", encoding="utf-8") as handle:
                handle.write(f"{run_id}\n")
        except OSError as exc:
            typer.echo(f"chainbreak run: could not record run id: {exc}", err=True)
            raise typer.Exit(code=1) from exc
    typer.echo(f"chainbreak run: {result.status.value} -> {run_dir}")
    for discarded in result.discarded_matrices:
        typer.echo(
            f"chainbreak run: matrix {discarded.matrix_id!r} (phase "
            f"{discarded.phase_name!r}) discarded: {discarded.reason}",
            err=True,
        )


def _chainbreak_version() -> str:
    from chainbreak import __version__

    return __version__


def _python_version() -> str:
    import platform

    return platform.python_version()


def _git_provenance() -> tuple[str | None, bool]:
    """Capture repository identity without making a run depend on git."""
    git = shutil.which("git")
    if git is None:
        return None, False
    try:
        commit_result = subprocess.run(  # noqa: S603  # nosec B603 -- fixed literal argv
            [git, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        status_result = subprocess.run(  # noqa: S603  # nosec B603 -- fixed literal argv
            [git, "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None, False
    commit = commit_result.stdout.strip() if commit_result.returncode == 0 else None
    dirty = bool(status_result.stdout.strip()) if status_result.returncode == 0 else False
    return commit, dirty
