"""`chainbreak runs list|show|reindex` and `chainbreak evidence export
--public` -- resolved by M6 (cli/runs.py wraps evidence/index.py and
evidence/export.py; no business logic lives in the CLI module itself,
ARCHITECTURE.md section 3.1)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_RUN_DIR = (
    REPO_ROOT / "tests" / "fixtures" / "bundles" / "golden" / "01J8XKQ4V7ZP3N2M9YB6TCGOLD"
)


@pytest.fixture
def runs_root(tmp_path: Path) -> Path:
    root = tmp_path / "runs"
    root.mkdir()
    shutil.copytree(GOLDEN_RUN_DIR, root / GOLDEN_RUN_DIR.name)
    return root


def test_runs_reindex_then_list(runs_root: Path) -> None:
    from chainbreak.cli.main import app

    runner = CliRunner()
    reindex_result = runner.invoke(app, ["runs", "reindex", "--runs-root", str(runs_root)])
    assert reindex_result.exit_code == 0
    assert "reindexed 1 run" in reindex_result.output

    list_result = runner.invoke(app, ["runs", "list", "--runs-root", str(runs_root)])
    assert list_result.exit_code == 0
    assert "01J8XKQ4V7ZP3N2M9YB6TCGOLD" in list_result.output
    assert "sealed" in list_result.output


def test_runs_list_on_an_empty_runs_root_is_informative(tmp_path: Path) -> None:
    from chainbreak.cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["runs", "list", "--runs-root", str(tmp_path / "runs")])
    assert result.exit_code == 0
    assert "no indexed runs" in result.output


def test_runs_show_a_sealed_run(runs_root: Path) -> None:
    from chainbreak.cli.main import app

    runner = CliRunner()
    result = runner.invoke(
        app, ["runs", "show", "01J8XKQ4V7ZP3N2M9YB6TCGOLD", "--runs-root", str(runs_root)]
    )
    assert result.exit_code == 0
    assert "run_id:      01J8XKQ4V7ZP3N2M9YB6TCGOLD" in result.output
    assert "sealed:      True" in result.output
    assert "root_verified:True" in result.output


def test_runs_show_a_missing_run(tmp_path: Path) -> None:
    from chainbreak.cli.main import app

    runner = CliRunner()
    result = runner.invoke(
        app, ["runs", "show", "not-a-real-run", "--runs-root", str(tmp_path / "runs")]
    )
    assert result.exit_code == 1


def test_evidence_export_public_dry_run(runs_root: Path) -> None:
    from chainbreak.cli.main import app

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "evidence",
            "export",
            "01J8XKQ4V7ZP3N2M9YB6TCGOLD",
            "--public",
            "--dry-run",
            "--runs-root",
            str(runs_root),
        ],
    )
    assert result.exit_code == 0
    assert "dry run" in result.output


def test_evidence_export_without_public_is_still_a_stub(runs_root: Path) -> None:
    from chainbreak.cli.main import app

    runner = CliRunner()
    result = runner.invoke(
        app, ["evidence", "export", "01J8XKQ4V7ZP3N2M9YB6TCGOLD", "--runs-root", str(runs_root)]
    )
    assert result.exit_code == 2
    assert "only --public export is implemented" in result.output


def test_evidence_export_archive_writes_a_self_contained_tarball(
    runs_root: Path, tmp_path: Path
) -> None:
    from chainbreak.cli.main import app

    output = tmp_path / "out.tar.gz"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "evidence",
            "export",
            "01J8XKQ4V7ZP3N2M9YB6TCGOLD",
            "--archive",
            "--output",
            str(output),
            "--runs-root",
            str(runs_root),
        ],
    )
    assert result.exit_code == 0, result.output
    assert output.is_file()
    assert "wrote self-contained archive" in result.output


def test_evidence_export_archive_and_dry_run_together_exits_two(runs_root: Path) -> None:
    from chainbreak.cli.main import app

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "evidence",
            "export",
            "01J8XKQ4V7ZP3N2M9YB6TCGOLD",
            "--archive",
            "--dry-run",
            "--runs-root",
            str(runs_root),
        ],
    )
    assert result.exit_code == 2
    assert "--dry-run is not supported" in result.output
