"""Gathers everything a renderer needs from a sealed bundle into one
:class:`ReportData`, so ``terminal.py``/``markdown.py``/``html.py`` each read
the bundle exactly once, the same way, rather than triplicating the
bundle-reading logic ``scoring/categories.py::score_bundle`` and
``scoring/aggregate.py::score_set_from_bundle`` already established as the
one-gathering-function-per-consumer pattern.

Not in M16's own "Required components" file list, the same way
``evidence/verify.py`` (M6) and ``scoring/aggregate.py``'s bundle
convenience functions (M15) were not in their milestones' literal lists --
added because avoiding duplicated bundle-reading logic across three
renderers is worth one extra module.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from chainbreak.analysis.authority import aggregate_observations
from chainbreak.analysis.divergence import analyze_graph
from chainbreak.analysis.pipeline import analyze_bundle, revocation_measurements
from chainbreak.analysis.stale import stale_authority_measurements
from chainbreak.core.enums import CategoryStatus, Provider
from chainbreak.core.errors import BundleIntegrityError
from chainbreak.core.models import (
    CategoryResult,
    DetectorCheck,
    Finding,
    RevocationMeasurement,
    StaleAuthorityMeasurement,
)
from chainbreak.evidence.reader import (
    read_credentials,
    read_events,
    read_manifest,
    read_observations,
    read_scenario,
)
from chainbreak.reporting.figures import (
    Figure,
    authorization_graph_figure,
    gain_loss_per_hop_figure,
    per_hop_authority_figure,
    repeatability_figure,
    revocation_timeline_figure,
    scenario_comparison_figure,
    stale_authority_window_figure,
)
from chainbreak.scoring.categories import not_measured_notice, score_categories

__all__ = ["ReportData", "gather_report_data"]


@dataclass(frozen=True, slots=True)
class ReportData:
    run_id: str
    status: str
    created_at: str
    completed_at: str | None
    scenario: dict[str, object]
    provenance: dict[str, object]
    provider: Provider
    git_dirty: bool
    bundle_root_verified: bool
    warnings: tuple[str, ...]
    findings: tuple[Finding, ...]
    detector_checks: tuple[DetectorCheck, ...]
    categories: tuple[CategoryResult, ...]
    not_measured_notice: str | None
    figures: tuple[Figure, ...]
    #: Kept as their own richer types (not flattened into
    #: ``CategoryResult.measurements``, which drops ``mutation_kind`` /
    #: ``mechanism``) so a "MEASUREMENTS" section can satisfy
    #: EXPERIMENT_PROTOCOL §7's "n, an interval, the mechanism, and the
    #: region" requirement without re-deriving the mechanism from a finding.
    revocation_measurements: tuple[RevocationMeasurement, ...]
    stale_measurements: tuple[StaleAuthorityMeasurement, ...]

    @property
    def is_fake_provider(self) -> bool:
        return self.provider is Provider.FAKE

    @property
    def has_not_measured(self) -> bool:
        return any(c.status is CategoryStatus.NOT_MEASURED for c in self.categories)


def gather_report_data(run_dir: Path, *, allow_unsealed: bool = False) -> ReportData:
    manifest = read_manifest(run_dir / "manifest.json")
    result = analyze_bundle(run_dir)
    if not result.bundle_root_verified and not allow_unsealed:
        raise BundleIntegrityError(
            "bundle failed integrity verification; refusing to render a report "
            "without allow_unsealed",
            run_id=manifest.run_id,
        )

    scenario = read_scenario(run_dir)
    provider = Provider(str(manifest.provenance.get("provider", "fake")))

    events = list(read_events(run_dir))
    observations = list(read_observations(run_dir))
    credentials = list(read_credentials(run_dir))

    categories = score_categories(
        scenario=scenario,
        populated_graph=result.populated_graph,
        findings=result.findings,
        detector_checks=result.detector_checks,
        events=events,
        observations=observations,
        credentials=credentials,
    )

    edge_divergences = analyze_graph(result.populated_graph).edges if result.populated_graph else ()
    revocations = revocation_measurements(events, observations)
    stale = stale_authority_measurements(events, observations, credentials)
    cells = {
        (str(key[0]), str(key[1])): cell.trials
        for key, cell in aggregate_observations(observations).items()
    }

    figures = (
        authorization_graph_figure(result.populated_graph, provider=provider),
        per_hop_authority_figure(result.populated_graph, provider=provider),
        gain_loss_per_hop_figure(edge_divergences, provider=provider),
        revocation_timeline_figure(revocations, provider=provider),
        stale_authority_window_figure(stale, provider=provider),
        repeatability_figure(cells, provider=provider),
        scenario_comparison_figure(None, provider=provider),
    )

    return ReportData(
        run_id=manifest.run_id,
        status=manifest.status,
        created_at=manifest.created_at,
        completed_at=manifest.completed_at,
        scenario=manifest.scenario,
        provenance=manifest.provenance,
        provider=provider,
        git_dirty=bool(manifest.provenance.get("git_dirty", False)),
        bundle_root_verified=result.bundle_root_verified,
        warnings=tuple(manifest.warnings),
        findings=result.findings,
        detector_checks=result.detector_checks,
        categories=categories,
        not_measured_notice=not_measured_notice(categories),
        figures=figures,
        revocation_measurements=tuple(revocations),
        stale_measurements=tuple(stale),
    )
