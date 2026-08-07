"""providers/fake/consistency.py -- F4's injectable consistency model, and the
negative controls M05-fake-provider.md names directly: ``propagation_delay_ms
= 2000`` produces a transition window containing 2000ms, and oscillation
produces a genuinely non-monotonic visibility sequence rather than a single
clean flip.
"""

from __future__ import annotations

import pytest

from chainbreak.providers.fake.clock import VirtualClock
from chainbreak.providers.fake.consistency import ConsistencyModel

pytestmark = pytest.mark.unit


class TestImmediateVisibility:
    def test_zero_delay_is_visible_at_the_moment_applied(self):
        model = ConsistencyModel()
        visibility = model.schedule(applied_at_ms=1000)
        assert visibility.is_visible(1000) is True

    def test_never_visible_before_it_was_applied(self):
        model = ConsistencyModel(propagation_delay_ms=0)
        visibility = model.schedule(applied_at_ms=1000)
        assert visibility.is_visible(999) is False


class TestPropagationDelay:
    def test_not_visible_before_the_delay_elapses(self):
        model = ConsistencyModel(propagation_delay_ms=2000, seed=1)
        visibility = model.schedule(applied_at_ms=0)
        assert visibility.is_visible(1999) is False

    def test_visible_once_the_delay_elapses(self):
        model = ConsistencyModel(propagation_delay_ms=2000, seed=1)
        visibility = model.schedule(applied_at_ms=0)
        assert visibility.is_visible(2000) is True

    def test_transition_window_contains_2000ms(self):
        """The milestone's own negative control, verified at the level that
        actually exists at M5 (the fake's own mechanism) rather than via a
        full scenario -> analysis pipeline that does not exist until M7/M12:
        the interval between "not yet visible" and "visible" must contain
        exactly the configured 2000ms delay."""
        model = ConsistencyModel(propagation_delay_ms=2000, seed=1)
        applied_at_ms = 500
        visibility = model.schedule(applied_at_ms=applied_at_ms)
        transition_ms = visibility.settle_at_ms - applied_at_ms
        assert transition_ms == 2000

    def test_jitter_keeps_the_transition_within_bounds(self):
        model = ConsistencyModel(propagation_delay_ms=2000, jitter_ms=250, seed=1)
        for applied_at_ms in range(0, 5000, 500):
            visibility = model.schedule(applied_at_ms=applied_at_ms)
            transition_ms = visibility.settle_at_ms - applied_at_ms
            assert 1750 <= transition_ms <= 2250


class TestOscillation:
    def test_oscillation_produces_flip_points(self):
        model = ConsistencyModel(
            propagation_delay_ms=2000, oscillate=True, oscillation_flip_count=3, seed=1
        )
        visibility = model.schedule(applied_at_ms=0)
        assert len(visibility.oscillation_flips_ms) == 3

    def test_oscillation_is_genuinely_non_monotonic(self):
        """Sampling visibility across the window must show at least one
        False *after* a True -- otherwise it is just a slow single flip, not
        oscillation, and a future poller (M12) would have nothing to catch."""
        model = ConsistencyModel(
            propagation_delay_ms=2000, oscillate=True, oscillation_flip_count=3, seed=3
        )
        visibility = model.schedule(applied_at_ms=0)
        samples = [visibility.is_visible(ms) for ms in range(0, 2001, 50)]
        seen_true = False
        went_false_after_true = False
        for sample in samples:
            if sample:
                seen_true = True
            elif seen_true:
                went_false_after_true = True
        assert went_false_after_true

    def test_settles_unconditionally_after_the_window(self):
        model = ConsistencyModel(
            propagation_delay_ms=2000, oscillate=True, oscillation_flip_count=5, seed=1
        )
        visibility = model.schedule(applied_at_ms=0)
        assert visibility.is_visible(2000) is True
        assert visibility.is_visible(999_999) is True

    def test_no_oscillation_flips_when_disabled(self):
        model = ConsistencyModel(propagation_delay_ms=2000, oscillate=False, seed=1)
        visibility = model.schedule(applied_at_ms=0)
        assert visibility.oscillation_flips_ms == ()


class TestDeterminism:
    def test_same_seed_produces_the_same_schedule(self):
        a = ConsistencyModel(propagation_delay_ms=2000, jitter_ms=500, oscillate=True, seed=42)
        b = ConsistencyModel(propagation_delay_ms=2000, jitter_ms=500, oscillate=True, seed=42)
        visibility_a = a.schedule(applied_at_ms=1000)
        visibility_b = b.schedule(applied_at_ms=1000)
        assert visibility_a == visibility_b

    def test_different_seeds_produce_different_jitter(self):
        a = ConsistencyModel(propagation_delay_ms=2000, jitter_ms=500, seed=1)
        b = ConsistencyModel(propagation_delay_ms=2000, jitter_ms=500, seed=2)
        settled = {
            a.schedule(applied_at_ms=0).settle_at_ms,
            b.schedule(applied_at_ms=0).settle_at_ms,
        }
        assert len(settled) == 2


class TestVirtualClock:
    def test_starts_at_zero_by_default(self):
        clock = VirtualClock()
        assert clock.now_ms == 0

    def test_advance_moves_forward(self):
        clock = VirtualClock()
        clock.advance(500)
        assert clock.now_ms == 500
        clock.advance(500)
        assert clock.now_ms == 1000

    def test_cannot_advance_backwards(self):
        clock = VirtualClock()
        with pytest.raises(ValueError, match="backwards"):
            clock.advance(-1)
