"""Orchestrates a sealed bundle into ``findings.json`` (F8: idempotent -- a
pure function of bundle content, no clock reads, no randomness that affects
output).

Scope, stated plainly: the authority/divergence family (per phase, from
``observations.jsonl``), the revocation-timing family (from
``POLICY_MUTATION_APPLIED`` events paired with ``POST_MUTATION``-phase poll
observations), the stale-authority family (since M13, from
``DEFERRED_EXECUTION``/``PAIRED_FRESH_CREDENTIAL``-phase observations, see
:mod:`chainbreak.analysis.stale`), and the silent-narrowing family (since
M14, from ``TASK_OUTCOME_RECORDED`` events, see
:mod:`chainbreak.analysis.task_contract`) are all detected automatically
from any bundle, regardless of what produced it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from chainbreak.analysis.authority import aggregate_observations, populate_observed_authority
from chainbreak.analysis.detector import check_negative_control
from chainbreak.analysis.divergence import analyze_graph
from chainbreak.analysis.rules import (
    rule_authority_expansion,
    rule_authority_narrowing,
    rule_authority_survival,
    rule_delegation_drift,
    rule_execution_error,
    rule_expected_behavior,
    rule_expired_credential_accepted,
    rule_lifetime_capped,
    rule_no_transition_observed,
    rule_revocation_delay,
    rule_stale_authority,
)
from chainbreak.analysis.stale import stale_authority_measurements
from chainbreak.analysis.task_contract import extract_task_outcomes, task_contract_findings
from chainbreak.analysis.timing import PollSample, compute_revocation_window
from chainbreak.core.enums import MutationKind, PlanPhase
from chainbreak.core.ids import CapabilityId, IdentityId
from chainbreak.core.models import (
    AuthorizationGraph,
    CompiledExpectation,
    CompiledScenario,
    DetectorCheck,
    Finding,
    Observation,
    PathAnalysis,
    RevocationMeasurement,
)
from chainbreak.evidence.reader import (
    read_credentials,
    read_graph,
    read_manifest,
    read_observations,
    read_scenario,
)
from chainbreak.evidence.writer import write_findings
from chainbreak.graph.paths import analyze_all_paths

_ANALYZER_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    findings: tuple[Finding, ...]
    detector_checks: tuple[DetectorCheck, ...]
    bundle_root_verified: bool
    #: M11 F3: first divergence and monotonicity per root-to-leaf path
    #: (AUTHORIZATION_MODEL.md section 4.5), keyed by ``PlanPhase.value`` --
    #: a branching graph diverges independently per branch, which no
    #: per-node or per-edge finding above captures on its own.
    path_analyses: dict[str, tuple[PathAnalysis, ...]] = field(default_factory=dict)
    #: M15: the graph after every authority-axis phase has been folded in
    #: (the same ``accumulated_graph`` the path-analysis loop below already
    #: builds) -- ``scoring/categories.py`` needs per-edge "was this node
    #: actually measured" state and re-deriving it from scratch would
    #: duplicate this exact accumulation loop rather than reuse its output.
    #: ``None`` only when the bundle has no authority-axis phase at all
    #: (a pure revocation/task/stale-authority-only run).
    populated_graph: AuthorizationGraph | None = None


def _authority_findings_for_phase(
    graph: AuthorizationGraph, observations: list[Observation], phase: PlanPhase
) -> list[Finding]:
    populated = populate_observed_authority(graph, observations, phase=phase)
    cells_by_identity: dict[IdentityId, dict[CapabilityId, Any]] = defaultdict(dict)
    for (identity_id, capability_id, _obs_phase), cell in aggregate_observations(
        o for o in observations if o.phase is phase
    ).items():
        cells_by_identity[identity_id][capability_id] = cell

    analysis = analyze_graph(populated)
    findings: list[Finding] = []
    # M11 F4: the finding_id of the AUTHORITY_EXPANSION at the TRUE origin of
    # a gain, threaded through every downstream hop that carries it forward
    # (PROPAGATED/AMPLIFIED) -- not just the immediate parent's own finding.
    # Looking up only the parent's AUTHORITY_EXPANSION (as an earlier version
    # of this function did) loses the citation past the origin's immediate
    # child: a PROPAGATED node never gets its own AUTHORITY_EXPANSION finding
    # (rule_authority_expansion's predicate excludes PROPAGATED/AMPLIFIED),
    # so a grandchild looking up its own parent would find nothing there. A
    # CORRECTED hop deliberately gets no entry, which is what resets the
    # chain: any later, independent gain past a correction is a fresh
    # origin, not attributed to the earlier, already-fixed defect.
    origin_by_identity: dict[IdentityId, str] = {}

    for node in sorted(populated.nodes, key=lambda n: n.hop_index):
        if node.observed_authority is None:
            continue
        cells = cells_by_identity.get(node.identity_id, {})
        drift_class = analysis.drift.get(node.identity_id)

        # Both may fire for the same node (see rule_delegation_drift's
        # docstring): the origin of a gain at a non-root hop is both an
        # AUTHORITY_EXPANSION and a DELEGATION_DRIFT (drift_class=ORIGINATED);
        # a downstream PROPAGATED/AMPLIFIED node gets only the latter, since
        # rule_authority_expansion's own predicate excludes it.
        expansion = rule_authority_expansion(node, drift_class, cells)
        if expansion is not None:
            findings.append(expansion)
            origin_by_identity[node.identity_id] = expansion.finding_id

        origin_finding_id = origin_by_identity.get(node.parent_id or "")
        drift_finding = rule_delegation_drift(node, drift_class, origin_finding_id, cells)
        if drift_finding is not None:
            findings.append(drift_finding)
            if node.identity_id not in origin_by_identity and origin_finding_id is not None:
                origin_by_identity[node.identity_id] = origin_finding_id

        narrowing = rule_authority_narrowing(node, cells)
        if narrowing is not None:
            findings.append(narrowing)

        if expansion is None and narrowing is None:
            expected = rule_expected_behavior(node, cells)
            if expected is not None:
                findings.append(expected)

    for edge in populated.edges:
        edge_div = next((e for e in analysis.edges if e.edge_id == edge.edge_id), None)
        if edge_div is None:
            continue
        target_cells = cells_by_identity.get(edge.target_id, {})
        survival = rule_authority_survival(edge, edge_div, target_cells)
        if survival is not None:
            findings.append(survival)

    return findings


def revocation_measurements(
    events: list[dict[str, Any]], observations: list[Observation]
) -> list[RevocationMeasurement]:
    """One :class:`RevocationMeasurement` per polled (identity, capability)
    cell (M12). Split out from ``_revocation_findings`` (M15) so
    ``scoring/categories.py`` can consume the same measurements
    ``analysis/rules.py``'s finding predicates are built from, rather than
    re-parsing ``events``/``observations`` a second time."""
    measurements: list[RevocationMeasurement] = []
    mutation_events = [e for e in events if e.get("kind") == "POLICY_MUTATION_APPLIED"]

    poll_observations = [o for o in observations if o.phase is PlanPhase.POST_MUTATION]
    polls_by_cell: dict[tuple[IdentityId, CapabilityId], list[PollSample]] = defaultdict(list)
    for observation in poll_observations:
        key = (observation.identity_id, observation.capability_id)
        polls_by_cell[key].append(
            PollSample(
                monotonic_ns=observation.timing.monotonic_start_ns,
                outcome=observation.outcome.outcome_class,
            )
        )
    if not mutation_events or not polls_by_cell:
        return measurements

    # A run has one mutation to observe against (ADR-011: concurrent
    # mutations would destroy the timing measurement); every polled cell is
    # measured against it regardless of which identity the mutation itself
    # targeted -- nc-no-revocation.yaml's whole point is a cell that was
    # *polled* while a *different* identity was mutated, which the harness
    # cannot know in advance is unrelated.
    event = mutation_events[0]
    receipt = event.get("receipt", {})
    mutation_sent_ns = event.get("timing", {}).get("monotonic_ns")
    mutation_kind_raw = event.get("mutation_kind")
    mutation_kind: MutationKind | None
    try:
        mutation_kind = MutationKind(mutation_kind_raw) if mutation_kind_raw is not None else None
    except ValueError:
        mutation_kind = None
    if mutation_sent_ns is None or mutation_kind is None:
        return measurements

    for (identity_id, capability_id), samples in polls_by_cell.items():
        measurements.append(
            compute_revocation_window(
                samples,
                identity_id=identity_id,
                capability_id=capability_id,
                mutation_kind=mutation_kind,
                mutation_sent_ns=mutation_sent_ns,
                poll_interval_ms=500,
                mutation_receipt_confirmed=bool(receipt.get("confirmed", False)),
            )
        )

    return measurements


def _revocation_findings(
    events: list[dict[str, Any]],
    observations: list[Observation],
    expectations: tuple[CompiledExpectation, ...],
) -> list[Finding]:
    findings: list[Finding] = []
    for measurement in revocation_measurements(events, observations):
        no_transition = rule_no_transition_observed(measurement)
        if no_transition is not None:
            findings.append(no_transition)
            continue
        expectation = next(
            (
                e
                for e in expectations
                if e.kind == "revocation_within"
                and e.identity_id == measurement.identity_id
                and e.capability_id == measurement.capability_id
            ),
            None,
        )
        delay = rule_revocation_delay(measurement, expectation)
        if delay is not None:
            findings.append(delay)

    return findings


def _stale_authority_findings(
    events: list[dict[str, Any]],
    observations: list[Observation],
    credentials: list[Any],
) -> list[Finding]:
    findings: list[Finding] = []
    for measurement in stale_authority_measurements(events, observations, credentials):
        stale = rule_stale_authority(measurement)
        if stale is not None:
            findings.append(stale)
        expired = rule_expired_credential_accepted(measurement)
        if expired is not None:
            findings.append(expired)
    return findings


def analyze_bundle(run_dir: Path) -> AnalysisResult:
    from chainbreak.evidence.reader import read_events, verify_integrity

    manifest = read_manifest(run_dir / "manifest.json")
    scenario: CompiledScenario = read_scenario(run_dir)
    graph = read_graph(run_dir)
    observations = list(read_observations(run_dir))
    events = list(read_events(run_dir))
    credentials = list(read_credentials(run_dir))

    findings: list[Finding] = []
    path_analyses: dict[str, tuple[PathAnalysis, ...]] = {}
    # F3: unlike per-node/per-edge findings (independently correct using
    # only their own phase's observations), a root-to-leaf PATH's first
    # divergence needs the root's own measurement too -- and a scenario's
    # own baseline phase is typically the only phase that ever re-probes the
    # root (an after-delegation phase's targets are usually the delegated
    # agents alone). Populating progressively, feeding each phase's output
    # graph into the next call, accumulates observed authority across
    # phases instead of re-populating fresh each time (a node with no
    # observations in a later phase keeps whatever an earlier phase already
    # measured for it, since populate_observed_authority leaves it
    # unchanged rather than resetting it) -- so "the path analysis as of
    # this phase" reflects everything measured up to and including it, the
    # same accumulated view a scenario's own scenario-wide (not per-phase)
    # no_first_divergence/attenuation_monotone expectations assume.
    accumulated_graph = graph

    # POST_MUTATION (M12), DEFERRED_EXECUTION/PAIRED_FRESH_CREDENTIAL (M13)
    # and TASK_EXECUTION (M14) each get their own dedicated analysis below
    # instead: a probe against a deliberately-pinned pre-mutation
    # credential, a freshly re-delegated pairing probe, or a task's own
    # step invocation, would otherwise look like an ordinary
    # AUTHORITY_EXPANSION/NARROWING relative to the graph's static
    # expected_authority -- noise duplicating (and potentially conflicting
    # with) the dedicated finding each of those phases exists to produce.
    phases_present = {o.phase for o in observations} - {
        PlanPhase.POST_MUTATION,
        PlanPhase.DEFERRED_EXECUTION,
        PlanPhase.PAIRED_FRESH_CREDENTIAL,
        PlanPhase.TASK_EXECUTION,
    }
    for phase in sorted(phases_present, key=lambda p: p.value):
        findings.extend(_authority_findings_for_phase(graph, observations, phase))
        accumulated_graph = populate_observed_authority(
            accumulated_graph, observations, phase=phase
        )
        path_analyses[phase.value] = analyze_all_paths(accumulated_graph)

    # M15: expose the fully-accumulated graph only when at least one
    # authority-axis phase actually populated it -- otherwise it is
    # byte-identical to the unpopulated ``graph`` and callers should treat
    # this category axis as unmeasured, not "measured with zero coverage".
    populated_graph = accumulated_graph if phases_present else None

    findings.extend(_revocation_findings(events, observations, scenario.expectations))
    findings.extend(_stale_authority_findings(events, observations, credentials))
    findings.extend(task_contract_findings(extract_task_outcomes(events), scenario.task_plans))

    for credential in credentials:
        capped = rule_lifetime_capped(credential)
        if capped is not None:
            findings.append(capped)

    execution_error = rule_execution_error(manifest.status)
    if execution_error is not None:
        findings.append(execution_error)

    detector_checks: list[DetectorCheck] = []
    if scenario.expected_finding is not None:
        detector_checks.append(
            check_negative_control(
                scenario.expected_finding, findings, negative_control_id=scenario.scenario_id
            )
        )

    return AnalysisResult(
        findings=tuple(findings),
        detector_checks=tuple(detector_checks),
        bundle_root_verified=verify_integrity(run_dir),
        path_analyses=path_analyses,
        populated_graph=populated_graph,
    )


def _findings_document(manifest_completed_at: str | None, result: AnalysisResult) -> dict[str, Any]:
    return {
        "analysis": {
            "analyzer_version": _ANALYZER_VERSION,
            # Deliberately the bundle's own completed_at, not "now" (F8):
            # analyze must be idempotent, and a wall-clock read here would
            # make findings.json differ on every single invocation.
            "analyzed_at": manifest_completed_at,
            "bundle_root_verified": result.bundle_root_verified,
        },
        "findings": [f.model_dump(mode="json") for f in result.findings],
        "detector_checks": [
            {
                "negative_control": c.negative_control_id,
                "expected": c.expected_type.value,
                "produced": c.produced,
                "result": c.result,
            }
            for c in result.detector_checks
        ],
        # M11 F3: per root-to-leaf path, keyed by phase -- a branching graph
        # diverges independently per branch, which no single per-node or
        # per-edge finding above captures on its own.
        "path_analyses": {
            phase: [p.model_dump(mode="json") for p in paths]
            for phase, paths in result.path_analyses.items()
        },
    }


def analyze(run_dir: Path, *, allow_unsealed: bool = False) -> AnalysisResult:
    """Analyze a sealed bundle and write ``findings.json`` (F8: calling this
    twice on the same bundle produces byte-identical output).

    Refuses to produce findings for a bundle that failed integrity
    verification unless ``allow_unsealed`` is set (EVIDENCE_SCHEMA.md
    section 10, M6's F4): a mismatch means the evidence backing every
    finding might not be what was originally sealed.
    """
    from chainbreak.core.errors import BundleIntegrityError

    manifest = read_manifest(run_dir / "manifest.json")
    result = analyze_bundle(run_dir)
    if not result.bundle_root_verified and not allow_unsealed:
        raise BundleIntegrityError(
            "bundle failed integrity verification; refusing to produce findings "
            "without allow_unsealed",
            run_id=manifest.run_id,
        )
    write_findings(run_dir, _findings_document(manifest.completed_at, result))
    return result
