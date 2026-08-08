"""`chainbreak analyze` -- resolved by M7 (analysis/pipeline.py)."""

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


def test_analyze_a_sealed_bundle(runs_root: Path) -> None:
    from chainbreak.cli.main import app

    runner = CliRunner()
    result = runner.invoke(
        app, ["analyze", "01J8XKQ4V7ZP3N2M9YB6TCGOLD", "--runs-root", str(runs_root)]
    )
    assert result.exit_code == 0
    assert "finding(s)" in result.output
    assert (runs_root / "01J8XKQ4V7ZP3N2M9YB6TCGOLD" / "findings.json").is_file()


def test_analyze_refuses_a_tampered_bundle_without_allow_unsealed(tmp_path: Path) -> None:
    from chainbreak.cli.main import app

    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    shutil.copytree(TAMPERED_RUN_DIR, runs_root / TAMPERED_RUN_DIR.name)
    runner = CliRunner()
    result = runner.invoke(
        app, ["analyze", "01J8XKQ4V7ZP3N2M9YB6TCGOLD", "--runs-root", str(runs_root)]
    )
    assert result.exit_code == 1
    assert not (runs_root / "01J8XKQ4V7ZP3N2M9YB6TCGOLD" / "findings.json").exists()


def test_analyze_allow_unsealed_proceeds_anyway(tmp_path: Path) -> None:
    from chainbreak.cli.main import app

    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    shutil.copytree(TAMPERED_RUN_DIR, runs_root / TAMPERED_RUN_DIR.name)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "analyze",
            "01J8XKQ4V7ZP3N2M9YB6TCGOLD",
            "--runs-root",
            str(runs_root),
            "--allow-unsealed",
        ],
    )
    assert result.exit_code == 0
    assert (runs_root / "01J8XKQ4V7ZP3N2M9YB6TCGOLD" / "findings.json").is_file()


def test_analyze_missing_run_exits_one(tmp_path: Path) -> None:
    from chainbreak.cli.main import app

    runner = CliRunner()
    result = runner.invoke(
        app, ["analyze", "does-not-exist", "--runs-root", str(tmp_path / "runs")]
    )
    assert result.exit_code == 1
