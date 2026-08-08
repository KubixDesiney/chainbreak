"""`chainbreak analyze` -- turns a sealed bundle into ``findings.json`` (M7).

Thin CLI adapter over ``analysis/pipeline.py`` (ARCHITECTURE.md section
3.1); no business logic lives here.

A plain function registered directly on the root app (``cli/main.py``, the
same pattern ``compare`` uses) rather than a sub-``Typer`` app with a
``@app.callback(invoke_without_command=True)``: that pattern -- fine for a
command with no required positional argument, like ``validate`` -- misparses
a *required* positional against the group's own "COMMAND" slot (Click's
``resolve_command`` looks for a subcommand name before falling back to the
callback's own arguments), which turned ``chainbreak analyze <run_id>
--runs-root ...`` into "Missing parameter: run_id" every time an option
followed the argument.
"""

from __future__ import annotations

from pathlib import Path

import typer

_DEFAULT_RUNS_ROOT = Path("runs")


def analyze(
    run_id: str = typer.Argument(..., help="Run id to analyze."),
    runs_root: Path = typer.Option(
        _DEFAULT_RUNS_ROOT, "--runs-root", help="Directory containing run bundles."
    ),
    allow_unsealed: bool = typer.Option(
        False,
        "--allow-unsealed",
        help="Produce findings even if the bundle failed integrity verification.",
    ),
) -> None:
    """Derive findings from an evidence bundle."""
    from chainbreak.analysis.pipeline import analyze as run_analysis
    from chainbreak.core.errors import EvidenceError

    run_dir = runs_root / run_id
    try:
        result = run_analysis(run_dir, allow_unsealed=allow_unsealed)
    except EvidenceError as exc:
        typer.echo(f"chainbreak analyze: {exc.message}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"chainbreak analyze: {len(result.findings)} finding(s), "
        f"{len(result.detector_checks)} detector check(s) -> {run_dir / 'findings.json'}"
    )
