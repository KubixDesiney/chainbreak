"""F7: a fake binding for every catalog capability, one action each.

Mirrors the pattern ``tests/conftest.py::synthetic_aws_registry`` already
uses for a synthetic AWS binding set, but this one is real: it is what
``FakeProviderAdapter.resolve_capability`` actually returns, not a test-only
stand-in.
"""

from __future__ import annotations

from chainbreak.core.enums import Provider
from chainbreak.core.models import CapabilityCatalog, ProviderCapabilityBinding


def build_fake_bindings(catalog: CapabilityCatalog) -> tuple[ProviderCapabilityBinding, ...]:
    return tuple(
        ProviderCapabilityBinding(
            capability_id=capability.id,
            provider=Provider.FAKE,
            actions=(f"fake:{capability.id}",),
            resource_template="fake://{namespace}/" + capability.id,
            probe_kind=capability.probe_kind,
            preconditions=capability.requires_precondition,
        )
        for capability in catalog.capabilities
    )
