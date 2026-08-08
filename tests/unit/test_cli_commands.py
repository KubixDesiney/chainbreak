"""F3 (`chainbreak validate`'s six checks) and F4 (unimplemented commands
exit 2, never a stack trace) -- acceptance criteria 1 and 5 of
M04-cli-config-safety.md.

F3 is tested at two levels: the six ``_check_*`` functions directly (each
one is the unit a "fails informatively" claim is about), and one end-to-end
``CliRunner`` pass through ``chainbreak validate`` against a real, valid
config plus the repo's own scenario corpus, run from an isolated cwd so it
cannot pick up a stray ``chainbreak.toml`` or ambient ``CHAINBREAK_*``
env var from the developer's shell.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from chainbreak.cli.validate import (
    _check_account_allowlist,
    _check_catalog_loads,
    _check_clock_offset,
    _check_config_resolves,
    _check_namespace_prefix,
    _check_regions,
    _check_scenarios_compile,
)
from chainbreak.config.settings import Settings

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_SCENARIOS_DIR = REPO_ROOT / "scenarios"


class TestCheckConfigResolves:
    def test_passes_when_no_repo_config_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CHAINBREAK_ALLOWED_ACCOUNT_IDS", raising=False)
        result, settings = _check_config_resolves()
        assert result.passed is True
        assert settings == Settings()


class TestCheckAccountAllowlist:
    def test_fails_when_empty(self):
        result = _check_account_allowlist(Settings(allowed_account_ids=()))
        assert result.passed is False
        assert "no accounts" in result.detail

    def test_fails_when_not_explicit_12_digit(self):
        result = _check_account_allowlist(Settings(allowed_account_ids=("*",)))
        assert result.passed is False

    def test_passes_with_explicit_account(self):
        result = _check_account_allowlist(Settings(allowed_account_ids=("123456789012",)))
        assert result.passed is True


class TestCheckRegions:
    def test_fails_when_empty(self):
        result = _check_regions(Settings(allowed_regions=()))
        assert result.passed is False

    def test_passes_when_configured(self):
        result = _check_regions(Settings(allowed_regions=("us-east-1",)))
        assert result.passed is True


class TestCheckNamespacePrefix:
    def test_fails_on_malformed_prefix(self):
        result = _check_namespace_prefix(Settings(namespace_prefix="Not_Valid!"))
        assert result.passed is False

    def test_passes_on_well_formed_prefix(self):
        result = _check_namespace_prefix(Settings(namespace_prefix="cb"))
        assert result.passed is True


class TestCheckCatalogLoads:
    def test_passes_against_the_real_catalog(self):
        result = _check_catalog_loads()
        assert result.passed is True
        assert "capabilities" in result.detail


class TestCheckScenariosCompile:
    def test_fails_when_directory_has_no_yaml_files(self, tmp_path: Path):
        result = _check_scenarios_compile(tmp_path)
        assert result.passed is False
        assert "no scenario files" in result.detail

    def test_passes_against_the_repo_scenario_corpus(self):
        result = _check_scenarios_compile(REPO_SCENARIOS_DIR)
        assert result.passed is True


class TestCheckClockOffset:
    def test_unmeasured_offset_passes(self):
        result = _check_clock_offset()
        assert result.passed is True
        assert "unmeasured" in result.detail


class TestValidateCommandEndToEnd:
    def _isolated_toml(self, tmp_path: Path) -> Path:
        toml_path = tmp_path / "chainbreak.toml"
        toml_path.write_text(
            """
            [safety]
            allowed_account_ids = ["123456789012"]
            allowed_regions = ["us-east-2"]
            namespace_prefix = "cb"
            """,
            encoding="utf-8",
        )
        return toml_path

    def test_correct_config_passes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        self._isolated_toml(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CHAINBREAK_ALLOWED_ACCOUNT_IDS", raising=False)

        from chainbreak.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["validate", "--scenarios-dir", str(REPO_SCENARIOS_DIR)])
        assert result.exit_code == 0, result.output
        assert "FAIL" not in result.output

    def test_correct_config_passes_as_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        self._isolated_toml(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CHAINBREAK_ALLOWED_ACCOUNT_IDS", raising=False)

        from chainbreak.cli.main import app

        runner = CliRunner()
        result = runner.invoke(
            app, ["validate", "--json", "--scenarios-dir", str(REPO_SCENARIOS_DIR)]
        )
        assert result.exit_code == 0, result.output
        assert '"passed": true' in result.output

    def test_missing_config_fails_informatively(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CHAINBREAK_ALLOWED_ACCOUNT_IDS", raising=False)
        monkeypatch.delenv("CHAINBREAK_ALLOWED_REGIONS", raising=False)

        from chainbreak.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["validate", "--json"])
        assert result.exit_code == 1
        assert '"passed": false' in result.output
        assert "no accounts configured" in result.output


class TestUnimplementedCommandsExitTwoNotAStackTrace:
    @pytest.mark.parametrize(
        "args",
        [
            ["run"],
            ["analyze"],
            ["report"],
            # `runs list|show|reindex` and `evidence export --public` were
            # resolved by M6; see test_cli_runs_command.py for their real
            # behavior. `evidence export` without --public remains a stub.
            ["infra", "plan"],
            ["infra", "apply"],
            ["infra", "destroy"],
            ["infra", "status"],
            ["infra", "verify-clean"],
            ["compare"],
        ],
    )
    def test_exits_two_with_a_clear_message(self, args: list[str]):
        from chainbreak.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, args)
        assert result.exit_code == 2
        assert "not implemented until M" in result.output
        assert result.exception is None or isinstance(result.exception, SystemExit)
