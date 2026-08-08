"""``chainbreak infra verify-clean`` (M9, F5): enumerate every AWS resource
still tagged ``Project=CHAINBREAK`` via the Resource Groups Tagging API.

A thin, deliberately narrow module: not part of the ``ProviderAdapter``
Protocol (this is infrastructure cleanup verification, not probing), but
still confined to ``providers/aws/`` per ARCH-1's "boto3 is confined to
providers.aws" contract -- ``cli/infra.py`` calls this rather than importing
boto3 itself. Every raw ``botocore`` exception this module's own calls can
raise is translated to a ``chainbreak.core.errors`` type before it leaves
this module, so no caller (including the CLI, which
ARCHITECTURE.md's ``cli -> everything`` rule lets dispatch here) ever needs
its own ``import botocore`` just to catch one.
"""

from __future__ import annotations

from typing import Any

from chainbreak.core.errors import ConfigurationError


def list_tagged_resources(*, region: str | None = None) -> tuple[str, ...]:
    """Every resource ARN currently tagged ``Project=CHAINBREAK``, across
    every resource type the Resource Groups Tagging API covers.

    Raises :class:`ConfigurationError` if no region can be resolved --
    never the raw ``botocore.exceptions.NoRegionError``.
    """
    import boto3
    from botocore.exceptions import NoRegionError

    kwargs: dict[str, Any] = {"region_name": region} if region else {}
    try:
        client = boto3.client("resourcegroupstaggingapi", **kwargs)
    except NoRegionError as exc:
        raise ConfigurationError(
            "no AWS region available to call the Resource Groups Tagging API with"
        ) from exc

    resources: list[str] = []
    paginator = client.get_paginator("get_resources")
    for page in paginator.paginate(TagFilters=[{"Key": "Project", "Values": ["CHAINBREAK"]}]):
        resources.extend(r["ResourceARN"] for r in page.get("ResourceTagMappingList", []))
    return tuple(resources)
