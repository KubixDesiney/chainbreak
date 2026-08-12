"""``chainbreak compare`` (M18 F1-F3): classify per-measurement reproducibility
across two runs into REPRODUCIBILITY.md section 1's three levels.

Two design decisions worth recording, because REPRODUCIBILITY.md's own text
constrains them tightly:

1. **``finding_id`` and ``evidence.*_refs`` are excluded from every content
   comparison.** ``finding_id`` is a content-derived hash that folds in the
   run's own ``observation_refs`` (``analysis/rules.py::_deterministic_finding_id``),
   and ``evidence.observation_refs``/``event_refs``/``policy_state_refs`` are
   literal observation/event ids -- both are salted per run (ADR-013) and
   therefore *provably* unique to a run by construction, even when two runs
   measured the identical thing. Comparing them would report every finding
   as DIVERGENT across any two independently-produced runs, which is not
   what "structural reproducibility" means.
2. **Two different runs of the same scenario+seed report STRUCTURALLY_IDENTICAL,
   never IDENTICAL, for set-valued measurements; timing measurements across
   two different runs never report IDENTICAL at all, even on a bit-exact
   coincidence.** ``IDENTICAL`` is reserved for Level 1 -- literally the same
   evidence bundle re-analyzed (REPRODUCIBILITY.md section 1: "given the SAME
   evidence bundle"). REPRODUCIBILITY.md is explicit that timing is Level 3
   and "anyone claiming exact timing reproducibility on a shared cloud
   control plane is mistaken, and the tool should not imply otherwise" -- so
   this tool never labels a cross-run timing match ``IDENTICAL``, regardless
   of what the numbers happen to be. M18's own negative-controls section
   paraphrases the same-seed-twice case as "must report identical"; that
   shorthand is superseded here by REPRODUCIBILITY.md section 1's own more
   careful definition, which this module implements directly.

Timing (Level 3) comparisons are built from
:func:`~chainbreak.analysis.pipeline.revocation_measurements` directly rather
than from ``findings.json``: most revocation windows never produce a
``REVOCATION_DELAY`` finding at all (that rule only fires when an
*assertive* expectation was exceeded -- ``analysis/rules.py::rule_revocation_delay``),
so a findings-only comparison would silently skip the very measurements
Level 3 exists to describe.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from chainbreak.core.enums import FindingType
from chainbreak.core.errors import AnalysisError, EvidenceError, HeterogeneousComparisonError
from chainbreak.core.ids import CapabilityId, IdentityId
from chainbreak.core.models import Finding, Interval, RevocationMeasurement

__all__ = [
    "ComparisonReport",
    "MeasurementComparison",
    "RunSnapshot",
    "compare_bundles",
    "snapshot_from_bundle",
]

#: Finding types built from an Interval measurement (REPRODUCIBILITY.md
#: Level 3). Excluded from the generic set-valued comparison below and
#: handled instead via the raw :class:`RevocationMeasurement`, which exists
#: for every polled cell regardless of whether either of these fired.
_TIMING_FINDING_TYPES = frozenset(
    {FindingType.REVOCATION_DELAY, FindingType.NO_TRANSITION_OBSERVED}
)

#: Fields excluded from the Level-2 content comparison: both are provably
#: unique per run by construction (see module docstring point 1).
_RUN_SPECIFIC_FIELDS = frozenset({"finding_id", "evidence"})


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    """One run's comparison-relevant state, read once so ``compare_bundles``
    never re-reads a bundle. Mirrors ``scoring/aggregate.py::RunScoreSet``."""

    run_id: str
    compiled_hash: str
    adapter_version: str
    catalog_version: str
    infrastructure_fingerprint: str | None
    findings: tuple[Finding, ...]
    revocation_measurements: tuple[RevocationMeasurement, ...]

    @property
    def version_key(self) -> tuple[str, str, str]:
        return (self.compiled_hash, self.adapter_version, self.catalog_version)


@dataclass(frozen=True, slots=True)
class MeasurementComparison:
    key: str
    level: str
    verdict: str
    detail: str


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    run_a: str
    run_b: str
    heterogeneous: bool
    cross_operator: bool
    comparisons: tuple[MeasurementComparison, ...]
    notes: tuple[str, ...]

    @property
    def divergent_count(self) -> int:
        return sum(1 for c in self.comparisons if c.verdict == "DIVERGENT")


def _intervals_overlap(a: Interval, b: Interval) -> bool:
    return a.low <= b.high and b.low <= a.high


def _finding_label(finding: Finding) -> str:
    parts = [finding.type.value, finding.subject_kind]
    if finding.identity_id:
        parts.append(str(finding.identity_id))
    if finding.edge_id:
        parts.append(finding.edge_id)
    if finding.hop_index is not None:
        parts.append(f"hop{finding.hop_index}")
    return ":".join(parts)


def _content_fingerprint(finding: Finding) -> str:
    from chainbreak.core.canonical import dumps

    return dumps(finding.model_dump(mode="json", exclude=set(_RUN_SPECIFIC_FIELDS)))


def _compare_set_valued(
    findings_a: Sequence[Finding], findings_b: Sequence[Finding], *, match_verdict: str
) -> list[MeasurementComparison]:
    """Level 2: exact multiset comparison of every non-timing finding's
    content, excluding run-specific identifiers. A finding present in one
    run's multiset and absent from the other's -- even if something with the
    same ``(type, identity_id, ...)`` exists there with different content --
    is DIVERGENT: REPRODUCIBILITY.md section 1 is explicit that "a Level 2
    failure is itself a finding," not a tool error, so it is reported the
    same way a genuine content match is, never raised as an exception."""
    set_valued_a = [f for f in findings_a if f.type not in _TIMING_FINDING_TYPES]
    set_valued_b = [f for f in findings_b if f.type not in _TIMING_FINDING_TYPES]

    by_fingerprint: dict[str, Finding] = {
        _content_fingerprint(f): f for f in (*set_valued_b, *set_valued_a)
    }
    counts_a = Counter(_content_fingerprint(f) for f in set_valued_a)
    counts_b = Counter(_content_fingerprint(f) for f in set_valued_b)

    comparisons: list[MeasurementComparison] = []
    for fingerprint in sorted(counts_a & counts_b):
        finding = by_fingerprint[fingerprint]
        comparisons.append(
            MeasurementComparison(
                key=_finding_label(finding),
                level="STRUCTURAL",
                verdict=match_verdict,
                detail="set-valued content matches exactly (Level 2)",
            )
        )
    for fingerprint in sorted(counts_a - counts_b):
        finding = by_fingerprint[fingerprint]
        comparisons.append(
            MeasurementComparison(
                key=_finding_label(finding),
                level="STRUCTURAL",
                verdict="DIVERGENT",
                detail="present in run A with no exact match in run B -- non-deterministic "
                "authorization behavior, not a tool error",
            )
        )
    for fingerprint in sorted(counts_b - counts_a):
        finding = by_fingerprint[fingerprint]
        comparisons.append(
            MeasurementComparison(
                key=_finding_label(finding),
                level="STRUCTURAL",
                verdict="DIVERGENT",
                detail="present in run B with no exact match in run A -- non-deterministic "
                "authorization behavior, not a tool error",
            )
        )
    return comparisons


def _compare_revocation(
    measurements_a: Sequence[RevocationMeasurement],
    measurements_b: Sequence[RevocationMeasurement],
    *,
    match_verdict: str,
) -> list[MeasurementComparison]:
    """Level 3: every polled (identity, capability) cell's transition window,
    compared for interval overlap -- never for bit-exact equality, per the
    module docstring's second design decision."""
    by_key_a: dict[tuple[IdentityId, CapabilityId], RevocationMeasurement] = {
        (m.identity_id, m.capability_id): m for m in measurements_a
    }
    by_key_b: dict[tuple[IdentityId, CapabilityId], RevocationMeasurement] = {
        (m.identity_id, m.capability_id): m for m in measurements_b
    }

    comparisons: list[MeasurementComparison] = []
    for identity_id, capability_id in sorted(set(by_key_a) | set(by_key_b)):
        label = f"revocation:{identity_id}:{capability_id}"
        a = by_key_a.get((identity_id, capability_id))
        b = by_key_b.get((identity_id, capability_id))

        if a is None or b is None:
            missing = "run A" if a is None else "run B"
            comparisons.append(
                MeasurementComparison(
                    key=label,
                    level="DISTRIBUTIONAL",
                    verdict="DIVERGENT",
                    detail=f"polled in one run only ({missing} has no measurement)",
                )
            )
            continue

        if a.transition_observed != b.transition_observed:
            comparisons.append(
                MeasurementComparison(
                    key=label,
                    level="DISTRIBUTIONAL",
                    verdict="DIVERGENT",
                    detail=f"transition observed in one run but not the other "
                    f"({a.transition_observed} vs {b.transition_observed})",
                )
            )
            continue

        if not a.transition_observed:
            comparisons.append(
                MeasurementComparison(
                    key=label,
                    level="DISTRIBUTIONAL",
                    verdict=match_verdict,
                    detail="neither run observed a transition within its window",
                )
            )
            continue

        window_a, window_b = a.transition_window, b.transition_window
        if window_a is None or window_b is None:
            # Unreachable given transition_observed=True: RevocationMeasurement's own
            # _window_present_iff_observed validator guarantees the pairing. Raised
            # rather than asserted so a future model change that breaks the invariant
            # fails loudly here too, not just wherever it happens to be read next.
            raise AnalysisError(
                "transition_observed=True but transition_window is None; "
                "RevocationMeasurement invariant violated",
                identity_id=identity_id,
                capability_id=capability_id,
            )
        if _intervals_overlap(window_a, window_b):
            comparisons.append(
                MeasurementComparison(
                    key=label,
                    level="DISTRIBUTIONAL",
                    verdict=match_verdict,
                    detail=(
                        f"windows overlap: [{window_a.low:.3f}, {window_a.high:.3f}]s vs "
                        f"[{window_b.low:.3f}, {window_b.high:.3f}]s -- timing is Level 3 "
                        "(distributional); exact values are not expected to reproduce"
                    ),
                )
            )
        else:
            comparisons.append(
                MeasurementComparison(
                    key=label,
                    level="DISTRIBUTIONAL",
                    verdict="DIVERGENT",
                    detail=(
                        f"windows do not overlap: [{window_a.low:.3f}, {window_a.high:.3f}]s vs "
                        f"[{window_b.low:.3f}, {window_b.high:.3f}]s"
                    ),
                )
            )
    return comparisons


def compare_bundles(
    run_a: RunSnapshot,
    run_b: RunSnapshot,
    *,
    allow_heterogeneous: bool = False,
    cross_operator: bool = False,
) -> ComparisonReport:
    """F1-F3. Refuses (:class:`HeterogeneousComparisonError`) rather than
    comparing runs whose ``compiled_hash``/``adapter_version``/``catalog_version``
    differ, unless ``allow_heterogeneous`` is set -- mirrors
    ``scoring/aggregate.py::aggregate_runs`` exactly, down to the message
    shape, because it is the same refusal for the same reason (F7 there,
    F2 here). Separately refuses across differing ``infrastructure_fingerprint``
    unless ``cross_operator`` is set (F3); ``cross_operator`` does not relax
    the version gate above, only the environment one.
    """
    mismatched = run_a.version_key != run_b.version_key
    if mismatched and not allow_heterogeneous:
        raise HeterogeneousComparisonError(
            f"{run_b.run_id} differs from {run_a.run_id}'s compiled_hash/adapter_version/"
            "catalog_version; pass allow_heterogeneous=True to compare anyway -- this only "
            "ever lowers confidence, never raises it (F2, S1)",
            run_a=run_a.run_id,
            run_b=run_b.run_id,
        )

    notes: list[str] = []
    if mismatched:
        notes.append(
            "HETEROGENEOUS: compiled_hash/adapter_version/catalog_version differ between "
            f"{run_a.run_id} and {run_b.run_id} -- every verdict below is a lower-confidence "
            "comparison, never a higher-confidence one (F2, S1)"
        )

    if cross_operator:
        notes.append(
            "CROSS-OPERATOR: environment equivalence (account, region, infrastructure) is "
            "ASSUMED and UNVERIFIED -- --cross-operator does not check it (F3)"
        )
    elif (
        run_a.infrastructure_fingerprint is not None
        and run_b.infrastructure_fingerprint is not None
        and run_a.infrastructure_fingerprint != run_b.infrastructure_fingerprint
    ):
        raise HeterogeneousComparisonError(
            f"{run_a.run_id} and {run_b.run_id} were produced against different "
            "infrastructure (infrastructure_fingerprint differs); pass cross_operator=True "
            "to compare anyway -- environment equivalence is then assumed, not verified (F3)",
            run_a=run_a.run_id,
            run_b=run_b.run_id,
        )

    self_comparison = run_a.run_id == run_b.run_id
    set_valued_match_verdict = "IDENTICAL" if self_comparison else "STRUCTURALLY_IDENTICAL"
    # A cross-run timing match is DISTRIBUTIONALLY_CONSISTENT even when its
    # bounds happen to coincide exactly -- REPRODUCIBILITY section 1's
    # "anyone claiming exact timing reproducibility... is mistaken" is a
    # claim about two INDEPENDENT runs; self_comparison (the same bundle's
    # own data compared to itself) is the one case IDENTICAL still applies.
    timing_match_verdict = "IDENTICAL" if self_comparison else "DISTRIBUTIONALLY_CONSISTENT"

    comparisons = [
        *_compare_set_valued(
            run_a.findings, run_b.findings, match_verdict=set_valued_match_verdict
        ),
        *_compare_revocation(
            run_a.revocation_measurements,
            run_b.revocation_measurements,
            match_verdict=timing_match_verdict,
        ),
    ]

    return ComparisonReport(
        run_a=run_a.run_id,
        run_b=run_b.run_id,
        heterogeneous=mismatched,
        cross_operator=cross_operator,
        comparisons=tuple(comparisons),
        notes=tuple(notes),
    )


def snapshot_from_bundle(run_dir: Path) -> RunSnapshot:
    """Build one run's :class:`RunSnapshot` from a sealed, already-analyzed
    bundle. Requires ``findings.json`` to exist (i.e. ``chainbreak analyze``
    has already run) -- ``compare`` classifies existing findings, it does
    not implicitly run analysis as a side effect."""
    from chainbreak.analysis.pipeline import revocation_measurements
    from chainbreak.evidence.reader import (
        read_events,
        read_findings,
        read_manifest,
        read_observations,
    )

    manifest = read_manifest(run_dir / "manifest.json")
    findings_path = run_dir / "findings.json"
    if not findings_path.is_file():
        raise EvidenceError(
            f"no findings.json under {run_dir}; run `chainbreak analyze {manifest.run_id}` first",
            run_id=manifest.run_id,
        )
    document = read_findings(findings_path)
    findings = tuple(Finding.model_validate(entry) for entry in document.get("findings", []))

    events = list(read_events(run_dir))
    observations = list(read_observations(run_dir))
    revocation = tuple(revocation_measurements(events, observations))

    return RunSnapshot(
        run_id=manifest.run_id,
        compiled_hash=str(manifest.scenario.get("compiled_hash", "")),
        adapter_version=str(manifest.provenance.get("provider_adapter_version", "")),
        catalog_version=str(manifest.provenance.get("capability_catalog_version", "")),
        infrastructure_fingerprint=manifest.provenance.get("infrastructure_fingerprint"),
        findings=findings,
        revocation_measurements=revocation,
    )
