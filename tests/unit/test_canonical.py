"""core/canonical.py -- canonical JSON serialization.

Acceptance criterion 5: canonical JSON round-trips identically across two
processes (not just two calls in the same process, which would not catch a
dependency on hash-seed-dependent ordering).
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone

import pytest

from chainbreak.core.canonical import dumps, format_datetime
from chainbreak.core.enums import PlanPhase
from chainbreak.core.models import AuthoritySet, ExpectedAuthority

pytestmark = pytest.mark.unit


class TestDumps:
    def test_sorted_keys(self):
        assert dumps({"b": 1, "a": 2.0}) == '{"a":2.0,"b":1}'

    def test_fixed_float_formatting(self):
        assert dumps({"x": 2.0}) == '{"x":2.0}'
        assert dumps({"x": 2.5}) == '{"x":2.5}'

    def test_nested_dict_keys_sorted_too(self):
        assert dumps({"outer": {"z": 1, "a": 2}}) == '{"outer":{"a":2,"z":1}}'

    def test_list_order_preserved(self):
        """Lists are ordered data, not sets -- their order is meaningful and untouched."""
        assert dumps({"items": [3, 1, 2]}) == '{"items":[3,1,2]}'

    def test_frozenset_renders_as_sorted_list(self):
        assert dumps({"s": frozenset({"b", "a", "c"})}) == '{"s":["a","b","c"]}'

    def test_authority_set_renders_as_its_own_sorted_list(self):
        authority = AuthoritySet.of("b.read", "a.write")
        assert dumps(authority) == '["a.write","b.read"]'

    def test_authority_set_nested_in_model_renders_correctly(self):
        """Regression: model_dump(mode='python') would flatten AuthoritySet into
        {"capabilities": [...]}, double-nesting the field. A shallow, per-level
        extraction must produce the plain sorted list at the field's own key."""
        authority = ExpectedAuthority(
            capabilities=AuthoritySet.of("b.read", "a.write"),
            phase=PlanPhase.POST_DELEGATION,
            derivation="DECLARED",
        )
        result = dumps(authority)
        assert result == (
            '{"capabilities":["a.write","b.read"],"derivation":"DECLARED",'
            '"phase":"POST_DELEGATION"}'
        )

    def test_datetime_formats_as_utc_iso8601_with_microseconds(self):
        ts = datetime(2026, 8, 7, 13, 0, 0, 123456, tzinfo=UTC)
        assert dumps({"t": ts}) == '{"t":"2026-08-07T13:00:00.123456Z"}'

    def test_datetime_without_microseconds_still_shows_six_digits(self):
        ts = datetime(2026, 8, 7, 13, 0, 0, tzinfo=UTC)
        assert dumps({"t": ts}) == '{"t":"2026-08-07T13:00:00.000000Z"}'

    def test_non_utc_timezone_converted_to_utc(self):
        plus_two = timezone(timedelta(hours=2))
        ts = datetime(2026, 8, 7, 15, 0, 0, tzinfo=plus_two)
        assert dumps({"t": ts}) == '{"t":"2026-08-07T13:00:00.000000Z"}'

    def test_naive_datetime_rejected(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            dumps({"t": datetime(2026, 8, 7)})  # noqa: DTZ001 -- exercising the rejection path

    def test_unserializable_type_raises_type_error(self):
        with pytest.raises(TypeError, match="not canonically serializable"):
            dumps({"x": object()})

    def test_two_calls_in_same_process_are_identical(self):
        payload = {"z": 1, "a": [3, 1, 2], "m": 2.5, "s": frozenset({"y", "x"})}
        assert dumps(payload) == dumps(payload)


class TestFormatDatetime:
    def test_rejects_naive(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            format_datetime(datetime(2026, 8, 7))  # noqa: DTZ001 -- exercising the rejection path


class TestCrossProcessDeterminism:
    def test_identical_output_across_two_separate_processes(self):
        """The M1 spec's own verification command, run twice as two independent
        interpreters -- guards against anything depending on PYTHONHASHSEED or
        per-process dict/set iteration order."""
        code = (
            "from chainbreak.core.canonical import dumps; "
            "print(dumps({'b': 1, 'a': 2.0, 's': frozenset({'y', 'x', 'z'})}))"
        )
        results = {
            subprocess.run(
                [sys.executable, "-c", code], capture_output=True, text=True, check=True
            ).stdout
            for _ in range(2)
        }
        assert len(results) == 1
