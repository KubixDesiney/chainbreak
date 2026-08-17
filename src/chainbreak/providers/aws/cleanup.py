"""Fail-closed verification of the Terraform AWS cleanup contract.

Resource Groups Tagging API does not cover every service used by the sandbox,
notably IAM.  Verification therefore enumerates each provisioned service with
that service's own read-only list and tag APIs.  Any failed or unknown
enumerator makes the result unsafe; no caller may interpret partial results as
clean.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from chainbreak.core.errors import ConfigurationError

_PROJECT = "CHAINBREAK"


def _tags(values: object) -> dict[str, str]:
    if isinstance(values, Mapping):
        return {str(key): str(value) for key, value in values.items()}
    if not isinstance(values, list):
        return {}
    result: dict[str, str] = {}
    for entry in values:
        if isinstance(entry, Mapping) and "Key" in entry and "Value" in entry:
            result[str(entry["Key"])] = str(entry["Value"])
    return result


def _classify(
    service: str,
    identifier: str,
    tags: Mapping[str, str],
    namespace: str,
    resources: list[str],
    unsafe: list[str],
) -> None:
    project = tags.get("Project")
    tagged_namespace = tags.get("Namespace")
    looks_relevant = project == _PROJECT or namespace in identifier or tagged_namespace == namespace
    if not looks_relevant:
        return
    if project != _PROJECT or tagged_namespace != namespace:
        unsafe.append(
            f"{service}: {identifier} is relevant but lacks exact tags "
            f"Project={_PROJECT}, Namespace={namespace}"
        )
        return
    resources.append(identifier)


def _get_tags(client: Any, operation: str, parameters: Mapping[str, Any]) -> dict[str, str]:
    try:
        response = getattr(client, operation)(**parameters)
    except Exception as exc:
        error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if error_code == "NoSuchTagSet":
            return {}
        raise
    for key in (
        "TagSet",
        "Tags",
        "ResourceTags",
        "tags",
        "ResourceTagList",
        "ResourceTagMappingList",
    ):
        if key in response:
            values = response[key]
            if key == "ResourceTagMappingList" and values:
                values = [
                    tag
                    for mapping in values
                    if isinstance(mapping, Mapping)
                    for tag in mapping.get("Tags", [])
                ]
            return _tags(values)
    return {}


def _enumerate_s3(client: Any, namespace: str, resources: list[str], unsafe: list[str]) -> None:
    for bucket in client.list_buckets().get("Buckets", []):
        name = str(bucket["Name"])
        _classify(
            "s3",
            f"arn:aws:s3:::{name}",
            _get_tags(client, "get_bucket_tagging", {"Bucket": name}),
            namespace,
            resources,
            unsafe,
        )


def _enumerate_dynamodb(
    client: Any, namespace: str, resources: list[str], unsafe: list[str]
) -> None:
    for page in client.get_paginator("list_tables").paginate():
        for name in page.get("TableNames", []):
            table = client.describe_table(TableName=name)["Table"]
            arn = str(table["TableArn"])
            tags = _get_tags(client, "list_tags_of_resource", {"ResourceArn": arn})
            _classify("dynamodb", arn, tags, namespace, resources, unsafe)


def _enumerate_lambda(client: Any, namespace: str, resources: list[str], unsafe: list[str]) -> None:
    for page in client.get_paginator("list_functions").paginate():
        for function in page.get("Functions", []):
            arn = str(function["FunctionArn"])
            _classify(
                "lambda",
                arn,
                _get_tags(client, "list_tags", {"Resource": arn}),
                namespace,
                resources,
                unsafe,
            )


def _enumerate_sqs(client: Any, namespace: str, resources: list[str], unsafe: list[str]) -> None:
    for url in client.list_queues().get("QueueUrls", []):
        attributes = client.get_queue_attributes(QueueUrl=url, AttributeNames=["QueueArn"])
        arn = str(attributes["Attributes"]["QueueArn"])
        tags = _get_tags(client, "list_queue_tags", {"QueueUrl": url})
        _classify("sqs", arn, tags, namespace, resources, unsafe)


def _enumerate_sns(client: Any, namespace: str, resources: list[str], unsafe: list[str]) -> None:
    for topic in client.list_topics().get("Topics", []):
        arn = str(topic["TopicArn"])
        _classify(
            "sns",
            arn,
            _get_tags(client, "list_tags_for_resource", {"ResourceArn": arn}),
            namespace,
            resources,
            unsafe,
        )


def _enumerate_logs(client: Any, namespace: str, resources: list[str], unsafe: list[str]) -> None:
    for page in client.get_paginator("describe_log_groups").paginate():
        for group in page.get("logGroups", []):
            arn = group.get("logGroupArn")
            if not arn:
                unsafe.append("logs: describe_log_groups returned a log group without logGroupArn")
                continue
            tags = _get_tags(client, "list_tags_for_resource", {"resourceArn": arn})
            _classify("logs", str(arn), tags, namespace, resources, unsafe)


def _enumerate_cloudtrail(
    client: Any, namespace: str, resources: list[str], unsafe: list[str]
) -> None:
    for trail in client.list_trails().get("Trails", []):
        arn = str(trail["TrailARN"])
        tags = _get_tags(client, "list_tags", {"ResourceId": arn})
        _classify("cloudtrail", arn, tags, namespace, resources, unsafe)


def _enumerate_budgets(
    client: Any, namespace: str, resources: list[str], unsafe: list[str]
) -> None:
    paginator = client.get_paginator("describe_budgets")
    account_id = _account_id(client)
    for page in paginator.paginate(AccountId=account_id):
        for budget in page.get("Budgets", []):
            name = budget.get("BudgetName")
            arn = budget.get("BudgetArn") or (
                f"arn:aws:budgets::{account_id}:budget/{name}" if name else None
            )
            if not arn:
                unsafe.append("budgets: describe_budgets returned a budget without an identifier")
                continue
            tags = _get_tags(client, "list_tags_for_resource", {"ResourceARN": arn})
            _classify("budgets", str(arn), tags, namespace, resources, unsafe)


def _account_id(client: Any) -> str:
    # Budgets is account-scoped and does not accept an omitted AccountId.  The
    # caller identity read is still read-only and is confined to this module.
    import boto3

    return str(
        boto3.client("sts", region_name=client.meta.region_name).get_caller_identity()["Account"]
    )


def _enumerate_iam(client: Any, namespace: str, resources: list[str], unsafe: list[str]) -> None:
    for page in client.get_paginator("list_roles").paginate():
        for role in page.get("Roles", []):
            arn = str(role["Arn"])
            tags = _get_tags(client, "list_role_tags", {"RoleName": role["RoleName"]})
            _classify("iam-role", arn, tags, namespace, resources, unsafe)
    for page in client.get_paginator("list_policies").paginate(Scope="Local"):
        for policy in page.get("Policies", []):
            arn = str(policy["Arn"])
            tags = _get_tags(client, "list_policy_tags", {"PolicyArn": arn})
            _classify("iam-policy", arn, tags, namespace, resources, unsafe)


_SERVICE_ENUMERATORS: tuple[tuple[str, Callable[..., None]], ...] = (
    ("s3", _enumerate_s3),
    ("dynamodb", _enumerate_dynamodb),
    ("lambda", _enumerate_lambda),
    ("sqs", _enumerate_sqs),
    ("sns", _enumerate_sns),
    ("logs", _enumerate_logs),
    ("cloudtrail", _enumerate_cloudtrail),
    ("budgets", _enumerate_budgets),
    ("iam", _enumerate_iam),
)
_EXPECTED_SERVICE_NAMES = frozenset(name for name, _ in _SERVICE_ENUMERATORS)


def list_tagged_resources(*, region: str | None = None, namespace: str) -> tuple[str, ...]:
    """Return exact-namespace leftovers only after every service is verified.

    ``ConfigurationError`` means the result is unsafe, including an
    enumerator failure or a resource with a missing/mismatched required tag.
    """
    import boto3
    from botocore.exceptions import NoRegionError

    if not namespace:
        raise ConfigurationError("cleanup is unsafe: exact Terraform namespace is required")
    if not re.fullmatch(r"cb-[0-9a-f]{8}", namespace):
        raise ConfigurationError("cleanup is unsafe: namespace is not an exact Terraform namespace")
    try:
        clients = {
            "s3": boto3.client("s3", region_name=region),
            "dynamodb": boto3.client("dynamodb", region_name=region),
            "lambda": boto3.client("lambda", region_name=region),
            "sqs": boto3.client("sqs", region_name=region),
            "sns": boto3.client("sns", region_name=region),
            "logs": boto3.client("logs", region_name=region),
            "cloudtrail": boto3.client("cloudtrail", region_name=region),
            "budgets": boto3.client("budgets", region_name=region),
            "iam": boto3.client("iam", region_name=region),
        }
    except NoRegionError as exc:
        raise ConfigurationError("cleanup is unsafe: no AWS region available") from exc

    resources: list[str] = []
    unsafe: list[str] = []
    enumerated_services = [service for service, _ in _SERVICE_ENUMERATORS]
    if (
        len(enumerated_services) != len(set(enumerated_services))
        or set(enumerated_services) != _EXPECTED_SERVICE_NAMES
    ):
        unsafe.append(
            "cleanup: unknown or incomplete service enumerator registry; refusing to report clean"
        )
    for service, enumerator in _SERVICE_ENUMERATORS:
        try:
            client = clients[service]
            enumerator(client, namespace, resources, unsafe)
        except Exception as exc:
            unsafe.append(
                f"{service}: unknown, failed, or unsupported enumerator: "
                f"{type(exc).__name__}: {exc}"
            )

    if unsafe:
        raise ConfigurationError(
            "cleanup is unsafe; no clean result is available: " + "; ".join(sorted(unsafe)),
            unsafe=sorted(unsafe),
        )
    return tuple(sorted(set(resources)))
