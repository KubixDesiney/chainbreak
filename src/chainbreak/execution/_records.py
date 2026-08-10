"""Shared :class:`~chainbreak.core.models.Observation` construction.

``control.py``'s calibration probe and ``matrix.py``'s regular probe cells
build the exact same record shape from the exact same inputs (a
:class:`~chainbreak.providers.base.types.ProbeResult` plus the request
context that produced it); factored out once here rather than duplicated so
the two can never silently drift apart on a field.

Private to ``execution/`` (leading underscore) -- not part of this package's
public surface, callers outside ``execution/`` should have no reason to
build an ``Observation`` directly.
"""

from __future__ import annotations

from datetime import datetime

from chainbreak.core.canonical import dumps
from chainbreak.core.enums import PlanPhase
from chainbreak.core.ids import IdentityId, digest_ref, fingerprint_json, new_observation_id
from chainbreak.core.models import (
    CredentialRecord,
    Observation,
    ProbeRequestRecord,
    ProviderCapabilityBinding,
)
from chainbreak.providers.base.types import ProbeResult


def credential_age_ms(credential: CredentialRecord | None, *, now: datetime) -> float | None:
    """Age of the credential the probe was issued under, at probe time.

    ``None`` for a root identity (registered directly, never delegated to --
    there is no ``CredentialRecord`` to measure an age from).
    """
    if credential is None:
        return None
    return (now - credential.issued_at).total_seconds() * 1000


def build_observation(
    *,
    run_id: str,
    sequence: int,
    phase: PlanPhase,
    matrix_id: str,
    identity_id: IdentityId,
    identity_ref_value: str,
    capability_id: str,
    trial: int,
    trial_count: int,
    binding: ProviderCapabilityBinding,
    namespace: str,
    result: ProbeResult,
    credential: CredentialRecord | None,
    now: datetime,
    preconditions_verified: bool,
    salt: str,
) -> Observation:
    target_ref = binding.resource_template.format(namespace=namespace)
    parameters = dumps({"capability_id": capability_id, "trial": trial})
    return Observation(
        observation_id=new_observation_id(),
        run_id=run_id,
        sequence=sequence,
        phase=phase,
        probe_matrix_id=matrix_id,
        identity_id=identity_id,
        identity_ref_hash=digest_ref(identity_ref_value, salt),
        capability_id=capability_id,
        trial=trial,
        trial_count=trial_count,
        credential_id=credential.credential_id if credential is not None else None,
        credential_age_ms=credential_age_ms(credential, now=now),
        request=ProbeRequestRecord(
            probe_kind=binding.probe_kind,
            binding_actions=binding.actions,
            target_ref_hash=digest_ref(target_ref, salt),
            target_namespace=namespace,
            parameters_fingerprint=fingerprint_json(parameters),
        ),
        timing=result.timing,
        outcome=result.outcome,
        preconditions_verified=preconditions_verified,
    )
