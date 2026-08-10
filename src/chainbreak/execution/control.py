"""C-1: the control-capability calibration probe (RESEARCH_METHODOLOGY.md
section 4; CAPABILITY_MODEL.md section on ``identity.whoami``).

Every capability the catalog marks ``is_control=True`` (v0.1 ships exactly
one, ``identity.whoami``) cannot be denied by an identity policy. Its
failure therefore means the apparatus itself is broken -- credentials,
network, endpoint -- not that the identity under test lacks authority.
Reported as a wave of denials, it would look exactly like a real finding;
raising :class:`~chainbreak.core.errors.ControlCapabilityFailedError`
instead is what lets the orchestrator discard the whole matrix rather than
publish a false result.

Probed once per identity, before the shuffled, trial-repeated capability
loop (``matrix.py``) runs -- calibrating first is the point: an apparatus
fault should be caught before any of the matrix's other probes are spent
finding out the hard way.
"""

from __future__ import annotations

from datetime import datetime

from chainbreak.core.enums import OutcomeClass, PlanPhase
from chainbreak.core.errors import ControlCapabilityFailedError
from chainbreak.core.ids import IdentityId
from chainbreak.core.models import CapabilityCatalog, CredentialRecord, IdentityRef, Observation
from chainbreak.execution._records import build_observation
from chainbreak.providers.base.protocol import ProviderAdapter
from chainbreak.providers.base.types import ProbeRequest

__all__ = ["calibrate_matrix"]


def calibrate_matrix(
    adapter: ProviderAdapter,
    catalog: CapabilityCatalog,
    *,
    ref: IdentityRef,
    identity_id: IdentityId,
    run_id: str,
    phase: PlanPhase,
    matrix_id: str,
    sequence: int,
    credential: CredentialRecord | None,
    now: datetime,
    salt: str,
    namespace: str,
) -> tuple[Observation, ...]:
    """Probe every control capability once for ``identity_id``.

    Raises :class:`ControlCapabilityFailedError` on the first non-``ALLOWED``
    outcome; the caller (``matrix.py``) is expected to discard the entire
    matrix, not just this identity's row, since a broken control capability
    for one identity casts doubt on the apparatus for all of them.
    """
    observations: list[Observation] = []
    for control in catalog.controls():
        binding = adapter.resolve_capability(control.id)
        result = adapter.probe(
            ProbeRequest(
                identity_ref=ref,
                capability_id=control.id,
                binding=binding,
                namespace=namespace,
                trial=1,
            )
        )
        observations.append(
            build_observation(
                run_id=run_id,
                sequence=sequence + len(observations),
                phase=phase,
                matrix_id=matrix_id,
                identity_id=identity_id,
                identity_ref_value=ref.value,
                capability_id=control.id,
                trial=1,
                trial_count=1,
                binding=binding,
                namespace=namespace,
                result=result,
                credential=credential,
                now=now,
                preconditions_verified=True,
                salt=salt,
            )
        )
        if result.outcome.outcome_class is not OutcomeClass.ALLOWED:
            raise ControlCapabilityFailedError(
                f"control capability {control.id!r} was not ALLOWED for "
                f"{identity_id!r} (got {result.outcome.outcome_class}); apparatus "
                f"fault, discarding matrix {matrix_id!r}",
                identity_id=identity_id,
                capability_id=control.id,
                matrix_id=matrix_id,
                outcome_class=str(result.outcome.outcome_class),
            )
    return tuple(observations)
