"""Builds :class:`~chainbreak.core.models.StaleAuthorityMeasurement` records
from a bundle's ``DEFERRED_EXECUTION``/``PAIRED_FRESH_CREDENTIAL``
observations (M13). ``analysis/timing.py::classify_stale_authority``
(AUTHORIZATION_MODEL.md section 5.2's six-row table) already existed from M7
and is unit-tested there; this module is what actually drives it from real
evidence -- the same "measurement layer already existed, execution/analysis
wiring is the milestone's own contribution" pattern M12 followed for the
revocation family.

F3, restated: a deferred observation is paired with the immediately-
following fresh-credential observation for the *same* (identity,
capability) -- never classified alone. ``session_scope_removed`` is read
from the evidence stream too (a ``POLICY_MUTATION_APPLIED`` event of kind
``DELETE_SESSION_POLICY_SCOPE`` targeting this identity), not guessed from
the observed outcome: the fake's own implementation of that mutation kind is
a documented no-op on live authority (M12's ``delete-session-scope.yaml``),
so nothing about the *outcome* alone could ever distinguish "the scope was
removed but sessions are cached" from ordinary staleness -- only the
mutation record can.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from chainbreak.analysis.timing import classify_stale_authority
from chainbreak.core.enums import MutationKind, PlanPhase
from chainbreak.core.ids import CapabilityId, IdentityId
from chainbreak.core.models import CredentialRecord, Observation, StaleAuthorityMeasurement

__all__ = ["stale_authority_measurements"]


def _session_scope_removed_identities(events: Sequence[dict[str, Any]]) -> set[IdentityId]:
    return {
        e["target_identity"]
        for e in events
        if e.get("kind") == "POLICY_MUTATION_APPLIED"
        and e.get("mutation_kind") == MutationKind.DELETE_SESSION_POLICY_SCOPE.value
        and e.get("target_identity")
    }


def stale_authority_measurements(
    events: Sequence[dict[str, Any]],
    observations: Sequence[Observation],
    credentials: Sequence[CredentialRecord],
) -> list[StaleAuthorityMeasurement]:
    deferred = [o for o in observations if o.phase is PlanPhase.DEFERRED_EXECUTION]
    if not deferred:
        return []

    fresh_by_cell: dict[tuple[IdentityId, CapabilityId], Observation] = {}
    for observation in observations:
        if observation.phase is PlanPhase.PAIRED_FRESH_CREDENTIAL:
            fresh_by_cell[(observation.identity_id, observation.capability_id)] = observation

    credentials_by_id = {c.credential_id: c for c in credentials}
    session_scope_removed_identities = _session_scope_removed_identities(events)

    measurements: list[StaleAuthorityMeasurement] = []
    for observation in deferred:
        credential = (
            credentials_by_id.get(observation.credential_id) if observation.credential_id else None
        )
        if credential is None:
            # No credential record for this observation -- cannot determine
            # expiry, so this cell cannot be classified (prefer INCONCLUSIVE
            # over a guess, CLAUDE_CODE_HANDOFF.md Part 2).
            continue

        fresh = fresh_by_cell.get((observation.identity_id, observation.capability_id))
        credential_expired_at_execution = observation.timing.wall_start >= credential.expires_at
        deferral_seconds = max(
            0.0, (observation.timing.wall_start - credential.issued_at).total_seconds()
        )

        classification = classify_stale_authority(
            deferred_outcome=observation.outcome.outcome_class,
            credential_expired_at_execution=credential_expired_at_execution,
            session_scope_removed=observation.identity_id in session_scope_removed_identities,
            fresh_outcome=fresh.outcome.outcome_class if fresh is not None else None,
        )

        measurements.append(
            StaleAuthorityMeasurement(
                identity_id=observation.identity_id,
                capability_id=observation.capability_id,
                classification=classification,
                deferral_seconds=deferral_seconds,
                credential_expired_at_execution=credential_expired_at_execution,
                paired_fresh_credential_outcome=(
                    fresh.outcome.outcome_class if fresh is not None else None
                ),
            )
        )

    return measurements
