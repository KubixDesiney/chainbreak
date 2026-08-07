"""The adapter Protocol every provider package must implement
(ARCHITECTURE.md section 3.8).

A ``typing.Protocol``, not an ABC: providers/fake and providers/aws each
implement this structurally, with no shared base class to inherit from and
therefore nothing for either package to import from the other (the layered
contract "provider adapters depend only on providers.base" is enforced by
import-linter, not by inheritance).

**INVARIANT PROV-1** (enforced by the binding validator, not here): an
adapter may narrow but never broaden a scenario's requested capability set.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from chainbreak.core.ids import CapabilityId
from chainbreak.core.models import (
    IdentityRef,
    MutationReceipt,
    PolicyMutation,
    PolicyStateSnapshot,
    ProviderCapabilityBinding,
    SafetyEnvelope,
)
from chainbreak.providers.base.types import (
    DelegationRequest,
    DelegationResult,
    EnvironmentDescriptor,
    PreflightReport,
    ProbeRequest,
    ProbeResult,
)


@runtime_checkable
class ProviderAdapter(Protocol):  # pragma: no cover -- structural interface, never instantiated
    """Every provider package (``providers/fake``, ``providers/aws``)
    implements this Protocol. The shared contract test suite
    (``tests/integration/test_provider_contract.py``) exercises any object
    satisfying it identically."""

    name: str
    adapter_version: str

    def preflight(self, envelope: SafetyEnvelope) -> PreflightReport: ...

    def resolve_capability(self, cap_id: CapabilityId) -> ProviderCapabilityBinding: ...

    def describe_environment(self) -> EnvironmentDescriptor: ...

    def delegate(self, request: DelegationRequest) -> DelegationResult: ...

    def probe(self, request: ProbeRequest) -> ProbeResult: ...

    def apply_policy_mutation(self, mutation: PolicyMutation) -> MutationReceipt: ...

    def snapshot_policy_state(self, identity_ref: IdentityRef) -> PolicyStateSnapshot: ...
