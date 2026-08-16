"""Strict AWS account and namespace checks used at the adapter boundary.

The provider-agnostic namespace helper intentionally keeps the fake provider's
substring semantics.  AWS requests need a stronger check: an ARN must be in
the commercial partition, carry the configured account when AWS exposes an
account component, and contain the exact namespace token (not a prefix or
suffix lookalike).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from chainbreak.core.errors import NamespaceViolationError

_NAMESPACE_TOKEN = re.compile(r"cb-[0-9a-f]{8}")
_ARN = re.compile(
    r"^arn:(?P<partition>[^:]+):(?P<service>[^:]+):(?P<region>[^:]*):"
    r"(?P<account>[^:]*):(?P<resource>.+)$"
)


def _has_exact_namespace(value: str, namespace: str) -> bool:
    escaped = re.escape(namespace)
    return re.search(rf"(?<![0-9A-Za-z]){escaped}(?![0-9A-Za-z])", value) is not None


def _assert_namespace_tokens(value: str, namespace: str) -> None:
    for match in _NAMESPACE_TOKEN.finditer(value):
        start, end = match.span()
        if (
            match.group() != namespace
            or (start > 0 and value[start - 1].isalnum())
            or (end < len(value) and value[end].isalnum())
        ):
            raise NamespaceViolationError(
                f"AWS reference contains a namespace lookalike: {value!r}",
                namespace=namespace,
                ref=value,
            )


def assert_aws_reference(ref: str, *, account_id: str, namespace: str) -> None:
    """Reject an AWS reference outside the exact account/namespace boundary."""
    if not _has_exact_namespace(ref, namespace):
        raise NamespaceViolationError(
            f"AWS reference is not in namespace {namespace!r}: {ref!r}",
            namespace=namespace,
            ref=ref,
        )
    _assert_namespace_tokens(ref, namespace)

    match = _ARN.match(ref)
    if match is None:
        return
    if match.group("partition") != "aws":
        raise NamespaceViolationError(
            f"AWS reference uses an unexpected partition: {ref!r}",
            namespace=namespace,
            ref=ref,
        )
    arn_account = match.group("account")
    # S3 bucket ARNs intentionally have no account component.  Every ARN
    # which does expose one must bind to the Terraform/live account exactly.
    if arn_account and arn_account != account_id:
        raise NamespaceViolationError(
            f"AWS reference targets account {arn_account!r}, expected {account_id!r}",
            account=account_id,
            ref=ref,
        )


def assert_outbound_parameters(
    params: Mapping[str, Any],
    *,
    account_id: str,
    namespace: str,
    exact_parameters: Mapping[str, str],
    allowed_parameters: Mapping[str, frozenset[str]] | None = None,
) -> None:
    """Inspect botocore's serialized resource parameters before transmission."""
    for key, expected in exact_parameters.items():
        if key not in params:
            continue
        actual = params[key]
        if not isinstance(actual, str) or actual != expected:
            raise NamespaceViolationError(
                f"outbound {key} is not the exact benchmark resource: {actual!r}",
                namespace=namespace,
                ref=str(actual),
            )
    for key, allowed in (allowed_parameters or {}).items():
        if key in params and params[key] not in allowed:
            raise NamespaceViolationError(
                f"outbound {key} is not a provisioned benchmark resource: {params[key]!r}",
                namespace=namespace,
                ref=str(params[key]),
            )

    def inspect(value: Any) -> None:
        if isinstance(value, str):
            _assert_namespace_tokens(value, namespace)
            for arn in re.findall(r"arn:[^\s\"']+", value):
                assert_aws_reference(arn.rstrip(",}]"), account_id=account_id, namespace=namespace)
        elif isinstance(value, Mapping):
            for nested in value.values():
                inspect(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                inspect(nested)

    inspect(params)

    # S3 object keys/prefixes are resource selectors rather than the nested
    # DynamoDB item key.  They must remain inside this namespace's prefix.
    for key in ("Key", "Prefix"):
        value = params.get(key)
        if isinstance(value, str) and not value.startswith(f"{namespace}/"):
            raise NamespaceViolationError(
                f"outbound {key} is outside the exact namespace prefix: {value!r}",
                namespace=namespace,
                ref=str(value),
            )


__all__ = ["assert_aws_reference", "assert_outbound_parameters"]
