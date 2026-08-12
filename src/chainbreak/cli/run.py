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

``--provider aws`` is a documented stub (F4) -- M10 wires and verifies the
fake-provider path only; running the same orchestrator against a real AWS
account is M17's job, not this milestone's.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

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


def _build_registry(catalog: CapabilityCatalog) -> BindingRegistry:
    from chainbreak.capabilities.registry import BindingRegistry
    from chainbreak.providers.aws.bindings import build_aws_bindings

    registry = BindingRegistry()
    registry.register_all(
        build_aws_bindings(
            catalog, account_id=_SYNTHETIC_AWS_ACCOUNT_ID, region=_SYNTHETIC_AWS_REGION
        )
    )
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
) -> None:
    """Execute a compiled scenario against a provider, producing a sealed
    evidence bundle under ``<runs-root>/<run-id>/``."""
    if provider not in {"fake", "aws"}:
        typer.echo(
            f"chainbreak run: unknown provider {provider!r} (expected fake or aws)", err=True
        )
        raise typer.Exit(code=2)

    if provider == "aws":
        typer.echo("chainbreak run --provider aws: not implemented until M17", err=True)
        raise typer.Exit(code=2)

    if not scenario_path.is_file():
        typer.echo(f"chainbreak run: no such scenario file {scenario_path}", err=True)
        raise typer.Exit(code=2)

    if fake_profile not in {"deterministic", "eventual", "hostile"}:
        typer.echo(
            f"chainbreak run: unknown --fake-profile {fake_profile!r} "
            "(expected deterministic, eventual or hostile)",
            err=True,
        )
        raise typer.Exit(code=2)

    from datetime import datetime

    from chainbreak.capabilities.loader import load_catalog
    from chainbreak.config.fingerprint import fingerprint_settings
    from chainbreak.config.settings import resolve_safety_envelope, resolve_settings
    from chainbreak.core.errors import ChainbreakError
    from chainbreak.core.ids import new_run_id
    from chainbreak.evidence.manifest import hash_file
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

    _fake_profiles = {
        "deterministic": deterministic_profile,
        "eventual": eventual_profile,
        "hostile": hostile_profile,
    }
    adapter = _fake_profiles[fake_profile](seed=seed)

    settings = resolve_settings(repo_config_path=Path("chainbreak.toml"))
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

    run_id = str(new_run_id())
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
            "capability_catalog_fingerprint": hash_file(
                Path(__file__).resolve().parents[1] / "capabilities" / "catalog.yaml"
            ),
            "provider": adapter.name,
            "provider_adapter_version": compiled.adapter_version,
            "python_version": _python_version(),
            "config_fingerprint": fingerprint_settings(settings),
            "seed": seed,
        },
    )

    # The fake adapter's CredentialRecord timestamps are computed from its
    # own virtual clock (an arbitrary fixed epoch, never real wall time --
    # see providers/fake/session.py), so F6's remaining-lifetime check must
    # be measured against that same virtual "now", not datetime.now(UTC) --
    # comparing a virtual-epoch expiry against real wall-clock time would
    # read every credential as already expired and re-delegate every matrix.
    def _now() -> datetime:
        return virtual_ms_to_datetime(adapter.clock.now_ms)

    try:
        with writer as sink:
            result = orchestrate(
                compiled,
                adapter,
                sink,
                build_fake_preconditions(adapter.markers),
                run_id=run_id,
                envelope=envelope,
                seed=seed,
                max_duration_seconds=settings.max_run_duration_seconds,
                now=_now,
            )
    except ChainbreakError as exc:
        typer.echo(f"chainbreak run: {exc.message}", err=True)
        typer.echo(f"chainbreak run: partial evidence left at {writer.run_dir}", err=True)
        raise typer.Exit(code=1) from exc

    run_dir = runs_root / run_id
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
