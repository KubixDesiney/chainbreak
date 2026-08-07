"""Probe outcome construction for the fake provider (F7): preconditions,
the control-capability override, and denial attribution -- all sharing the
same policy-evaluation core (``engine.PolicyEngine``).

Splits cleanly from ``adapter.py``: this module packages a *precomputed*
``OutcomeClass`` into a ``ProbeOutcome`` (handling preconditions and the
control-capability override on the way); *deciding* that outcome class is
the adapter's job, because only the adapter knows whether a consistency-model
transition is still in flight and therefore whether to evaluate against live
state or a pre-mutation snapshot (``engine.PolicyEngine.evaluate_against``).

Timing, retries and fault injection are cross-cutting concerns applied once,
uniformly, by the adapter -- duplicating them per probe kind here would be
the same mistake AWS_PROVIDER_SPEC section 6.3 warns against (a probe-specific
retry policy is how you accidentally manufacture a timing artifact).

Real AWS's probe-specific disambiguation hazards (403-vs-404, "FunctionError
that isn't a denial", ...) are the AWS adapter's concern (M8) -- the fake's
job (F2) is to be a faithful *policy* engine, not to reproduce every provider
HTTP quirk. What the fake *does* reproduce faithfully: ``identity.whoami`` is
never denied (a control capability calibrates the matrix, it does not test
it), and a failed precondition is an infrastructure fault, never a wave of
denials (CAPABILITY_MODEL.md section 4 rule 3).
"""

from __future__ import annotations

from dataclasses import dataclass

from chainbreak.capabilities.preconditions import PreconditionRegistry
from chainbreak.core.enums import DenialAttribution, OutcomeClass
from chainbreak.core.models import AuthoritySet, Capability, IdentityRef, ProbeOutcome


@dataclass
class MarkerStore:
    """The fake's own provisioned state -- always present by default, since
    the fake is its own infrastructure. Tests can flip a flag to False to
    exercise the precondition-failure path deliberately."""

    objectstore_marker_present: bool = True
    keyvalue_marker_present: bool = True
    function_alive: bool = True
    queue_present: bool = True


def build_fake_preconditions(markers: MarkerStore) -> PreconditionRegistry:
    """Registers a verifier per precondition name the catalog declares
    (``capabilities.catalog.yaml``'s ``requires_precondition`` entries)."""
    registry = PreconditionRegistry()
    registry.register("objectstore.marker_present", lambda _ref: markers.objectstore_marker_present)
    registry.register("keyvalue.marker_present", lambda _ref: markers.keyvalue_marker_present)
    registry.register("function.alive", lambda _ref: markers.function_alive)
    registry.register("queue.present", lambda _ref: markers.queue_present)
    return registry


def _denial_attribution(
    outcome_class: OutcomeClass,
    *,
    identity_allow: AuthoritySet,
    capability_id: str,
    session_narrowed_it: bool,
) -> DenialAttribution | None:
    if outcome_class is OutcomeClass.DENIED_EXPLICIT:
        return DenialAttribution.EXPLICIT_DENY
    if outcome_class is OutcomeClass.DENIED_IMPLICIT:
        if session_narrowed_it and capability_id in identity_allow:
            return DenialAttribution.SESSION_POLICY
        return DenialAttribution.IMPLICIT_NO_ALLOW
    return None


def build_probe_outcome(
    *,
    preconditions: PreconditionRegistry,
    provisioning_identity: IdentityRef,
    capability: Capability,
    outcome_class: OutcomeClass,
    identity_allow: AuthoritySet,
    session_allow: AuthoritySet | None,
) -> ProbeOutcome:
    """Packages a precomputed policy decision into a ``ProbeOutcome``,
    applying the two overrides that take priority over any policy decision:
    a failed precondition (infrastructure fault, checked first) and the
    control-capability exemption (never denied, checked second)."""
    for name in capability.requires_precondition:
        if not preconditions.verify(name, provisioning_identity):
            return ProbeOutcome(
                outcome_class=OutcomeClass.ERROR_INFRASTRUCTURE,
                message_redacted=f"precondition {name!r} not satisfied",
                disambiguation_path="precondition_failed",
            )

    if capability.is_control:
        return ProbeOutcome(
            outcome_class=OutcomeClass.ALLOWED,
            disambiguation_path="control_capability",
        )

    attribution = _denial_attribution(
        outcome_class,
        identity_allow=identity_allow,
        capability_id=capability.id,
        session_narrowed_it=session_allow is not None,
    )
    return ProbeOutcome(
        outcome_class=outcome_class,
        denial_attribution=attribution,
        disambiguation_path="policy_engine",
    )
