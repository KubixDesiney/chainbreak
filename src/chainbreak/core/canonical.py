"""Canonical JSON serialization.

Byte-identical output for logically identical input, independent of dict
insertion order, hash randomization, or process. This is what makes evidence
diffable and policy fingerprints comparable across reads
(AUTHORIZATION_MODEL.md section 1.4), and what any hash-based deduplication
elsewhere in the codebase can rely on.

Rules: object keys sorted; ``AuthoritySet`` renders as its own canonical
sorted list rather than its internal field shape; every ``datetime`` must be
timezone-aware and renders as UTC ISO-8601 with exactly six fractional digits
and a ``Z`` suffix; ``frozenset``/``set`` render as a sorted list.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from chainbreak.core.models import AuthoritySet


def format_datetime(value: datetime) -> str:
    """UTC ISO-8601 with microseconds, e.g. ``2026-08-07T13:00:00.123456Z``."""
    if value.tzinfo is None:
        raise ValueError("canonical datetimes must be timezone-aware")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _default(obj: Any) -> Any:
    if isinstance(obj, AuthoritySet):
        return obj.model_dump_canonical()
    if isinstance(obj, datetime):
        return format_datetime(obj)
    if isinstance(obj, BaseModel):
        # A shallow, one-level extraction (not obj.model_dump()): model_dump
        # recurses eagerly and would flatten nested AuthoritySet/datetime
        # fields into plain dicts/strings before this function ever sees
        # them, bypassing the special-casing above. Extracting one level at a
        # time lets json.dumps re-invoke `default` at every nested level.
        return {name: getattr(obj, name) for name in type(obj).model_fields}
    if isinstance(obj, frozenset | set):
        return sorted(obj)
    if isinstance(obj, Mapping):
        return dict(obj)
    raise TypeError(f"object of type {type(obj).__name__} is not canonically serializable")


def dumps(obj: Any) -> str:
    """Canonical JSON: sorted keys, fixed float formatting, UTC ISO-8601 with microseconds."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_default,
    )
