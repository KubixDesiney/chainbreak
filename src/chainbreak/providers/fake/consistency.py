"""The injectable consistency model (F4): how long a mutation takes to become
visible to a probe, against the virtual clock in ``clock.py``.

Three regimes, selected per mutation via ``propagation_delay_ms``/``jitter_ms``/
``oscillate``:

* **Immediate** (all zero, the default): a mutation is visible to any probe
  issued after it, with no transition period at all -- the ``deterministic``
  profile.
* **Delayed**: visible only once ``propagation_delay_ms`` (+/- a seeded
  jitter) has elapsed on the virtual clock -- the ``eventual`` profile.
* **Oscillating**: after the nominal delay, visibility flips a fixed number
  of times across a settling window before landing on its final state --
  this is what lets a poller (M12) observe a genuine
  ``NON_MONOTONIC_TRANSITION`` against a *known* answer, rather than having
  to trust that AWS itself is behaving non-monotonically on any given test
  run.

Every random draw here comes from a ``random.Random`` seeded once at
construction, never from the module-global RNG or the system clock -- this is
what makes F6 ("same seed => identical run") possible.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class MutationVisibility:
    """When one applied mutation becomes visible, and how it behaves in
    between, expressed purely in virtual-clock milliseconds."""

    applied_at_ms: int
    settle_at_ms: int
    oscillation_flips_ms: tuple[int, ...] = ()

    def is_visible(self, query_at_ms: int) -> bool:
        """Whether the mutation's effect is visible at ``query_at_ms``.

        Below ``applied_at_ms`` the mutation has not happened yet: never
        visible. Between ``applied_at_ms`` and ``settle_at_ms``, with
        oscillation flips scheduled in between, visibility alternates at each
        scheduled flip point. From ``settle_at_ms`` onward it is
        unconditionally visible.
        """
        if query_at_ms < self.applied_at_ms:
            return False
        if query_at_ms >= self.settle_at_ms:
            return True
        visible = False
        for flip_ms in self.oscillation_flips_ms:
            if query_at_ms < flip_ms:
                break
            visible = not visible
        return visible


@dataclass
class ConsistencyModel:
    """Configuration for how mutations propagate, plus the seeded RNG that
    makes jitter and oscillation deterministic per run."""

    propagation_delay_ms: int = 0
    jitter_ms: int = 0
    oscillate: bool = False
    oscillation_flip_count: int = 3
    seed: int = 0
    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        # Deterministic simulation input, not a security control (F6 requires
        # reproducibility from a seed, which rules out `secrets`) -- nosec/noqa.
        self._rng = random.Random(self.seed)  # noqa: S311  # nosec B311

    def schedule(self, applied_at_ms: int) -> MutationVisibility:
        jitter = self._rng.randint(-self.jitter_ms, self.jitter_ms) if self.jitter_ms else 0
        settle_at_ms = applied_at_ms + max(0, self.propagation_delay_ms + jitter)

        flips: tuple[int, ...] = ()
        if self.oscillate and settle_at_ms > applied_at_ms:
            span = settle_at_ms - applied_at_ms
            flips = tuple(
                sorted(
                    applied_at_ms + self._rng.randint(1, max(1, span - 1))
                    for _ in range(self.oscillation_flip_count)
                )
            )
        return MutationVisibility(
            applied_at_ms=applied_at_ms, settle_at_ms=settle_at_ms, oscillation_flips_ms=flips
        )
