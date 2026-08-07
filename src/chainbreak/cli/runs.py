"""`chainbreak runs list|show|reindex` and `chainbreak evidence export` -- not yet
implemented until M6 (evidence pipeline and redaction), which is what creates
run indices and evidence bundles in the first place.
"""

from __future__ import annotations

import typer

app = typer.Typer(help="Inspect past runs. Not yet implemented.")
evidence_app = typer.Typer(help="Export evidence bundles. Not yet implemented.")


def _not_implemented(command: str) -> None:
    typer.echo(f"chainbreak {command}: not implemented until M6", err=True)
    raise typer.Exit(code=2)


@app.command("list")
def list_runs() -> None:
    _not_implemented("runs list")


@app.command("show")
def show_run(run_id: str) -> None:
    _not_implemented("runs show")


@app.command("reindex")
def reindex_runs() -> None:
    _not_implemented("runs reindex")


@evidence_app.command("export")
def export_evidence(run_id: str) -> None:
    _not_implemented("evidence export")
