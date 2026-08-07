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

    Stage 4 (provider binding) always resolves against an empty registry
    today: no provider package (M5 fake, M8 AWS) has registered a real
    binding into one yet, so any scenario naming a real capability currently
    fails at exit 4 -- see PROJECT_STATUS.md known issue 2.
    """
    from chainbreak.capabilities.loader import load_catalog
    from chainbreak.capabilities.registry import BindingRegistry
    from chainbreak.scenarios.loader import EXIT_VALID, validate_scenario

    result = validate_scenario(path, catalog=load_catalog(), registry=BindingRegistry())
    if result.compiled is not None:
        typer.echo(f"OK  {path}  compiled_hash={result.compiled.compiled_hash}")
        raise typer.Exit(code=EXIT_VALID)

    typer.echo(f"FAIL  {path}  (exit {result.exit_code})", err=True)
    for error in result.errors:
        typer.echo(f"  - {error}", err=True)
    raise typer.Exit(code=result.exit_code)


@app.command("list")
def list_scenarios(
    directory: Path = typer.Option(_DEFAULT_SCENARIOS_DIR, "--dir", help="Scenario corpus root."),
) -> None:
    """List every scenario file found under ``directory``."""
    if not directory.exists():
        typer.echo(f"no such directory: {directory}", err=True)
        raise typer.Exit(code=2)
    paths = sorted(directory.rglob("*.yaml"))
    for path in paths:
        typer.echo(str(path))
    if not paths:
        typer.echo(f"no scenario files found under {directory}", err=True)
