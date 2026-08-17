"""`chainbreak runs list|show|reindex` and `chainbreak evidence export`.

Thin CLI adapters over ``evidence/index.py`` and ``evidence/export.py`` (M6).
No business logic lives here (ARCHITECTURE.md section 3.1).
"""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="Inspect past runs.")
evidence_app = typer.Typer(help="Export evidence bundles.")

_DEFAULT_RUNS_ROOT = Path("runs")


def _index_path(runs_root: Path) -> Path:
    return runs_root / "index.db"


@app.command("list")
def list_runs(
    runs_root: Path = typer.Option(
        _DEFAULT_RUNS_ROOT, "--runs-root", help="Directory containing run bundles."
    ),
) -> None:
    """List indexed runs, most recent first."""
    from chainbreak.evidence.index import list_runs as index_list_runs
    from chainbreak.evidence.index import open_index

    conn = open_index(_index_path(runs_root))
    rows = index_list_runs(conn)
    conn.close()
    if not rows:
        typer.echo("no indexed runs (run `chainbreak runs reindex` after a run completes)")
        return
    for row in rows:
        sealed = "sealed" if row["sealed"] else "UNSEALED"
        typer.echo(
            f"{row['run_id']}  {row['created_at']}  {row['status']}  {row['scenario_id']}  {sealed}"
        )


@app.command("show")
def show_run(
    run_id: str,
    runs_root: Path = typer.Option(
        _DEFAULT_RUNS_ROOT, "--runs-root", help="Directory containing run bundles."
    ),
) -> None:
    """Show one run's manifest summary."""
    from chainbreak.core.errors import EvidenceError
    from chainbreak.evidence.reader import read_manifest, verify_integrity

    run_dir = runs_root / run_id
    try:
        manifest = read_manifest(run_dir / "manifest.json")
    except EvidenceError as exc:
        typer.echo(f"chainbreak runs show: {exc.message}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"run_id:      {manifest.run_id}")
    typer.echo(f"status:      {manifest.status}")
    typer.echo(f"created_at:  {manifest.created_at}")
    typer.echo(f"completed_at:{manifest.completed_at}")
    typer.echo(f"scenario:    {manifest.scenario.get('id')} v{manifest.scenario.get('version')}")
    typer.echo(f"provider:    {manifest.provenance.get('provider')}")
    typer.echo(f"sealed:      {manifest.integrity.root is not None}")
    if manifest.integrity.root is not None:
        typer.echo(f"root_verified:{verify_integrity(run_dir)}")
    typer.echo(
        f"counts:      observations={manifest.counts.observations} "
        f"events={manifest.counts.events} "
        f"policy_snapshots={manifest.counts.policy_snapshots} "
        f"credentials={manifest.counts.credentials}"
    )


@app.command("reindex")
def reindex_runs(
    runs_root: Path = typer.Option(
        _DEFAULT_RUNS_ROOT, "--runs-root", help="Directory containing run bundles."
    ),
) -> None:
    """Rebuild the local run index from the bundles on disk (F5)."""
    from chainbreak.evidence.index import reindex

    count = reindex(_index_path(runs_root), runs_root)
    typer.echo(f"reindexed {count} run(s) from {runs_root}")


@evidence_app.command("export")
def export_evidence(
    run_id: str,
    public: bool = typer.Option(
        False, "--public", help="Scrub identifiers before writing the copy (F6)."
    ),
    archive: bool = typer.Option(
        False,
        "--archive",
        help="Produce a self-contained tarball (bundle, resolved scenario, capability "
        "catalog as it was at run time, JSON Schemas, REPRODUCE.md) (M18 F4). Always "
        "implies --public scrubbing (S1); there is no unscrubbed archive path.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Report what would be stripped without writing files."
    ),
    output_dir: Path | None = typer.Option(
        None, "--output-dir", help="Destination directory for --public (ignored by --archive)."
    ),
    output: Path | None = typer.Option(
        None, "-o", "--output", help="Destination file for --archive (ignored by --public)."
    ),
    include_policy_documents: bool = typer.Option(
        False, "--include-policy-documents", help="Do not strip policy document bodies."
    ),
    runs_root: Path = typer.Option(
        _DEFAULT_RUNS_ROOT, "--runs-root", help="Directory containing run bundles."
    ),
    provider: str = typer.Option(
        "offline", "--provider", help="Provenance context: offline or aws."
    ),
    block_id: str | None = typer.Option(
        None, "--block-id", help="Required AWS experiment block identifier."
    ),
) -> None:
    """Export a bundle. ``--public`` produces the scrubbed, shareable copy (F6);
    ``--archive`` additionally packages it into a self-contained tarball (M18 F4)."""
    if provider not in {"offline", "aws"}:
        typer.echo("chainbreak evidence export: --provider must be offline or aws", err=True)
        raise typer.Exit(code=2)
    if provider == "aws" and not block_id:
        typer.echo(
            "chainbreak evidence export: --block-id is required with --provider aws", err=True
        )
        raise typer.Exit(code=2)
    if not public and not archive:
        typer.echo("chainbreak evidence export: only --public export is implemented (M6)", err=True)
        raise typer.Exit(code=2)

    from chainbreak.core.errors import EvidenceError

    run_dir = runs_root / run_id

    if archive:
        if dry_run:
            typer.echo("chainbreak evidence export --archive: --dry-run is not supported", err=True)
            raise typer.Exit(code=2)

        from chainbreak.evidence.archive import create_archive

        try:
            archive_report = create_archive(
                run_dir,
                output_path=output,
                include_policy_documents=include_policy_documents,
            )
        except EvidenceError as exc:
            typer.echo(f"chainbreak evidence export --archive: {exc.message}", err=True)
            raise typer.Exit(code=1) from exc

        typer.echo(archive_report.export_report.render_diff())
        typer.echo(
            f"wrote self-contained archive to {archive_report.archive_path} "
            f"(catalog {archive_report.catalog_version}, "
            f"{len(archive_report.schema_files)} schema file(s))"
        )
        return

    from chainbreak.evidence.export import export_public

    try:
        report = export_public(
            run_dir,
            output_dir=output_dir,
            dry_run=dry_run,
            include_policy_documents=include_policy_documents,
        )
    except EvidenceError as exc:
        typer.echo(f"chainbreak evidence export: {exc.message}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(report.render_diff())
    if dry_run:
        typer.echo(f"(dry run: nothing written to {report.output_dir})")
    else:
        typer.echo(f"wrote scrubbed bundle to {report.output_dir}")
