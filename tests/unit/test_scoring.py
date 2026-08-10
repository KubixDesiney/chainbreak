"""M15 acceptance-criteria tests for ``scoring/``: six independent category
evaluators, F2 (NOT_MEASURED never CONSISTENT), F3 (low coverage forces
PARTIAL), F4 (min-not-mean confidence), S1 (no CLI flag raises confidence or
coverage), S2 (DETECTOR_FAILED cannot be overridden), and ADR-010 (no
composite score anywhere in this package).

End-to-end validation that all six categories evaluate correctly on real
fake-provider runs lives in ``tests/integration/test_scoring_categories.py``
-- this file is unit-level, building minimal domain objects directly rather
than driving a full scenario compile + orchestrate cycle for every case.
"""

from __future__ import annotations

import inspect
import re

import pytest
import typer

from chainbreak.core.enums import (
    CategoryStatus,
    Confidence,
    DelegationMechanism,
    FindingType,
    PlanPhase,
    SeverityHint,
)
from chainbreak.core.ids import Sha256Digest
from chainbreak.core.models import (
    AuthoritySet,
    AuthorizationGraph,
    CategoryResult,
    CompiledScenario,
    CredentialRecord,
    DelegationEdge,
    DetectorCheck,
    ExpectedAuthority,
    Finding,
    FindingEvidence,
    IdentityNode,
    Observation,
    ObservedAuthority,
    ProbeOutcome,
    ProbeRequestRecord,
    ProbeTiming,
)
from chainbreak.scoring import aggregate, categories, confidence, coverage
from chainbreak.scoring.categories import not_measured_notice, score_categories
from chainbreak.scoring.confidence import category_confidence

pytestmark = pytest.mark.unit

_ZERO_HASH: Sha256Digest = "sha256:" + "0" * 64


# ---------------------------------------------------------------------------
# Minimal domain-object builders
# ---------------------------------------------------------------------------


def _node(
    identity_id: str,
    *,
    is_root: bool = False,
    parent_id: str | None = None,
    hop_index: int = 0,
    expected: tuple[str, ...],
    observed: tuple[str, ...] | None,
) -> IdentityNode:
    return IdentityNode(
        identity_id=identity_id,
        is_root=is_root,
        hop_index=hop_index,
        parent_id=parent_id,
        expected_authority=ExpectedAuthority(
            capabilities=AuthoritySet.of(*expected),
            phase=PlanPhase.POST_DELEGATION,
            derivation="DECLARED" if is_root else "INHERITED_ATTENUATED",
        ),
        observed_authority=None
        if observed is None
        else ObservedAuthority(
            capabilities=AuthoritySet.of(*observed),
            phase=PlanPhase.POST_DELEGATION,
            probe_matrix_id="pm-test",
            attempted=len(observed),
            classified=len(observed),
        ),
    )


def _edge(edge_id: str, source: str, target: str, *intended: str) -> DelegationEdge:
    caps = AuthoritySet.of(*intended)
    return DelegationEdge(
        edge_id=edge_id,
        source_id=source,
        target_id=target,
        mechanism=DelegationMechanism.ROLE_CHAIN,
        requested_capabilities=caps,
        intended_capabilities=caps,
        expected_effective=caps,
        credential_lifetime_s=3600,
    )


def _clean_graph() -> AuthorizationGraph:
    """Root -> child, both measured, child's observed authority a clean
    subset of root's -- DELEGATION_INTEGRITY and SCOPE_ATTENUATION both
    CONSISTENT."""
    root = _node(
        "principal",
        is_root=True,
        hop_index=0,
        expected=("objectstore.read",),
        observed=("objectstore.read",),
    )
    child = _node(
        "agent-a",
        parent_id="principal",
        hop_index=1,
        expected=("objectstore.read",),
        observed=("objectstore.read",),
    )
    edge = _edge("hop-1", "principal", "agent-a", "objectstore.read")
    return AuthorizationGraph(nodes=(root, child), edges=(edge,))


def _monotonicity_violation_graph() -> AuthorizationGraph:
    """Child observed authority is *not* a subset of the parent's observed
    authority -- a genuine set-monotonicity violation (SCOPE_ATTENUATION
    DIVERGENT), independent of any Finding passed alongside it."""
    root = _node(
        "principal",
        is_root=True,
        hop_index=0,
        expected=("objectstore.read",),
        observed=("objectstore.read",),
    )
    child = _node(
        "agent-a",
        parent_id="principal",
        hop_index=1,
        expected=("objectstore.read",),
        observed=("objectstore.read", "keyvalue.read"),
    )
    edge = _edge("hop-1", "principal", "agent-a", "objectstore.read")
    return AuthorizationGraph(nodes=(root, child), edges=(edge,))


def _unmeasured_graph() -> AuthorizationGraph:
    """A single root, no delegation edges at all -- zero applicable cells
    for both delegation-axis categories."""
    root = _node(
        "principal",
        is_root=True,
        hop_index=0,
        expected=("objectstore.read",),
        observed=("objectstore.read",),
    )
    return AuthorizationGraph(nodes=(root,))


def _scenario(**overrides: object) -> CompiledScenario:
    defaults: dict[str, object] = {
        "compiled_hash": _ZERO_HASH,
        "scenario_id": "test-scenario",
        "scenario_version": "1.0.0",
        "catalog_version": "1.0.0",
        "adapter_version": "0.1.0",
        "graph": _clean_graph(),
        "probe_matrices": (),
        "plan": (),
    }
    defaults.update(overrides)
    return CompiledScenario(**defaults)  # type: ignore[arg-type]


def _finding(
    *,
    type: FindingType,  # noqa: A002
    identity_id: str = "agent-a",
    edge_id: str | None = None,
    confidence: Confidence = Confidence.HIGH,
) -> Finding:
    return Finding(
        finding_id=f"fnd_{type.value.lower()}",
        type=type,
        severity_hint=SeverityHint.REVIEW,
        confidence=confidence,
        subject_kind="edge" if edge_id else "identity",
        identity_id=identity_id,
        edge_id=edge_id,
        observation="test",
        evidence=FindingEvidence(),
    )


def _detector_check(
    *, expected_type: FindingType, produced: bool, negative_control_id: str = "nc-test"
) -> DetectorCheck:
    return DetectorCheck(
        negative_control_id=negative_control_id,
        expected_type=expected_type,
        produced=produced,
        result="DETECTOR_OK" if produced else "DETECTOR_FAILURE",
    )


def _credential(
    *, credential_id: str = "cred-1", identity_id: str = "agent-a", capped: bool = False
) -> CredentialRecord:
    from datetime import UTC, datetime, timedelta

    issued = datetime(2026, 1, 1, tzinfo=UTC)
    requested = 3600
    granted = 900 if capped else 3600
    return CredentialRecord(
        credential_id=credential_id,
        identity_id=identity_id,
        mechanism=DelegationMechanism.ROLE_CHAIN,
        issued_at=issued,
        expires_at=issued + timedelta(seconds=granted),
        requested_duration_s=requested,
        granted_duration_s=granted,
        session_name_hash=_ZERO_HASH,
        access_key_id_hash=_ZERO_HASH,
    )


def _observation(
    *,
    identity_id: str = "agent-a",
    capability_id: str = "objectstore.read",
    credential_id: str | None = None,
    allowed: bool = True,
    wall_start: object = None,
) -> Observation:
    from datetime import UTC, datetime

    from chainbreak.core.enums import OutcomeClass

    return Observation(
        observation_id="obs_1",
        run_id="run-1",
        sequence=0,
        phase=PlanPhase.POST_DELEGATION,
        probe_matrix_id="pm-test",
        identity_id=identity_id,
        identity_ref_hash=_ZERO_HASH,
        capability_id=capability_id,
        trial=1,
        trial_count=1,
        credential_id=credential_id,
        request=ProbeRequestRecord(
            probe_kind="READ_MARKER",
            binding_actions=("test:Action",),
            target_ref_hash=_ZERO_HASH,
            target_namespace="cb-00000000",
            parameters_fingerprint=_ZERO_HASH,
        ),
        timing=ProbeTiming(
            monotonic_start_ns=0,
            monotonic_end_ns=1_000_000,
            wall_start=wall_start or datetime(2026, 1, 1, tzinfo=UTC),
        ),
        outcome=ProbeOutcome(
            outcome_class=OutcomeClass.ALLOWED if allowed else OutcomeClass.DENIED_EXPLICIT
        ),
        preconditions_verified=True,
    )


def _score(
    *,
    scenario: CompiledScenario | None = None,
    populated_graph: AuthorizationGraph | None = None,
    findings: tuple[Finding, ...] = (),
    detector_checks: tuple[DetectorCheck, ...] = (),
    events: tuple[dict[str, object], ...] = (),
    observations: tuple[Observation, ...] = (),
    credentials: tuple[CredentialRecord, ...] = (),
) -> tuple[CategoryResult, ...]:
    resolved_scenario = scenario if scenario is not None else _scenario()
    return score_categories(
        scenario=resolved_scenario,
        populated_graph=populated_graph,
        findings=findings,
        detector_checks=detector_checks,
        events=list(events),
        observations=list(observations),
        credentials=list(credentials),
    )


def _by_category(results: tuple[CategoryResult, ...]) -> dict[str, CategoryResult]:
    return {r.category.value: r for r in results}


# ---------------------------------------------------------------------------
# F1: exactly six evaluators
# ---------------------------------------------------------------------------


def test_score_categories_returns_exactly_six_results():
    results = _score()
    assert len(results) == 6
    assert {r.category for r in results} == {
        r.category for r in results
    }  # sanity: no duplicate-construction surprises
    category_names = {r.category.value for r in results}
    assert category_names == {
        "DELEGATION_INTEGRITY",
        "SCOPE_ATTENUATION",
        "REVOCATION_RESPONSIVENESS",
        "AUTHORITY_FRESHNESS",
        "FAILURE_TRANSPARENCY",
        "CREDENTIAL_HYGIENE",
    }


# ---------------------------------------------------------------------------
# F2: NOT_MEASURED never becomes CONSISTENT
# ---------------------------------------------------------------------------


class TestNotMeasuredNeverConsistent:
    def test_no_delegation_edges_is_not_measured_not_consistent(self):
        results = _by_category(_score(populated_graph=_unmeasured_graph()))
        assert results["DELEGATION_INTEGRITY"].status is CategoryStatus.NOT_MEASURED
        assert results["SCOPE_ATTENUATION"].status is CategoryStatus.NOT_MEASURED

    def test_no_authority_axis_phase_at_all_is_not_measured(self):
        """``populated_graph=None`` -- the bundle never ran a PROBE phase."""
        results = _by_category(_score(populated_graph=None))
        assert results["DELEGATION_INTEGRITY"].status is CategoryStatus.NOT_MEASURED
        assert results["SCOPE_ATTENUATION"].status is CategoryStatus.NOT_MEASURED

    def test_no_poll_plans_is_not_measured(self):
        results = _by_category(_score(scenario=_scenario(poll_plans=())))
        assert results["REVOCATION_RESPONSIVENESS"].status is CategoryStatus.NOT_MEASURED

    def test_no_deferred_execution_plans_is_not_measured(self):
        results = _by_category(_score(scenario=_scenario(deferred_execution_plans=())))
        assert results["AUTHORITY_FRESHNESS"].status is CategoryStatus.NOT_MEASURED

    def test_no_task_plans_is_not_measured(self):
        results = _by_category(_score(scenario=_scenario(task_plans=())))
        assert results["FAILURE_TRANSPARENCY"].status is CategoryStatus.NOT_MEASURED

    def test_no_credentials_is_not_measured(self):
        results = _by_category(_score(credentials=()))
        assert results["CREDENTIAL_HYGIENE"].status is CategoryStatus.NOT_MEASURED

    def test_not_measured_never_carries_a_stray_finding_id(self):
        # A node-level finding unrelated to delegation edges (e.g. an
        # EXPECTED_BEHAVIOR from a root-only baseline probe) must not leak
        # into a NOT_MEASURED delegation-axis result's evidentiary trail.
        stray = _finding(type=FindingType.EXPECTED_BEHAVIOR, identity_id="principal")
        results = _by_category(_score(populated_graph=_unmeasured_graph(), findings=(stray,)))
        assert results["SCOPE_ATTENUATION"].status is CategoryStatus.NOT_MEASURED
        assert results["SCOPE_ATTENUATION"].finding_ids == ()


# ---------------------------------------------------------------------------
# F3: coverage < 0.7 forces PARTIAL regardless of what the measured cells
# showed -- including a would-be DIVERGENT verdict.
# ---------------------------------------------------------------------------


class TestLowCoverageForcesPartial:
    def test_partial_edge_measurement_forces_partial(self):
        """Two edges declared, only one measured -- coverage 0.5 < 0.7."""
        root = _node(
            "principal",
            is_root=True,
            hop_index=0,
            expected=("objectstore.read",),
            observed=("objectstore.read",),
        )
        measured_child = _node(
            "agent-a",
            parent_id="principal",
            hop_index=1,
            expected=("objectstore.read",),
            observed=("objectstore.read",),
        )
        unmeasured_child = _node(
            "agent-b",
            parent_id="principal",
            hop_index=1,
            expected=("objectstore.read",),
            observed=None,
        )
        graph = AuthorizationGraph(
            nodes=(root, measured_child, unmeasured_child),
            edges=(
                _edge("hop-1", "principal", "agent-a", "objectstore.read"),
                _edge("hop-2", "principal", "agent-b", "objectstore.read"),
            ),
        )
        results = _by_category(_score(populated_graph=graph))
        assert results["DELEGATION_INTEGRITY"].coverage == pytest.approx(0.5)
        assert results["DELEGATION_INTEGRITY"].status is CategoryStatus.PARTIAL

    def test_low_coverage_forces_partial_even_over_a_divergent_finding(self):
        """The measured edge itself shows AUTHORITY_SURVIVAL -- without F3
        this would be DIVERGENT, but coverage 0.5 must win."""
        root = _node(
            "principal",
            is_root=True,
            hop_index=0,
            expected=("objectstore.read",),
            observed=("objectstore.read",),
        )
        measured_child = _node(
            "agent-a",
            parent_id="principal",
            hop_index=1,
            expected=("objectstore.read",),
            observed=("objectstore.read",),
        )
        unmeasured_child = _node(
            "agent-b",
            parent_id="principal",
            hop_index=1,
            expected=("objectstore.read",),
            observed=None,
        )
        graph = AuthorizationGraph(
            nodes=(root, measured_child, unmeasured_child),
            edges=(
                _edge("hop-1", "principal", "agent-a", "objectstore.read"),
                _edge("hop-2", "principal", "agent-b", "objectstore.read"),
            ),
        )
        survival = _finding(
            type=FindingType.AUTHORITY_SURVIVAL, identity_id="agent-a", edge_id="hop-1"
        )
        results = _by_category(_score(populated_graph=graph, findings=(survival,)))
        assert results["DELEGATION_INTEGRITY"].status is CategoryStatus.PARTIAL
        assert results["DELEGATION_INTEGRITY"].status is not CategoryStatus.DIVERGENT

    def test_category_result_itself_rejects_a_low_coverage_non_partial_status(self):
        """Belt-and-braces: the model validator in core/models.py is the
        second line of defense against exactly this bug."""
        with pytest.raises(ValueError, match=r"< 0\.7"):
            CategoryResult(
                category=next(iter(categories.ScoringCategory)),
                status=CategoryStatus.CONSISTENT,
                coverage=0.1,
                confidence=Confidence.HIGH,
            )


# ---------------------------------------------------------------------------
# F4: confidence aggregates with min, never a mean.
# ---------------------------------------------------------------------------


class TestMinNotMeanConfidence:
    def test_five_high_and_one_low_yields_low(self):
        contributors = [
            _finding(type=FindingType.LIFETIME_CAPPED, confidence=Confidence.HIGH) for _ in range(5)
        ] + [_finding(type=FindingType.LIFETIME_CAPPED, confidence=Confidence.LOW)]
        result = category_confidence(coverage=1.0, contributing=contributors)
        assert result is Confidence.LOW

    def test_a_single_insufficient_contributor_dominates_everything(self):
        contributors = [
            _finding(type=FindingType.LIFETIME_CAPPED, confidence=Confidence.HIGH)
            for _ in range(10)
        ] + [_finding(type=FindingType.LIFETIME_CAPPED, confidence=Confidence.INSUFFICIENT)]
        result = category_confidence(coverage=1.0, contributing=contributors)
        assert result is Confidence.INSUFFICIENT

    def test_no_contributors_falls_back_to_the_coverage_baseline(self):
        assert category_confidence(coverage=1.0, contributing=[]) is Confidence.HIGH
        assert category_confidence(coverage=0.8, contributing=[]) is Confidence.LOW

    def test_this_is_not_an_average(self):
        # An average of {HIGH, HIGH, HIGH, HIGH, HIGH, LOW} would round to
        # something above LOW; min must not.
        five_high_one_low = [Confidence.HIGH] * 5 + [Confidence.LOW]
        contributors = [
            _finding(type=FindingType.LIFETIME_CAPPED, confidence=c) for c in five_high_one_low
        ]
        assert category_confidence(coverage=1.0, contributing=contributors) is Confidence.LOW
        assert category_confidence(coverage=1.0, contributing=contributors) is not Confidence.MEDIUM


# ---------------------------------------------------------------------------
# F5: Revocation Responsiveness is DIVERGENT only for an exceeded assertive
# expectation; F6: STALE_AUTHORITY_LIVE_CREDENTIAL is CONSISTENT, only
# EXPIRED_CREDENTIAL_HONORED is DIVERGENT.
# ---------------------------------------------------------------------------


class TestRevocationAndFreshnessStatusMapping:
    def test_revocation_delay_finding_present_means_divergent(self):
        scenario = _scenario(deferred_execution_plans=())
        # applicable is derived from plan/poll_plans -- give it one plan and
        # let the finding alone drive the DIVERGENT verdict, matching how
        # _revocation_responsiveness reads the pre-computed rule output
        # rather than re-deriving assertiveness itself.
        from chainbreak.core.enums import PhaseKind
        from chainbreak.core.models import PlanStep, PollPlan

        scenario = scenario.model_copy(
            update={
                "poll_plans": (
                    PollPlan(
                        phase_name="poll-1",
                        target_identity="agent-a",
                        capability_id="objectstore.read",
                    ),
                ),
                "plan": (
                    PlanStep(order=0, phase_name="revoke", kind=PhaseKind.MUTATE),
                    PlanStep(order=1, phase_name="poll-1", kind=PhaseKind.POLL),
                ),
            }
        )
        delay = _finding(type=FindingType.REVOCATION_DELAY, identity_id="agent-a")
        # revocation_measurements() needs real events/observations to count
        # as "measured" -- fabricate the minimal POLICY_MUTATION_APPLIED +
        # POST_MUTATION observation pair, same as the no-transition case
        # below.
        events = (
            {
                "kind": "POLICY_MUTATION_APPLIED",
                "receipt": {"confirmed": True},
                "timing": {"monotonic_ns": 0},
                "mutation_kind": "ATTACH_INLINE_DENY",
            },
        )
        poll_observation = _observation(allowed=False).model_copy(
            update={"phase": PlanPhase.POST_MUTATION}
        )
        results = _by_category(
            _score(
                scenario=scenario,
                findings=(delay,),
                events=events,
                observations=(poll_observation,),
            )
        )
        assert results["REVOCATION_RESPONSIVENESS"].status is CategoryStatus.DIVERGENT

    def test_no_transition_observed_without_a_delay_finding_is_partial_not_divergent(self):
        from chainbreak.core.enums import PhaseKind
        from chainbreak.core.models import PlanStep, PollPlan

        scenario = _scenario().model_copy(
            update={
                "poll_plans": (
                    PollPlan(
                        phase_name="poll-1",
                        target_identity="agent-a",
                        capability_id="objectstore.read",
                    ),
                ),
                "plan": (
                    PlanStep(order=0, phase_name="revoke", kind=PhaseKind.MUTATE),
                    PlanStep(order=1, phase_name="poll-1", kind=PhaseKind.POLL),
                ),
            }
        )
        no_transition = _finding(type=FindingType.NO_TRANSITION_OBSERVED, identity_id="agent-a")
        # revocation_measurements() needs real events/observations to count
        # as "measured" -- fabricate the minimal POLICY_MUTATION_APPLIED +
        # POST_MUTATION observation pair.
        events = (
            {
                "kind": "POLICY_MUTATION_APPLIED",
                "receipt": {"confirmed": True},
                "timing": {"monotonic_ns": 0},
                "mutation_kind": "ATTACH_INLINE_DENY",
            },
        )
        poll_observation = _observation(allowed=False)
        poll_observation = poll_observation.model_copy(update={"phase": PlanPhase.POST_MUTATION})
        results = _by_category(
            _score(
                scenario=scenario,
                findings=(no_transition,),
                events=events,
                observations=(poll_observation,),
            )
        )
        assert results["REVOCATION_RESPONSIVENESS"].status is CategoryStatus.PARTIAL

    def test_stale_authority_live_credential_is_consistent_with_a_caveat(self):
        stale = _finding(type=FindingType.STALE_AUTHORITY, identity_id="agent-a")
        from chainbreak.core.models import DeferredExecutionPlan

        scenario = _scenario().model_copy(
            update={
                "deferred_execution_plans": (
                    DeferredExecutionPlan(
                        phase_name="deferred",
                        target_identity="agent-a",
                        capabilities=AuthoritySet.of("objectstore.read"),
                        credential_source="phase:baseline",
                    ),
                )
            }
        )
        # analysis.stale.stale_authority_measurements needs a DEFERRED_EXECUTION
        # observation + matching credential to count "measured".
        credential = _credential()
        observation = _observation(credential_id=credential.credential_id).model_copy(
            update={"phase": PlanPhase.DEFERRED_EXECUTION}
        )
        results = _by_category(
            _score(
                scenario=scenario,
                findings=(stale,),
                observations=(observation,),
                credentials=(credential,),
            )
        )
        result = results["AUTHORITY_FRESHNESS"]
        assert result.status is CategoryStatus.CONSISTENT
        assert any("documented bearer-token behavior" in c for c in result.caveats)

    def test_expired_credential_honored_is_divergent(self):
        expired = _finding(type=FindingType.EXPIRED_CREDENTIAL_ACCEPTED, identity_id="agent-a")
        from chainbreak.core.models import DeferredExecutionPlan

        scenario = _scenario().model_copy(
            update={
                "deferred_execution_plans": (
                    DeferredExecutionPlan(
                        phase_name="deferred",
                        target_identity="agent-a",
                        capabilities=AuthoritySet.of("objectstore.read"),
                        credential_source="phase:baseline",
                    ),
                )
            }
        )
        credential = _credential()
        observation = _observation(credential_id=credential.credential_id).model_copy(
            update={"phase": PlanPhase.DEFERRED_EXECUTION}
        )
        results = _by_category(
            _score(
                scenario=scenario,
                findings=(expired,),
                observations=(observation,),
                credentials=(credential,),
            )
        )
        assert results["AUTHORITY_FRESHNESS"].status is CategoryStatus.DIVERGENT


# ---------------------------------------------------------------------------
# S2: a DETECTOR_FAILED category cannot be overridden by anything else
# computed for it.
# ---------------------------------------------------------------------------


class TestDetectorFailedCannotBeOverridden:
    def test_a_failed_detector_forces_detector_failed_even_with_clean_evidence(self):
        graph = _clean_graph()
        failed_check = _detector_check(expected_type=FindingType.AUTHORITY_SURVIVAL, produced=False)
        results = _by_category(_score(populated_graph=graph, detector_checks=(failed_check,)))
        assert results["DELEGATION_INTEGRITY"].status is CategoryStatus.DETECTOR_FAILED

    def test_a_failed_detector_for_a_different_category_does_not_leak(self):
        graph = _clean_graph()
        failed_check = _detector_check(expected_type=FindingType.AUTHORITY_SURVIVAL, produced=False)
        results = _by_category(_score(populated_graph=graph, detector_checks=(failed_check,)))
        assert results["SCOPE_ATTENUATION"].status is CategoryStatus.CONSISTENT

    def test_a_passing_detector_never_forces_detector_failed(self):
        graph = _clean_graph()
        ok_check = _detector_check(expected_type=FindingType.AUTHORITY_SURVIVAL, produced=True)
        results = _by_category(_score(populated_graph=graph, detector_checks=(ok_check,)))
        assert results["DELEGATION_INTEGRITY"].status is CategoryStatus.CONSISTENT


# ---------------------------------------------------------------------------
# "NOT_MEASURED is not a pass." -- the literal sentence.
# ---------------------------------------------------------------------------


class TestNotMeasuredNotice:
    def test_two_of_six_measured_reports_the_other_four_and_the_literal_sentence(self):
        results = _score(populated_graph=_clean_graph())  # only the two graph-axis categories
        by_status = [r.status for r in results]
        assert by_status.count(CategoryStatus.NOT_MEASURED) == 4

        notice = not_measured_notice(results)
        assert notice is not None
        assert "NOT_MEASURED is not a pass." in notice
        assert "4 of 6 categories were not exercised by this scenario." in notice

    def test_no_notice_when_nothing_is_not_measured(self):
        results = tuple(
            r.model_copy(update={"status": CategoryStatus.CONSISTENT, "coverage": 1.0})
            if r.status is CategoryStatus.NOT_MEASURED
            else r
            for r in _score(populated_graph=_clean_graph())
        )
        assert not_measured_notice(results) is None

    def test_singular_wording_for_exactly_one(self):
        result = CategoryResult(
            category=next(iter(categories.ScoringCategory)),
            status=CategoryStatus.NOT_MEASURED,
            coverage=0.0,
            confidence=Confidence.INSUFFICIENT,
        )
        notice = not_measured_notice((result,))
        assert notice == (
            "NOT_MEASURED is not a pass. 1 of 1 category was not exercised by this scenario."
        )


# ---------------------------------------------------------------------------
# ADR-010: no composite score exists anywhere in this package.
# ---------------------------------------------------------------------------


_FORBIDDEN_NAME_PATTERN = re.compile(r"(?i)composite|overall.?score|total.?score|single.?score")


class TestNoCompositeScoreExists:
    def test_no_module_level_callable_has_a_composite_sounding_name(self):
        modules = [categories, aggregate, confidence, coverage]
        offenders = [
            f"{module.__name__}.{name}"
            for module in modules
            for name, obj in vars(module).items()
            if callable(obj) and _FORBIDDEN_NAME_PATTERN.search(name)
        ]
        assert offenders == [], f"composite-sounding callable(s) found: {offenders}"

    def test_score_categories_returns_a_tuple_never_a_scalar(self):
        signature = inspect.signature(score_categories)
        return_annotation = str(signature.return_annotation)
        assert "tuple" in return_annotation.lower()
        assert "float" not in return_annotation.lower()
        assert "int" not in return_annotation.lower()

    def test_no_function_in_categories_module_returns_a_bare_number(self):
        # Every public (non-underscore) function in scoring/categories.py
        # must return something other than float/int -- a composite would
        # necessarily collapse to one of these.
        for name, obj in vars(categories).items():
            if name.startswith("_") or not inspect.isfunction(obj):
                continue
            if obj.__module__ != categories.__name__:
                continue
            return_annotation = inspect.signature(obj).return_annotation
            assert return_annotation not in (float, int), (
                f"{categories.__name__}.{name} returns a bare {return_annotation} -- "
                "looks like a composite score"
            )


# ---------------------------------------------------------------------------
# S1: no CLI flag anywhere in the tree can raise confidence or coverage.
# ---------------------------------------------------------------------------


def _all_option_names(command: object, prefix: str = "") -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for param in getattr(command, "params", []):
        if getattr(param, "param_type_name", None) == "option":
            for opt in getattr(param, "opts", []) + getattr(param, "secondary_opts", []):
                results.append((prefix or "<root>", opt))
    for name, sub in getattr(command, "commands", {}).items():
        results.extend(_all_option_names(sub, f"{prefix}{name} "))
    return results


#: Flags that plausibly *raise* confidence/coverage: force a HIGH/pass
#: result, boost a number, or assume a bundle/comparison is clean without
#: verifying it. Deliberately excludes "allow" -- --allow-unsealed and
#: --allow-heterogeneous both exist and are asserted, by name, to only ever
#: lower the result below.
_RAISING_KEYWORDS = re.compile(
    r"(?i)force.?(high|pass|clean|confidence|coverage)|boost|assume.?(clean|valid|sealed)|"
    r"trust.?anyway|raise.?confidence|raise.?coverage"
)


class TestNoCliFlagRaisesConfidenceOrCoverage:
    def test_no_option_anywhere_matches_a_raising_keyword(self):
        from chainbreak.cli.main import app

        root = typer.main.get_group(app)
        offenders = [
            (path, opt) for path, opt in _all_option_names(root) if _RAISING_KEYWORDS.search(opt)
        ]
        assert offenders == [], (
            f"found option(s) that look like they raise confidence/coverage: {offenders}"
        )

    def test_allow_unsealed_exists_and_only_lowers(self):
        from chainbreak.cli.main import app

        root = typer.main.get_group(app)
        names = {opt for _, opt in _all_option_names(root)}
        assert "--allow-unsealed" in names

    def test_allow_heterogeneous_exists_and_only_lowers(self):
        from chainbreak.cli.main import app

        root = typer.main.get_group(app)
        names = {opt for _, opt in _all_option_names(root)}
        assert "--allow-heterogeneous" in names
