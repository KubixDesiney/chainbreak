"""Provider construction is an offline, validated boundary."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from chainbreak.providers.aws.factory import create_aws_provider

pytestmark = pytest.mark.unit


def _outputs() -> dict[str, str]:
    namespace = "cb-a1b2c3d4"
    values = {
        "namespace": namespace,
        "account_id": "123456789012",
        "region": "us-east-1",
        "bootstrap_role_arn": f"arn:aws:iam::123456789012:role/{namespace}-bootstrap",
        "principal_role_arn": f"arn:aws:iam::123456789012:role/{namespace}-principal",
        "objectstore_bucket": f"{namespace}-objectstore",
        "objectstore_marker_key": f"{namespace}/markers/marker.json",
        "objectstore_marker_sha256": "sha256:" + "0" * 64,
        "keyvalue_table": f"{namespace}-keyvalue",
        "keyvalue_marker_pk": "cb-marker",
        "keyvalue_marker_sha256": "sha256:" + "0" * 64,
        "function_name": f"{namespace}-noop",
        "queue_url": f"https://sqs.us-east-1.amazonaws.com/123456789012/{namespace}-queue",
        "external_id": namespace,
        "infrastructure_fingerprint": "sha256:" + "1" * 64,
    }
    values.update(
        {
            f"agent_{letter}_role_arn": f"arn:aws:iam::123456789012:role/{namespace}-agent-{letter}"
            for letter in "abcdef"
        }
    )
    return values


def test_factory_loads_outputs_and_does_not_call_aws(tmp_path: Path) -> None:
    outputs_path = tmp_path / "outputs.json"
    outputs_path.write_text(json.dumps(_outputs()), encoding="utf-8")
    session = Mock()

    adapter = create_aws_provider(outputs_path, session=session, run_id="offline-test")

    assert adapter.outputs.namespace == "cb-a1b2c3d4"
    assert adapter.run_id == "offline-test"
    session.client.assert_not_called()


def test_factory_rejects_two_session_injections(tmp_path: Path) -> None:
    outputs_path = tmp_path / "outputs.json"
    outputs_path.write_text(json.dumps(_outputs()), encoding="utf-8")

    with pytest.raises(ValueError, match="only one"):
        create_aws_provider(
            outputs_path,
            operator_session=Mock(),
            session=Mock(),
        )
