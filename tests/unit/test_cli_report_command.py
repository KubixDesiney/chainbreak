"""`chainbreak report` -- resolved by M16 (reporting/*). This file covers
the CLI's own argument handling and exit codes; ``test_report_generation.py``
(integration) covers what the rendered report actually contains.
"""

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
TAMPERED_RUN_DIR = (
    REPO_ROOT / "tests" / "fixtures" / "bundles" / "tampered" / "01J8XKQ4V7ZP3N2M9YB6TCGOLD"
)


@pytest.fixture
def runs_root(tmp_path: Path) -> Path:
    root = tmp_path / "runs"
    root.mkdir()
    shutil.copytree(GOLDEN_RUN_DIR, root / GOLDEN_RUN_DIR.name)
    return root


def test_missing_run_id_exits_two(tmp_path: Path) -> None:
    from chainbreak.cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["report", "--runs-root", str(tmp_path / "runs")])
    assert result.exit_code == 2
    assert "run_id is required" in result.output


def test_unknown_format_exits_two(runs_root: Path) -> None:
    from chainbreak.cli.main import app

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "report",
            "01J8XKQ4V7ZP3N2M9YB6TCGOLD",
            "--format",
            "pdf",
            "--runs-root",
            str(runs_root),
        ],
    )
    assert result.exit_code == 2
    assert "unknown --format" in result.output


def test_missing_run_exits_two(tmp_path: Path) -> None:
    from chainbreak.cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["report", "does-not-exist", "--runs-root", str(tmp_path / "runs")])
    assert result.exit_code == 2
    assert "no such run" in result.output


def test_terminal_report_to_stdout(runs_root: Path) -> None:
    from chainbreak.cli.main import app

    runner = CliRunner()
    result = runner.invoke(
        app, ["report", "01J8XKQ4V7ZP3N2M9YB6TCGOLD", "--runs-root", str(runs_root)]
    )
    assert result.exit_code == 0
    assert "CHAINBREAK" in result.output
    assert "01J8XKQ4V7ZP3N2M9YB6TCGOLD" in result.output


@pytest.mark.parametrize("output_format", ["terminal", "markdown", "html"])
def test_write_each_format_to_a_file(runs_root: Path, tmp_path: Path, output_format: str) -> None:
    from chainbreak.cli.main import app

    out = tmp_path / f"report.{output_format}"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "report",
            "01J8XKQ4V7ZP3N2M9YB6TCGOLD",
            "--format",
            output_format,
            "--output",
            str(out),
            "--runs-root",
            str(runs_root),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.is_file()
    assert "01J8XKQ4V7ZP3N2M9YB6TCGOLD" in out.read_text(encoding="utf-8")


def test_refuses_a_tampered_bundle_without_allow_unsealed(tmp_path: Path) -> None:
    from chainbreak.cli.main import app

    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    shutil.copytree(TAMPERED_RUN_DIR, runs_root / TAMPERED_RUN_DIR.name)
    runner = CliRunner()
    result = runner.invoke(
        app, ["report", "01J8XKQ4V7ZP3N2M9YB6TCGOLD", "--runs-root", str(runs_root)]
    )
    assert result.exit_code == 1


def test_allow_unsealed_proceeds_anyway(tmp_path: Path) -> None:
    from chainbreak.cli.main import app

    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    shutil.copytree(TAMPERED_RUN_DIR, runs_root / TAMPERED_RUN_DIR.name)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "report",
            "01J8XKQ4V7ZP3N2M9YB6TCGOLD",
            "--runs-root",
            str(runs_root),
            "--allow-unsealed",
        ],
    )
    assert result.exit_code == 0, result.output
