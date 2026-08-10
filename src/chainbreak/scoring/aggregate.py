"""Cross-run aggregation (M15 F7/F8, SCORING_MODEL.md section 5,
RESEARCH_METHODOLOGY.md section 8): combine independent runs of the *same*
compiled scenario into one descriptive summary per category.

Two rules carried over directly from RESEARCH_METHODOLOGY.md section 8's
"deliberately conservative" statistical treatment, not reinvented here:

- **No mean without dispersion; no dispersion below n=5.** Median, IQR, min,
  max -- never a mean, and ``iqr`` is ``None`` below
  :data:`MIN_N_FOR_DISPERSION` rather than a fabricated spread over too few
  points.
- **Excluded runs are counted and reported, with reasons** -- a category
  that was ``NOT_MEASURED`` or ``DETECTOR_FAILED`` in a given run
  contributes no numeric point to that category's aggregate, but the run is
  still named in ``AggregatedCategory.excluded``, never silently dropped.

F7 is the other half: refusing to combine runs whose ``compiled_hash``,
``adapter_version`` or ``catalog_version`` differ, because a different
compiled scenario or a different provider adapter version is not a wider
sample of the same thing -- it is a different thing.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from chainbreak.core.enums import CategoryStatus, ScoringCategory
from chainbreak.core.errors import HeterogeneousComparisonError
from chainbreak.core.models import CategoryResult

__all__ = [
    "MIN_N_FOR_DISPERSION",
    "AggregatedCategory",
    "AggregatedMeasurement",
    "CrossRunAggregate",
    "RunScoreSet",
    "aggregate_runs",
    "score_set_from_bundle",
]

#: Category statuses that carry no numeric measurement to aggregate.
_UNMEASURED_STATUSES = frozenset({CategoryStatus.NOT_MEASURED, CategoryStatus.DETECTOR_FAILED})

#: F8: no dispersion measure below this sample size -- report the count instead.
MIN_N_FOR_DISPERSION = 5


@dataclass(frozen=True, slots=True)
class RunScoreSet:
    """One run's six category results, tagged with the three fields F7
    gates comparability on."""

    run_id: str
    compiled_hash: str
    adapter_version: str
    catalog_version: str
    categories: tuple[CategoryResult, ...]

    @property
    def version_key(self) -> tuple[str, str, str]:
        return (self.compiled_hash, self.adapter_version, self.catalog_version)


@dataclass(frozen=True, slots=True)
class AggregatedMeasurement:
    """n, median, IQR, min, max for one ``Measurement.metric`` within one
    category, computed over every included run's point estimate. ``iqr`` is
    ``None`` below :data:`MIN_N_FOR_DISPERSION` -- F8 forbids reporting a
    dispersion measure at small n, not just a mean without one."""

    metric: str
    unit: str
    n: int
    median: float
    low: float
    high: float
    iqr: tuple[float, float] | None


@dataclass(frozen=True, slots=True)
class AggregatedCategory:
    category: ScoringCategory
    n_included: int
    #: (run_id, exclusion reason) for every run whose result for this
    #: category was NOT_MEASURED or DETECTOR_FAILED -- counted, never dropped.
    excluded: tuple[tuple[str, str], ...]
    measurements: tuple[AggregatedMeasurement, ...]


@dataclass(frozen=True, slots=True)
class CrossRunAggregate:
    compiled_hash: str
    adapter_version: str
    catalog_version: str
    n_runs: int
    #: True only when ``allow_heterogeneous`` let mismatched runs through
    #: (S1: this can only ever be a downgrade signal for a reader, never a
    #: reason to trust the aggregate more).
    heterogeneous: bool
    categories: tuple[AggregatedCategory, ...]


def _quartiles(ordered: Sequence[float]) -> tuple[float, float]:
    q1, _, q3 = statistics.quantiles(ordered, n=4)
    return (q1, q3)


def _aggregate_metric(metric: str, unit: str, points: Sequence[float]) -> AggregatedMeasurement:
    ordered = sorted(points)
    n = len(ordered)
    iqr = _quartiles(ordered) if n >= MIN_N_FOR_DISPERSION else None
    return AggregatedMeasurement(
        metric=metric,
        unit=unit,
        n=n,
        median=statistics.median(ordered),
        low=ordered[0],
        high=ordered[-1],
        iqr=iqr,
    )


def _aggregate_category(
    category: ScoringCategory, results_by_run: Sequence[tuple[str, CategoryResult]]
) -> AggregatedCategory:
    excluded: list[tuple[str, str]] = []
    included: list[CategoryResult] = []
    for run_id, result in results_by_run:
        if result.status in _UNMEASURED_STATUSES:
            excluded.append((run_id, result.status.value))
        else:
            included.append(result)

    points_by_metric: dict[tuple[str, str], list[float]] = {}
    for result in included:
        for measurement in result.measurements:
            key = (measurement.metric, measurement.value.unit)
            points_by_metric.setdefault(key, []).append(measurement.value.point)

    measurements = tuple(
        _aggregate_metric(metric, unit, points)
        for (metric, unit), points in sorted(points_by_metric.items())
    )

    return AggregatedCategory(
        category=category,
        n_included=len(included),
        excluded=tuple(excluded),
        measurements=measurements,
    )


def aggregate_runs(
    run_sets: Sequence[RunScoreSet], *, allow_heterogeneous: bool = False
) -> CrossRunAggregate:
    """F7: refuses to aggregate runs whose ``compiled_hash``,
    ``adapter_version`` or ``catalog_version`` differ from the first run's,
    unless ``allow_heterogeneous`` is set. Even then, the result is stamped
    ``heterogeneous=True`` rather than silently treated as a clean
    same-scenario sample -- S1: nothing about this flag can ever raise a
    downstream confidence or coverage value, only mark the aggregate as
    less trustworthy than a homogeneous one."""
    if not run_sets:
        raise ValueError("aggregate_runs: no runs supplied")

    reference = run_sets[0]
    mismatched = [rs for rs in run_sets if rs.version_key != reference.version_key]
    if mismatched and not allow_heterogeneous:
        raise HeterogeneousComparisonError(
            f"{len(mismatched)} of {len(run_sets)} run(s) differ from "
            f"{reference.run_id}'s compiled_hash/adapter_version/catalog_version; "
            "pass allow_heterogeneous=True to aggregate anyway -- this only ever lowers "
            "confidence, never raises it (F7, S1)",
            heterogeneous_run_ids=tuple(rs.run_id for rs in mismatched),
            reference_run_id=reference.run_id,
        )

    per_category: dict[ScoringCategory, list[tuple[str, CategoryResult]]] = {
        category: [] for category in ScoringCategory
    }
    for run_set in run_sets:
        for result in run_set.categories:
            per_category[result.category].append((run_set.run_id, result))

    aggregated = tuple(
        _aggregate_category(category, per_category[category]) for category in ScoringCategory
    )

    return CrossRunAggregate(
        compiled_hash=reference.compiled_hash,
        adapter_version=reference.adapter_version,
        catalog_version=reference.catalog_version,
        n_runs=len(run_sets),
        heterogeneous=bool(mismatched),
        categories=aggregated,
    )


def score_set_from_bundle(run_dir: Path) -> RunScoreSet:
    """Convenience mirroring ``analysis/drift.py``'s bundle-reading helpers:
    build one run's :class:`RunScoreSet` directly from a sealed bundle."""
    from chainbreak.evidence.reader import read_manifest
    from chainbreak.scoring.categories import score_bundle

    manifest = read_manifest(run_dir / "manifest.json")
    return RunScoreSet(
        run_id=manifest.run_id,
        compiled_hash=str(manifest.scenario.get("compiled_hash", "")),
        adapter_version=str(manifest.provenance.get("provider_adapter_version", "")),
        catalog_version=str(manifest.provenance.get("capability_catalog_version", "")),
        categories=score_bundle(run_dir),
    )
