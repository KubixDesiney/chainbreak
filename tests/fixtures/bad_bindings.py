"""Deliberately invalid provider capability bindings, for M2's binding-validator
and operation-allowlist tests.

Built against the real ``objectstore.read`` catalog entry (``probe_kind:
READ_MARKER``, ``requires_precondition: [objectstore.marker_present]``) so
these exercise ``validate_binding`` against a capability that actually ships,
not a synthetic stand-in.
"""

from __future__ import annotations

from chainbreak.core.enums import ProbeKind, Provider
from chainbreak.core.models import ProviderCapabilityBinding

_OBJECTSTORE_READ = "objectstore.read"


def wrong_provider_binding() -> ProviderCapabilityBinding:
    """Declares FAKE while the caller will validate against AWS."""
    return ProviderCapabilityBinding(
        capability_id=_OBJECTSTORE_READ,
        provider=Provider.FAKE,
        actions=("s3:GetObject",),
        resource_template="arn:aws:s3:::{bucket}/{namespace}/markers/marker.json",
        probe_kind=ProbeKind.READ_MARKER,
        preconditions=("objectstore.marker_present",),
    )


def wrong_probe_kind_binding() -> ProviderCapabilityBinding:
    """Declares LIST_PREFIX for a capability that requires READ_MARKER."""
    return ProviderCapabilityBinding(
        capability_id=_OBJECTSTORE_READ,
        provider=Provider.AWS,
        actions=("s3:GetObject",),
        resource_template="arn:aws:s3:::{bucket}/{namespace}/markers/marker.json",
        probe_kind=ProbeKind.LIST_PREFIX,
        preconditions=("objectstore.marker_present",),
    )


def missing_precondition_binding() -> ProviderCapabilityBinding:
    """Omits objectstore.marker_present, which the capability requires."""
    return ProviderCapabilityBinding(
        capability_id=_OBJECTSTORE_READ,
        provider=Provider.AWS,
        actions=("s3:GetObject",),
        resource_template="arn:aws:s3:::{bucket}/{namespace}/markers/marker.json",
        probe_kind=ProbeKind.READ_MARKER,
        preconditions=(),
    )


def narrow_binding_for_broadening_test() -> ProviderCapabilityBinding:
    """Otherwise-valid binding with a narrow ``actions`` set.

    Used to demonstrate the "over-broad" negative control: a probe that
    invokes an operation outside this declared set must be caught by
    ``OperationAllowlist``, independent of whether the probe itself
    "succeeded" (M2 spec's own negative-controls example, adapted to the
    real objectstore.read capability rather than a synthetic ``fake:*`` pair).
    """
    return ProviderCapabilityBinding(
        capability_id=_OBJECTSTORE_READ,
        provider=Provider.AWS,
        actions=("s3:GetObject",),
        resource_template="arn:aws:s3:::{bucket}/{namespace}/markers/marker.json",
        probe_kind=ProbeKind.READ_MARKER,
        preconditions=("objectstore.marker_present",),
    )
