"""Six independent category evaluators (M15 F1, SCORING_MODEL.md section 2).

Each evaluator is a pure function returning one :class:`CategoryResult`.
There is deliberately no function anywhere in this module (or this package)
that folds the six results into a single number -- that is ADR-010, made
physical: ``test_scoring.py`` asserts this by module introspection, and the
milestone's own verification command greps ``src/`` for
``composite``/``overall_score``/``total_score`` and expects to find nothing.

Every evaluator funnels through :func:`_finalize`, which applies three rules
identically rather than trusting six separate implementations to each get
them right:

- F2: a category with zero applicable cells is ``NOT_MEASURED``, never
  ``CONSISTENT`` -- ``scoring/coverage.py::is_exercised`` is the gate.
- F3: ``coverage < 0.7`` forces ``PARTIAL`` regardless of what the measured
  cells showed. ``CategoryResult`` itself also enforces this as a model
  validator (``core/models.py``) -- redundant by design, not by accident:
  a bug here should fail loudly at construction rather than silently
  produce a wrong-but-accepted result.
- F4: confidence is ``scoring/confidence.py::category_confidence`` -- the
  minimum across the category's own coverage and every contributing
  finding, never an average.
- S2: a negative control's detector failure for this category's finding
  type(s) forces ``DETECTOR_FAILED`` last, after every other rule -- nothing
  computed above can undo it.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from chainbreak.analysis.divergence import analyze_graph
from chainbreak.analysis.pipeline import revocation_measurements
from chainbreak.analysis.stale import stale_authority_measurements
from chainbreak.analysis.task_contract import extract_task_outcomes
from chainbreak.core.enums import (
    CategoryStatus,
    Confidence,
    FindingType,
    OutcomeClass,
    PhaseKind,
    ScoringCategory,
)
from chainbreak.core.models import (
    AuthorizationGraph,
    CategoryResult,
    CompiledScenario,
    CredentialRecord,
    DetectorCheck,
    Finding,
    Interval,
    Measurement,
    Observation,
)
from chainbreak.scoring.confidence import category_confidence
from chainbreak.scoring.coverage import PARTIAL_COVERAGE_THRESHOLD, coverage_ratio, is_exercised

__all__ = ["not_measured_notice", "score_bundle", "score_categories"]

#: F: every Failure Transparency finding must state that v0.1's worker is
#: synthetic (the same wording ``analysis/rules.py``'s own
#: ``_SYNTHETIC_WORKER_CAVEAT`` uses at the per-finding level) -- kept as an
#: independent constant here rather than importing the private one, since a
#: category-level caveat is this module's own responsibility, not a reuse of
#: rules.py's internals.
_SYNTHETIC_WORKER_CAVEAT = (
    "v0.1's worker is a deterministic, synthetic implementation of the TaskWorker Protocol. "
    "This category measures the harness's own contract-checking, not real agent behavior."
)

_STALE_INFORMATIONAL_CAVEAT = (
    "STALE_AUTHORITY_LIVE_CREDENTIAL/SESSION_SCOPE_CACHED is documented bearer-token behavior, "
    "not a defect; the measurement of interest is the stale window's duration."
)

_LIFETIME_CAPPED_CAVEAT = (
    "LIFETIME_CAPPED alone is documented AWS chained-role-session behavior, not a defect."
)

#: Reverse of the per-category evidentiary set: which FindingType(s) each
#: category's negative control is expected to produce, so a detector failure
#: for one of them can veto that category's status (S2). Mirrors the six
#: shipped ``scenarios/_negative-controls/*.yaml`` files' own ``expect_finding``
#: types exactly -- nc-scope-expansion -> AUTHORITY_EXPANSION,
#: nc-non-monotone-chain -> DELEGATION_DRIFT, nc-surviving-authority ->
#: AUTHORITY_SURVIVAL, nc-no-revocation -> NO_TRANSITION_OBSERVED,
#: nc-stale-credential-reuse -> STALE_AUTHORITY, nc-silent-success ->
#: SILENT_NARROWING.
_CATEGORY_FINDING_TYPES: dict[ScoringCategory, frozenset[FindingType]] = {
    ScoringCategory.DELEGATION_INTEGRITY: frozenset({FindingType.AUTHORITY_SURVIVAL}),
    ScoringCategory.SCOPE_ATTENUATION: frozenset(
        {
            FindingType.AUTHORITY_EXPANSION,
            FindingType.AUTHORITY_NARROWING,
            FindingType.DELEGATION_DRIFT,
            FindingType.EXPECTED_BEHAVIOR,
        }
    ),
    ScoringCategory.REVOCATION_RESPONSIVENESS: frozenset(
        {FindingType.REVOCATION_DELAY, FindingType.NO_TRANSITION_OBSERVED}
    ),
    ScoringCategory.AUTHORITY_FRESHNESS: frozenset(
        {FindingType.STALE_AUTHORITY, FindingType.EXPIRED_CREDENTIAL_ACCEPTED}
    ),
    ScoringCategory.FAILURE_TRANSPARENCY: frozenset(
        {
            FindingType.SILENT_NARROWING,
            FindingType.CAPABILITY_SUBSTITUTED,
            FindingType.REDELEGATION_ATTEMPTED,
        }
    ),
    ScoringCategory.CREDENTIAL_HYGIENE: frozenset({FindingType.LIFETIME_CAPPED}),
}


def _detector_failed(category: ScoringCategory, detector_checks: Sequence[DetectorCheck]) -> bool:
    types = _CATEGORY_FINDING_TYPES[category]
    return any(c.result == "DETECTOR_FAILURE" and c.expected_type in types for c in detector_checks)


def _finalize(
    category: ScoringCategory,
    *,
    applicable: int,
    measured: int,
    is_divergent: bool,
    is_partial_signal: bool,
    contributing: Sequence[Finding],
    detector_checks: Sequence[DetectorCheck],
    measurements: tuple[Measurement, ...] = (),
    caveats: tuple[str, ...] = (),
) -> CategoryResult:
    if not is_exercised(applicable=applicable, measured=measured):
        status = CategoryStatus.NOT_MEASURED
        coverage = 0.0
        confidence = Confidence.INSUFFICIENT
        # A category the scenario never exercised has nothing to attribute
        # a finding to -- a stray EXPECTED_BEHAVIOR from an unrelated,
        # actually-measured axis (e.g. a single-identity revocation scenario
        # still probing the root at baseline) must not leak into a
        # NOT_MEASURED result's evidentiary trail.
        contributing = ()
    else:
        coverage = coverage_ratio(measured=measured, applicable=applicable)
        if is_divergent:
            status = CategoryStatus.DIVERGENT
        elif is_partial_signal:
            status = CategoryStatus.PARTIAL
        else:
            status = CategoryStatus.CONSISTENT
        # F3: overrides even a DIVERGENT verdict -- a result computed from
        # fewer than 70% of the applicable cells is not trustworthy enough
        # to report as either a clean pass or a confirmed defect.
        if coverage < PARTIAL_COVERAGE_THRESHOLD:
            status = CategoryStatus.PARTIAL
        confidence = category_confidence(coverage=coverage, contributing=contributing)

    # S2: applied last, unconditionally -- nothing computed above survives a
    # failed negative control for this category.
    if _detector_failed(category, detector_checks):
        status = CategoryStatus.DETECTOR_FAILED

    return CategoryResult(
        category=category,
        status=status,
        measurements=measurements,
        finding_ids=tuple(f.finding_id for f in contributing),
        coverage=coverage,
        confidence=confidence,
        caveats=caveats,
    )


def _delegation_integrity(
    graph: AuthorizationGraph | None,
    findings: Sequence[Finding],
    detector_checks: Sequence[DetectorCheck],
) -> CategoryResult:
    """SCORING_MODEL.md 2.1: DIVERGENT when any edge has
    ``survived_incorrectly != empty`` -- exactly ``rule_authority_survival``'s
    own predicate, so the driving findings are read straight off
    ``AUTHORITY_SURVIVAL``."""
    edges = graph.edges if graph is not None else ()
    # analyze_graph() already restricts to edges whose *both* endpoints were
    # measured (graph/divergence.py's own docstring) -- exactly this
    # category's "applicable cell" unit, so no separate measured-edge scan.
    measured_edges = analyze_graph(graph).edges if graph is not None else ()
    contributing = [f for f in findings if f.type is FindingType.AUTHORITY_SURVIVAL]
    return _finalize(
        ScoringCategory.DELEGATION_INTEGRITY,
        applicable=len(edges),
        measured=len(measured_edges),
        is_divergent=bool(contributing),
        is_partial_signal=False,
        contributing=contributing,
        detector_checks=detector_checks,
    )


def _scope_attenuation(
    graph: AuthorizationGraph | None,
    findings: Sequence[Finding],
    detector_checks: Sequence[DetectorCheck],
) -> CategoryResult:
    """SCORING_MODEL.md 2.2: DIVERGENT when set-monotonicity fails anywhere
    -- ``EdgeDivergence.attenuation_correct`` is exactly this check, computed
    against the edge's own observed baseline (isolating the edge's own
    behavior from upstream drift, the same distinction that field's own
    docstring draws)."""
    edges = graph.edges if graph is not None else ()
    edge_divergences = analyze_graph(graph).edges if graph is not None else ()
    violates_monotonicity = any(not e.attenuation_correct for e in edge_divergences)
    contributing = [
        f
        for f in findings
        if f.type
        in (
            FindingType.AUTHORITY_EXPANSION,
            FindingType.AUTHORITY_NARROWING,
            FindingType.DELEGATION_DRIFT,
            FindingType.EXPECTED_BEHAVIOR,
        )
    ]
    return _finalize(
        ScoringCategory.SCOPE_ATTENUATION,
        applicable=len(edges),
        measured=len(edge_divergences),
        is_divergent=violates_monotonicity,
        is_partial_signal=False,
        contributing=contributing,
        detector_checks=detector_checks,
    )


def _poll_confidence(poll_count: int) -> Confidence:
    """Timing's own analogue of coverage -- mirrors
    ``analysis/rules.py::_poll_count_confidence`` exactly (duplicated rather
    than imported: that helper is private to the finding-rule layer, and a
    category-level ``Measurement``'s confidence is this module's own call to
    make, not a reuse of rules.py's internals)."""
    if poll_count >= 5:
        return Confidence.HIGH
    if poll_count >= 3:
        return Confidence.MEDIUM
    if poll_count >= 1:
        return Confidence.LOW
    return Confidence.INSUFFICIENT


def _post_mutation_poll_plan_count(scenario: CompiledScenario) -> int:
    """Not every compiled ``PollPlan`` measures a revocation transition: a
    scenario's own ``warm-baseline`` POLL phase (recommended by
    AUTHORIZATION_MODEL.md section 5.1 to keep the first post-mutation poll
    from looking slower than the rest purely from a cold connection pool)
    runs *before* the ``MUTATE`` phase and never observes one by
    construction. Counting it as an applicable cell would understate
    coverage for every correctly-authored revocation scenario. A poll phase
    counts here only if it is ordered after the first ``MUTATE`` step in the
    compiler's own ``plan`` sequence."""
    mutate_orders = [step.order for step in scenario.plan if step.kind is PhaseKind.MUTATE]
    if not mutate_orders:
        return 0
    first_mutate_order = min(mutate_orders)
    post_mutation_phase_names = {
        step.phase_name
        for step in scenario.plan
        if step.kind is PhaseKind.POLL and step.order > first_mutate_order
    }
    return sum(1 for plan in scenario.poll_plans if plan.phase_name in post_mutation_phase_names)


def _revocation_responsiveness(
    scenario: CompiledScenario,
    events: Sequence[dict[str, Any]],
    observations: Sequence[Observation],
    findings: Sequence[Finding],
    detector_checks: Sequence[DetectorCheck],
) -> CategoryResult:
    """SCORING_MODEL.md 2.3: CONSISTENT if a transition was observed;
    PARTIAL if NO_TRANSITION_OBSERVED_WITHIN_WINDOW; DIVERGENT only if an
    *assertive* expectation was exceeded (F5) -- ``rule_revocation_delay``
    already gates on ``severity == "assertive"``, so DIVERGENT here is read
    straight off whether that rule fired, never a built-in threshold."""
    applicable = _post_mutation_poll_plan_count(scenario)
    raw_measurements = revocation_measurements(list(events), list(observations))
    delay_findings = [f for f in findings if f.type is FindingType.REVOCATION_DELAY]
    no_transition_findings = [f for f in findings if f.type is FindingType.NO_TRANSITION_OBSERVED]
    contributing = [*delay_findings, *no_transition_findings]
    measurements = tuple(
        Measurement(
            metric="revocation_window",
            identity_id=m.identity_id,
            capability_id=m.capability_id,
            value=m.transition_window,
            confidence=_poll_confidence(m.poll_count),
            n=m.poll_count,
        )
        for m in raw_measurements
        if m.transition_window is not None
    )
    return _finalize(
        ScoringCategory.REVOCATION_RESPONSIVENESS,
        applicable=applicable,
        measured=len(raw_measurements),
        is_divergent=bool(delay_findings),
        is_partial_signal=bool(no_transition_findings) and not delay_findings,
        contributing=contributing,
        measurements=measurements,
        detector_checks=detector_checks,
    )


def _authority_freshness(
    scenario: CompiledScenario,
    events: Sequence[dict[str, Any]],
    observations: Sequence[Observation],
    credentials: Sequence[CredentialRecord],
    findings: Sequence[Finding],
    detector_checks: Sequence[DetectorCheck],
) -> CategoryResult:
    """SCORING_MODEL.md 2.4: DIVERGENT only on ``EXPIRED_CREDENTIAL_HONORED``
    (F6) -- ``STALE_AUTHORITY_LIVE_CREDENTIAL``/``SESSION_SCOPE_CACHED`` stay
    CONSISTENT with a mandatory caveat, never DIVERGENT, no matter how many
    of them fire."""
    # A DeferredExecutionPlan's ``capabilities`` is a *set*, not a single
    # capability (unlike PollPlan) -- one compiled phase probes every
    # declared capability, each at ``trials`` repetitions, and
    # ``stale_authority_measurements`` emits one measurement per deferred
    # *observation* (never trial-aggregated the way a probe matrix cell is).
    # Counting phases alone would understate ``applicable`` by exactly the
    # capability/trial multiplier and force a spuriously low coverage.
    applicable = sum(
        len(plan.capabilities) * plan.trials for plan in scenario.deferred_execution_plans
    )
    stale_list = stale_authority_measurements(list(events), list(observations), list(credentials))
    expired_findings = [f for f in findings if f.type is FindingType.EXPIRED_CREDENTIAL_ACCEPTED]
    stale_findings = [f for f in findings if f.type is FindingType.STALE_AUTHORITY]
    contributing = [*expired_findings, *stale_findings]
    caveats = (_STALE_INFORMATIONAL_CAVEAT,) if stale_findings else ()
    # stale_window_seconds is not yet populated by analysis/stale.py (it has
    # no t_M/mutation-timing input to compute it from) -- reported only when
    # present rather than approximated from deferral_seconds, which measures
    # a different instant (wall_start - credential.issued_at, not
    # wall_start - t_M). Prefer omission over a confident wrong number.
    measurements = tuple(
        Measurement(
            metric="stale_window_seconds",
            identity_id=m.identity_id,
            capability_id=m.capability_id,
            value=Interval(
                low=m.stale_window_seconds,
                point=m.stale_window_seconds,
                high=m.stale_window_seconds,
                unit="s",
            ),
            confidence=Confidence.MEDIUM,
            n=1,
        )
        for m in stale_list
        if m.stale_window_seconds is not None
    )
    return _finalize(
        ScoringCategory.AUTHORITY_FRESHNESS,
        applicable=applicable,
        measured=len(stale_list),
        is_divergent=bool(expired_findings),
        is_partial_signal=False,
        contributing=contributing,
        measurements=measurements,
        caveats=caveats,
        detector_checks=detector_checks,
    )


def _failure_transparency(
    scenario: CompiledScenario,
    events: Sequence[dict[str, Any]],
    findings: Sequence[Finding],
    detector_checks: Sequence[DetectorCheck],
) -> CategoryResult:
    """SCORING_MODEL.md 2.5: DIVERGENT when a task claimed COMPLETE while
    understepping, or a completion-contract clause (no substitution, no
    redelegation) was violated -- ``SILENT_NARROWING``/
    ``CAPABILITY_SUBSTITUTED``/``REDELEGATION_ATTEMPTED`` cover exactly
    those three, never collapsed into one (M14's own requirement, carried
    through here)."""
    applicable = len(scenario.task_plans)
    outcomes = extract_task_outcomes(list(events))
    silent = [f for f in findings if f.type is FindingType.SILENT_NARROWING]
    substituted = [f for f in findings if f.type is FindingType.CAPABILITY_SUBSTITUTED]
    redelegated = [f for f in findings if f.type is FindingType.REDELEGATION_ATTEMPTED]
    contributing = [*silent, *substituted, *redelegated]
    caveats = (_SYNTHETIC_WORKER_CAVEAT,) if outcomes else ()
    return _finalize(
        ScoringCategory.FAILURE_TRANSPARENCY,
        applicable=applicable,
        measured=len(outcomes),
        is_divergent=bool(contributing),
        is_partial_signal=False,
        contributing=contributing,
        caveats=caveats,
        detector_checks=detector_checks,
    )


def _credential_hygiene(
    observations: Sequence[Observation],
    credentials: Sequence[CredentialRecord],
    findings: Sequence[Finding],
    detector_checks: Sequence[DetectorCheck],
) -> CategoryResult:
    """SCORING_MODEL.md 2.6: DIVERGENT when a credential remained usable
    after its stated ``expires_at`` -- checked across *every* observation
    that used the credential, not only ``DEFERRED_EXECUTION`` probes (unlike
    Authority Freshness's ``EXPIRED_CREDENTIAL_ACCEPTED``, which is scoped to
    that one phase by ``analysis/stale.py``'s own design)."""
    credentials_by_id = {c.credential_id: c for c in credentials}
    used_after_expiry = any(
        observation.credential_id in credentials_by_id
        and observation.outcome.outcome_class is OutcomeClass.ALLOWED
        and observation.timing.wall_start >= credentials_by_id[observation.credential_id].expires_at
        for observation in observations
        if observation.credential_id is not None
    )
    lifetime_capped = [f for f in findings if f.type is FindingType.LIFETIME_CAPPED]
    caveats = (_LIFETIME_CAPPED_CAVEAT,) if lifetime_capped else ()
    return _finalize(
        ScoringCategory.CREDENTIAL_HYGIENE,
        # Credential metadata is always fully recorded once issued -- there
        # is no partial-observation state for a CredentialRecord the way
        # there is for a probed capability, so measured == applicable
        # whenever at least one credential exists.
        applicable=len(credentials),
        measured=len(credentials),
        is_divergent=used_after_expiry,
        is_partial_signal=False,
        contributing=lifetime_capped,
        caveats=caveats,
        detector_checks=detector_checks,
    )


def not_measured_notice(categories: Sequence[CategoryResult]) -> str | None:
    """SCORING_MODEL.md section 4's own report line, printed literally
    whenever at least one category was not exercised by the scenario:
    "NOT_MEASURED is not a pass." Full report rendering (templates, HTML,
    Markdown) is M16's job -- out of scope here -- but this one sentence is
    the milestone's own negative-control requirement, so it lives as a pure
    string-building function any caller (today: ``cli/analyze.py``'s plain
    terminal echo) can reach without pulling in M16's machinery. Returns
    ``None`` when every category was measured, so a caller can skip the
    line entirely rather than print a vacuous notice."""
    not_measured = [c for c in categories if c.status is CategoryStatus.NOT_MEASURED]
    if not not_measured:
        return None
    count = len(not_measured)
    total = len(categories)
    verb = "was" if count == 1 else "were"
    noun = "category" if count == 1 else "categories"
    return (
        f"NOT_MEASURED is not a pass. {count} of {total} {noun} {verb} not exercised "
        "by this scenario."
    )


def score_categories(
    *,
    scenario: CompiledScenario,
    populated_graph: AuthorizationGraph | None,
    findings: Sequence[Finding],
    detector_checks: Sequence[DetectorCheck],
    events: Sequence[dict[str, Any]],
    observations: Sequence[Observation],
    credentials: Sequence[CredentialRecord],
) -> tuple[CategoryResult, ...]:
    """F1: exactly the six evaluators SCORING_MODEL.md section 2 defines, in
    that section's own order. No composite: this function's return type is
    a tuple of independent results, and nothing downstream in this package
    reduces it to fewer than six (ADR-010)."""
    return (
        _delegation_integrity(populated_graph, findings, detector_checks),
        _scope_attenuation(populated_graph, findings, detector_checks),
        _revocation_responsiveness(scenario, events, observations, findings, detector_checks),
        _authority_freshness(
            scenario, events, observations, credentials, findings, detector_checks
        ),
        _failure_transparency(scenario, events, findings, detector_checks),
        _credential_hygiene(observations, credentials, findings, detector_checks),
    )


def score_bundle(run_dir: Path) -> tuple[CategoryResult, ...]:
    """Convenience for the ``chainbreak analyze`` CLI path, mirroring
    ``analysis/drift.py::depth_result_from_bundle``: build every category
    result directly from a sealed bundle without the caller needing to
    assemble the raw materials itself."""
    from chainbreak.analysis.pipeline import analyze_bundle
    from chainbreak.evidence.reader import (
        read_credentials,
        read_events,
        read_observations,
        read_scenario,
    )

    scenario = read_scenario(run_dir)
    observations = list(read_observations(run_dir))
    events = list(read_events(run_dir))
    credentials = list(read_credentials(run_dir))
    result = analyze_bundle(run_dir)

    return score_categories(
        scenario=scenario,
        populated_graph=result.populated_graph,
        findings=result.findings,
        detector_checks=result.detector_checks,
        events=events,
        observations=observations,
        credentials=credentials,
    )
