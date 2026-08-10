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
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from collections.abc import Sequence

    from chainbreak.core.models import CategoryResult

_DEFAULT_RUNS_ROOT = Path("runs")


def analyze(
    run_id: str | None = typer.Argument(
        None, help="Run id to analyze. Omit when using --aggregate."
    ),
    runs_root: Path = typer.Option(
        _DEFAULT_RUNS_ROOT, "--runs-root", help="Directory containing run bundles."
    ),
    allow_unsealed: bool = typer.Option(
        False,
        "--allow-unsealed",
        help="Produce findings even if the bundle failed integrity verification.",
    ),
    aggregate: bool = typer.Option(
        False,
        "--aggregate",
        help="Aggregate a depth sweep across a scenario family (M11 F6) instead of "
        "analyzing one run. Requires --scenario-family.",
    ),
    scenario_family: str | None = typer.Option(
        None,
        "--scenario-family",
        help="Scenario family to aggregate, matched against each run's manifest "
        "(e.g. delegation-drift). Required with --aggregate.",
    ),
    aggregate_scores: bool = typer.Option(
        False,
        "--aggregate-scores",
        help="Aggregate category scores (M15 F7/F8) across independent runs of the same "
        "compiled scenario instead of analyzing one run. Requires --scenario-id.",
    ),
    scenario_id: str | None = typer.Option(
        None,
        "--scenario-id",
        help="Scenario id to aggregate scores for, matched against each run's manifest. "
        "Required with --aggregate-scores.",
    ),
    allow_heterogeneous: bool = typer.Option(
        False,
        "--allow-heterogeneous",
        help="Aggregate runs even if compiled_hash/adapter_version/catalog_version differ "
        "(M15 F7). Lowers confidence in the result; no flag ever raises it (S1).",
    ),
) -> None:
    """Derive findings and category scores from an evidence bundle, aggregate a depth
    sweep across a scenario family with ``--aggregate --scenario-family <family>``, or
    aggregate category scores across runs with ``--aggregate-scores --scenario-id <id>``."""
    if aggregate:
        _aggregate_depth_sweep(runs_root, scenario_family)
        return

    if aggregate_scores:
        _aggregate_scores(runs_root, scenario_id, allow_heterogeneous=allow_heterogeneous)
        return

    if run_id is None:
        typer.echo("chainbreak analyze: run_id is required unless --aggregate is given", err=True)
        raise typer.Exit(code=2)

    from chainbreak.analysis.pipeline import analyze as run_analysis
    from chainbreak.core.errors import EvidenceError
    from chainbreak.evidence.writer import write_scores
    from chainbreak.scoring.categories import not_measured_notice, score_bundle

    run_dir = runs_root / run_id
    try:
        result = run_analysis(run_dir, allow_unsealed=allow_unsealed)
    except EvidenceError as exc:
        typer.echo(f"chainbreak analyze: {exc.message}", err=True)
        raise typer.Exit(code=1) from exc

    categories = score_bundle(run_dir)
    write_scores(run_dir, _scores_document(run_dir, categories))

    typer.echo(
        f"chainbreak analyze: {len(result.findings)} finding(s), "
        f"{len(result.detector_checks)} detector check(s) -> {run_dir / 'findings.json'}"
    )
    typer.echo(
        f"chainbreak analyze: {len(categories)} categor{'y' if len(categories) == 1 else 'ies'} "
        f"scored -> {run_dir / 'scores.json'}"
    )
    for category_result in categories:
        typer.echo(
            f"  {category_result.category.value}: {category_result.status.value} "
            f"coverage {category_result.coverage:.2f} confidence {category_result.confidence.value}"
        )
    notice = not_measured_notice(categories)
    if notice is not None:
        typer.echo(notice)


def _scores_document(run_dir: Path, categories: Sequence[CategoryResult]) -> dict[str, object]:
    """``scores.json``'s shape. ``analyzed_at`` comes from the bundle's own
    ``completed_at``, never a wall-clock read -- ``scoring/categories.py``
    is a pure function of bundle content, so this document must be too
    (mirroring ``analysis/pipeline.py::_findings_document``'s F8 idempotency
    exactly)."""
    from chainbreak.evidence.reader import read_manifest

    manifest = read_manifest(run_dir / "manifest.json")
    return {
        "analysis": {"analyzed_at": manifest.completed_at},
        "categories": [c.model_dump(mode="json") for c in categories],
    }


def _aggregate_scores(
    runs_root: Path, scenario_id: str | None, *, allow_heterogeneous: bool
) -> None:
    """M15 F7/F8: every sealed run under ``runs_root`` whose manifest names
    ``scenario_id`` becomes one :class:`~chainbreak.scoring.aggregate.RunScoreSet`,
    combined with :func:`~chainbreak.scoring.aggregate.aggregate_runs`."""
    if scenario_id is None:
        typer.echo("chainbreak analyze --aggregate-scores: --scenario-id is required", err=True)
        raise typer.Exit(code=2)
    if not runs_root.is_dir():
        typer.echo(
            f"chainbreak analyze --aggregate-scores: no such runs root {runs_root}", err=True
        )
        raise typer.Exit(code=2)

    from chainbreak.core.errors import HeterogeneousComparisonError
    from chainbreak.evidence.reader import read_manifest
    from chainbreak.scoring.aggregate import RunScoreSet, aggregate_runs, score_set_from_bundle

    run_sets: list[RunScoreSet] = []
    for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = read_manifest(manifest_path)
        if manifest.scenario.get("id") != scenario_id:
            continue
        run_sets.append(score_set_from_bundle(run_dir))

    if not run_sets:
        typer.echo(
            f"chainbreak analyze --aggregate-scores: no runs under {runs_root} matched "
            f"scenario id {scenario_id!r}",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        report = aggregate_runs(run_sets, allow_heterogeneous=allow_heterogeneous)
    except HeterogeneousComparisonError as exc:
        typer.echo(f"chainbreak analyze --aggregate-scores: {exc.message}", err=True)
        raise typer.Exit(code=1) from exc

    heterogeneous_note = (
        ", HETEROGENEOUS -- confidence only, never a clean sample" if (report.heterogeneous) else ""
    )
    typer.echo(
        f"chainbreak analyze --aggregate-scores: {scenario_id} "
        f"({report.n_runs} run(s){heterogeneous_note})"
    )
    for category_result in report.categories:
        excluded_note = (
            f", excluded {len(category_result.excluded)}" if category_result.excluded else ""
        )
        typer.echo(
            f"  {category_result.category.value}: n={category_result.n_included}{excluded_note}"
        )
        for measurement in category_result.measurements:
            if measurement.iqr is not None:
                dispersion_note = f", IQR [{measurement.iqr[0]:.2f}, {measurement.iqr[1]:.2f}]"
            else:
                dispersion_note = " (n<5, no dispersion reported)"
            typer.echo(
                f"    {measurement.metric}: n={measurement.n} median={measurement.median:.2f}"
                f"{measurement.unit} [{measurement.low:.2f}, {measurement.high:.2f}]"
                f"{dispersion_note}"
            )


def _aggregate_depth_sweep(runs_root: Path, scenario_family: str | None) -> None:
    """M11 F6: every sealed run under ``runs_root`` whose manifest names
    ``scenario_family`` becomes one :class:`~chainbreak.analysis.drift.DepthResult`;
    ``chainbreak run`` is what stamps that family onto ``manifest.json`` in the
    first place (``cli/run.py``'s ``scenario_ref["family"]``)."""
    if scenario_family is None:
        typer.echo("chainbreak analyze --aggregate: --scenario-family is required", err=True)
        raise typer.Exit(code=2)
    if not runs_root.is_dir():
        typer.echo(f"chainbreak analyze --aggregate: no such runs root {runs_root}", err=True)
        raise typer.Exit(code=2)

    from chainbreak.analysis.drift import (
        DepthResult,
        depth_result_from_bundle,
        summarize_depth_sweep,
    )
    from chainbreak.evidence.reader import read_manifest

    results: list[DepthResult] = []
    for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = read_manifest(manifest_path)
        if manifest.scenario.get("family") != scenario_family:
            continue
        results.append(depth_result_from_bundle(run_dir))

    if not results:
        typer.echo(
            f"chainbreak analyze --aggregate: no runs under {runs_root} matched family "
            f"{scenario_family!r}",
            err=True,
        )
        raise typer.Exit(code=1)

    report = summarize_depth_sweep(results)
    typer.echo(
        f"chainbreak analyze --aggregate: {scenario_family} depth sweep "
        f"({len(report.results)} depth(s))"
    )
    for r in report.results:
        typer.echo(
            f"  depth {r.depth}: divergence {r.divergence_rate_per_hop:.3f}/hop "
            f"({r.diverged_hops}/{r.total_hops} hops), exclusions {r.exclusion_rate:.3f} "
            f"({r.excluded_cells}/{r.total_cells} cells) -- {r.scenario_id}"
        )
    if report.inconclusive:
        typer.echo(f"chainbreak analyze --aggregate: INCONCLUSIVE -- {report.inconclusive_reason}")
    else:
        typer.echo("chainbreak analyze --aggregate: no divergence/exclusion confound detected (F6)")
