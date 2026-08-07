"""capabilities/loader.py: assert_no_dangerous (SI-9) and the restricted YAML
loader (S3: the catalog loader rejects unknown YAML tags).
"""

from __future__ import annotations

import pytest
import yaml

from chainbreak.capabilities.loader import assert_no_dangerous, load_catalog
from chainbreak.core.enums import ProbeKind, Sensitivity
from chainbreak.core.errors import BindingValidationError, DangerousCapabilityError
from chainbreak.core.models import Capability, CapabilityCatalog

pytestmark = pytest.mark.unit


def _dangerous_capability() -> Capability:
    return Capability(
        id="test.dangerous",
        title="A capability that should never ship",
        description="Exists only to prove the double-switch gate works.",
        probe_kind=ProbeKind.READ_MARKER,
        sensitivity=Sensitivity.DANGEROUS,
    )


class TestDangerousCapabilityDoubleSwitch:
    """SI-9: two independent switches, in two different places."""

    def test_shipped_catalog_has_nothing_to_gate(self):
        catalog = load_catalog()
        assert_no_dangerous(catalog, config_allows=False, cli_allows=False)

    def test_dangerous_capability_blocked_with_neither_switch(self):
        catalog = CapabilityCatalog(version="1.0.0", capabilities=(_dangerous_capability(),))
        with pytest.raises(DangerousCapabilityError, match="DANGEROUS"):
            assert_no_dangerous(catalog, config_allows=False, cli_allows=False)

    def test_dangerous_capability_blocked_with_only_config_switch(self):
        catalog = CapabilityCatalog(version="1.0.0", capabilities=(_dangerous_capability(),))
        with pytest.raises(DangerousCapabilityError):
            assert_no_dangerous(catalog, config_allows=True, cli_allows=False)

    def test_dangerous_capability_blocked_with_only_cli_switch(self):
        catalog = CapabilityCatalog(version="1.0.0", capabilities=(_dangerous_capability(),))
        with pytest.raises(DangerousCapabilityError):
            assert_no_dangerous(catalog, config_allows=False, cli_allows=True)

    def test_dangerous_capability_allowed_with_both_switches(self):
        catalog = CapabilityCatalog(version="1.0.0", capabilities=(_dangerous_capability(),))
        assert_no_dangerous(catalog, config_allows=True, cli_allows=True)

    def test_error_names_the_dangerous_capabilities(self):
        catalog = CapabilityCatalog(version="1.0.0", capabilities=(_dangerous_capability(),))
        with pytest.raises(DangerousCapabilityError) as excinfo:
            assert_no_dangerous(catalog, config_allows=False, cli_allows=False)
        assert excinfo.value.context["capabilities"] == ["test.dangerous"]


class TestRestrictedYamlLoader:
    def test_catalog_loader_rejects_unknown_tag(self, tmp_path):
        bad_catalog = tmp_path / "catalog.yaml"
        bad_catalog.write_text(
            "version: '1.0.0'\ncapabilities: !!python/object:builtins.list []\n",
            encoding="utf-8",
        )
        with pytest.raises(BindingValidationError, match="unsupported YAML tag"):
            load_catalog(bad_catalog)

    def test_catalog_loader_rejects_non_mapping_document(self, tmp_path):
        bad_catalog = tmp_path / "catalog.yaml"
        bad_catalog.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(BindingValidationError, match="not a mapping"):
            load_catalog(bad_catalog)

    def test_strict_loader_rejects_a_local_tag_directly(self):
        """Confirms the loader used by load_catalog, not just load_catalog's
        own document-shape check, is what's doing the rejecting."""
        from chainbreak.capabilities.loader import _StrictLoader

        with pytest.raises(BindingValidationError, match="unsupported YAML tag"):
            yaml.load("!custom_tag value", Loader=_StrictLoader)  # nosec B506
