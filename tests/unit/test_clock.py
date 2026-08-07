"""core/clock.py -- RunClock (SI-7) and the clock-offset estimator interface.

All timing is driven by an injected ``now_ns`` callable so nothing here
sleeps or depends on wall-clock speed.
"""

from __future__ import annotations

import pytest

from chainbreak.core.clock import NANOSECONDS_PER_SECOND, RunClock, no_offset_estimator
from chainbreak.core.errors import RunDurationExceededError

pytestmark = pytest.mark.unit


class _FakeClock:
    """A controllable monotonic source: advance() moves it forward explicitly."""

    def __init__(self, start_ns: int = 0) -> None:
        self._now_ns = start_ns

    def advance(self, seconds: float) -> None:
        self._now_ns += int(seconds * NANOSECONDS_PER_SECOND)

    def __call__(self) -> int:
        return self._now_ns


class TestRunClockBeforeDeadline:
    def test_check_does_not_raise(self):
        fake = _FakeClock()
        clock = RunClock(60, now_ns=fake)
        fake.advance(30)
        clock.check()  # must not raise

    def test_elapsed_seconds(self):
        fake = _FakeClock()
        clock = RunClock(60, now_ns=fake)
        fake.advance(12.5)
        assert clock.elapsed_seconds == pytest.approx(12.5)

    def test_remaining_seconds(self):
        fake = _FakeClock()
        clock = RunClock(60, now_ns=fake)
        fake.advance(20)
        assert clock.remaining_seconds == pytest.approx(40.0)

    def test_not_expired(self):
        fake = _FakeClock()
        clock = RunClock(60, now_ns=fake)
        fake.advance(59)
        assert clock.expired is False


class TestRunClockAtOrPastDeadline:
    def test_check_raises_run_duration_exceeded(self):
        fake = _FakeClock()
        clock = RunClock(10, now_ns=fake)
        fake.advance(10)
        with pytest.raises(RunDurationExceededError):
            clock.check()

    def test_check_raises_past_deadline(self):
        fake = _FakeClock()
        clock = RunClock(10, now_ns=fake)
        fake.advance(999)
        with pytest.raises(RunDurationExceededError):
            clock.check()

    def test_error_carries_context(self):
        fake = _FakeClock()
        clock = RunClock(10, now_ns=fake)
        fake.advance(15)
        with pytest.raises(RunDurationExceededError) as excinfo:
            clock.check()
        assert excinfo.value.context["max_duration_seconds"] == 10
        assert excinfo.value.context["elapsed_seconds"] == pytest.approx(15.0)

    def test_expired_true(self):
        fake = _FakeClock()
        clock = RunClock(10, now_ns=fake)
        fake.advance(10)
        assert clock.expired is True

    def test_remaining_seconds_floors_at_zero(self):
        fake = _FakeClock()
        clock = RunClock(10, now_ns=fake)
        fake.advance(999)
        assert clock.remaining_seconds == 0.0


class TestRunClockDefaultsToRealMonotonicClock:
    def test_construction_without_explicit_now_ns_does_not_raise(self):
        # Exercises the real time.monotonic_ns default; deadline is generous
        # so this cannot flake.
        clock = RunClock(3600)
        assert clock.elapsed_seconds >= 0.0
        assert clock.expired is False


class TestNoOffsetEstimator:
    def test_returns_zero(self):
        assert no_offset_estimator() == 0.0

    def test_is_unmeasured_not_verified(self):
        # Documented distinction (core/clock.py docstring): 0.0 here means
        # "no provider configured to measure with", not "offset confirmed
        # zero". There is no separate signal for that today; this test
        # exists so a future change to the return type is deliberate.
        offset = no_offset_estimator()
        assert isinstance(offset, float)
