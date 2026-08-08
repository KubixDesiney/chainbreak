"""Revocation window math (AUTHORIZATION_MODEL.md section 5.1) and stale
authority classification (section 5.2). Pure functions; every timing value
is monotonic nanoseconds in, an :class:`Interval` out -- never a bare scalar.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from chainbreak.core.enums import MutationKind, OutcomeClass, StaleAuthorityClass
from chainbreak.core.ids import CapabilityId, IdentityId
from chainbreak.core.models import Interval, RevocationMeasurement

_NS_PER_S = 1_000_000_000


def _ns_to_s(nanoseconds: int) -> float:
    return nanoseconds / _NS_PER_S


@dataclass(frozen=True, slots=True)
class PollSample:
    """One serial poll of a single (identity, capability) pair during a
    revocation transition (AUTHORIZATION_MODEL.md section 5.1)."""

    monotonic_ns: int
    outcome: OutcomeClass


def compute_revocation_window(
    samples: Sequence[PollSample],
    *,
    identity_id: IdentityId,
    capability_id: CapabilityId,
    mutation_kind: MutationKind,
    mutation_sent_ns: int,
    poll_interval_ms: int,
    mutation_receipt_confirmed: bool,
) -> RevocationMeasurement:
    """``mutation_sent_ns`` is ``t_M`` -- the monotonic instant the mutation
    *request was sent*, not when its receipt confirmed (deliberately
    conservative: using the send instant can only make the reported window
    look wider, never narrower).

    Flip-flop handling: an ``ALLOWED`` sample after ``t_first_deny`` is
    preserved as ``non_monotonic=True`` with a note, never smoothed away --
    oscillation is itself the interesting result in this family.
    """
    ordered = sorted(samples, key=lambda sample: sample.monotonic_ns)

    if not ordered:
        return RevocationMeasurement(
            identity_id=identity_id,
            capability_id=capability_id,
            mutation_kind=mutation_kind,
            transition_observed=False,
            poll_interval_ms=poll_interval_ms,
            poll_count=0,
            window_length_s=0.0,
            mutation_receipt_confirmed=mutation_receipt_confirmed,
            notes=("no poll samples recorded",),
        )

    window_length_s = _ns_to_s(ordered[-1].monotonic_ns - mutation_sent_ns)
    common = {
        "identity_id": identity_id,
        "capability_id": capability_id,
        "mutation_kind": mutation_kind,
        "poll_interval_ms": poll_interval_ms,
        "poll_count": len(ordered),
        "window_length_s": window_length_s,
        "mutation_receipt_confirmed": mutation_receipt_confirmed,
    }

    allowed_ns = [s.monotonic_ns for s in ordered if s.outcome is OutcomeClass.ALLOWED]
    denied_ns = [s.monotonic_ns for s in ordered if s.outcome.is_denial]

    if not allowed_ns:
        return RevocationMeasurement(
            **common, transition_observed=False, notes=("never observed ALLOWED",)
        )

    t_last_allow = max(allowed_ns)
    later_denies = [t for t in denied_ns if t > t_last_allow]
    if not later_denies:
        return RevocationMeasurement(
            **common,
            transition_observed=False,
            notes=("NO_TRANSITION_OBSERVED_WITHIN_WINDOW",),
        )
    t_first_deny = min(later_denies)

    # NOT "any ALLOWED after t_first_deny": t_last_allow is the *global* max
    # of every ALLOWED sample, so no sample can ever exceed it -- that check
    # is vacuously false by construction and would never fire. Oscillation
    # is instead detected directly: count ALLOWED<->denied state changes in
    # chronological order (errors/indeterminate samples don't carry a state
    # for this purpose). A clean transition has exactly one; more than one
    # is a genuine flip-flop.
    transitions = 0
    previous_state: bool | None = None
    for sample in ordered:
        if sample.outcome is OutcomeClass.ALLOWED:
            state = True
        elif sample.outcome.is_denial:
            state = False
        else:
            continue
        if previous_state is not None and state != previous_state:
            transitions += 1
        previous_state = state
    non_monotonic = transitions > 1

    low = _ns_to_s(t_last_allow - mutation_sent_ns)
    high = _ns_to_s(t_first_deny - mutation_sent_ns)
    window = Interval(low=low, point=(low + high) / 2, high=high, unit="s")

    notes = ("NON_MONOTONIC_TRANSITION",) if non_monotonic else ()
    return RevocationMeasurement(
        **common,
        transition_window=window,
        transition_observed=True,
        non_monotonic=non_monotonic,
        notes=notes,
    )


def classify_stale_authority(
    *,
    deferred_outcome: OutcomeClass,
    credential_expired_at_execution: bool,
    session_scope_removed: bool = False,
    fresh_outcome: OutcomeClass | None = None,
) -> StaleAuthorityClass:
    """The six-row table (AUTHORIZATION_MODEL.md section 5.2).

    ``fresh_outcome`` -- the paired, freshly-minted-credential probe at the
    same instant (M13's design element) -- disambiguates the one row the
    naive table cannot: an ``ALLOWED`` deferred probe with an unexpired
    credential is ``STALE_AUTHORITY_LIVE_CREDENTIAL`` only if a *fresh*
    credential would see the *new* policy. If the fresh credential is
    ``ALLOWED`` too, the mutation has not propagated anywhere yet -- a
    materially different, more fundamental result than staleness, and one
    the current classification vocabulary has no dedicated member for; per
    "prefer INCONCLUSIVE over a guess" (CLAUDE_CODE_HANDOFF.md Part 2), that
    case is reported as ``INDETERMINATE`` rather than mislabelled.
    """
    is_denial = deferred_outcome.is_denial
    is_allowed = deferred_outcome is OutcomeClass.ALLOWED

    if is_denial and credential_expired_at_execution:
        return StaleAuthorityClass.CREDENTIAL_EXPIRED
    if is_allowed and credential_expired_at_execution:
        return StaleAuthorityClass.EXPIRED_CREDENTIAL_HONORED
    if is_denial and not credential_expired_at_execution:
        return StaleAuthorityClass.CURRENT_AUTHORITY
    if is_allowed and not credential_expired_at_execution:
        if session_scope_removed:
            return StaleAuthorityClass.SESSION_SCOPE_CACHED
        if fresh_outcome is OutcomeClass.ALLOWED:
            return StaleAuthorityClass.INDETERMINATE
        return StaleAuthorityClass.STALE_AUTHORITY_LIVE_CREDENTIAL
    return StaleAuthorityClass.INDETERMINATE
