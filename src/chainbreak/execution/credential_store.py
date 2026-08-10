"""Per-phase credential registry (M13, F1): records which
:class:`~chainbreak.core.models.CredentialRecord` was current for an
identity as of a given scenario phase, so a later ``DEFERRED_EXECUTION``
phase's ``credential_source: phase:<name>`` can resolve back to "the
credential minted at that phase" without re-delegating.

S2 (EV-1): this store is in-memory only for the lifetime of a single run and
is never serialized -- ``execution/orchestrator.py`` constructs one per
``orchestrate()`` call and discards it when the run ends.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from chainbreak.core.errors import ExecutionError
from chainbreak.core.ids import IdentityId
from chainbreak.core.models import CredentialRecord

__all__ = ["CredentialStore"]


@dataclass
class CredentialStore:
    """Keyed by ``(phase_name, identity_id)``. ``record`` is called once per
    identity every time a phase actually runs against it (matrix.py's own
    caller, ``execution/orchestrator.py``); ``resolve`` parses a
    scenario-declared ``credential_source`` string (already validated by
    ``ScenarioSpec._referential_integrity`` to reference a real phase name)
    back to the credential that was current then."""

    _by_phase_and_identity: dict[tuple[str, IdentityId], CredentialRecord | None] = field(
        default_factory=dict
    )

    def record(
        self, phase_name: str, identity_id: IdentityId, credential: CredentialRecord | None
    ) -> None:
        self._by_phase_and_identity[(phase_name, identity_id)] = credential

    def resolve(self, credential_source: str, identity_id: IdentityId) -> CredentialRecord:
        phase_name = credential_source.removeprefix("phase:")
        try:
            credential = self._by_phase_and_identity[(phase_name, identity_id)]
        except KeyError:
            raise ExecutionError(
                f"credential_source {credential_source!r} for {identity_id!r}: no credential "
                f"was ever recorded for phase {phase_name!r} -- it may not have run yet, or "
                "never targeted this identity",
                identity_id=identity_id,
                credential_source=credential_source,
            ) from None
        if credential is None:
            raise ExecutionError(
                f"credential_source {credential_source!r} for {identity_id!r}: phase "
                f"{phase_name!r} recorded no credential for it (a root identity has none to "
                "pin)",
                identity_id=identity_id,
                credential_source=credential_source,
            )
        return credential
