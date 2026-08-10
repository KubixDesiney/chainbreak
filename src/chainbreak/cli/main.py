"""The CLI entry point.

Logging (with the redaction filter, SI-10) is installed here, first, before
anything else is imported -- the reason ``cli/logging.py`` exists as its own
module rather than being set up inline somewhere later.

The CLI is a thin adapter: it parses arguments, loads config, calls the
SafetyGate, and delegates (ARCHITECTURE.md section 3.1). No business logic
lives here; every command module below either wraps a library function
(``validate``, ``scenario``) or is a documented stub (F4) for a milestone
that has not landed yet.
"""

from __future__ import annotations

from chainbreak.cli import logging as cb_logging

cb_logging.install()

import typer  # noqa: E402 -- logging must install before any other import that may log

from chainbreak.cli import analyze, infra, report, run, runs, scenario, validate  # noqa: E402

app = typer.Typer(
    name="chainbreak",
    help="An empirical benchmark for authorization behavior in delegated and "
    "agentic cloud systems.",
    no_args_is_help=True,
    # Typer's default rich-rendered --help (panels, color) costs ~270ms at
    # invocation time -- it lazily drives rich's layout engine over every
    # option/command on each render, independent of import time. Plain
    # click-style help meets the <500ms budget; rich.table is still used
    # directly for `validate`'s own output where the cost is one-time.
    rich_markup_mode=None,
)

app.add_typer(validate.app, name="validate")
app.add_typer(scenario.app, name="scenario")
app.command("run")(run.run)
app.command("analyze")(analyze.analyze)
app.command("report")(report.report)
app.add_typer(runs.app, name="runs")
app.add_typer(runs.evidence_app, name="evidence")
app.add_typer(infra.app, name="infra")


@app.command()
def compare(run_ids: list[str] = typer.Argument(None, help="Run ids to compare.")) -> None:
    """Compare findings across runs. Not yet implemented until M18."""
    typer.echo("chainbreak compare: not implemented until M18", err=True)
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
