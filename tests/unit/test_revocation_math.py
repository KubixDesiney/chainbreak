"""``analysis/timing.py``'s revocation window math (AUTHORIZATION_MODEL.md
section 5.1). Validates the interval math against known answers -- the only
place this math can be checked against ground truth without AWS."""

from __future__ import annotations

import pytest

from chainbreak.analysis.timing import PollSample, compute_revocation_window
from chainbreak.core.enums import MutationKind, OutcomeClass

pytestmark = pytest.mark.unit

_S = 1_000_000_000  # one second in nanoseconds


def _samples(*pairs: tuple[int, OutcomeClass]) -> list[PollSample]:
    return [PollSample(monotonic_ns=ns, outcome=outcome) for ns, outcome in pairs]


class TestCleanTransition:
    def test_bracketed_window_matches_known_bounds(self):
        samples = _samples(
            (0, OutcomeClass.ALLOWED),
            (1 * _S, OutcomeClass.ALLOWED),
            (2 * _S, OutcomeClass.ALLOWED),
            (3 * _S, OutcomeClass.DENIED_EXPLICIT),
            (4 * _S, OutcomeClass.DENIED_EXPLICIT),
        )
        measurement = compute_revocation_window(
            samples,
            identity_id="agent-b",
            capability_id="objectstore.read",
            mutation_kind=MutationKind.ATTACH_INLINE_DENY,
            mutation_sent_ns=int(1.5 * _S),
            poll_interval_ms=1000,
            mutation_receipt_confirmed=True,
        )
        assert measurement.transition_observed is True
        assert measurement.transition_window is not None
        # t_last_allow=2s, t_first_deny=3s, t_M=1.5s -> window [0.5s, 1.5s]
        assert measurement.transition_window.low == pytest.approx(0.5)
        assert measurement.transition_window.high == pytest.approx(1.5)
        assert measurement.transition_window.point == pytest.approx(1.0)
        assert measurement.non_monotonic is False

    @pytest.mark.parametrize("propagation_delay_s", [0, 0.5, 2, 10])
    def test_window_contains_the_true_propagation_delay(self, propagation_delay_s):
        """The measured window must contain the true value in every case
        (the fake provider's own ``propagation_delay_ms`` -- this is the
        differential control M07's spec names explicitly)."""
        mutation_sent_ns = 0
        transition_ns = int(propagation_delay_s * _S)
        samples = []
        t = -2 * _S
        while t < transition_ns:
            samples.append(PollSample(monotonic_ns=t, outcome=OutcomeClass.ALLOWED))
            t += _S // 4
        t = transition_ns
        while t < transition_ns + 2 * _S:
            samples.append(PollSample(monotonic_ns=t, outcome=OutcomeClass.DENIED_EXPLICIT))
            t += _S // 4

        measurement = compute_revocation_window(
            samples,
            identity_id="agent-b",
            capability_id="objectstore.read",
            mutation_kind=MutationKind.ATTACH_INLINE_DENY,
            mutation_sent_ns=mutation_sent_ns,
            poll_interval_ms=250,
            mutation_receipt_confirmed=True,
        )
        assert measurement.transition_window is not None
        window = measurement.transition_window
        assert window.low <= propagation_delay_s <= window.high


class TestNoTransition:
    def test_never_allowed_reports_no_transition(self):
        samples = _samples((0, OutcomeClass.DENIED_EXPLICIT), (_S, OutcomeClass.DENIED_EXPLICIT))
        measurement = compute_revocation_window(
            samples,
            identity_id="agent-b",
            capability_id="objectstore.read",
            mutation_kind=MutationKind.ATTACH_INLINE_DENY,
            mutation_sent_ns=0,
            poll_interval_ms=500,
            mutation_receipt_confirmed=True,
        )
        assert measurement.transition_observed is False
        assert measurement.transition_window is None

    def test_never_denied_after_allow_reports_no_transition(self):
        samples = _samples((0, OutcomeClass.ALLOWED), (_S, OutcomeClass.ALLOWED))
        measurement = compute_revocation_window(
            samples,
            identity_id="agent-b",
            capability_id="objectstore.read",
            mutation_kind=MutationKind.ATTACH_INLINE_DENY,
            mutation_sent_ns=0,
            poll_interval_ms=500,
            mutation_receipt_confirmed=True,
        )
        assert measurement.transition_observed is False
        assert "NO_TRANSITION_OBSERVED_WITHIN_WINDOW" in measurement.notes

    def test_no_samples_at_all(self):
        measurement = compute_revocation_window(
            [],
            identity_id="agent-b",
            capability_id="objectstore.read",
            mutation_kind=MutationKind.ATTACH_INLINE_DENY,
            mutation_sent_ns=0,
            poll_interval_ms=500,
            mutation_receipt_confirmed=True,
        )
        assert measurement.transition_observed is False
        assert measurement.poll_count == 0
        assert measurement.window_length_s == 0.0


class TestNonMonotonicTransition:
    def test_oscillation_preserved_not_smoothed(self):
        samples = _samples(
            (0, OutcomeClass.ALLOWED),
            (1 * _S, OutcomeClass.DENIED_EXPLICIT),
            (2 * _S, OutcomeClass.ALLOWED),  # flips back -- must not be hidden
            (3 * _S, OutcomeClass.DENIED_EXPLICIT),
        )
        measurement = compute_revocation_window(
            samples,
            identity_id="agent-b",
            capability_id="objectstore.read",
            mutation_kind=MutationKind.ATTACH_INLINE_DENY,
            mutation_sent_ns=0,
            poll_interval_ms=1000,
            mutation_receipt_confirmed=True,
        )
        assert measurement.transition_observed is True
        assert measurement.non_monotonic is True
        assert "NON_MONOTONIC_TRANSITION" in measurement.notes

    def test_clean_transition_is_not_flagged_non_monotonic(self):
        samples = _samples((0, OutcomeClass.ALLOWED), (1 * _S, OutcomeClass.DENIED_EXPLICIT))
        measurement = compute_revocation_window(
            samples,
            identity_id="agent-b",
            capability_id="objectstore.read",
            mutation_kind=MutationKind.ATTACH_INLINE_DENY,
            mutation_sent_ns=0,
            poll_interval_ms=1000,
            mutation_receipt_confirmed=True,
        )
        assert measurement.non_monotonic is False
        assert measurement.notes == ()


def test_poll_count_and_window_length_recorded():
    samples = _samples((0, OutcomeClass.ALLOWED), (5 * _S, OutcomeClass.DENIED_EXPLICIT))
    measurement = compute_revocation_window(
        samples,
        identity_id="agent-b",
        capability_id="objectstore.read",
        mutation_kind=MutationKind.ATTACH_INLINE_DENY,
        mutation_sent_ns=0,
        poll_interval_ms=1000,
        mutation_receipt_confirmed=True,
    )
    assert measurement.poll_count == 2
    assert measurement.window_length_s == pytest.approx(5.0)


def test_unconfirmed_receipt_is_recorded_verbatim():
    samples = _samples((0, OutcomeClass.ALLOWED), (_S, OutcomeClass.DENIED_EXPLICIT))
    measurement = compute_revocation_window(
        samples,
        identity_id="agent-b",
        capability_id="objectstore.read",
        mutation_kind=MutationKind.ATTACH_INLINE_DENY,
        mutation_sent_ns=0,
        poll_interval_ms=1000,
        mutation_receipt_confirmed=False,
    )
    assert measurement.mutation_receipt_confirmed is False
