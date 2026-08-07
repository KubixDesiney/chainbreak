"""Precondition declarations and the verification interface.

A precondition is a named assertion about benchmark state that must hold
before a probe matrix runs -- "the marker object exists", say. The executor
(M5+) verifies every precondition a capability requires, using the
*provisioning* identity, before any probe attempt; what a failed precondition
means for the matrix already in flight (every observation becomes
``ERROR_INFRASTRUCTURE``, the resulting finding ``CONFIGURATION_ERROR`` --
never a set of denials, CAPABILITY_MODEL.md section 4 rule 3) is the
executor's concern. This module only resolves a precondition name to its
verifier and invokes it; verifier implementations themselves are
provider-specific and out of scope here (M5 fake, M8 AWS).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from chainbreak.core.errors import BindingValidationError
from chainbreak.core.models import IdentityRef

PreconditionVerifier = Callable[[IdentityRef], bool]


class PreconditionRegistry:
    """Precondition name -> verifier callable."""

    def __init__(self) -> None:
        self._verifiers: dict[str, PreconditionVerifier] = {}

    def register(self, name: str, verifier: PreconditionVerifier) -> None:
        if name in self._verifiers:
            raise BindingValidationError(f"duplicate precondition verifier: {name!r}")
        self._verifiers[name] = verifier

    def resolve(self, name: str) -> PreconditionVerifier:
        try:
            return self._verifiers[name]
        except KeyError:
            raise BindingValidationError(
                f"no verifier registered for precondition {name!r}"
            ) from None

    def verify(self, name: str, provisioning_identity: IdentityRef) -> bool:
        return self.resolve(name)(provisioning_identity)

    def verify_all(
        self, names: Iterable[str], provisioning_identity: IdentityRef
    ) -> dict[str, bool]:
        return {name: self.verify(name, provisioning_identity) for name in names}
