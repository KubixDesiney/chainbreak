"""Offline regression tests for the fail-closed AWS cleanup contract."""

from __future__ import annotations

from typing import Any

import pytest


class _Paginator:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self._pages = pages

    def paginate(self, **kwargs: Any) -> list[dict[str, Any]]:
        return self._pages


class _IamClient:
    def get_paginator(self, operation: str) -> _Paginator:
        if operation == "list_roles":
            return _Paginator(
                [
                    {
                        "Roles": [
                            {
                                "RoleName": "cb-a1b2c3d4-agent-a",
                                "Arn": "arn:aws:iam::123456789012:role/cb-a1b2c3d4-agent-a",
                            }
                        ]
                    }
                ]
            )
        return _Paginator([{"Policies": []}])

    def list_role_tags(self, *, RoleName: str) -> dict[str, Any]:  # noqa: N803
        return {
            "Tags": [
                {"Key": "Project", "Value": "CHAINBREAK"},
                {"Key": "Namespace", "Value": "cb-a1b2c3d4"},
            ]
        }

    def list_policy_tags(self, *, PolicyArn: str) -> dict[str, Any]:  # noqa: N803
        return {"Tags": []}


def _noop(client: Any, namespace: str, resources: list[str], unsafe: list[str]) -> None:
    return None


def test_iam_role_leftover_prevents_clean_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import boto3

    from chainbreak.providers.aws import cleanup

    iam = _IamClient()
    monkeypatch.setattr(boto3, "client", lambda service, region_name=None: iam)
    monkeypatch.setattr(
        cleanup,
        "_SERVICE_ENUMERATORS",
        tuple(
            (name, cleanup._enumerate_iam if name == "iam" else _noop)
            for name in (
                "s3",
                "dynamodb",
                "lambda",
                "sqs",
                "sns",
                "logs",
                "cloudtrail",
                "budgets",
                "iam",
            )
        ),
    )

    leftovers = cleanup.list_tagged_resources(region="us-east-1", namespace="cb-a1b2c3d4")

    assert leftovers == ("arn:aws:iam::123456789012:role/cb-a1b2c3d4-agent-a",)


def test_failed_enumerator_is_unsafe(monkeypatch: pytest.MonkeyPatch) -> None:
    import boto3

    from chainbreak.core.errors import ConfigurationError
    from chainbreak.providers.aws import cleanup

    monkeypatch.setattr(boto3, "client", lambda service, region_name=None: object())

    def fail(client: Any, namespace: str, resources: list[str], unsafe: list[str]) -> None:
        raise RuntimeError("offline enumerator failure")

    monkeypatch.setattr(cleanup, "_SERVICE_ENUMERATORS", (("iam", fail),))

    with pytest.raises(ConfigurationError, match="cleanup is unsafe"):
        cleanup.list_tagged_resources(region="us-east-1", namespace="cb-a1b2c3d4")


def test_unknown_enumerator_is_unsafe(monkeypatch: pytest.MonkeyPatch) -> None:
    import boto3

    from chainbreak.core.errors import ConfigurationError
    from chainbreak.providers.aws import cleanup

    monkeypatch.setattr(boto3, "client", lambda service, region_name=None: object())
    monkeypatch.setattr(cleanup, "_SERVICE_ENUMERATORS", (("not-provisioned", _noop),))

    with pytest.raises(ConfigurationError, match="unknown"):
        cleanup.list_tagged_resources(region="us-east-1", namespace="cb-a1b2c3d4")


def test_cloudwatch_and_cloudtrail_tag_shapes_are_supported() -> None:
    from chainbreak.providers.aws.cleanup import _get_tags

    class Client:
        def list_tags_for_resource(self, **_: Any) -> dict[str, Any]:
            return {"tags": {"Project": "CHAINBREAK", "Namespace": "cb-a1b2c3d4"}}

        def list_tags(self, **_: Any) -> dict[str, Any]:
            return {
                "ResourceTagList": [
                    {"Key": "Project", "Value": "CHAINBREAK"},
                    {"Key": "Namespace", "Value": "cb-a1b2c3d4"},
                ]
            }

    client = Client()
    assert _get_tags(client, "list_tags_for_resource", {}) == {
        "Project": "CHAINBREAK",
        "Namespace": "cb-a1b2c3d4",
    }
    assert _get_tags(client, "list_tags", {}) == {
        "Project": "CHAINBREAK",
        "Namespace": "cb-a1b2c3d4",
    }
