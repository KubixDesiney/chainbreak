"""One rule per finding type (F4), each an explicit predicate over already-
computed analysis pieces (never over raw bundle content -- S2): every rule
returns a :class:`Finding` with ``observation``, ``expected_state``,
``observed_state`` and ``security_interpretation`` as **separate** fields
(ADR-006), and ``security_interpretation`` is always a static template with
substituted values, never text built from a bundle field, which is what
keeps it safe to render into an HTML report unescaped (T-10).

Confidence gating is centralized in :func:`_build`: a candidate whose
confidence resolves to ``INSUFFICIENT`` is emitted as ``INCONCLUSIVE``
instead of its "natural" type (F3) -- every rule function benefits from this
by construction rather than remembering to check it themselves.

AUTHORIZATION_MODEL.md section 6's coverage/unanimity formula is defined over
``ProbeCellResult`` and is the gate for the five authority-axis finding types
(``EXPECTED_BEHAVIOR``, ``AUTHORITY_EXPANSION``, ``AUTHORITY_NARROWING``,
``DELEGATION_DRIFT``, ``AUTHORITY_SURVIVAL``). The timing, stale-authority,
task and credential finding types are not built from probe cells at all, so
forcing them through the same formula would spuriously downgrade every one
of them to ``INCONCLUSIVE`` (an empty cell list is, correctly,
``INSUFFICIENT``). Those rules instead pass ``confidence_override`` with a
value derived from their own domain-appropriate evidentiary strength --
documented at each call site.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from chainbreak.analysis.confidence import confidence_rationale, gate_confidence
from chainbreak.core.enums import Confidence, DriftClass, FindingType, SeverityHint
from chainbreak.core.ids import CapabilityId, IdentityId
from chainbreak.core.models import (
    CompiledExpectation,
    CredentialRecord,
    DelegationEdge,
    EdgeDivergence,
    Finding,
    FindingEvidence,
    IdentityNode,
    ProbeCellResult,
    RevocationMeasurement,
    StaleAuthorityMeasurement,
    TaskOutcome,
)

CellMap = Mapping[CapabilityId, ProbeCellResult]


def _observation_refs(cells: CellMap, capabilities: Sequence[str]) -> tuple[str, ...]:
    refs: list[str] = []
    for capability_id in capabilities:
        cell = cells.get(capability_id)
        if cell is not None:
            refs.extend(cell.observation_ids)
    return tuple(refs)


def _contributing_cells(cells: CellMap, capabilities: Sequence[str]) -> list[ProbeCellResult]:
    return [cells[c] for c in capabilities if c in cells]


def _deterministic_finding_id(
    *,
    type: FindingType,  # noqa: A002 -- matches Finding.type by design
    subject_kind: str,
    identity_id: str | None,
    edge_id: str | None,
    hop_index: int | None,
    observation_refs: Sequence[str],
) -> str:
    """A content-derived id, not :func:`chainbreak.core.ids.new_finding_id`
    (a wall-clock-seeded ULID): F8 requires ``analyze`` to be idempotent --
    byte-identical ``findings.json`` across two runs against the same bundle
    -- and a time-seeded id would break that on every single invocation."""
    payload = "|".join(
        (
            type.value,
            subject_kind,
            identity_id or "",
            edge_id or "",
            "" if hop_index is None else str(hop_index),
            ",".join(sorted(observation_refs)),
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"fnd_{digest[:26]}"


def _build(
    *,
    type: FindingType,  # noqa: A002 -- matches Finding.type by design
    severity_hint: SeverityHint,
    subject_kind: str,
    observation: str,
    expected_state: dict[str, Any],
    observed_state: dict[str, Any],
    security_interpretation: str,
    delta: dict[str, list[str]] | None = None,
    identity_id: IdentityId | None = None,
    edge_id: str | None = None,
    hop_index: int | None = None,
    drift_class: DriftClass | None = None,
    coverage: float = 1.0,
    cells: Sequence[ProbeCellResult] = (),
    policy_snapshot_ok: bool = True,
    caveats: tuple[str, ...] = (),
    observation_refs: tuple[str, ...] = (),
    confidence_override: Confidence | None = None,
) -> Finding:
    """Every rule funnels through here so confidence gating (F3) and
    evidence-reference bookkeeping happen exactly once.

    ``confidence_override`` bypasses the statistical gate for findings that
    are definitional facts about the run rather than claims about observed
    authority (``EXECUTION_ERROR``, ``CONFIGURATION_ERROR``): coverage and
    unanimity describe how much you trust a *measurement*, and these two
    finding types are not measurements, they are what the harness itself
    observed about its own apparatus.
    """
    if confidence_override is not None:
        confidence = confidence_override
        rationale = f"confidence set directly by the rule: {confidence.value.lower()}"
    else:
        confidence = gate_confidence(
            coverage=coverage, cells=cells, policy_snapshot_ok=policy_snapshot_ok
        )
        rationale = confidence_rationale(
            coverage=coverage, cells=cells, policy_snapshot_ok=policy_snapshot_ok
        )
    final_type = FindingType.INCONCLUSIVE if confidence is Confidence.INSUFFICIENT else type
    return Finding(
        finding_id=_deterministic_finding_id(
            type=final_type,
            subject_kind=subject_kind,
            identity_id=identity_id,
            edge_id=edge_id,
            hop_index=hop_index,
            observation_refs=observation_refs,
        ),
        type=final_type,
        severity_hint=severity_hint,
        confidence=confidence,
        subject_kind=subject_kind,
        identity_id=identity_id,
        edge_id=edge_id,
        hop_index=hop_index,
        observation=observation,
        expected_state=expected_state,
        observed_state=observed_state,
        delta=delta or {},
        security_interpretation=security_interpretation,
        confidence_rationale=rationale,
        caveats=caveats,
        drift_class=drift_class,
        evidence=FindingEvidence(observation_refs=observation_refs),
    )


# ---------------------------------------------------------------------------
# Authority-axis rules (per node / per edge)
# ---------------------------------------------------------------------------


def rule_expected_behavior(node: IdentityNode, cells: CellMap) -> Finding | None:
    if node.observed_authority is None or node.diverged:
        return None
    universe = sorted(cells)
    return _build(
        type=FindingType.EXPECTED_BEHAVIOR,
        severity_hint=SeverityHint.INFORMATIONAL,
        subject_kind="identity",
        observation=(
            f"{node.identity_id} returned observed authority matching expected authority "
            f"in all {len(universe)} probed capabilities at phase {node.observed_authority.phase}"
        ),
        expected_state={"capabilities": list(node.expected_authority.capabilities.sorted)},
        observed_state={"capabilities": list(node.observed_authority.capabilities.sorted)},
        security_interpretation="No divergence detected. This is a measurement, not a guarantee.",
        identity_id=node.identity_id,
        hop_index=node.hop_index,
        coverage=node.observed_authority.coverage,
        cells=list(cells.values()),
        observation_refs=_observation_refs(cells, universe),
    )


def rule_authority_expansion(
    node: IdentityNode, drift_class: DriftClass | None, cells: CellMap
) -> Finding | None:
    gain = node.unexpected_gain
    if not gain or drift_class not in (None, DriftClass.ORIGINATED):
        return None
    contributing = _contributing_cells(cells, list(gain))
    return _build(
        type=FindingType.AUTHORITY_EXPANSION,
        severity_hint=SeverityHint.REVIEW,
        subject_kind="identity",
        observation=(
            f"{node.identity_id} returned ALLOWED for {', '.join(sorted(gain))} in all trials "
            f"at phase {node.observed_authority.phase}"  # type: ignore[union-attr]
        ),
        expected_state={"capabilities": list(node.expected_authority.capabilities.sorted)},
        observed_state={"capabilities": list(node.observed_authority.capabilities.sorted)},  # type: ignore[union-attr]
        delta={"unexpected_gain": list(gain.sorted), "unexpected_loss": []},
        security_interpretation=(
            f"{node.identity_id} holds authority its delegation chain did not intend it to "
            "hold. Determine whether the capability originates from the identity's own "
            "permission policy rather than the delegated scope."
        ),
        identity_id=node.identity_id,
        hop_index=node.hop_index,
        drift_class=drift_class,
        coverage=node.observed_authority.coverage,  # type: ignore[union-attr]
        cells=contributing,
        observation_refs=_observation_refs(cells, list(gain)),
    )


def rule_authority_narrowing(node: IdentityNode, cells: CellMap) -> Finding | None:
    loss = node.unexpected_loss
    if not loss:
        return None
    contributing = _contributing_cells(cells, list(loss))
    return _build(
        type=FindingType.AUTHORITY_NARROWING,
        severity_hint=SeverityHint.INFORMATIONAL,
        subject_kind="identity",
        observation=(
            f"{node.identity_id} did not return ALLOWED for expected capabilities "
            f"{', '.join(sorted(loss))} at phase {node.observed_authority.phase}"  # type: ignore[union-attr]
        ),
        expected_state={"capabilities": list(node.expected_authority.capabilities.sorted)},
        observed_state={"capabilities": list(node.observed_authority.capabilities.sorted)},  # type: ignore[union-attr]
        delta={"unexpected_gain": [], "unexpected_loss": list(loss.sorted)},
        security_interpretation=(
            "Authority expected by the scenario was not observed. This is a narrowing, not "
            "necessarily a defect -- it may be a legitimate, tighter-than-intended grant."
        ),
        identity_id=node.identity_id,
        hop_index=node.hop_index,
        coverage=node.observed_authority.coverage,  # type: ignore[union-attr]
        cells=contributing,
        observation_refs=_observation_refs(cells, list(loss)),
    )


def rule_delegation_drift(
    node: IdentityNode,
    drift_class: DriftClass | None,
    origin_finding_id: str | None,
    cells: CellMap,
) -> Finding | None:
    """AUTHORIZATION_MODEL.md section 6's table gives ``AUTHORITY_EXPANSION``
    the predicate "unexpected_gain != empty at a node" and ``DELEGATION_DRIFT``
    "divergence at hop i>0 with a defined drift class" -- neither predicate
    excludes the other, and both are true for the *origin* of a gain at a
    non-root hop (``drift_class=ORIGINATED``). ``nc-non-monotone-chain.yaml``'s
    own ``expect_finding`` (``DELEGATION_DRIFT`` at the origin node itself,
    not only at a downstream node) confirms this reading, so this rule fires
    for ``ORIGINATED`` too -- alongside ``rule_authority_expansion``, not
    instead of it. A downstream ``PROPAGATED``/``AMPLIFIED`` node still
    produces only this finding, never ``AUTHORITY_EXPANSION`` (that rule's
    own predicate excludes it), matching AUTHORIZATION_MODEL.md section 7's
    worked example exactly: one ``AUTHORITY_EXPANSION`` at the origin, one
    ``DELEGATION_DRIFT`` downstream.
    """
    gain = node.unexpected_gain
    if (
        not gain
        or node.hop_index == 0
        or drift_class is None
        or drift_class is DriftClass.CORRECTED
    ):
        return None
    contributing = _contributing_cells(cells, list(gain))
    citation = f" citing {origin_finding_id} as its cause" if origin_finding_id else ""
    return _build(
        type=FindingType.DELEGATION_DRIFT,
        severity_hint=SeverityHint.REVIEW,
        subject_kind="identity",
        observation=(
            f"{node.identity_id} holds unexpected authority "
            f"{', '.join(sorted(gain))} ({drift_class.value})"
        ),
        expected_state={"capabilities": list(node.expected_authority.capabilities.sorted)},
        observed_state={"capabilities": list(node.observed_authority.capabilities.sorted)},  # type: ignore[union-attr]
        delta={"unexpected_gain": list(gain.sorted), "unexpected_loss": []},
        security_interpretation=(
            f"Divergence at an upstream hop propagated to {node.identity_id}{citation}. "
            "Remediation belongs at the origin hop, not here."
        ),
        identity_id=node.identity_id,
        hop_index=node.hop_index,
        drift_class=drift_class,
        coverage=node.observed_authority.coverage,  # type: ignore[union-attr]
        cells=contributing,
        observation_refs=_observation_refs(cells, list(gain)),
    )


def rule_authority_survival(
    edge: DelegationEdge, edge_div: EdgeDivergence, target_cells: CellMap
) -> Finding | None:
    """``target_cells`` is the delegation target's own cells -- confidence is
    gated on how well *its* observed authority (what ``survived_incorrectly``
    is computed from) was measured, the same way a node-level finding would
    be."""
    survived = edge_div.survived_incorrectly
    if not survived:
        return None
    contributing = _contributing_cells(target_cells, list(survived))
    coverage = len(contributing) / len(survived) if survived else 0.0
    return _build(
        type=FindingType.AUTHORITY_SURVIVAL,
        severity_hint=SeverityHint.INVESTIGATE,
        subject_kind="edge",
        observation=(
            f"edge {edge.edge_id} target holds {', '.join(sorted(survived))}, which the hop "
            "never intended to grant"
        ),
        expected_state={"intended_capabilities": list(edge.intended_capabilities.sorted)},
        observed_state={"survived_incorrectly": list(survived.sorted)},
        delta={"unexpected_gain": list(survived.sorted), "unexpected_loss": []},
        security_interpretation=(
            "The target of this delegation hop holds authority the hop never intended to "
            "grant. Because this is computed against the source's own observed authority, "
            "the hop itself -- not upstream drift -- is where this authority survived."
        ),
        edge_id=edge.edge_id,
        # subject_kind stays "edge" (AUTHORITY_SURVIVAL's predicate in
        # AUTHORIZATION_MODEL.md section 6 is edge-based), but the target
        # identity is also recorded: negative controls for this type name
        # the identity that ends up holding the survived authority, not the
        # edge id (see nc-surviving-authority.yaml's expect_finding).
        identity_id=edge.target_id,
        coverage=coverage,
        cells=contributing,
        observation_refs=_observation_refs(target_cells, list(survived)),
    )


# ---------------------------------------------------------------------------
# Timing-axis rules
# ---------------------------------------------------------------------------


def _poll_count_confidence(poll_count: int) -> Confidence:
    """Confidence for a poll-derived finding scales with how many serial
    samples back it -- there is no ``ProbeCellResult`` to gate on here, so
    this is timing's own analogue of coverage."""
    if poll_count >= 5:
        return Confidence.HIGH
    if poll_count >= 3:
        return Confidence.MEDIUM
    if poll_count >= 1:
        return Confidence.LOW
    return Confidence.INSUFFICIENT


def rule_no_transition_observed(measurement: RevocationMeasurement) -> Finding | None:
    if measurement.transition_observed:
        return None
    return _build(
        type=FindingType.NO_TRANSITION_OBSERVED,
        severity_hint=SeverityHint.INFORMATIONAL,
        subject_kind="identity",
        observation=(
            f"no ALLOWED->denied transition observed for {measurement.identity_id}/"
            f"{measurement.capability_id} within a {measurement.window_length_s:.1f}s window "
            f"({measurement.poll_count} polls at {measurement.poll_interval_ms}ms)"
        ),
        expected_state={},
        observed_state={"window_length_s": measurement.window_length_s},
        security_interpretation="An honest negative: the window closed without a transition.",
        identity_id=measurement.identity_id,
        confidence_override=_poll_count_confidence(measurement.poll_count),
    )


def rule_revocation_delay(
    measurement: RevocationMeasurement, expectation: CompiledExpectation | None
) -> Finding | None:
    """Fires only when an ``assertive`` ``revocation_within`` expectation was
    exceeded (SCORING_MODEL.md): CHAINBREAK does not assert a normative
    propagation time without the scenario author having justified one."""
    if (
        not measurement.transition_observed
        or measurement.transition_window is None
        or expectation is None
        or expectation.kind != "revocation_within"
        or expectation.severity != "assertive"
        or expectation.max_seconds is None
        or measurement.transition_window.low <= expectation.max_seconds
    ):
        return None
    return _build(
        type=FindingType.REVOCATION_DELAY,
        severity_hint=SeverityHint.INVESTIGATE,
        subject_kind="identity",
        observation=(
            f"transition window lower bound {measurement.transition_window.low:.2f}s exceeds "
            f"the declared threshold of {expectation.max_seconds:.2f}s"
        ),
        expected_state={"max_seconds": expectation.max_seconds},
        observed_state={
            "transition_window": {
                "low": measurement.transition_window.low,
                "high": measurement.transition_window.high,
            }
        },
        security_interpretation=(
            "The scenario declared an assertive expectation that revocation would take no "
            f"longer than {expectation.max_seconds:.2f}s; the observed window's lower bound "
            "exceeded it."
        ),
        identity_id=measurement.identity_id,
        # A clean bracketed transition is exact interval math, not a
        # statistical claim over repeated trials -- HIGH by construction.
        confidence_override=Confidence.HIGH,
        caveats=("Single run; not repeated across sessions.",),
    )


# ---------------------------------------------------------------------------
# Stale-authority rules
# ---------------------------------------------------------------------------

_STALE_FINDING_CLASSES = {"STALE_AUTHORITY_LIVE_CREDENTIAL", "SESSION_SCOPE_CACHED"}


def rule_stale_authority(measurement: StaleAuthorityMeasurement) -> Finding | None:
    if measurement.classification.value not in _STALE_FINDING_CLASSES:
        return None
    return _build(
        type=FindingType.STALE_AUTHORITY,
        severity_hint=SeverityHint.INFORMATIONAL,
        subject_kind="credential",
        observation=(
            f"{measurement.identity_id}/{measurement.capability_id} classified "
            f"{measurement.classification.value} after a {measurement.deferral_seconds:.1f}s "
            "deferral"
        ),
        expected_state={},
        observed_state={"classification": measurement.classification.value},
        security_interpretation=(
            "Documented bearer-token behavior: a credential issued before a policy change "
            "remains honored until it expires or is otherwise invalidated. Not a defect; "
            "the stale window's duration is the interesting quantity."
        ),
        identity_id=measurement.identity_id,
        # A single deferred-vs-fresh-credential pair (M13's design element),
        # not a repeated-trial statistic -- MEDIUM reflects n=1, not doubt
        # about the classification itself.
        confidence_override=Confidence.MEDIUM,
    )


def rule_expired_credential_accepted(measurement: StaleAuthorityMeasurement) -> Finding | None:
    if measurement.classification.value != "EXPIRED_CREDENTIAL_HONORED":
        return None
    return _build(
        type=FindingType.EXPIRED_CREDENTIAL_ACCEPTED,
        severity_hint=SeverityHint.INVESTIGATE,
        subject_kind="credential",
        observation=(
            f"{measurement.identity_id}/{measurement.capability_id} was ALLOWED using a "
            "credential past its recorded expires_at"
        ),
        expected_state={},
        observed_state={"classification": measurement.classification.value},
        security_interpretation=(
            "An expired credential was honored. This contradicts documented credential "
            "lifetime behavior and would warrant escalation."
        ),
        identity_id=measurement.identity_id,
        # A binary fact (allowed past a recorded expiry), not a sampled
        # measurement.
        confidence_override=Confidence.HIGH,
    )


# ---------------------------------------------------------------------------
# Task / credential / run-level rules
# ---------------------------------------------------------------------------

#: M14, AC5/ADR-007: every finding this family produces must carry this
#: scope statement -- v0.1's worker is a deterministic, synthetic
#: implementation, so a task-contract finding measures CHAINBREAK's own
#: contract-checking, not real agent behavior. It becomes a measurement of
#: agent behavior only once a v0.4 LLM-backed worker implements the same
#: TaskWorker Protocol.
_SYNTHETIC_WORKER_CAVEAT = (
    "v0.1's worker is a deterministic, synthetic implementation of the TaskWorker Protocol. "
    "This finding measures the harness's own contract-checking, not real agent behavior."
)


def rule_silent_narrowing(task: TaskOutcome) -> Finding | None:
    if not (task.claims_complete_but_is_not or task.claims_output_that_does_not_exist):
        return None
    return _build(
        type=FindingType.SILENT_NARROWING,
        severity_hint=SeverityHint.INVESTIGATE,
        subject_kind="task",
        observation=(
            f"task {task.task_id} ({task.worker}) reported {task.status.value} while "
            f"{task.steps_succeeded}/{task.steps_total} steps actually succeeded"
        ),
        expected_state={"steps_total": task.steps_total},
        observed_state={
            "steps_succeeded": task.steps_succeeded,
            "output_marker_verified_independently": task.output_marker_verified_independently,
        },
        security_interpretation=(
            "The task reported success while an independent check of its own side effects "
            "disagrees. A caller trusting the self-report alone would not detect this."
        ),
        identity_id=task.identity_id,
        # An independently-verified side-effect check (bootstrap-confirmed
        # marker presence), not a sampled measurement.
        confidence_override=Confidence.HIGH,
        caveats=(_SYNTHETIC_WORKER_CAVEAT,),
    )


def rule_capability_substituted(task: TaskOutcome, *, must_not_substitute: bool) -> Finding | None:
    """M14, F5: reported distinctly from ``rule_silent_narrowing``, never
    collapsed into it, even though both can fire for the same task.
    ``must_not_substitute`` comes from the task's own declared
    ``completion_contract`` -- a scenario that permits substitution never
    triggers this, regardless of what the invocation log shows."""
    if not must_not_substitute or not task.substituted_capabilities:
        return None
    return _build(
        type=FindingType.CAPABILITY_SUBSTITUTED,
        severity_hint=SeverityHint.INVESTIGATE,
        subject_kind="task",
        observation=(
            f"task {task.task_id} ({task.worker}) invoked "
            f"{', '.join(task.substituted_capabilities.sorted)} in place of a declared step's "
            "capability"
        ),
        expected_state={"must_not_substitute": True},
        observed_state={"substituted_capabilities": list(task.substituted_capabilities.sorted)},
        security_interpretation=(
            "The task's completion contract forbids substituting a different capability for a "
            "declared step. A caller trusting the declared step list alone would not detect this."
        ),
        identity_id=task.identity_id,
        # Objectively observed from the executor's own invocation log
        # (execution/task_runner.py), never the worker's self-report.
        confidence_override=Confidence.HIGH,
        caveats=(_SYNTHETIC_WORKER_CAVEAT,),
    )


def rule_redelegation_attempted(task: TaskOutcome, *, must_not_redelegate: bool) -> Finding | None:
    """M14, F5/S2: reported distinctly from ``rule_silent_narrowing``. The
    attempt itself is always refused by the executor regardless of this
    rule -- this finding exists because a worker *willing* to try is itself
    worth reporting, independent of whether the attempt could ever have
    succeeded."""
    if not must_not_redelegate or task.redelegation_attempts == 0:
        return None
    return _build(
        type=FindingType.REDELEGATION_ATTEMPTED,
        severity_hint=SeverityHint.INVESTIGATE,
        subject_kind="task",
        observation=(
            f"task {task.task_id} ({task.worker}) attempted redelegation "
            f"{task.redelegation_attempts} time(s); refused and recorded (S2)"
        ),
        expected_state={"must_not_redelegate": True},
        observed_state={"redelegation_attempts": task.redelegation_attempts},
        security_interpretation=(
            "The task's completion contract forbids seeking authority elsewhere. The attempt "
            "was refused before it could reach the provider, but a worker willing to try is "
            "itself the finding."
        ),
        identity_id=task.identity_id,
        confidence_override=Confidence.HIGH,
        caveats=(_SYNTHETIC_WORKER_CAVEAT,),
    )


def rule_lifetime_capped(credential: CredentialRecord) -> Finding | None:
    if not credential.lifetime_capped:
        return None
    return _build(
        type=FindingType.LIFETIME_CAPPED,
        severity_hint=SeverityHint.INFORMATIONAL,
        subject_kind="credential",
        observation=(
            f"credential for {credential.identity_id} requested "
            f"{credential.requested_duration_s}s, granted {credential.granted_duration_s}s"
        ),
        expected_state={"requested_duration_s": credential.requested_duration_s},
        observed_state={"granted_duration_s": credential.granted_duration_s},
        security_interpretation=(
            "The provider capped the credential's lifetime below what was requested -- "
            "commonly a role-chaining ceiling. Documented behavior, recorded as data."
        ),
        identity_id=credential.identity_id,
        # A direct comparison of two recorded integers -- no sampling.
        confidence_override=Confidence.HIGH,
    )


def rule_execution_error(status: str) -> Finding | None:
    if status != "ABORTED_ERROR":
        return None
    return _build(
        type=FindingType.EXECUTION_ERROR,
        severity_hint=SeverityHint.INVESTIGATE,
        subject_kind="run",
        observation="the run's manifest recorded status ABORTED_ERROR",
        expected_state={"status": "COMPLETED"},
        observed_state={"status": status},
        security_interpretation="Run orchestration failed; results from this run are unreliable.",
        confidence_override=Confidence.HIGH,
    )


def rule_configuration_error(
    identity_id: IdentityId, capability_id: CapabilityId, reason: str
) -> Finding:
    """``identity.whoami``'s failure is an apparatus fault, never a denial
    (AUTH-1's control-capability exemption). Called by the pipeline once per
    discarded matrix, never as a candidate that might return ``None``."""
    return _build(
        type=FindingType.CONFIGURATION_ERROR,
        severity_hint=SeverityHint.INVESTIGATE,
        subject_kind="identity",
        observation=f"{identity_id}: control capability {capability_id} failed ({reason})",
        expected_state={},
        observed_state={"reason": reason},
        security_interpretation=(
            "The control capability failed, which invalidates every other measurement in "
            "this matrix -- discarded rather than recorded as a wave of denials."
        ),
        identity_id=identity_id,
        confidence_override=Confidence.HIGH,
    )
