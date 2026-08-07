"""The shipped capability catalog and the binding registry (M2).

Acceptance criteria 1 and 4: all ten capabilities load, validate and resolve
against a test binding set; the shipped catalog contains zero DANGEROUS
entries.
"""

from __future__ import annotations

import re

import pytest

from chainbreak.capabilities.loader import DEFAULT_CATALOG_PATH, load_catalog, resolve_bindings
from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.enums import Provider, Sensitivity
from chainbreak.core.errors import CapabilityResolutionError
from chainbreak.core.ids import CAPABILITY_ID_PATTERN
from chainbreak.core.models import ProviderCapabilityBinding

pytestmark = pytest.mark.unit


class TestCatalogContents:
    def test_catalog_loads(self):
        catalog = load_catalog()
        assert catalog.version == "1.0.0"
        assert len(catalog.capabilities) == 10

    def test_every_capability_id_matches_the_pattern(self):
        catalog = load_catalog()
        for capability in catalog.capabilities:
            assert re.match(CAPABILITY_ID_PATTERN, capability.id), capability.id

    def test_every_capability_has_a_probe_kind(self):
        catalog = load_catalog()
        for capability in catalog.capabilities:
            assert capability.probe_kind is not None

    def test_ids_are_unique(self):
        catalog = load_catalog()
        ids = [c.id for c in catalog.capabilities]
        assert len(ids) == len(set(ids))

    def test_no_dangerous_entries_in_the_shipped_catalog(self):
        """Acceptance criterion 4."""
        catalog = load_catalog()
        assert catalog.dangerous() == ()
        assert all(c.sensitivity is not Sensitivity.DANGEROUS for c in catalog.capabilities)

    def test_default_catalog_path_is_the_shipped_file(self):
        assert DEFAULT_CATALOG_PATH.name == "catalog.yaml"
        assert DEFAULT_CATALOG_PATH.exists()


def _binding_for(capability_id: str, catalog) -> ProviderCapabilityBinding:
    capability = catalog.get(capability_id)
    return ProviderCapabilityBinding(
        capability_id=capability_id,
        provider=Provider.FAKE,
        actions=(f"fake:{capability_id}",),
        resource_template="fake://{namespace}/" + capability_id,
        probe_kind=capability.probe_kind,
        preconditions=capability.requires_precondition,
    )


class TestCatalogResolvesAgainstATestBindingSet:
    """Acceptance criterion 1: all ten capabilities load, validate and resolve."""

    def test_every_capability_resolves(self):
        catalog = load_catalog()
        bindings = {c.id: _binding_for(c.id, catalog) for c in catalog.capabilities}
        resolved = resolve_bindings(catalog, catalog.ids(), bindings, Provider.FAKE)
        assert set(resolved) == {c.id for c in catalog.capabilities}

    def test_missing_binding_names_every_unresolved_capability(self):
        catalog = load_catalog()
        with pytest.raises(CapabilityResolutionError, match=re.escape("objectstore.read")):
            resolve_bindings(catalog, catalog.ids(), {}, Provider.FAKE)


class TestBindingRegistry:
    def test_register_and_get(self):
        catalog = load_catalog()
        registry = BindingRegistry()
        binding = _binding_for("objectstore.read", catalog)
        registry.register(binding)
        assert registry.get(Provider.FAKE, "objectstore.read") is binding
        assert len(registry) == 1
        assert (Provider.FAKE, "objectstore.read") in registry

    def test_register_all(self):
        catalog = load_catalog()
        registry = BindingRegistry()
        bindings = [_binding_for(c.id, catalog) for c in catalog.capabilities]
        registry.register_all(bindings)
        assert len(registry) == 10

    def test_duplicate_registration_rejected(self):
        catalog = load_catalog()
        registry = BindingRegistry()
        binding = _binding_for("objectstore.read", catalog)
        registry.register(binding)
        with pytest.raises(Exception, match="duplicate"):
            registry.register(binding)

    def test_get_missing_raises_capability_resolution_error(self):
        registry = BindingRegistry()
        with pytest.raises(CapabilityResolutionError, match=re.escape("objectstore.read")):
            registry.get(Provider.FAKE, "objectstore.read")

    def test_for_provider_filters_by_provider(self):
        catalog = load_catalog()
        registry = BindingRegistry()
        fake_binding = _binding_for("objectstore.read", catalog)
        registry.register(fake_binding)
        aws_binding = ProviderCapabilityBinding(
            capability_id="objectstore.write",
            provider=Provider.AWS,
            actions=("s3:PutObject",),
            resource_template="arn:aws:s3:::{bucket}/{namespace}/scratch/{run_id}/*",
            probe_kind=catalog.get("objectstore.write").probe_kind,
        )
        registry.register(aws_binding)

        fake_only = registry.for_provider(Provider.FAKE)
        assert set(fake_only) == {"objectstore.read"}
        aws_only = registry.for_provider(Provider.AWS)
        assert set(aws_only) == {"objectstore.write"}

    def test_for_provider_empty_when_nothing_registered(self):
        registry = BindingRegistry()
        assert registry.for_provider(Provider.AWS) == {}
