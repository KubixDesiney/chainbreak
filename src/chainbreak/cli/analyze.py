"""`chainbreak analyze` -- not yet implemented until M7 (analysis, findings and confidence)."""

from __future__ import annotations

import typer

app = typer.Typer(help="Derive findings from an evidence bundle. Not yet implemented.")


@app.callback(invoke_without_command=True)
def analyze(run_id: str = typer.Argument(None, help="Run id to analyze.")) -> None:
    typer.echo("chainbreak analyze: not implemented until M7", err=True)
    raise typer.Exit(code=2)
