"""core/ids.py -- identifier generation and hashing helpers.

Not part of M1's own scope, but M1's coverage acceptance criterion
(``core/`` >= 95%, TESTING.md) is a hard bar on the whole package, and several
of this module's ID constructors and the ULID clock-backwards branch had no
dedicated test before now.
"""

from __future__ import annotations

import re
import time

import pytest

from chainbreak.core.ids import (
    digest_ref,
    fingerprint_json,
    is_ulid,
    new_credential_id,
    new_event_id,
    new_finding_id,
    new_observation_id,
    new_run_id,
    new_ulid,
    run_salt,
)

pytestmark = pytest.mark.unit


class TestPrefixedIdConstructors:
    def test_run_id_is_a_bare_ulid(self):
        assert is_ulid(new_run_id())

    def test_observation_id_prefix(self):
        value = new_observation_id()
        assert value.startswith("obs_")
        assert is_ulid(value.removeprefix("obs_"))

    def test_event_id_prefix(self):
        value = new_event_id()
        assert value.startswith("ev_")
        assert is_ulid(value.removeprefix("ev_"))

    def test_finding_id_prefix(self):
        value = new_finding_id()
        assert value.startswith("fnd_")
        assert is_ulid(value.removeprefix("fnd_"))

    def test_credential_id_prefix(self):
        value = new_credential_id()
        assert value.startswith("cred_")
        assert is_ulid(value.removeprefix("cred_"))


class TestHashingHelpers:
    def test_digest_ref_format(self):
        assert digest_ref("arn:aws:iam::123456789012:role/x", "salt").startswith("sha256:")

    def test_digest_ref_is_salted(self):
        assert digest_ref("value", "salt-a") != digest_ref("value", "salt-b")

    def test_fingerprint_json_format(self):
        assert fingerprint_json('{"a":1}').startswith("sha256:")

    def test_fingerprint_json_deterministic(self):
        assert fingerprint_json('{"a":1}') == fingerprint_json('{"a":1}')

    def test_run_salt_embeds_run_id(self):
        run_id = new_run_id()
        assert run_id in run_salt(run_id)


class TestUlidMonotonicity:
    def test_is_ulid_rejects_garbage(self):
        assert is_ulid("not-a-ulid") is False
        assert is_ulid("") is False

    def test_is_ulid_accepts_generated_value(self):
        assert is_ulid(new_ulid()) is True

    def test_sequential_ulids_are_monotonically_increasing(self):
        values = [new_ulid() for _ in range(50)]
        assert values == sorted(values)

    def test_clock_stepping_backwards_stays_monotonic(self, monkeypatch: pytest.MonkeyPatch):
        """Simulated NTP step-back: the sequence must not regress (ids.py lines 77-81)."""
        real_time = time.time
        # Two calls: first at a normal time, second stepped backwards by an hour.
        times = iter([real_time(), real_time() - 3600])

        def fake_time() -> float:
            return next(times, real_time())

        monkeypatch.setattr(time, "time", fake_time)

        first = new_ulid()
        second = new_ulid()
        assert second > first


class TestPatterns:
    def test_capability_id_pattern_documented_examples(self):
        from chainbreak.core.ids import CAPABILITY_ID_PATTERN

        assert re.match(CAPABILITY_ID_PATTERN, "objectstore.read")
        assert not re.match(CAPABILITY_ID_PATTERN, "no-dot")
