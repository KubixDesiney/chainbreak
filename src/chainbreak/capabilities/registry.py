"""Per-provider binding registry.

Where a provider package (``providers/aws/bindings.py``, M8) registers its
``ProviderCapabilityBinding``s so ``resolve_bindings`` (loader.py) has a real
``dict[str, ProviderCapabilityBinding]`` to resolve against, instead of the
empty dict every caller has had to pass until now.
"""

from __future__ import annotations

from collections.abc import Iterable

from chainbreak.core.enums import Provider
from chainbreak.core.errors import BindingValidationError, CapabilityResolutionError
from chainbreak.core.models import ProviderCapabilityBinding


class BindingRegistry:
    """Bindings keyed by ``(provider, capability_id)``.

    F1: duplicate registration for the same key is rejected outright. A
    second registration is far more likely to be a bug -- an accidental
    double-import, a copy-pasted binding -- than an intentional override, and
    a silent overwrite would make CAP-1/CAP-2 violations depend on import
    order.
    """

    def __init__(self) -> None:
        self._bindings: dict[tuple[Provider, str], ProviderCapabilityBinding] = {}

    def register(self, binding: ProviderCapabilityBinding) -> None:
        key = (binding.provider, binding.capability_id)
        if key in self._bindings:
            raise BindingValidationError(
                f"duplicate binding registration: {binding.provider}/{binding.capability_id}",
                provider=str(binding.provider),
                capability_id=binding.capability_id,
            )
        self._bindings[key] = binding

    def register_all(self, bindings: Iterable[ProviderCapabilityBinding]) -> None:
        for binding in bindings:
            self.register(binding)

    def get(self, provider: Provider, capability_id: str) -> ProviderCapabilityBinding:
        try:
            return self._bindings[(provider, capability_id)]
        except KeyError:
            raise CapabilityResolutionError(
                f"no binding registered for {provider}/{capability_id}",
                provider=str(provider),
                capability_id=capability_id,
            ) from None

    def for_provider(self, provider: Provider) -> dict[str, ProviderCapabilityBinding]:
        """The ``dict[str, ProviderCapabilityBinding]`` shape ``resolve_bindings`` expects."""
        return {
            capability_id: binding
            for (registered_provider, capability_id), binding in self._bindings.items()
            if registered_provider is provider
        }

    def __len__(self) -> int:
        return len(self._bindings)

    def __contains__(self, key: tuple[Provider, str]) -> bool:
        return key in self._bindings
