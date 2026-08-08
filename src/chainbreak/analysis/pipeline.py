"""Orchestrates a sealed bundle into ``findings.json`` (F8: idempotent -- a
pure function of bundle content, no clock reads, no randomness that affects
output).

Scope, stated plainly: the authority/divergence family (per phase, from
``observations.jsonl``) and the revocation-timing family (from
``POLICY_MUTATION_APPLIED`` events paired with ``POST_MUTATION``-phase poll
observations) are detected automatically from any bundle, regardless of what
produced it. Stale-authority and silent-narrowing require deferred-execution
and task-worker machinery that belongs to M13/M14, which do not exist yet;
:mod:`chainbreak.analysis.rules` and :mod:`chainbreak.analysis.timing`
already implement their predicates and are directly callable once bundles
carrying that data exist -- this pipeline does not yet extract that data
from a bundle automatically, and says so rather than silently doing nothing.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
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
    rule_lifetime_capped,
    rule_no_transition_observed,
    rule_revocation_delay,
)
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
)
from chainbreak.evidence.reader import (
    read_credentials,
    read_graph,
    read_manifest,
    read_observations,
    read_scenario,
)
from chainbreak.evidence.writer import write_findings

_ANALYZER_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    findings: tuple[Finding, ...]
    detector_checks: tuple[DetectorCheck, ...]
    bundle_root_verified: bool


def _origin_finding_id(findings_so_far: list[Finding], identity_id: IdentityId) -> str | None:
    """The most recent ``AUTHORITY_EXPANSION`` finding at ``identity_id``, if
    any -- what a ``DELEGATION_DRIFT`` finding downstream cites as its cause
    (AUTHORIZATION_MODEL.md section 7's worked example)."""
    from chainbreak.core.enums import FindingType

    for finding in reversed(findings_so_far):
        if finding.type is FindingType.AUTHORITY_EXPANSION and finding.identity_id == identity_id:
            return finding.finding_id
    return None


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

    for node in populated.nodes:
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
        drift_finding = rule_delegation_drift(
            node, drift_class, _origin_finding_id(findings, node.parent_id or ""), cells
        )
        if drift_finding is not None:
            findings.append(drift_finding)

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


def _revocation_findings(
    events: list[dict[str, Any]],
    observations: list[Observation],
    expectations: tuple[CompiledExpectation, ...],
) -> list[Finding]:
    findings: list[Finding] = []
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
        return findings

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
        return findings

    for (identity_id, capability_id), samples in polls_by_cell.items():
        measurement = compute_revocation_window(
            samples,
            identity_id=identity_id,
            capability_id=capability_id,
            mutation_kind=mutation_kind,
            mutation_sent_ns=mutation_sent_ns,
            poll_interval_ms=500,
            mutation_receipt_confirmed=bool(receipt.get("confirmed", False)),
        )
        no_transition = rule_no_transition_observed(measurement)
        if no_transition is not None:
            findings.append(no_transition)
            continue
        expectation = next(
            (
                e
                for e in expectations
                if e.kind == "revocation_within"
                and e.identity_id == identity_id
                and e.capability_id == capability_id
            ),
            None,
        )
        delay = rule_revocation_delay(measurement, expectation)
        if delay is not None:
            findings.append(delay)

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

    phases_present = {o.phase for o in observations} - {PlanPhase.POST_MUTATION}
    for phase in sorted(phases_present, key=lambda p: p.value):
        findings.extend(_authority_findings_for_phase(graph, observations, phase))

    findings.extend(_revocation_findings(events, observations, scenario.expectations))

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
