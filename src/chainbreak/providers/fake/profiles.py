"""F8: three named fake configurations, so a scenario or test can ask for
"the hostile one" rather than hand-assembling fault parameters.
"""

from __future__ import annotations

from chainbreak.providers.fake.adapter import FakeProviderAdapter


def deterministic_profile(seed: int = 0) -> FakeProviderAdapter:
    """No faults, no propagation delay. The default profile: every mutation
    is visible to the very next probe."""
    return FakeProviderAdapter(seed=seed)


def eventual_profile(seed: int = 0) -> FakeProviderAdapter:
    """A 2 s propagation delay with jitter -- makes the revocation family's
    transition-window logic exercisable without AWS."""
    return FakeProviderAdapter(seed=seed, propagation_delay_ms=2000, jitter_ms=250)


def hostile_profile(seed: int = 0) -> FakeProviderAdapter:
    """Faults, clock skew and oscillation together: propagation delay with
    jitter, a 5% transient error rate, 250ms of clock skew, and a mutation
    that oscillates before settling."""
    return FakeProviderAdapter(
        seed=seed,
        propagation_delay_ms=2000,
        jitter_ms=250,
        oscillate=True,
        transient_error_rate=0.05,
        clock_skew_ms=250.0,
    )
