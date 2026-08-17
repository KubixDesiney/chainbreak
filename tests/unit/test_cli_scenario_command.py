"""`chainbreak scenario validate|list` (cli/scenario.py) -- the thin CLI
adapter over scenarios/loader.py (M3). Exercises the command bodies
directly rather than only the library functions they wrap, since a CLI
adapter can still get argument plumbing or exit codes wrong even when the
underlying library is fully tested.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from chainbreak.cli.main import app
from chainbreak.scenarios.loader import EXIT_VALID

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_SCENARIOS_DIR = REPO_ROOT / "scenarios"
FOUR_HOP = REPO_SCENARIOS_DIR / "delegation-drift" / "four-hop.yaml"
SCENARIO_FILES = sorted(REPO_SCENARIOS_DIR.rglob("*.yaml"))


class TestScenarioValidateCommand:
    def test_valid_scenario_exits_zero(self):
        runner = CliRunner()
        result = runner.invoke(app, ["scenario", "validate", str(FOUR_HOP)])
        assert result.exit_code == EXIT_VALID, result.output

    @pytest.mark.parametrize("path", SCENARIO_FILES, ids=lambda path: path.stem)
    def test_every_shipped_scenario_validates_through_the_cli(self, path: Path):
        runner = CliRunner()
        result = runner.invoke(app, ["scenario", "validate", str(path)])
        assert result.exit_code == EXIT_VALID, result.output

    def test_validation_makes_no_aws_call(self, monkeypatch: pytest.MonkeyPatch):
        import boto3
        import botocore.session

        def fail_if_called(*args: object, **kwargs: object) -> None:
            raise AssertionError(f"scenario validation made an AWS call: {args!r} {kwargs!r}")

        monkeypatch.setattr(boto3, "client", fail_if_called)
        monkeypatch.setattr(boto3.session.Session, "client", fail_if_called)
        monkeypatch.setattr(botocore.session.Session, "create_client", fail_if_called)

        runner = CliRunner()
        for path in SCENARIO_FILES:
            result = runner.invoke(app, ["scenario", "validate", str(path)])
            assert result.exit_code == EXIT_VALID, result.output

    def test_nonexistent_scenario_fails(self, tmp_path: Path):
        runner = CliRunner()
        missing = tmp_path / "does-not-exist.yaml"
        result = runner.invoke(app, ["scenario", "validate", str(missing)])
        assert result.exit_code != 0

    def test_structurally_invalid_scenario_prints_errors(self, tmp_path: Path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("not: [valid, scenario, document", encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(app, ["scenario", "validate", str(bad)])
        assert result.exit_code != 0
        assert "FAIL" in result.output


class TestScenarioListCommand:
    def test_lists_yaml_files_under_the_repo_corpus(self):
        runner = CliRunner()
        result = runner.invoke(app, ["scenario", "list", "--dir", str(REPO_SCENARIOS_DIR)])
        assert result.exit_code == 0
        assert "four-hop.yaml" in result.output

    def test_missing_directory_exits_two(self, tmp_path: Path):
        runner = CliRunner()
        missing_dir = tmp_path / "no-such-dir"
        result = runner.invoke(app, ["scenario", "list", "--dir", str(missing_dir)])
        assert result.exit_code == 2
        assert "no such directory" in result.output

    def test_empty_directory_reports_no_scenarios_found(self, tmp_path: Path):
        runner = CliRunner()
        result = runner.invoke(app, ["scenario", "list", "--dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "no scenario files found" in result.output
