"""capabilities/loader.py: validate_binding (CAP-2), against tests/fixtures/bad_bindings.py.

Each fixture must be rejected with a message naming the specific problem.
"""

from __future__ import annotations

import re

import pytest

from chainbreak.capabilities.loader import load_catalog, resolve_bindings, validate_binding
from chainbreak.core.enums import ProbeKind, Provider, Sensitivity
from chainbreak.core.errors import BindingValidationError, CapabilityResolutionError
from chainbreak.core.models import AuthoritySet, Capability, ProviderCapabilityBinding
from tests.fixtures.bad_bindings import (
    missing_precondition_binding,
    narrow_binding_for_broadening_test,
    wrong_probe_kind_binding,
    wrong_provider_binding,
)

pytestmark = pytest.mark.unit


class TestBadBindingsAreRejected:
    def test_wrong_provider_binding_rejected(self):
        catalog = load_catalog()
        capability = catalog.get("objectstore.read")
        with pytest.raises(BindingValidationError, match="provider"):
            validate_binding(capability, wrong_provider_binding(), Provider.AWS)

    def test_wrong_probe_kind_binding_rejected(self):
        catalog = load_catalog()
        capability = catalog.get("objectstore.read")
        with pytest.raises(BindingValidationError, match="probe_kind"):
            validate_binding(capability, wrong_probe_kind_binding(), Provider.AWS)

    def test_missing_precondition_binding_rejected(self):
        catalog = load_catalog()
        capability = catalog.get("objectstore.read")
        with pytest.raises(BindingValidationError, match="preconditions"):
            validate_binding(capability, missing_precondition_binding(), Provider.AWS)


class TestGoodBindingIsAccepted:
    def test_narrow_binding_passes_validation(self):
        """The binding used for the over-broad/extra-action negative control is
        otherwise fully valid -- validate_binding must not reject it. The
        broadening itself is a runtime concern (OperationAllowlist), not a
        compile-time one."""
        catalog = load_catalog()
        capability = catalog.get("objectstore.read")
        validate_binding(capability, narrow_binding_for_broadening_test(), Provider.AWS)


class TestWrongCapabilityIdBinding:
    def test_binding_attached_to_the_wrong_capability_rejected(self):
        catalog = load_catalog()
        read_capability = catalog.get("objectstore.read")
        write_capability = catalog.get("objectstore.write")

        mismatched = ProviderCapabilityBinding(
            capability_id="objectstore.write",
            provider=Provider.AWS,
            actions=("s3:PutObject",),
            resource_template="arn:aws:s3:::{bucket}/{namespace}/scratch/{run_id}/*",
            probe_kind=write_capability.probe_kind,
        )
        with pytest.raises(BindingValidationError, match="attached to capability"):
            validate_binding(read_capability, mismatched, Provider.AWS)


class TestDangerousCapabilityBindingRejected:
    def test_dangerous_capability_binding_rejected_regardless_of_switches(self):
        """SI-9: DANGEROUS capabilities cannot be validated through the normal
        binding path at all, independent of the config/CLI double-switch that
        gates the catalog as a whole (test_catalog_safety.py)."""
        dangerous = Capability(
            id="test.dangerous",
            title="dangerous",
            description="fixture",
            probe_kind=ProbeKind.READ_MARKER,
            sensitivity=Sensitivity.DANGEROUS,
        )
        binding = ProviderCapabilityBinding(
            capability_id="test.dangerous",
            provider=Provider.AWS,
            actions=("s3:GetObject",),
            resource_template="arn:aws:s3:::{bucket}/{namespace}",
            probe_kind=ProbeKind.READ_MARKER,
        )
        with pytest.raises(BindingValidationError, match="SI-9"):
            validate_binding(dangerous, binding, Provider.AWS)


class TestResolveBindingsCapabilityNotInCatalog:
    def test_required_capability_absent_from_catalog_is_reported_missing(self):
        """resolve_bindings must treat "not in the catalog at all" the same as
        "no binding registered" -- both are CAP-1 violations, not two
        different code paths with different failure behavior."""
        catalog = load_catalog()
        with pytest.raises(CapabilityResolutionError, match=re.escape("test.does_not_exist")):
            resolve_bindings(catalog, AuthoritySet.of("test.does_not_exist"), {}, Provider.AWS)
