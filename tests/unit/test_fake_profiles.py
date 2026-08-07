"""providers/fake/profiles.py -- F8's three named configurations."""

from __future__ import annotations

import pytest

from chainbreak.providers.fake.profiles import (
    deterministic_profile,
    eventual_profile,
    hostile_profile,
)

pytestmark = pytest.mark.unit


class TestDeterministicProfile:
    def test_no_delay_no_faults(self):
        adapter = deterministic_profile(seed=1)
        assert adapter.propagation_delay_ms == 0
        assert adapter.transient_error_rate == 0.0
        assert adapter.oscillate is False


class TestEventualProfile:
    def test_two_second_propagation_with_jitter(self):
        adapter = eventual_profile(seed=1)
        assert adapter.propagation_delay_ms == 2000
        assert adapter.jitter_ms > 0


class TestHostileProfile:
    def test_faults_skew_and_oscillation_all_present(self):
        adapter = hostile_profile(seed=1)
        assert adapter.propagation_delay_ms > 0
        assert adapter.oscillate is True
        assert adapter.transient_error_rate > 0.0
        assert adapter.clock_skew_ms > 0.0


class TestProfilesAreSeeded:
    def test_same_seed_across_profile_calls_is_reproducible(self):
        a = deterministic_profile(seed=7)
        b = deterministic_profile(seed=7)
        assert a.seed == b.seed == 7
