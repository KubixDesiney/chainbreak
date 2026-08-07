"""CHAINBREAK domain models.

Authoritative definitions for AUTHORIZATION_MODEL.md. Pure data plus set
algebra: this module imports nothing from CHAINBREAK except ``enums``,
``errors``, ``ids`` and ``secrets``, and performs no I/O (ARCH-1).

Two conventions run throughout:

* Capability collections are ``AuthoritySet``, which guarantees canonical
  ordering so serialized evidence is diffable and hashable.
* Every timestamp is timezone-aware UTC, and every *interval* is derived from
  monotonic nanoseconds, never from wall-clock subtraction.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import datetime
from typing import Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    field_validator,
    model_validator,
)

from chainbreak.core.enums import (
    BenchmarkFamily,
    CategoryStatus,
    Confidence,
    DelegationMechanism,
    DenialAttribution,
    DivergenceKind,
    DriftClass,
    ExclusionReason,
    FindingType,
    MutationKind,
    OutcomeClass,
    PhaseKind,
    PlanPhase,
    PolicyKind,
    ProbeKind,
    Provider,
    RunStatus,
    ScoringCategory,
    Sensitivity,
    SeverityHint,
    StaleAuthorityClass,
    TaskStatus,
)
from chainbreak.core.errors import ScenarioSemanticError
from chainbreak.core.ids import (
    CapabilityId,
    IdentityId,
    Namespace,
    ScenarioId,
    Sha256Digest,
)

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class DomainModel(BaseModel):
    """Frozen, strictly validated base for every domain object."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
        validate_default=True,
        use_enum_values=False,
    )


# ---------------------------------------------------------------------------
# Authority sets
# ---------------------------------------------------------------------------


class AuthoritySet(DomainModel):
    """A canonically ordered set of capability IDs.

    Set algebra lives here rather than in the graph package so that every layer
    -- compiler, executor, analyzer, reporter -- performs identical operations
    with identical ordering guarantees.
    """

    capabilities: frozenset[CapabilityId] = Field(default_factory=frozenset)

    @classmethod
    def of(cls, *capabilities: str) -> AuthoritySet:
        return cls(capabilities=frozenset(capabilities))

    @classmethod
    def from_iterable(cls, values: Iterable[str]) -> AuthoritySet:
        return cls(capabilities=frozenset(values))

    @property
    def sorted(self) -> tuple[str, ...]:
        """Canonical ordering. Every serialization uses this."""
        return tuple(sorted(self.capabilities))

    def __iter__(self) -> Iterator[str]:  # type: ignore[override]
        return iter(self.sorted)

    def __len__(self) -> int:
        return len(self.capabilities)

    def __contains__(self, item: str) -> bool:
        return item in self.capabilities

    def __sub__(self, other: AuthoritySet) -> AuthoritySet:
        return AuthoritySet(capabilities=self.capabilities - other.capabilities)

    def __and__(self, other: AuthoritySet) -> AuthoritySet:
        return AuthoritySet(capabilities=self.capabilities & other.capabilities)

    def __or__(self, other: AuthoritySet) -> AuthoritySet:
        return AuthoritySet(capabilities=self.capabilities | other.capabilities)

    def is_subset_of(self, other: AuthoritySet) -> bool:
        return self.capabilities <= other.capabilities

    def is_superset_of(self, other: AuthoritySet) -> bool:
        return self.capabilities >= other.capabilities

    def is_empty(self) -> bool:
        return not self.capabilities

    def model_dump_canonical(self) -> list[str]:
        return list(self.sorted)


EMPTY_AUTHORITY = AuthoritySet()


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


class Capability(DomainModel):
    """An abstract, provider-neutral unit of authority (CAPABILITY_MODEL.md)."""

    id: CapabilityId
    title: str = Field(max_length=120)
    description: str = Field(max_length=1000)
    probe_kind: ProbeKind
    sensitivity: Sensitivity
    idempotent: bool = True
    mutates_state: bool = False
    is_control: bool = Field(
        default=False,
        description="Control capabilities calibrate a matrix; their failure aborts rather "
        "than being recorded as a denial (identity.whoami).",
    )
    requires_precondition: tuple[str, ...] = ()
    permitted_action_families: tuple[str, ...] = Field(
        default=(),
        description="Coarse families a binding's actions must fall within (SI-3).",
    )

    @model_validator(mode="after")
    def _write_capabilities_must_mutate(self) -> Self:
        if self.sensitivity is Sensitivity.BENIGN_WRITE and not self.mutates_state:
            raise ValueError(f"{self.id}: BENIGN_WRITE capability must set mutates_state=True")
        if self.sensitivity is Sensitivity.BENIGN_READ and self.mutates_state:
            raise ValueError(f"{self.id}: BENIGN_READ capability must not mutate state")
        return self


class CapabilityCatalog(DomainModel):
    """The loaded catalog. Version participates in every bundle's provenance."""

    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    capabilities: tuple[Capability, ...]

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [c.id for c in self.capabilities]
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            raise ValueError(f"duplicate capability ids: {sorted(duplicates)}")
        return self

    def get(self, capability_id: str) -> Capability:
        for capability in self.capabilities:
            if capability.id == capability_id:
                return capability
        raise KeyError(capability_id)

    def ids(self) -> AuthoritySet:
        return AuthoritySet.from_iterable(c.id for c in self.capabilities)

    def controls(self) -> tuple[Capability, ...]:
        return tuple(c for c in self.capabilities if c.is_control)

    def dangerous(self) -> tuple[Capability, ...]:
        return tuple(c for c in self.capabilities if c.sensitivity is Sensitivity.DANGEROUS)


class ProviderCapabilityBinding(DomainModel):
    """How a provider realizes a capability.

    ``actions`` is the *complete* set of provider operations the probe may
    invoke. The executor asserts the observed operation set is a subset of it
    (SI-3); anything else aborts the run.
    """

    capability_id: CapabilityId
    provider: Provider
    actions: tuple[str, ...] = Field(min_length=1)
    resource_template: str = Field(min_length=1)
    probe_kind: ProbeKind
    preconditions: tuple[str, ...] = ()
    notes: str = ""

    @field_validator("actions")
    @classmethod
    def _actions_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("binding actions must be unique")
        return value


# ---------------------------------------------------------------------------
# Identity and credentials
# ---------------------------------------------------------------------------


class IdentityRef(DomainModel):
    """Opaque provider handle. The core never parses ``value``."""

    provider: Provider
    kind: str = Field(max_length=64)
    value: str = Field(max_length=2048, repr=False)
    region: str | None = None
    account_ref: str | None = None


class SafetyEnvelope(DomainModel):
    """The resolved safety envelope. A run without one is refused (SI-5)."""

    allowed_account_ids: tuple[str, ...] = Field(min_length=1)
    allowed_regions: tuple[str, ...] = Field(min_length=1)
    namespace: Namespace
    namespace_pattern: str
    max_run_duration_seconds: PositiveInt = 1800
    max_estimated_cost_usd: NonNegativeFloat = 1.0
    max_delegation_depth: PositiveInt = 6
    allow_dangerous_capabilities: bool = False
    allow_concurrent_runs: bool = False

    @field_validator("allowed_account_ids")
    @classmethod
    def _no_wildcards(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for account in value:
            if account.strip() in {"*", "", "any", "ALL"}:
                raise ValueError(
                    "allowed_account_ids must be explicit 12-digit account IDs; "
                    "wildcards are forbidden (SI-6)"
                )
            if not (account.isdigit() and len(account) == 12):
                raise ValueError(f"not a valid AWS account id: {account!r}")
        return value

    @field_validator("max_run_duration_seconds")
    @classmethod
    def _hard_ceiling(cls, value: int) -> int:
        if value > 14_400:
            raise ValueError("max_run_duration_seconds may not exceed 14400 (SI-7)")
        return value


class CredentialRecord(DomainModel):
    """Credential *metadata*. Contains no secret material, by construction (EV-1)."""

    credential_id: str
    edge_id: str | None = None
    identity_id: IdentityId
    mechanism: DelegationMechanism
    issued_at: datetime
    expires_at: datetime
    requested_duration_s: PositiveInt
    granted_duration_s: PositiveInt
    session_name_hash: Sha256Digest
    access_key_id_hash: Sha256Digest
    session_policy_fingerprint: Sha256Digest | None = None
    scope_capabilities: AuthoritySet = EMPTY_AUTHORITY

    @property
    def lifetime_capped(self) -> bool:
        """AWS silently caps chained-role sessions at 3600 s (H7)."""
        return self.granted_duration_s < self.requested_duration_s

    @model_validator(mode="after")
    def _tz_aware(self) -> Self:
        for name, value in (("issued_at", self.issued_at), ("expires_at", self.expires_at)):
            if value.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware UTC")
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be after issued_at")
        return self


# ---------------------------------------------------------------------------
# Policy state
# ---------------------------------------------------------------------------


class PolicyFingerprint(DomainModel):
    policy_kind: PolicyKind
    name_hash: Sha256Digest
    document_sha256: Sha256Digest
    statement_count: NonNegativeInt
    has_explicit_deny: bool


class PolicyStateSnapshot(DomainModel):
    snapshot_id: str
    identity_id: IdentityId
    taken_at: datetime
    monotonic_ns: int
    policies: tuple[PolicyFingerprint, ...]

    def differs_from(self, other: PolicyStateSnapshot) -> bool:
        return {p.document_sha256 for p in self.policies} != {
            p.document_sha256 for p in other.policies
        }


class MutationReceipt(DomainModel):
    """Confirms a control-plane write. Anchors every revocation measurement."""

    confirmed: bool
    confirmation_method: str = Field(pattern=r"^(read_after_write|api_ack_only)$")
    confirmation_latency_ms: NonNegativeFloat | None = None
    request_id_hash: Sha256Digest | None = None
    monotonic_sent_ns: int
    wall_sent: datetime


class PolicyMutation(DomainModel):
    mutation_id: str
    kind: MutationKind
    target_identity: IdentityId
    denies_capabilities: AuthoritySet = EMPTY_AUTHORITY
    grants_capabilities: AuthoritySet = EMPTY_AUTHORITY
    policy_before: Sha256Digest | None = None
    policy_after: Sha256Digest | None = None
    receipt: MutationReceipt | None = None


# ---------------------------------------------------------------------------
# Delegation and graph
# ---------------------------------------------------------------------------


class DelegationConstraints(DomainModel):
    session_name_template: str | None = None
    session_tags: dict[str, str] = Field(default_factory=dict)
    external_id_ref: str | None = None
    source_identity: str | None = None


class ExpectedAuthority(DomainModel):
    capabilities: AuthoritySet
    phase: PlanPhase
    derivation: str = Field(pattern=r"^(DECLARED|INHERITED_ATTENUATED)$")


class ObservedAuthority(DomainModel):
    """Only ALLOWED outcomes contribute to ``capabilities`` (AUTH-1)."""

    capabilities: AuthoritySet
    excluded: dict[CapabilityId, ExclusionReason] = Field(default_factory=dict)
    phase: PlanPhase
    probe_matrix_id: str
    attempted: NonNegativeInt
    classified: NonNegativeInt

    @property
    def coverage(self) -> float:
        if self.attempted == 0:
            return 0.0
        return self.classified / self.attempted

    @model_validator(mode="after")
    def _classified_within_attempted(self) -> Self:
        if self.classified > self.attempted:
            raise ValueError("classified cannot exceed attempted")
        return self


class DelegationEdge(DomainModel):
    edge_id: str
    source_id: IdentityId
    target_id: IdentityId
    mechanism: DelegationMechanism
    requested_capabilities: AuthoritySet
    intended_capabilities: AuthoritySet
    expected_effective: AuthoritySet
    credential_lifetime_s: PositiveInt
    constraints: DelegationConstraints = Field(default_factory=DelegationConstraints)
    session_policy_fingerprint: Sha256Digest | None = None
    delegated_at: datetime | None = None
    delegated_monotonic_ns: int | None = None

    @model_validator(mode="after")
    def _no_self_delegation(self) -> Self:
        if self.source_id == self.target_id:
            raise ValueError(f"edge {self.edge_id}: self-delegation is not a delegation")
        return self


class IdentityNode(DomainModel):
    identity_id: IdentityId
    is_root: bool = False
    hop_index: NonNegativeInt = 0
    parent_id: IdentityId | None = None
    identity_ref: IdentityRef | None = None
    expected_authority: ExpectedAuthority
    observed_authority: ObservedAuthority | None = None
    credentials: tuple[CredentialRecord, ...] = ()

    @model_validator(mode="after")
    def _root_consistency(self) -> Self:
        if self.is_root:
            if self.parent_id is not None:
                raise ValueError("root node must not have a parent")
            if self.hop_index != 0:
                raise ValueError("root node must have hop_index 0")
        elif self.parent_id is None:
            raise ValueError(f"{self.identity_id}: non-root node requires a parent")
        return self

    # -- divergence (AUTHORIZATION_MODEL 4.1) ---------------------------------

    @property
    def unexpected_gain(self) -> AuthoritySet:
        if self.observed_authority is None:
            return EMPTY_AUTHORITY
        return self.observed_authority.capabilities - self.expected_authority.capabilities

    @property
    def unexpected_loss(self) -> AuthoritySet:
        if self.observed_authority is None:
            return EMPTY_AUTHORITY
        return self.expected_authority.capabilities - self.observed_authority.capabilities

    @property
    def agreement(self) -> AuthoritySet:
        if self.observed_authority is None:
            return EMPTY_AUTHORITY
        return self.observed_authority.capabilities & self.expected_authority.capabilities

    @property
    def diverged(self) -> bool:
        return bool(self.unexpected_gain) or bool(self.unexpected_loss)


class DivergencePoint(DomainModel):
    hop_index: NonNegativeInt
    identity_id: IdentityId
    kind: DivergenceKind
    gain: AuthoritySet = EMPTY_AUTHORITY
    loss: AuthoritySet = EMPTY_AUTHORITY


class PathAnalysis(DomainModel):
    path: tuple[IdentityId, ...]
    first_divergence: DivergencePoint | None = None
    attenuation_monotone_set: bool
    attenuation_monotone_cardinality: bool
    terminal_gain: AuthoritySet = EMPTY_AUTHORITY


class EdgeDivergence(DomainModel):
    """Per-edge attenuation correctness (AUTHORIZATION_MODEL 4.2).

    Two baselines are computed. The *observed* baseline (``*_observed`` /
    ``attenuation_correct``) isolates this edge's own behavior from upstream
    drift and drives the edge verdict. The *expected* baseline
    (``*_intended`` / ``attenuation_correct_vs_intent``) asks the same
    question against design intent rather than reality, and is what drives
    chain-level drift attribution rather than a single hop's verdict.
    """

    edge_id: str
    expected_at_target_observed: AuthoritySet
    expected_at_target_intended: AuthoritySet
    attenuation_correct: bool
    attenuation_correct_vs_intent: bool
    survived_incorrectly: AuthoritySet = EMPTY_AUTHORITY
    dropped_incorrectly: AuthoritySet = EMPTY_AUTHORITY
    dropped_incorrectly_vs_intent: AuthoritySet = EMPTY_AUTHORITY


class AuthorizationGraph(DomainModel):
    """Rooted DAG of identities joined by delegations. Invariants G-1..G-5."""

    nodes: tuple[IdentityNode, ...] = Field(min_length=1)
    edges: tuple[DelegationEdge, ...] = ()

    @model_validator(mode="after")
    def _validate_invariants(self) -> Self:
        ids = [n.identity_id for n in self.nodes]
        if len(set(ids)) != len(ids):
            raise ScenarioSemanticError("duplicate identity ids in graph")

        roots = [n for n in self.nodes if n.is_root]
        if len(roots) != 1:
            raise ScenarioSemanticError(f"G-2: expected exactly one root, found {len(roots)}")

        known = set(ids)
        for edge in self.edges:
            if edge.source_id not in known or edge.target_id not in known:
                raise ScenarioSemanticError(f"edge {edge.edge_id} references an unknown identity")

        inbound: dict[str, int] = dict.fromkeys(ids, 0)
        for edge in self.edges:
            inbound[edge.target_id] += 1
        if inbound[roots[0].identity_id] != 0:
            raise ScenarioSemanticError("G-2: root must have no inbound edge")

        self._assert_acyclic(ids)
        return self

    def _assert_acyclic(self, ids: list[str]) -> None:
        """G-1. Kahn's algorithm; a cycle makes hop index meaningless."""
        adjacency: dict[str, list[str]] = {i: [] for i in ids}
        indegree: dict[str, int] = dict.fromkeys(ids, 0)
        for edge in self.edges:
            adjacency[edge.source_id].append(edge.target_id)
            indegree[edge.target_id] += 1

        queue = [i for i in ids if indegree[i] == 0]
        visited = 0
        while queue:
            current = queue.pop()
            visited += 1
            for neighbour in adjacency[current]:
                indegree[neighbour] -= 1
                if indegree[neighbour] == 0:
                    queue.append(neighbour)
        if visited != len(ids):
            raise ScenarioSemanticError("G-1: delegation graph contains a cycle")

    # -- accessors ------------------------------------------------------------

    def node(self, identity_id: str) -> IdentityNode:
        for candidate in self.nodes:
            if candidate.identity_id == identity_id:
                return candidate
        raise KeyError(identity_id)

    @property
    def root(self) -> IdentityNode:
        return next(n for n in self.nodes if n.is_root)

    def edge_into(self, identity_id: str) -> DelegationEdge | None:
        for edge in self.edges:
            if edge.target_id == identity_id:
                return edge
        return None

    def children_of(self, identity_id: str) -> tuple[IdentityNode, ...]:
        return tuple(self.node(e.target_id) for e in self.edges if e.source_id == identity_id)

    @property
    def depth(self) -> int:
        return max((n.hop_index for n in self.nodes), default=0)

    def paths(self) -> tuple[tuple[IdentityId, ...], ...]:
        """Every root-to-leaf path. Divergence is analyzed per path."""
        results: list[tuple[str, ...]] = []

        def walk(current: str, prefix: tuple[str, ...]) -> None:
            children = self.children_of(current)
            if not children:
                results.append((*prefix, current))
                return
            for child in children:
                walk(child.identity_id, (*prefix, current))

        walk(self.root.identity_id, ())
        return tuple(results)


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------


class ProbeTiming(DomainModel):
    """All interval arithmetic uses monotonic nanoseconds. Wall clock is context only."""

    monotonic_start_ns: int
    monotonic_end_ns: int
    wall_start: datetime
    clock_offset_ms: float | None = None
    attempt_number: PositiveInt = 1
    retries: NonNegativeInt = 0

    @property
    def duration_ms(self) -> float:
        return (self.monotonic_end_ns - self.monotonic_start_ns) / 1_000_000

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.monotonic_end_ns < self.monotonic_start_ns:
            raise ValueError("monotonic_end_ns precedes monotonic_start_ns")
        return self


class ProbeRequestRecord(DomainModel):
    probe_kind: ProbeKind
    binding_actions: tuple[str, ...]
    target_ref_hash: Sha256Digest
    target_namespace: Namespace
    parameters_fingerprint: Sha256Digest


class ProbeOutcome(DomainModel):
    outcome_class: OutcomeClass
    provider_status_code: int | None = None
    provider_error_code: str | None = None
    denial_attribution: DenialAttribution | None = None
    disambiguation_path: str = Field(
        default="",
        description="Names the exact classifier branch that fired, so a later correction "
        "can find every affected observation.",
    )
    message_digest: Sha256Digest | None = None
    message_redacted: str = ""
    request_id_hash: Sha256Digest | None = None

    @model_validator(mode="after")
    def _attribution_only_for_denials(self) -> Self:
        if self.denial_attribution is not None and not self.outcome_class.is_denial:
            raise ValueError("denial_attribution set on a non-denial outcome")
        return self


class Observation(DomainModel):
    """The atom of CHAINBREAK. Immutable, append-only, written during the run."""

    observation_id: str
    run_id: str
    sequence: NonNegativeInt
    phase: PlanPhase
    probe_matrix_id: str
    identity_id: IdentityId
    identity_ref_hash: Sha256Digest
    capability_id: CapabilityId
    trial: PositiveInt
    trial_count: PositiveInt
    credential_id: str | None = None
    credential_age_ms: NonNegativeFloat | None = None
    request: ProbeRequestRecord
    timing: ProbeTiming
    outcome: ProbeOutcome
    preconditions_verified: bool
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _trial_in_range(self) -> Self:
        if self.trial > self.trial_count:
            raise ValueError("trial exceeds trial_count")
        return self


class ProbeCellResult(DomainModel):
    """Aggregation of one (identity, capability) cell across its trials.

    A cell is ALLOWED only if *every* trial was ALLOWED. Unanimity is the
    conservative choice: it prevents one throttled request from reading as a
    denial (RESEARCH_METHODOLOGY 8).
    """

    identity_id: IdentityId
    capability_id: CapabilityId
    phase: PlanPhase
    trials: tuple[OutcomeClass, ...] = Field(min_length=1)
    observation_ids: tuple[str, ...] = ()

    @property
    def resolved(self) -> OutcomeClass:
        distinct = set(self.trials)
        if distinct == {OutcomeClass.ALLOWED}:
            return OutcomeClass.ALLOWED
        if all(t.is_denial for t in self.trials):
            # Denials agree in kind, or we report the weakest attribution.
            return self.trials[0] if len(distinct) == 1 else OutcomeClass.DENIED_UNATTRIBUTED
        if all(t.is_error for t in self.trials):
            return self.trials[0]
        return OutcomeClass.INDETERMINATE

    @property
    def unanimous(self) -> bool:
        return len(set(self.trials)) == 1


# ---------------------------------------------------------------------------
# Timing measurements
# ---------------------------------------------------------------------------


class Interval(DomainModel):
    """A measurement with explicit uncertainty. There is no bare-scalar variant."""

    low: float
    point: float
    high: float
    unit: str = "s"

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not self.low <= self.point <= self.high:
            raise ValueError(f"interval not ordered: {self.low} <= {self.point} <= {self.high}")
        return self

    @property
    def half_width(self) -> float:
        return (self.high - self.low) / 2

    @classmethod
    def from_bounds(cls, low: float, high: float, unit: str = "s") -> Interval:
        return cls(low=low, point=(low + high) / 2, high=high, unit=unit)


class RevocationMeasurement(DomainModel):
    identity_id: IdentityId
    capability_id: CapabilityId
    mutation_kind: MutationKind
    transition_window: Interval | None = None
    transition_observed: bool
    non_monotonic: bool = False
    poll_interval_ms: PositiveInt
    poll_count: NonNegativeInt
    window_length_s: NonNegativeFloat
    mutation_receipt_confirmed: bool
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _window_present_iff_observed(self) -> Self:
        if self.transition_observed and self.transition_window is None:
            raise ValueError("transition_observed=True requires a transition_window")
        if not self.transition_observed and self.transition_window is not None:
            raise ValueError("transition_window present without an observed transition")
        return self


class StaleAuthorityMeasurement(DomainModel):
    identity_id: IdentityId
    capability_id: CapabilityId
    classification: StaleAuthorityClass
    deferral_seconds: NonNegativeFloat
    stale_window_seconds: NonNegativeFloat | None = None
    credential_expired_at_execution: bool
    paired_fresh_credential_outcome: OutcomeClass | None = Field(
        default=None,
        description="The paired fresh-credential probe. Without it, an ALLOWED at t_exec is "
        "ambiguous between 'change never propagated' and 'old credential retained authority'.",
    )


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


class TaskStepOutcome(DomainModel):
    capability_id: CapabilityId
    succeeded: bool
    outcome_class: OutcomeClass


class TaskOutcome(DomainModel):
    task_id: str
    identity_id: IdentityId
    worker: str
    status: TaskStatus
    steps_total: NonNegativeInt
    steps_attempted: NonNegativeInt
    steps_succeeded: NonNegativeInt
    step_outcomes: tuple[TaskStepOutcome, ...] = ()
    reported_insufficient_authority: bool
    substituted_capabilities: AuthoritySet = EMPTY_AUTHORITY
    redelegation_attempts: NonNegativeInt = 0
    output_marker_written: bool
    output_marker_verified_independently: bool = Field(
        description="Verified by the bootstrap identity, not trusted from the worker's report."
    )

    @property
    def claims_complete_but_is_not(self) -> bool:
        """The SILENT_NARROWING predicate."""
        return self.status is TaskStatus.COMPLETE and self.steps_succeeded < self.steps_total

    @property
    def claims_output_that_does_not_exist(self) -> bool:
        """The purest form of silent failure: reported success, absent side effect."""
        return self.output_marker_written and not self.output_marker_verified_independently


# ---------------------------------------------------------------------------
# Findings and scoring
# ---------------------------------------------------------------------------


class FindingEvidence(DomainModel):
    observation_refs: tuple[str, ...] = ()
    event_refs: tuple[str, ...] = ()
    policy_state_refs: tuple[str, ...] = ()


class Finding(DomainModel):
    """Observation and interpretation are separate fields, rendered separately (ADR-006)."""

    finding_id: str
    type: FindingType
    severity_hint: SeverityHint
    confidence: Confidence
    subject_kind: str = Field(pattern=r"^(identity|edge|path|task|credential|run)$")
    identity_id: IdentityId | None = None
    edge_id: str | None = None
    hop_index: NonNegativeInt | None = None
    observation: str = Field(min_length=1, max_length=2000)
    expected_state: dict[str, Any] = Field(default_factory=dict)
    observed_state: dict[str, Any] = Field(default_factory=dict)
    delta: dict[str, list[str]] = Field(default_factory=dict)
    security_interpretation: str = Field(default="", max_length=4000)
    confidence_rationale: str = ""
    caveats: tuple[str, ...] = ()
    drift_class: DriftClass | None = None
    evidence: FindingEvidence = Field(default_factory=FindingEvidence)


class DetectorCheck(DomainModel):
    """Negative-control verification. A failure invalidates the block's positive results."""

    negative_control_id: str
    expected_type: FindingType
    produced: bool
    result: str = Field(pattern=r"^(DETECTOR_OK|DETECTOR_FAILURE)$")


class Measurement(DomainModel):
    metric: str
    identity_id: IdentityId | None = None
    capability_id: CapabilityId | None = None
    value: Interval
    confidence: Confidence
    n: PositiveInt = 1


class CategoryResult(DomainModel):
    category: ScoringCategory
    status: CategoryStatus
    measurements: tuple[Measurement, ...] = ()
    finding_ids: tuple[str, ...] = ()
    coverage: float = Field(ge=0.0, le=1.0)
    confidence: Confidence
    caveats: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _low_coverage_is_partial(self) -> Self:
        if (
            self.coverage < 0.7
            and self.status not in {CategoryStatus.NOT_MEASURED, CategoryStatus.DETECTOR_FAILED}
            and self.status is not CategoryStatus.PARTIAL
        ):
            raise ValueError(
                f"{self.category}: coverage {self.coverage:.2f} < 0.7 must be reported as PARTIAL"
            )
        return self


# ---------------------------------------------------------------------------
# Scenario compilation output (SCENARIO_SPECIFICATION.md section 10)
# ---------------------------------------------------------------------------


class ProbeMatrix(DomainModel):
    """The cartesian product {identity} x {capabilities under test} at one
    scenario phase, plus scheduling metadata (AUTHORIZATION_MODEL.md section 3)."""

    matrix_id: str
    phase_name: str
    identities: tuple[IdentityId, ...] = Field(min_length=1)
    capabilities: AuthoritySet
    trials: PositiveInt = 3


class PlanStep(DomainModel):
    """One entry in the compiler's fully ordered execution plan.

    ``auto_inserted`` distinguishes a compiler-injected ``SNAPSHOT`` (F4) from
    a phase the scenario author actually wrote.
    """

    order: NonNegativeInt
    phase_name: str
    kind: PhaseKind
    auto_inserted: bool = False


class SynthesizedPolicy(DomainModel):
    """A provider-neutral session-policy artifact (F7).

    The real, provider-specific policy document does not exist until the
    provider adapter does (AWS: M8); this is the size-checked, fingerprinted
    placeholder the compiler produces from a capability set alone.
    """

    identity_id: IdentityId
    edge_id: str | None = None
    capabilities: AuthoritySet
    document_size_bytes: NonNegativeInt
    fingerprint: Sha256Digest


class CompileWarning(DomainModel):
    """A downgraded invariant or an informational expectation, surfaced
    rather than silently dropped (F6)."""

    code: str
    message: str
    identity_id: IdentityId | None = None
    edge_id: str | None = None


class CompiledExpectedFinding(DomainModel):
    """A negative control's declared expectation, carried into the compiled
    artifact so the harness can assert it after a run (F6)."""

    type: FindingType
    identity_id: IdentityId | None = None
    capabilities: AuthoritySet = EMPTY_AUTHORITY
    min_confidence: Confidence = Confidence.MEDIUM


class CompiledScenario(DomainModel):
    """Output of ``scenarios/compiler.py`` (SCENARIO_SPECIFICATION.md section 10)."""

    compiled_hash: Sha256Digest
    scenario_id: ScenarioId
    scenario_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    catalog_version: str
    adapter_version: str
    graph: AuthorizationGraph
    probe_matrices: tuple[ProbeMatrix, ...]
    plan: tuple[PlanStep, ...]
    policy_artifacts: tuple[SynthesizedPolicy, ...] = ()
    warnings: tuple[CompileWarning, ...] = ()
    expected_finding: CompiledExpectedFinding | None = None


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


class Provenance(DomainModel):
    chainbreak_version: str
    git_commit: str | None = None
    git_dirty: bool = False
    capability_catalog_version: str
    provider: Provider
    provider_adapter_version: str
    python_version: str
    config_fingerprint: Sha256Digest
    infrastructure_fingerprint: Sha256Digest | None = None


class ScenarioRef(DomainModel):
    id: ScenarioId
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    family: BenchmarkFamily
    api_version: str
    compiled_hash: Sha256Digest


class ExperimentRun(DomainModel):
    run_id: str
    created_at: datetime
    completed_at: datetime | None = None
    status: RunStatus
    scenario: ScenarioRef
    provenance: Provenance
    envelope: SafetyEnvelope
    seeds: dict[str, int] = Field(default_factory=dict)
    block_id: str | None = None
    warnings: tuple[str, ...] = ()


def min_confidence(values: Iterable[Confidence]) -> Confidence:
    """Aggregate confidence with ``min``, never a mean.

    Averaging would let a pile of easy measurements launder one shaky one
    (SCORING_MODEL section 3).
    """
    collected = list(values)
    if not collected:
        return Confidence.INSUFFICIENT
    return min(collected, key=lambda c: c.rank)
