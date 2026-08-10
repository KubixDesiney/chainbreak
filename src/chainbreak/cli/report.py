"""`chainbreak report` (M16): render a sealed bundle into a terminal,
Markdown or self-contained HTML report.

A plain function registered directly on the root app (``cli/main.py``), the
same fix ``cli/analyze.py`` and ``cli/run.py`` both already document and
apply: a sub-``Typer`` app's ``@app.callback(invoke_without_command=True)``
misparses a positional argument followed by an option -- Click's
``resolve_command`` looks for a subcommand name before falling back to the
callback's own arguments, which turns ``chainbreak report <run-id>
--format terminal`` into "No such command '--format'" even though
``run_id`` is declared optional. Confirmed directly against this module
before switching approaches (same as the precedent the other two modules'
docstrings record).
"""

from __future__ import annotations

from pathlib import Path

import typer

_DEFAULT_RUNS_ROOT = Path("runs")
_FORMATS = ("terminal", "markdown", "html")


def report(
    run_id: str | None = typer.Argument(None, help="Run id to report on."),
    output_format: str = typer.Option("terminal", "--format", help="terminal, markdown or html."),
    output: Path | None = typer.Option(
        None, "-o", "--output", help="Write the report to this path instead of stdout."
    ),
    runs_root: Path = typer.Option(
        _DEFAULT_RUNS_ROOT, "--runs-root", help="Directory containing run bundles."
    ),
    allow_unsealed: bool = typer.Option(
        False,
        "--allow-unsealed",
        help="Render even if the bundle failed integrity verification.",
    ),
) -> None:
    """Render ``run_id``'s evidence bundle as a report."""
    if run_id is None:
        typer.echo("chainbreak report: run_id is required", err=True)
        raise typer.Exit(code=2)
    if output_format not in _FORMATS:
        typer.echo(
            f"chainbreak report: unknown --format {output_format!r} (expected one of "
            f"{', '.join(_FORMATS)})",
            err=True,
        )
        raise typer.Exit(code=2)

    run_dir = runs_root / run_id
    if not (run_dir / "manifest.json").is_file():
        typer.echo(f"chainbreak report: no such run {run_id!r} under {runs_root}", err=True)
        raise typer.Exit(code=2)

    from chainbreak.core.errors import ChainbreakError
    from chainbreak.reporting.data import gather_report_data
    from chainbreak.reporting.html import render_html
    from chainbreak.reporting.markdown import render_markdown
    from chainbreak.reporting.terminal import render_terminal

    try:
        data = gather_report_data(run_dir, allow_unsealed=allow_unsealed)
        renderer = {"terminal": render_terminal, "markdown": render_markdown, "html": render_html}[
            output_format
        ]
        text = renderer(data)
    except ChainbreakError as exc:
        typer.echo(f"chainbreak report: {exc.message}", err=True)
        raise typer.Exit(code=1) from exc

    if output is not None:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"chainbreak report: wrote {output_format} report -> {output}")
    else:
        # Report text (and evidence content it quotes, e.g. an identity id)
        # is not guaranteed ASCII; a native Windows console's default
        # code page (cp1252) raises UnicodeEncodeError on stdout.write for
        # anything outside it. Writing UTF-8 bytes directly, replacing what
        # the terminal cannot display rather than crashing, is the only
        # encoding-safe way to print an arbitrary report to any terminal.
        import sys

        sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")
