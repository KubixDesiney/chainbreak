"""``scoring/aggregate.py`` direct tests (M15 F7/F8)."""

from __future__ import annotations

import pytest

from chainbreak.core.enums import CategoryStatus, Confidence, ScoringCategory
from chainbreak.core.errors import HeterogeneousComparisonError
from chainbreak.core.models import CategoryResult, Interval, Measurement
from chainbreak.scoring.aggregate import (
    MIN_N_FOR_DISPERSION,
    RunScoreSet,
    aggregate_runs,
)

pytestmark = pytest.mark.unit


def _measurement(metric: str, point: float, *, unit: str = "s") -> Measurement:
    return Measurement(
        metric=metric,
        value=Interval(low=point, point=point, high=point, unit=unit),
        confidence=Confidence.HIGH,
        n=1,
    )


def _category_result(
    category: ScoringCategory,
    *,
    status: CategoryStatus = CategoryStatus.CONSISTENT,
    coverage: float = 1.0,
    measurements: tuple[Measurement, ...] = (),
) -> CategoryResult:
    return CategoryResult(
        category=category,
        status=status,
        measurements=measurements,
        coverage=coverage,
        confidence=Confidence.HIGH,
    )


def _run_score_set(
    run_id: str,
    *,
    compiled_hash: str = "sha256:" + "a" * 64,
    adapter_version: str = "0.1.0",
    catalog_version: str = "1.0.0",
    revocation_status: CategoryStatus = CategoryStatus.CONSISTENT,
    revocation_measurement_point: float | None = None,
) -> RunScoreSet:
    revocation_measurements = ()
    if revocation_measurement_point is not None:
        revocation_measurements = (_measurement("revocation_window", revocation_measurement_point),)
    categories = tuple(
        _category_result(
            category,
            status=revocation_status
            if category is ScoringCategory.REVOCATION_RESPONSIVENESS
            else CategoryStatus.CONSISTENT,
            measurements=(
                revocation_measurements
                if category is ScoringCategory.REVOCATION_RESPONSIVENESS
                else ()
            ),
        )
        for category in ScoringCategory
    )
    return RunScoreSet(
        run_id=run_id,
        compiled_hash=compiled_hash,
        adapter_version=adapter_version,
        catalog_version=catalog_version,
        categories=categories,
    )


class TestHomogeneousAggregation:
    def test_matching_runs_aggregate_without_error(self):
        runs = [_run_score_set(f"run-{i}", revocation_measurement_point=10.0 + i) for i in range(3)]
        report = aggregate_runs(runs)
        assert report.n_runs == 3
        assert report.heterogeneous is False

    def test_n_included_and_excluded_are_both_reported(self):
        runs = [
            _run_score_set("run-a", revocation_measurement_point=10.0),
            _run_score_set("run-b", revocation_status=CategoryStatus.NOT_MEASURED),
        ]
        report = aggregate_runs(runs)
        revocation = next(
            c for c in report.categories if c.category is ScoringCategory.REVOCATION_RESPONSIVENESS
        )
        assert revocation.n_included == 1
        assert revocation.excluded == (("run-b", "NOT_MEASURED"),)

    def test_median_min_max_computed_over_included_runs_only(self):
        runs = [
            _run_score_set(f"run-{i}", revocation_measurement_point=point)
            for i, point in enumerate([10.0, 20.0, 30.0])
        ]
        report = aggregate_runs(runs)
        revocation = next(
            c for c in report.categories if c.category is ScoringCategory.REVOCATION_RESPONSIVENESS
        )
        measurement = revocation.measurements[0]
        assert measurement.n == 3
        assert measurement.median == pytest.approx(20.0)
        assert measurement.low == pytest.approx(10.0)
        assert measurement.high == pytest.approx(30.0)

    def test_no_dispersion_below_n5(self):
        runs = [
            _run_score_set(f"run-{i}", revocation_measurement_point=float(i))
            for i in range(MIN_N_FOR_DISPERSION - 1)
        ]
        report = aggregate_runs(runs)
        revocation = next(
            c for c in report.categories if c.category is ScoringCategory.REVOCATION_RESPONSIVENESS
        )
        measurement = revocation.measurements[0]
        assert measurement.n == MIN_N_FOR_DISPERSION - 1
        assert measurement.iqr is None

    def test_dispersion_reported_at_n5(self):
        runs = [
            _run_score_set(f"run-{i}", revocation_measurement_point=float(i))
            for i in range(MIN_N_FOR_DISPERSION)
        ]
        report = aggregate_runs(runs)
        revocation = next(
            c for c in report.categories if c.category is ScoringCategory.REVOCATION_RESPONSIVENESS
        )
        measurement = revocation.measurements[0]
        assert measurement.n == MIN_N_FOR_DISPERSION
        assert measurement.iqr is not None

    def test_categories_with_no_measurements_report_zero_length_measurements(self):
        runs = [_run_score_set("run-a")]
        report = aggregate_runs(runs)
        delegation = next(
            c for c in report.categories if c.category is ScoringCategory.DELEGATION_INTEGRITY
        )
        assert delegation.measurements == ()


class TestHeterogeneousRefusal:
    def test_differing_compiled_hash_refused_by_default(self):
        homogeneous = _run_score_set("run-a")
        different = _run_score_set("run-b", compiled_hash="sha256:" + "b" * 64)
        with pytest.raises(HeterogeneousComparisonError):
            aggregate_runs([homogeneous, different])

    def test_differing_adapter_version_refused_by_default(self):
        homogeneous = _run_score_set("run-a")
        different = _run_score_set("run-b", adapter_version="9.9.9")
        with pytest.raises(HeterogeneousComparisonError):
            aggregate_runs([homogeneous, different])

    def test_differing_catalog_version_refused_by_default(self):
        homogeneous = _run_score_set("run-a")
        different = _run_score_set("run-b", catalog_version="9.9.9")
        with pytest.raises(HeterogeneousComparisonError):
            aggregate_runs([homogeneous, different])

    def test_allow_heterogeneous_lets_it_through_and_marks_the_result(self):
        homogeneous = _run_score_set("run-a")
        different = _run_score_set("run-b", compiled_hash="sha256:" + "b" * 64)
        report = aggregate_runs([homogeneous, different], allow_heterogeneous=True)
        assert report.n_runs == 2
        assert report.heterogeneous is True

    def test_error_names_every_mismatched_run(self):
        homogeneous = _run_score_set("run-a")
        different_one = _run_score_set("run-b", compiled_hash="sha256:" + "b" * 64)
        different_two = _run_score_set("run-c", compiled_hash="sha256:" + "c" * 64)
        with pytest.raises(HeterogeneousComparisonError) as excinfo:
            aggregate_runs([homogeneous, different_one, different_two])
        assert excinfo.value.context["heterogeneous_run_ids"] == ("run-b", "run-c")

    def test_no_runs_raises_value_error(self):
        with pytest.raises(ValueError, match="no runs supplied"):
            aggregate_runs([])
