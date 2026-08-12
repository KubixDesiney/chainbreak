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

from pathlib import Path

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
def compare(
    run_a: str = typer.Argument(..., help="First run id."),
    run_b: str = typer.Argument(..., help="Second run id."),
    runs_root: Path = typer.Option(
        Path("runs"), "--runs-root", help="Directory containing run bundles."
    ),
    allow_heterogeneous: bool = typer.Option(
        False,
        "--allow-heterogeneous",
        help="Compare runs even if compiled_hash/adapter_version/catalog_version differ "
        "(M18 F2). Lowers confidence in the result; no flag ever raises it (S1).",
    ),
    cross_operator: bool = typer.Option(
        False,
        "--cross-operator",
        help="Relax the environment (infrastructure_fingerprint) check (M18 F3). Prints a "
        "prominent note that environment equivalence is assumed and unverified.",
    ),
) -> None:
    """Compare findings across two runs (M18 F1-F3), classified into
    REPRODUCIBILITY.md section 1's three levels: identical / structurally
    identical / distributionally consistent / divergent per measurement."""
    from chainbreak.analysis.compare import compare_bundles, snapshot_from_bundle
    from chainbreak.core.errors import EvidenceError, HeterogeneousComparisonError

    try:
        snapshot_a = snapshot_from_bundle(runs_root / run_a)
        snapshot_b = snapshot_from_bundle(runs_root / run_b)
    except EvidenceError as exc:
        typer.echo(f"chainbreak compare: {exc.message}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        report = compare_bundles(
            snapshot_a,
            snapshot_b,
            allow_heterogeneous=allow_heterogeneous,
            cross_operator=cross_operator,
        )
    except HeterogeneousComparisonError as exc:
        typer.echo(f"chainbreak compare: {exc.message}", err=True)
        raise typer.Exit(code=1) from exc

    for note in report.notes:
        typer.echo(f"chainbreak compare: {note}")
    if not report.comparisons:
        typer.echo("chainbreak compare: no comparable measurements found in either run")
    for comparison in report.comparisons:
        typer.echo(
            f"  [{comparison.level}] {comparison.key}: {comparison.verdict} -- {comparison.detail}"
        )

    divergent = report.divergent_count
    typer.echo(
        f"chainbreak compare: {len(report.comparisons)} measurement(s) compared, "
        f"{divergent} divergent"
    )
    if divergent:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
