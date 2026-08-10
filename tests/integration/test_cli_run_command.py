"""`chainbreak run` (M10): CLI-level argument handling and the fake-provider
happy path end to end through the real `CliRunner` -- deeper orchestration
behavior (negative-control detection, control-capability/precondition
discard, F6 re-delegation) is `tests/integration/test_scope_attenuation.py`'s
job, exercised directly against `execution/orchestrator.py` rather than
through argument parsing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
BASIC_SCENARIO = REPO_ROOT / "scenarios" / "scope-attenuation" / "basic.yaml"


class TestArgumentHandling:
    def test_missing_scenario_argument_is_a_click_usage_error(self):
        from chainbreak.cli.main import app

        result = CliRunner().invoke(app, ["run"])
        assert result.exit_code == 2

    def test_unknown_scenario_file_exits_two(self, tmp_path: Path):
        from chainbreak.cli.main import app

        result = CliRunner().invoke(app, ["run", str(tmp_path / "does-not-exist.yaml")])
        assert result.exit_code == 2
        assert "no such scenario file" in result.output

    def test_unknown_provider_exits_two(self):
        from chainbreak.cli.main import app

        result = CliRunner().invoke(app, ["run", str(BASIC_SCENARIO), "--provider", "bogus"])
        assert result.exit_code == 2
        assert "unknown provider" in result.output

    def test_aws_provider_is_a_documented_stub_until_m17(self):
        from chainbreak.cli.main import app

        result = CliRunner().invoke(app, ["run", str(BASIC_SCENARIO), "--provider", "aws"])
        assert result.exit_code == 2
        assert "not implemented until M17" in result.output

    def test_unknown_fake_profile_exits_two(self):
        from chainbreak.cli.main import app

        result = CliRunner().invoke(app, ["run", str(BASIC_SCENARIO), "--fake-profile", "bogus"])
        assert result.exit_code == 2
        assert "unknown --fake-profile" in result.output

    def test_a_structurally_invalid_scenario_exits_one_not_a_stack_trace(self, tmp_path: Path):
        from chainbreak.cli.main import app

        bad = tmp_path / "bad.yaml"
        bad.write_text("apiVersion: chainbreak.dev/v1alpha1\nkind: Scenario\n", encoding="utf-8")
        result = CliRunner().invoke(app, ["run", str(bad), "--provider", "fake"])
        assert result.exit_code == 1
        assert result.exception is None or isinstance(result.exception, SystemExit)


class TestFakeProfileFlag:
    def test_eventual_profile_runs_end_to_end(self, tmp_path: Path, monkeypatch):
        from chainbreak.cli.main import app

        monkeypatch.chdir(tmp_path)
        runs_root = tmp_path / "runs"
        scenario = REPO_ROOT / "scenarios" / "revocation" / "inline-deny.yaml"
        result = CliRunner().invoke(
            app,
            [
                "run",
                str(scenario),
                "--provider",
                "fake",
                "--fake-profile",
                "eventual",
                "--seed",
                "5",
                "--runs-root",
                str(runs_root),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "COMPLETED" in result.output


class TestFakeProviderHappyPath:
    def test_scope_attenuation_basic_runs_end_to_end(self, tmp_path: Path, monkeypatch):
        from chainbreak.cli.main import app

        monkeypatch.chdir(tmp_path)  # no chainbreak.toml here -- fake needs none
        runs_root = tmp_path / "runs"
        result = CliRunner().invoke(
            app,
            [
                "run",
                str(BASIC_SCENARIO),
                "--provider",
                "fake",
                "--seed",
                "11",
                "--runs-root",
                str(runs_root),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "COMPLETED" in result.output

        run_dirs = list(runs_root.iterdir())
        assert len(run_dirs) == 1
        run_dir = run_dirs[0]
        assert (run_dir / "manifest.json").is_file()
        assert (run_dir / "observations.jsonl").is_file()

        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["status"] == "COMPLETED"

    def test_analyze_consumes_the_produced_bundle(self, tmp_path: Path, monkeypatch):
        from chainbreak.cli.main import app

        monkeypatch.chdir(tmp_path)
        runs_root = tmp_path / "runs"
        runner = CliRunner()
        run_result = runner.invoke(
            app,
            [
                "run",
                str(BASIC_SCENARIO),
                "--provider",
                "fake",
                "--seed",
                "11",
                "--runs-root",
                str(runs_root),
            ],
        )
        assert run_result.exit_code == 0, run_result.output
        run_id = next(runs_root.iterdir()).name

        analyze_result = runner.invoke(app, ["analyze", run_id, "--runs-root", str(runs_root)])
        assert analyze_result.exit_code == 0, analyze_result.output

        findings_path = runs_root / run_id / "findings.json"
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        assert findings["findings"]
        assert all(f["type"] == "EXPECTED_BEHAVIOR" for f in findings["findings"])
