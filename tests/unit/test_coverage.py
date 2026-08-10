"""``scoring/coverage.py`` direct branch coverage (M15 F2/F3)."""

from __future__ import annotations

import pytest

from chainbreak.scoring.coverage import PARTIAL_COVERAGE_THRESHOLD, coverage_ratio, is_exercised

pytestmark = pytest.mark.unit


class TestCoverageRatio:
    def test_zero_applicable_returns_zero_without_raising(self):
        assert coverage_ratio(measured=0, applicable=0) == 0.0

    def test_negative_applicable_returns_zero(self):
        # Callers are expected to have already routed a non-applicable
        # category to NOT_MEASURED via is_exercised(); this just guards
        # against a division by a non-positive denominator.
        assert coverage_ratio(measured=0, applicable=-1) == 0.0

    @pytest.mark.parametrize(
        ("measured", "applicable", "expected"),
        [(1, 1, 1.0), (3, 5, 0.6), (0, 4, 0.0), (7, 10, 0.7)],
    )
    def test_ratio(self, measured, applicable, expected):
        assert coverage_ratio(measured=measured, applicable=applicable) == pytest.approx(expected)

    def test_measured_exceeding_applicable_raises(self):
        with pytest.raises(ValueError, match="out of range"):
            coverage_ratio(measured=3, applicable=2)

    def test_negative_measured_raises(self):
        with pytest.raises(ValueError, match="out of range"):
            coverage_ratio(measured=-1, applicable=5)


class TestIsExercised:
    def test_zero_applicable_is_not_exercised(self):
        assert is_exercised(applicable=0, measured=0) is False

    def test_applicable_but_zero_measured_is_not_exercised(self):
        """A category the scenario declared but never actually measured a
        single cell of (e.g. the run aborted before the first poll) is not
        'not exercised by the scenario' the way zero applicable cells is --
        but it is also not something F2's NOT_MEASURED gate should treat as
        exercised. Both fall out of the same predicate: at least one
        applicable cell AND at least one measured cell."""
        assert is_exercised(applicable=3, measured=0) is False

    def test_both_positive_is_exercised(self):
        assert is_exercised(applicable=3, measured=1) is True

    def test_partial_threshold_matches_documented_value(self):
        assert PARTIAL_COVERAGE_THRESHOLD == 0.7
