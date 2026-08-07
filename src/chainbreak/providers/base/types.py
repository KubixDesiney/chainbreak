"""Live provider wire types (ARCHITECTURE.md section 3.8).

These are deliberately *not* the same objects as the evidence-layer records
in ``core/models.py`` (``Observation``, ``ProbeOutcome``, ``CredentialRecord``,
...). This module's types are what one call to a ``ProviderAdapter`` takes
and returns in-process; the evidence layer (``observation/``, M6+) is what
later converts a raw ``ProbeResult`` into a normalized, bookkept
``Observation`` -- adding the sequence number, run id and trial count only an
orchestrator (not a single adapter call) can know.

``ProbeResult`` reuses ``ProbeOutcome``/``ProbeTiming`` wholesale rather than
duplicating their fields: an adapter's local knowledge of one call *is*
exactly an outcome plus its timing, nothing more.

``DelegationResult`` is the one exception to "everything here is a
``DomainModel``": it carries a live ``TemporaryCredential``, which is a
plain, non-Pydantic class by design (SI-1 -- see ``core/secrets.py``). A
Pydantic model cannot hold that without either disabling validation for the
field or accepting that a serialization attempt raises ``SecretSerializationError``
by design; a plain frozen dataclass keeps the type honest about being a
transient, never-serialized, in-process value.
"""

from __future__ import annotations

from dataclasses import dataclass

from chainbreak.core.enums import DelegationMechanism, Provider
from chainbreak.core.ids import CapabilityId, IdentityId, Namespace
from chainbreak.core.models import (
    AuthoritySet,
    CredentialRecord,
    DelegationConstraints,
    DomainModel,
    IdentityRef,
    ProbeOutcome,
    ProbeTiming,
    ProviderCapabilityBinding,
)
from chainbreak.core.secrets import TemporaryCredential


class PreflightCheck(DomainModel):
    """One named check performed during ``preflight`` (mirrors AWS_PROVIDER_SPEC
    section 2's P1-P11 table, generalized to any provider)."""

    name: str
    passed: bool
    detail: str


class PreflightReport(DomainModel):
    """Result of ``ProviderAdapter.preflight``. ``passed`` is false if any
    check failed; ``checks`` records every check performed, not only the
    first failure, so a caller can report all of them at once."""

    passed: bool
    account_ref: str | None = None
    region: str | None = None
    checks: tuple[PreflightCheck, ...] = ()


class EnvironmentDescriptor(DomainModel):
    """Result of ``ProviderAdapter.describe_environment``: what the adapter
    is actually pointed at, for provenance."""

    provider: Provider
    adapter_version: str
    account_ref: str | None = None
    region: str | None = None
    namespace: Namespace


class DelegationRequest(DomainModel):
    """Input to ``ProviderAdapter.delegate``.

    ``intended_capabilities`` is what a ``SESSION_POLICY_SCOPED`` (or
    ``ROLE_CHAIN_WITH_SESSION_POLICY``) mechanism scopes the session to; the
    adapter is responsible for synthesizing its own provider-specific policy
    document from this set (AWS_PROVIDER_SPEC section 4) -- the compiler's
    ``SynthesizedPolicy`` (M3) records only the size and fingerprint of that
    future document, never the document itself.
    """

    source_identity: IdentityRef
    target_identity_id: IdentityId
    mechanism: DelegationMechanism
    requested_duration_s: int
    intended_capabilities: AuthoritySet
    constraints: DelegationConstraints = DelegationConstraints()


@dataclass(frozen=True, slots=True)
class DelegationResult:
    """Output of ``ProviderAdapter.delegate``. Not a ``DomainModel`` (see
    module docstring) -- it is the one live handle to usable credential
    material, held only for the lifetime of the caller's session."""

    identity_ref: IdentityRef
    credential: TemporaryCredential
    record: CredentialRecord
    granted_capabilities: AuthoritySet


class ProbeRequest(DomainModel):
    """Input to ``ProviderAdapter.probe``: one (identity, capability) cell,
    one trial."""

    identity_ref: IdentityRef
    capability_id: CapabilityId
    binding: ProviderCapabilityBinding
    namespace: Namespace
    trial: int = 1


class ProbeResult(DomainModel):
    """Output of ``ProviderAdapter.probe``: exactly what one call learned,
    nothing an orchestrator would need to supply."""

    outcome: ProbeOutcome
    timing: ProbeTiming
