"""Layered configuration resolution (ARCHITECTURE.md section 3.2).

    defaults -> chainbreak.toml (repo) -> ~/.config/chainbreak/config.toml
             -> CHAINBREAK_* environment variables -> CLI flags

Later layers override earlier ones field by field: a layer that does not
mention a field leaves whatever the previous layer resolved untouched. Each
``_load_*_layer`` helper therefore returns only the fields that layer
actually set, never filled in with its own defaults -- only the final
``Settings(**merged)`` construction applies defaults, and only for fields no
layer touched at all.

``Settings`` carries everything except a concrete ``namespace``: SI-2's
namespace is per-run (derived from a fresh run id), so it cannot be known at
config-resolution time. ``resolve_safety_envelope`` is what turns a
``Settings`` plus a caller-supplied namespace into the ``SafetyEnvelope`` a
run is refused without (F2, SI-5).
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pydantic
from pydantic import BaseModel, ConfigDict

from chainbreak.core.errors import SafetyEnvelopeError
from chainbreak.core.models import SafetyEnvelope

_ENV_PREFIX = "CHAINBREAK_"

_TUPLE_FIELDS = frozenset({"allowed_account_ids", "allowed_regions"})
_INT_FIELDS = frozenset({"max_run_duration_seconds", "max_delegation_depth"})
_FLOAT_FIELDS = frozenset({"max_estimated_cost_usd"})
_BOOL_FIELDS = frozenset(
    {"allow_dangerous_capabilities", "allow_concurrent_runs", "require_confirmation_for_apply"}
)

_ENV_VAR_TO_FIELD = {
    "ALLOWED_ACCOUNT_IDS": "allowed_account_ids",
    "ALLOWED_REGIONS": "allowed_regions",
    "NAMESPACE_PREFIX": "namespace_prefix",
    "MAX_RUN_DURATION_SECONDS": "max_run_duration_seconds",
    "MAX_ESTIMATED_COST_USD": "max_estimated_cost_usd",
    "MAX_DELEGATION_DEPTH": "max_delegation_depth",
    "ALLOW_DANGEROUS_CAPABILITIES": "allow_dangerous_capabilities",
    "ALLOW_CONCURRENT_RUNS": "allow_concurrent_runs",
    "REQUIRE_CONFIRMATION_FOR_APPLY": "require_confirmation_for_apply",
    "DEFAULT_PROVIDER": "default_provider",
}


class Settings(BaseModel):
    """Resolved configuration, mirroring ``chainbreak.example.toml``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed_account_ids: tuple[str, ...] = ()
    allowed_regions: tuple[str, ...] = ()
    namespace_prefix: str = "cb"
    max_run_duration_seconds: int = 1800
    max_estimated_cost_usd: float = 1.0
    max_delegation_depth: int = 6
    allow_dangerous_capabilities: bool = False
    allow_concurrent_runs: bool = False
    require_confirmation_for_apply: bool = True
    default_provider: str = "fake"


def _load_toml_layer(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    layer: dict[str, Any] = dict(data.get("safety", {}))
    provider_default = data.get("provider", {}).get("default")
    if provider_default is not None:
        layer["default_provider"] = provider_default
    return layer


def _coerce_env_value(field: str, raw: str) -> Any:
    if field in _TUPLE_FIELDS:
        return tuple(item.strip() for item in raw.split(",") if item.strip())
    if field in _INT_FIELDS:
        return int(raw)
    if field in _FLOAT_FIELDS:
        return float(raw)
    if field in _BOOL_FIELDS:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return raw


def _load_env_layer(env: Mapping[str, str]) -> dict[str, Any]:
    layer: dict[str, Any] = {}
    for env_suffix, field in _ENV_VAR_TO_FIELD.items():
        key = _ENV_PREFIX + env_suffix
        if key in env:
            layer[field] = _coerce_env_value(field, env[key])
    return layer


def resolve_settings(
    *,
    repo_config_path: Path | None = None,
    user_config_path: Path | None = None,
    env: Mapping[str, str] | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
) -> Settings:
    """Resolve all four layers, later winning, into a single ``Settings``."""
    merged: dict[str, Any] = {}
    if repo_config_path is not None:
        merged.update(_load_toml_layer(repo_config_path))
    if user_config_path is not None:
        merged.update(_load_toml_layer(user_config_path))
    merged.update(_load_env_layer(os.environ if env is None else env))
    if cli_overrides is not None:
        merged.update({key: value for key, value in cli_overrides.items() if value is not None})
    return Settings(**merged)


def resolve_safety_envelope(settings: Settings, *, namespace: str) -> SafetyEnvelope:
    """F2: a run without a resolved envelope is refused. Wraps the
    underlying Pydantic validation error (wildcard account, empty allowlist,
    duration over the hard ceiling, ...) as the domain-specific
    ``SafetyEnvelopeError`` callers are expected to catch."""
    try:
        return SafetyEnvelope(
            allowed_account_ids=settings.allowed_account_ids,
            allowed_regions=settings.allowed_regions,
            namespace=namespace,
            namespace_pattern=f"^{settings.namespace_prefix}-[0-9a-f]{{8}}$",
            max_run_duration_seconds=settings.max_run_duration_seconds,
            max_estimated_cost_usd=settings.max_estimated_cost_usd,
            max_delegation_depth=settings.max_delegation_depth,
            allow_dangerous_capabilities=settings.allow_dangerous_capabilities,
            allow_concurrent_runs=settings.allow_concurrent_runs,
        )
    except pydantic.ValidationError as exc:
        raise SafetyEnvelopeError(f"safety envelope did not resolve: {exc}") from exc
