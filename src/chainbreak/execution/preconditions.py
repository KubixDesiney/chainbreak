"""C-2: preconditions verified by the provisioning identity before every
read matrix (RESEARCH_METHODOLOGY.md section 4; handoff Part 3's "measurement
hazard").

On the object store, a read against a *missing* key returns a response
identical to a real denial when the caller lacks the corresponding list
permission, which an agent under test generally does (AWS_PROVIDER_SPEC.md
section 6.1's 403/404 problem, named without the literal provider action
string here since this module is provider-neutral). Without this check, a
missing marker would silently masquerade as a wave of denials in every
capability that required it. Verifying up front, once, before any probe in
the matrix runs, is what lets the whole matrix be reported
``ERROR_INFRASTRUCTURE`` instead.

This module only resolves precondition names against a
:class:`~chainbreak.capabilities.preconditions.PreconditionRegistry` and
reports pass/fail; what a failure means for the matrix already in flight is
``execution/matrix.py``'s concern.
"""

from __future__ import annotations

from chainbreak.capabilities.preconditions import PreconditionRegistry
from chainbreak.core.models import AuthoritySet, CapabilityCatalog, IdentityRef


def required_preconditions(
    catalog: CapabilityCatalog, capabilities: AuthoritySet
) -> tuple[str, ...]:
    """Every distinct precondition name the matrix's capabilities require,
    in a stable (sorted) order so evidence stays diffable."""
    names: set[str] = set()
    for capability_id in capabilities:
        names.update(catalog.get(capability_id).requires_precondition)
    return tuple(sorted(names))


def verify_matrix_preconditions(
    registry: PreconditionRegistry,
    catalog: CapabilityCatalog,
    capabilities: AuthoritySet,
    provisioning_identity: IdentityRef,
) -> dict[str, bool]:
    """Verify every precondition this matrix's capabilities require, using
    the provisioning identity, before any probe in the matrix runs (C-2).

    An empty result means the matrix has no read preconditions at all --
    that is a pass, not something to special-case at the call site.
    """
    names = required_preconditions(catalog, capabilities)
    return registry.verify_all(names, provisioning_identity)


def unsatisfied_preconditions(results: dict[str, bool]) -> tuple[str, ...]:
    """The subset of :func:`verify_matrix_preconditions`'s result that
    failed, in a stable order -- what a ``PreconditionFailedError`` names."""
    return tuple(sorted(name for name, passed in results.items() if not passed))
