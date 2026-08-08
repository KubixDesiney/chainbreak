"""``providers/aws/preflight.py::load_terraform_outputs`` (P5): reading and
validating a ``terraform output -json`` document. Pure file I/O against a
``tmp_path`` fixture -- no AWS account needed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chainbreak.core.errors import ConfigurationError
from chainbreak.providers.aws.preflight import load_terraform_outputs

pytestmark = pytest.mark.unit


def _valid_outputs() -> dict[str, object]:
    values: dict[str, str] = {
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
    }
    for letter in "abcdef":
        values[f"agent_{letter}_role_arn"] = (
            f"arn:aws:iam::123456789012:role/cb-a1b2c3d4-agent-{letter}"
        )
    return values


def _write(path: Path, document: dict[str, object]) -> Path:
    outputs_path = path / "outputs.json"
    outputs_path.write_text(json.dumps(document), encoding="utf-8")
    return outputs_path


class TestLoadTerraformOutputs:
    def test_loads_a_valid_bare_value_document(self, tmp_path: Path):
        path = _write(tmp_path, _valid_outputs())
        outputs = load_terraform_outputs(path)
        assert outputs.namespace == "cb-a1b2c3d4"
        assert outputs.agent_role_arns["a"].endswith("agent-a")

    def test_loads_a_valid_terraform_json_wrapped_document(self, tmp_path: Path):
        wrapped = {
            k: {"value": v, "type": "string", "sensitive": False}
            for k, v in _valid_outputs().items()
        }
        path = _write(tmp_path, wrapped)
        outputs = load_terraform_outputs(path)
        assert outputs.account_id == "123456789012"

    def test_missing_file_raises_configuration_error(self, tmp_path: Path):
        with pytest.raises(ConfigurationError, match="could not read"):
            load_terraform_outputs(tmp_path / "does-not-exist.json")

    def test_malformed_json_raises_configuration_error(self, tmp_path: Path):
        path = tmp_path / "outputs.json"
        path.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="could not read"):
            load_terraform_outputs(path)

    def test_non_object_json_raises_configuration_error(self, tmp_path: Path):
        path = tmp_path / "outputs.json"
        path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
        with pytest.raises(ConfigurationError, match="must be a JSON object"):
            load_terraform_outputs(path)

    def test_missing_required_names_raises_configuration_error(self, tmp_path: Path):
        incomplete = _valid_outputs()
        del incomplete["namespace"]
        del incomplete["agent_f_role_arn"]
        path = _write(tmp_path, incomplete)
        with pytest.raises(ConfigurationError, match="missing required names") as exc_info:
            load_terraform_outputs(path)
        assert "namespace" in str(exc_info.value)
        assert "agent_f_role_arn" in str(exc_info.value)


class TestOutputShapeValidation:
    """M9's own required assertion: every output not only exists (P5) but
    matches its expected shape -- namespace regex, ARN shape, digest format
    (AWS_PROVIDER_SPEC section 8; `infra/terraform/environments/aws-sandbox/
    CONTRACT.md`'s stable output list)."""

    def test_malformed_namespace_rejected(self, tmp_path: Path):
        bad = _valid_outputs()
        bad["namespace"] = "not-a-namespace"
        path = _write(tmp_path, bad)
        with pytest.raises(ConfigurationError, match="namespace"):
            load_terraform_outputs(path)

    def test_malformed_account_id_rejected(self, tmp_path: Path):
        bad = _valid_outputs()
        bad["account_id"] = "not-twelve-digits"
        path = _write(tmp_path, bad)
        with pytest.raises(ConfigurationError, match="account_id"):
            load_terraform_outputs(path)

    def test_malformed_role_arn_rejected(self, tmp_path: Path):
        bad = _valid_outputs()
        bad["bootstrap_role_arn"] = "not-an-arn"
        path = _write(tmp_path, bad)
        with pytest.raises(ConfigurationError, match="bootstrap_role_arn"):
            load_terraform_outputs(path)

    def test_malformed_agent_role_arn_rejected(self, tmp_path: Path):
        bad = _valid_outputs()
        bad["agent_c_role_arn"] = "arn:aws:s3:::not-a-role-arn"
        path = _write(tmp_path, bad)
        with pytest.raises(ConfigurationError, match="agent_c_role_arn"):
            load_terraform_outputs(path)

    def test_malformed_digest_rejected(self, tmp_path: Path):
        bad = _valid_outputs()
        bad["objectstore_marker_sha256"] = "not-a-digest"
        path = _write(tmp_path, bad)
        with pytest.raises(ConfigurationError, match="objectstore_marker_sha256"):
            load_terraform_outputs(path)

    def test_malformed_queue_url_rejected(self, tmp_path: Path):
        bad = _valid_outputs()
        bad["queue_url"] = "not-a-url"
        path = _write(tmp_path, bad)
        with pytest.raises(ConfigurationError, match="queue_url"):
            load_terraform_outputs(path)

    def test_multiple_shape_problems_all_reported_together(self, tmp_path: Path):
        bad = _valid_outputs()
        bad["namespace"] = "bad"
        bad["account_id"] = "bad"
        path = _write(tmp_path, bad)
        with pytest.raises(ConfigurationError) as exc_info:
            load_terraform_outputs(path)
        assert "namespace" in str(exc_info.value)
        assert "account_id" in str(exc_info.value)
