"""`chainbreak run` -- not yet implemented.

Executing a compiled scenario against a provider needs a provider adapter,
which does not exist until the fake provider (M5) or the AWS adapter (M8).
F4: an unimplemented command exits 2 with a clear message, never a stack trace.
"""

from __future__ import annotations

import typer

app = typer.Typer(help="Execute a compiled scenario. Not yet implemented.")


@app.callback(invoke_without_command=True)
def run(scenario_path: str = typer.Argument(None, help="Path to a scenario file.")) -> None:
    typer.echo(
        "chainbreak run: not implemented until M5 (fake provider) / M8 (AWS adapter)", err=True
    )
    raise typer.Exit(code=2)
