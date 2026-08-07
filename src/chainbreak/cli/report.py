"""`chainbreak report` -- not yet implemented until M16 (reporting and visualization)."""

from __future__ import annotations

import typer

app = typer.Typer(help="Render a report from findings. Not yet implemented.")


@app.callback(invoke_without_command=True)
def report(
    run_id: str = typer.Argument(None, help="Run id to report on."),
    output_format: str = typer.Option("terminal", "--format"),
) -> None:
    typer.echo("chainbreak report: not implemented until M16", err=True)
    raise typer.Exit(code=2)
