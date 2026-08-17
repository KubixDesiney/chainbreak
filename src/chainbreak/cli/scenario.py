"""`chainbreak scenario validate|list`.

Real commands: both wrap ``scenarios.loader`` (M3) directly, which is why
that module's ``validate_scenario``/``load_and_compile`` functions exist as
a library API rather than being embedded inside the CLI layer -- the CLI is
a thin adapter, no business logic (ARCHITECTURE.md section 3.1).

The heavy imports (pydantic scenario schema, jsonschema, the compiler) are
deferred into the command bodies rather than sitting at module level, for
the same reason as ``cli/validate.py``: this module loads on every CLI
invocation just to register the command.
"""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="Validate and list scenario files.")

_DEFAULT_SCENARIOS_DIR = Path("scenarios")


@app.command("validate")
def validate(
    path: Path = typer.Argument(..., help="Path to a scenario YAML file."),
) -> None:
    """Run all five validation stages, print the result, exit with the
    stage's documented exit code.

    Provider bindings use the same synthetic, non-network registry as the
    runtime compilation path. This lets the command validate shipped AWS
    scenarios offline without Terraform outputs or an AWS call.
    """
    from chainbreak.capabilities.loader import load_catalog
    from chainbreak.cli.run import _build_registry
    from chainbreak.scenarios.loader import EXIT_VALID, validate_scenario

    catalog = load_catalog()
    result = validate_scenario(path, catalog=catalog, registry=_build_registry(catalog))
    if result.compiled is not None:
        typer.echo(f"OK  {path}  compiled_hash={result.compiled.compiled_hash}")
        raise typer.Exit(code=EXIT_VALID)

    typer.echo(f"FAIL  {path}  (exit {result.exit_code})", err=True)
    for error in result.errors:
        typer.echo(f"  - {error}", err=True)
    raise typer.Exit(code=result.exit_code)


@app.command("list")
def list_scenarios(
    directory: Path | None = typer.Option(
        None,
        "--dir",
        help="Scenario corpus root. Defaults to the 24 scenarios shipped in the wheel.",
    ),
) -> None:
    """List every scenario file found under ``directory``."""
    if directory is not None:
        if not directory.exists():
            typer.echo(f"no such directory: {directory}", err=True)
            raise typer.Exit(code=2)
        paths = sorted(directory.rglob("*.yaml"))
        label = directory
        for path in paths:
            typer.echo(str(path))
    else:
        from chainbreak.scenarios.resources import packaged_scenarios_path

        with packaged_scenarios_path() as packaged:
            paths = sorted(packaged.rglob("*.yaml"))
            label = packaged
            for path in paths:
                typer.echo(str(path))
    if not paths:
        typer.echo(f"no scenario files found under {label}", err=True)
