"""Strict AWS account/namespace enforcement is independent of the fake provider."""

from __future__ import annotations

import pytest

from chainbreak.core.errors import NamespaceViolationError
from chainbreak.providers.aws.namespace import assert_aws_reference, assert_outbound_parameters

pytestmark = pytest.mark.unit

_ACCOUNT = "123456789012"
_NAMESPACE = "cb-a1b2c3d4"


def test_exact_account_and_namespace_pass() -> None:
    assert_aws_reference(
        f"arn:aws:iam::{_ACCOUNT}:role/{_NAMESPACE}-agent-a",
        account_id=_ACCOUNT,
        namespace=_NAMESPACE,
    )


@pytest.mark.parametrize(
    "reference",
    [
        "arn:aws:iam::999999999999:role/cb-a1b2c3d4-agent-a",
        "arn:aws:iam::123456789012:role/cb-a1b2c3d4x-agent-a",
        "arn:aws:iam::123456789012:role/xcb-a1b2c3d4-agent-a",
    ],
)
def test_account_and_namespace_lookalikes_are_rejected(reference: str) -> None:
    with pytest.raises(NamespaceViolationError):
        assert_aws_reference(reference, account_id=_ACCOUNT, namespace=_NAMESPACE)


def test_outbound_resource_parameter_is_exact() -> None:
    with pytest.raises(NamespaceViolationError):
        assert_outbound_parameters(
            {"Bucket": "cb-a1b2c3d4-objectstore-evil", "Key": "cb-a1b2c3d4/markers/marker.json"},
            account_id=_ACCOUNT,
            namespace=_NAMESPACE,
            exact_parameters={"Bucket": "cb-a1b2c3d4-objectstore"},
        )
