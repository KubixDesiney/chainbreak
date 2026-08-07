"""Monotonic run clock (SI-7): deadline enforcement and the clock-offset
estimation interface.

All interval arithmetic uses ``time.monotonic_ns()``, never wall-clock
subtraction -- the same convention ``core/models.py``'s ``ProbeTiming``
already follows. Wall-clock time is context only.

Wiring this into an actual run orchestrator (checking the deadline at every
phase boundary and poll iteration) is M5+'s job; execution does not exist
yet and is explicitly out of scope for this milestone. What is in scope is
the clock abstraction itself, injectable so it can be tested without
sleeping.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from chainbreak.core.errors import RunDurationExceededError

NANOSECONDS_PER_SECOND = 1_000_000_000

#: Real offset estimation needs a live provider session to compare local time
#: against a provider-reported timestamp; that arrives with the AWS adapter
#: (M8). This is the interface a provider adapter will implement: given
#: nothing, return the estimated clock offset in milliseconds.
ClockOffsetEstimator = Callable[[], float]


def no_offset_estimator() -> float:
    """The default estimator: no provider is configured, so no offset can be
    measured. Returns 0.0 -- an *unmeasured* offset, not a *verified* one."""
    return 0.0


class RunClock:
    """A monotonic deadline, armed at construction."""

    def __init__(
        self,
        max_duration_seconds: int,
        *,
        now_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self._now_ns = now_ns
        self._max_duration_seconds = max_duration_seconds
        self._start_ns = now_ns()
        self._deadline_ns = self._start_ns + max_duration_seconds * NANOSECONDS_PER_SECOND

    def check(self) -> None:
        """Raise if the deadline has passed. Call at every phase boundary and
        poll iteration once a run orchestrator exists to call it from."""
        if self._now_ns() >= self._deadline_ns:
            raise RunDurationExceededError(
                f"run exceeded its {self._max_duration_seconds}s deadline",
                max_duration_seconds=self._max_duration_seconds,
                elapsed_seconds=self.elapsed_seconds,
            )

    @property
    def elapsed_seconds(self) -> float:
        return (self._now_ns() - self._start_ns) / NANOSECONDS_PER_SECOND

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, (self._deadline_ns - self._now_ns()) / NANOSECONDS_PER_SECOND)

    @property
    def expired(self) -> bool:
        return self._now_ns() >= self._deadline_ns
