"""A virtual clock the fake provider advances explicitly.

No component under test ever sleeps in wall-clock time: a 120s deferral
scenario runs instantly against this clock instead (M5's own non-functional
requirement). ``VirtualClock`` is also what makes the fake fully seeded and
reproducible (F6) -- unlike ``core.clock.RunClock`` (real monotonic time, for
the actual run deadline) or ``core.ids.new_ulid`` (real wall time, for
evidence identifiers), nothing here reads the system clock.
"""

from __future__ import annotations


class VirtualClock:
    """Milliseconds since an arbitrary epoch, advanced only by explicit calls."""

    def __init__(self, start_ms: int = 0) -> None:
        self._now_ms = start_ms

    @property
    def now_ms(self) -> int:
        return self._now_ms

    def advance(self, milliseconds: int) -> None:
        if milliseconds < 0:
            raise ValueError("cannot advance a virtual clock backwards")
        self._now_ms += milliseconds
