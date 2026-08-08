"""`chainbreak infra plan|apply|destroy|status|verify-clean` -- resolved by
M9 (`src/chainbreak/cli/infra.py`). `plan`/`apply`/`destroy` wrap the real
`terraform` binary and are exercised here only through their argument
handling (unknown environment, missing terraform) -- actually running
`terraform` needs a real environment directory and provider plugins, which
`tests/aws/test_cleanup_contract.py` (e2e-marked) covers instead. `status`
and `verify-clean` need no terraform subprocess at all and are exercised
for real.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from moto import mock_aws
from typer.testing import CliRunner

pytestmark = pytest.mark.unit

_VALID_OUTPUTS = {
    "namespace": "cb-a1b2c3d4",
    "account_id": "123456789012",
    "region": "us-east-1",
    "bootstrap_role_arn": "arn:aws:iam::123456789012:role/cb-a1b2c3d4-bootstrap",
    "principal_role_arn": "arn:aws:iam::123456789012:role/cb-a1b2c3d4-principal",
    "objectstore_bucket": "cb-a1b2c3d4-objectstore",
    "objectstore_marker_key": "cb-a1b2c3d4/markers/marker.json",
    "objectstore_marker_sha256": "sha256:" + "0" * 64,
    "keyvalue_table": "cb-a1b2c3d4-keyvalue",
    "keyvalue_marker_pk": "cb-marker",
    "keyvalue_marker_sha256": "sha256:" + "0" * 64,
    "function_name": "cb-a1b2c3d4-noop",
    "queue_url": "https://sqs.us-east-1.amazonaws.com/123456789012/cb-a1b2c3d4-queue",
    "external_id": "cb-a1b2c3d4",
    "infrastructure_fingerprint": "sha256:" + "0" * 64,
    **{
        f"agent_{letter}_role_arn": f"arn:aws:iam::123456789012:role/cb-a1b2c3d4-agent-{letter}"
        for letter in "abcdef"
    },
}


class TestUnknownEnvironment:
    @pytest.mark.parametrize("subcommand", [["plan"], ["apply"], ["destroy"]])
    def test_unknown_environment_exits_two(
        self, subcommand: list[str], tmp_path: Path, monkeypatch
    ):
        from chainbreak.cli.main import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(app, ["infra", *subcommand, "does-not-exist"])
        assert result.exit_code == 2
        assert "no such environment" in result.output

    def test_status_unknown_environment_exits_two(self, tmp_path: Path, monkeypatch):
        from chainbreak.cli.main import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(app, ["infra", "status", "does-not-exist"])
        assert result.exit_code == 2


class TestTerraformNotOnPath:
    def test_plan_reports_missing_terraform_clearly(self, tmp_path: Path, monkeypatch):
        from chainbreak.cli.main import app

        env_dir = tmp_path / "infra" / "terraform" / "environments" / "aws-sandbox"
        env_dir.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("shutil.which", lambda _name: None)

        runner = CliRunner()
        result = runner.invoke(app, ["infra", "plan"])
        assert result.exit_code == 2
        assert "terraform not found on PATH" in result.output


class TestStatus:
    def test_no_captured_outputs_exits_one(self, tmp_path: Path, monkeypatch):
        from chainbreak.cli.main import app

        env_dir = tmp_path / "infra" / "terraform" / "environments" / "aws-sandbox"
        env_dir.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(app, ["infra", "status"])
        assert result.exit_code == 1
        assert "run `chainbreak infra apply` first" in result.output

    def test_valid_outputs_reports_namespace_and_account(self, tmp_path: Path, monkeypatch):
        from chainbreak.cli.main import app

        env_dir = tmp_path / "infra" / "terraform" / "environments" / "aws-sandbox"
        env_dir.mkdir(parents=True)
        wrapped = {k: {"value": v} for k, v in _VALID_OUTPUTS.items()}
        (env_dir / "outputs.json").write_text(json.dumps(wrapped), encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(app, ["infra", "status"])
        assert result.exit_code == 0
        assert "namespace: cb-a1b2c3d4" in result.output
        assert "account_id: 123456789012" in result.output

    def test_malformed_outputs_exits_one_with_a_clear_message(self, tmp_path: Path, monkeypatch):
        from chainbreak.cli.main import app

        env_dir = tmp_path / "infra" / "terraform" / "environments" / "aws-sandbox"
        env_dir.mkdir(parents=True)
        (env_dir / "outputs.json").write_text("{not valid json", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(app, ["infra", "status"])
        assert result.exit_code == 1


class TestVerifyClean:
    def test_works_even_when_the_environment_directory_was_never_checked_out(
        self, tmp_path: Path, monkeypatch
    ):
        """F5's whole point is verifying cleanup independent of local
        Terraform state -- an operator auditing an account by tag should
        not need infra/terraform/environments/<name>/ to exist on disk at
        all, so long as --region (or ambient AWS config) supplies one."""
        from chainbreak.cli.main import app

        monkeypatch.chdir(tmp_path)  # no infra/ tree here whatsoever
        runner = CliRunner()
        with mock_aws():
            result = runner.invoke(app, ["infra", "verify-clean", "--region", "us-east-1"])
        assert result.exit_code == 0
        assert "nothing remaining" in result.output

    def test_nothing_remaining_exits_zero(self, tmp_path: Path, monkeypatch):
        from chainbreak.cli.main import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        with mock_aws():
            result = runner.invoke(app, ["infra", "verify-clean", "--region", "us-east-1"])
        assert result.exit_code == 0
        assert "nothing remaining" in result.output

    def test_remaining_tagged_resource_exits_one(self, tmp_path: Path, monkeypatch):
        from chainbreak.cli.main import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        with mock_aws():
            import boto3

            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket="cb-a1b2c3d4-objectstore")
            s3.put_bucket_tagging(
                Bucket="cb-a1b2c3d4-objectstore",
                Tagging={"TagSet": [{"Key": "Project", "Value": "CHAINBREAK"}]},
            )
            result = runner.invoke(app, ["infra", "verify-clean", "--region", "us-east-1"])
        assert result.exit_code == 1
        assert "still tagged Project=CHAINBREAK" in result.output
        assert "cb-a1b2c3d4-objectstore" in result.output

    def test_no_region_available_exits_one_with_a_clear_message(self, tmp_path: Path, monkeypatch):
        import boto3

        from chainbreak.cli.main import app

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
        monkeypatch.delenv("AWS_REGION", raising=False)
        monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-such-config"))
        monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-such-credentials"))
        # boto3 caches a module-level default session lazily; an earlier
        # test in this same process may have already created one with a
        # region baked in from environment state that existed before this
        # test's monkeypatching. Force a fresh session so this test only
        # observes its own environment.
        monkeypatch.setattr(boto3, "DEFAULT_SESSION", None)
        runner = CliRunner()
        with mock_aws():
            result = runner.invoke(app, ["infra", "verify-clean"])
        assert result.exit_code == 1
        assert "no region available" in result.output

    def test_uses_captured_region_when_available(self, tmp_path: Path, monkeypatch):
        from chainbreak.cli.main import app

        env_dir = tmp_path / "infra" / "terraform" / "environments" / "aws-sandbox"
        env_dir.mkdir(parents=True)
        wrapped = {k: {"value": v} for k, v in _VALID_OUTPUTS.items()}
        (env_dir / "outputs.json").write_text(json.dumps(wrapped), encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        with mock_aws():
            result = runner.invoke(app, ["infra", "verify-clean"])
        assert result.exit_code == 0
