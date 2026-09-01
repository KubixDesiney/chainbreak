"""Capability catalog loading and binding validation.

Enforces CAP-1 (an unresolvable capability is a compile error, never a silent
skip), CAP-2 (a binding may not exceed its capability's permitted action
families), and SI-9 (dangerous capabilities require a double opt-in).
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any, Final

import yaml

from chainbreak.core.enums import Provider, Sensitivity
from chainbreak.core.errors import (
    BindingValidationError,
    CapabilityResolutionError,
    DangerousCapabilityError,
)
from chainbreak.core.models import (
    AuthoritySet,
    Capability,
    CapabilityCatalog,
    ProviderCapabilityBinding,
)

DEFAULT_CATALOG_PATH: Final = Path(__file__).parent / "catalog.yaml"


def catalog_bytes() -> bytes:
    """Return the packaged catalog without assuming a repository checkout."""
    return resources.files(__package__).joinpath("catalog.yaml").read_bytes()


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that additionally rejects unknown tags outright (SI-11)."""


def _reject_unknown(loader: _StrictLoader, suffix: str, node: yaml.Node) -> Any:
    raise BindingValidationError(f"unsupported YAML tag in catalog: !{suffix}")


_StrictLoader.add_multi_constructor("!", _reject_unknown)
_StrictLoader.add_multi_constructor("tag:", _reject_unknown)


def load_catalog(path: Path | None = None) -> CapabilityCatalog:
    """Load and validate the capability catalog."""
    text = path.read_text(encoding="utf-8") if path is not None else catalog_bytes().decode("utf-8")
    # _StrictLoader is a hardened SafeLoader subclass; see class docstring above.
    raw = yaml.load(text, Loader=_StrictLoader)  # noqa: S506 # nosec B506
    if not isinstance(raw, dict):
        location = path if path is not None else "packaged capability catalog"
        raise BindingValidationError(f"catalog {location} is not a mapping")
    return CapabilityCatalog(
        version=raw["version"],
        capabilities=tuple(Capability(**entry) for entry in raw["capabilities"]),
    )


def assert_no_dangerous(
    catalog: CapabilityCatalog,
    *,
    config_allows: bool,
    cli_allows: bool,
) -> None:
    """SI-9: two independent switches, in two different places.

    Neither a stale config file nor a copy-pasted command line is sufficient
    alone.
    """
    dangerous = catalog.dangerous()
    if not dangerous:
        return
    if not (config_allows and cli_allows):
        raise DangerousCapabilityError(
            "catalog contains DANGEROUS capabilities; both "
            "config.allow_dangerous_capabilities and --allow-dangerous-capabilities "
            "are required",
            capabilities=[c.id for c in dangerous],
        )


def resolve_bindings(
    catalog: CapabilityCatalog,
    required: AuthoritySet,
    bindings: dict[str, ProviderCapabilityBinding],
    provider: Provider,
) -> dict[str, ProviderCapabilityBinding]:
    """Resolve every required capability to a provider binding.

    CAP-1: a missing binding raises. Silently skipping an unbindable capability
    would let a scenario appear to pass while never testing the thing it exists
    to test.
    """
    resolved: dict[str, ProviderCapabilityBinding] = {}
    missing: list[str] = []

    for capability_id in required.sorted:
        try:
            capability = catalog.get(capability_id)
        except KeyError:
            missing.append(capability_id)
            continue

        binding = bindings.get(capability_id)
        if binding is None:
            missing.append(capability_id)
            continue

        validate_binding(capability, binding, provider)
        resolved[capability_id] = binding

    if missing:
        raise CapabilityResolutionError(
            f"provider {provider} has no binding for: {', '.join(sorted(missing))}",
            provider=str(provider),
            missing=sorted(missing),
        )
    return resolved


def validate_binding(
    capability: Capability,
    binding: ProviderCapabilityBinding,
    provider: Provider,
) -> None:
    """CAP-2 / SI-3: a binding may narrow, never broaden."""
    if binding.capability_id != capability.id:
        raise BindingValidationError(
            f"binding for {binding.capability_id} attached to capability {capability.id}"
        )
    if binding.provider is not provider:
        raise BindingValidationError(
            f"binding for {capability.id} declares provider {binding.provider}, expected {provider}"
        )
    if binding.probe_kind is not capability.probe_kind:
        raise BindingValidationError(
            f"binding for {capability.id} declares probe_kind {binding.probe_kind}, "
            f"capability requires {capability.probe_kind}"
        )
    if capability.sensitivity is Sensitivity.DANGEROUS:
        raise BindingValidationError(
            f"{capability.id}: DANGEROUS capabilities require a separate catalog (SI-9)"
        )
    missing_preconditions = set(capability.requires_precondition) - set(binding.preconditions)
    if missing_preconditions:
        raise BindingValidationError(
            f"binding for {capability.id} omits required preconditions: "
            f"{sorted(missing_preconditions)}"
        )
