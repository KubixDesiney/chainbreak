"""Canonical enumerations for the CHAINBREAK domain.

Every enum here is referenced by the evidence schema. Renaming a member is a
breaking change to the evidence format and requires an evidence format version
bump -- see EVIDENCE_SCHEMA.md section 11.

All enums subclass ``str`` so they serialize as their value in JSON without a
custom encoder, which keeps canonical JSON simple.
"""

from __future__ import annotations

from enum import StrEnum


class Provider(StrEnum):
    """Provider identifiers. v0.1 ships ``aws`` and ``fake``."""

    AWS = "aws"
    FAKE = "fake"


class ProbeKind(StrEnum):
    """The shape of test that demonstrates a capability.

    Open by convention: adding a member requires a probe implementation in every
    provider adapter or an explicit unsupported declaration (CAP-1).
    """

    READ_MARKER = "READ_MARKER"
    WRITE_SCRATCH = "WRITE_SCRATCH"
    LIST_PREFIX = "LIST_PREFIX"
    INVOKE_NOOP = "INVOKE_NOOP"
    SELF_DESCRIBE = "SELF_DESCRIBE"
    DELEGATE = "DELEGATE"


class Sensitivity(StrEnum):
    """Gates what a probe is permitted to do. See CAPABILITY_MODEL.md section 5."""

    BENIGN_READ = "BENIGN_READ"
    BENIGN_WRITE = "BENIGN_WRITE"
    BENIGN_INVOKE = "BENIGN_INVOKE"
    DELEGATION = "DELEGATION"
    DANGEROUS = "DANGEROUS"  # no v0.1 capability uses this; double opt-in required (SI-9)


class DelegationMechanism(StrEnum):
    """How authority is transferred across an edge."""

    DIRECT_ROLE_ASSUMPTION = "DIRECT_ROLE_ASSUMPTION"
    ROLE_CHAIN = "ROLE_CHAIN"
    SESSION_POLICY_SCOPED = "SESSION_POLICY_SCOPED"
    ROLE_CHAIN_WITH_SESSION_POLICY = "ROLE_CHAIN_WITH_SESSION_POLICY"
    RESOURCE_POLICY_GRANT = "RESOURCE_POLICY_GRANT"
    # Reserved for future versions; rejected by the v0.1 compiler.
    FEDERATED_TOKEN = "FEDERATED_TOKEN"  # noqa: S105 # nosec B105 -- enum member, not a credential
    WORKLOAD_IDENTITY = "WORKLOAD_IDENTITY"


class PlanPhase(StrEnum):
    """Named points in a run at which authority may be measured."""

    BASELINE = "BASELINE"
    POST_DELEGATION = "POST_DELEGATION"
    PRE_MUTATION = "PRE_MUTATION"
    POST_MUTATION = "POST_MUTATION"
    DEFERRED_EXECUTION = "DEFERRED_EXECUTION"
    PAIRED_FRESH_CREDENTIAL = "PAIRED_FRESH_CREDENTIAL"
    POST_EXPIRY = "POST_EXPIRY"
    TASK_EXECUTION = "TASK_EXECUTION"
    FINAL = "FINAL"


class PhaseKind(StrEnum):
    """Scenario phase types, in execution-plan order."""

    PROBE = "PROBE"
    MUTATE = "MUTATE"
    POLL = "POLL"
    WAIT = "WAIT"
    DEFERRED_EXECUTION = "DEFERRED_EXECUTION"
    TASK = "TASK"
    SNAPSHOT = "SNAPSHOT"


class OutcomeClass(StrEnum):
    """Classification of a single probe attempt.

    Only ``ALLOWED`` contributes to observed authority (AUTH-1). Every
    ``ERROR_*`` value excludes the cell from the authority set *and* from the
    denial set -- it is an absence of measurement, not a negative measurement.
    """

    ALLOWED = "ALLOWED"
    DENIED_EXPLICIT = "DENIED_EXPLICIT"
    DENIED_IMPLICIT = "DENIED_IMPLICIT"
    DENIED_UNATTRIBUTED = "DENIED_UNATTRIBUTED"
    ERROR_RESOURCE_MISSING = "ERROR_RESOURCE_MISSING"
    ERROR_TRANSIENT = "ERROR_TRANSIENT"
    ERROR_INFRASTRUCTURE = "ERROR_INFRASTRUCTURE"
    INDETERMINATE = "INDETERMINATE"

    @property
    def is_denial(self) -> bool:
        return self in _DENIALS

    @property
    def is_error(self) -> bool:
        return self in _ERRORS

    @property
    def counts_as_authority(self) -> bool:
        return self is OutcomeClass.ALLOWED


_DENIALS = frozenset(
    {
        OutcomeClass.DENIED_EXPLICIT,
        OutcomeClass.DENIED_IMPLICIT,
        OutcomeClass.DENIED_UNATTRIBUTED,
    }
)
_ERRORS = frozenset(
    {
        OutcomeClass.ERROR_RESOURCE_MISSING,
        OutcomeClass.ERROR_TRANSIENT,
        OutcomeClass.ERROR_INFRASTRUCTURE,
    }
)


class DenialAttribution(StrEnum):
    """Why the provider said no, when it discloses that."""

    EXPLICIT_DENY = "EXPLICIT_DENY"
    IMPLICIT_NO_ALLOW = "IMPLICIT_NO_ALLOW"
    SESSION_POLICY = "SESSION_POLICY"
    TRUST_POLICY = "TRUST_POLICY"
    RESOURCE_POLICY = "RESOURCE_POLICY"
    PERMISSION_BOUNDARY = "PERMISSION_BOUNDARY"
    UNDISCLOSED = "UNDISCLOSED"


class ExclusionReason(StrEnum):
    """Why a capability could not be classified for an identity."""

    PRECONDITION_FAILED = "PRECONDITION_FAILED"
    TRANSIENT_ERRORS_EXHAUSTED = "TRANSIENT_ERRORS_EXHAUSTED"
    INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"
    TRIALS_DISAGREED = "TRIALS_DISAGREED"
    NO_BINDING_IN_SCENARIO = "NO_BINDING_IN_SCENARIO"
    NOT_PROBED = "NOT_PROBED"
    CONTROL_CAPABILITY_FAILED = "CONTROL_CAPABILITY_FAILED"


class Confidence(StrEnum):
    """Ordered confidence levels. Aggregation uses ``min``, never a mean."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT"

    @property
    def rank(self) -> int:
        return _CONFIDENCE_RANK[self]


_CONFIDENCE_RANK: dict[Confidence, int] = {
    Confidence.HIGH: 3,
    Confidence.MEDIUM: 2,
    Confidence.LOW: 1,
    Confidence.INSUFFICIENT: 0,
}


class FindingType(StrEnum):
    """See AUTHORIZATION_MODEL.md section 6 for the predicate behind each."""

    EXPECTED_BEHAVIOR = "EXPECTED_BEHAVIOR"
    AUTHORITY_EXPANSION = "AUTHORITY_EXPANSION"
    AUTHORITY_SURVIVAL = "AUTHORITY_SURVIVAL"
    AUTHORITY_NARROWING = "AUTHORITY_NARROWING"
    DELEGATION_DRIFT = "DELEGATION_DRIFT"
    REVOCATION_DELAY = "REVOCATION_DELAY"
    NO_TRANSITION_OBSERVED = "NO_TRANSITION_OBSERVED"
    STALE_AUTHORITY = "STALE_AUTHORITY"
    EXPIRED_CREDENTIAL_ACCEPTED = "EXPIRED_CREDENTIAL_ACCEPTED"
    SILENT_NARROWING = "SILENT_NARROWING"
    CAPABILITY_SUBSTITUTED = "CAPABILITY_SUBSTITUTED"
    REDELEGATION_ATTEMPTED = "REDELEGATION_ATTEMPTED"
    LIFETIME_CAPPED = "LIFETIME_CAPPED"
    INCONCLUSIVE = "INCONCLUSIVE"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    DETECTOR_FAILURE = "DETECTOR_FAILURE"


class SeverityHint(StrEnum):
    """Deliberately a *hint*: CHAINBREAK does not know the operator's risk context."""

    INFORMATIONAL = "INFORMATIONAL"
    REVIEW = "REVIEW"
    INVESTIGATE = "INVESTIGATE"


class DriftClass(StrEnum):
    """How a node's divergence relates to its parent's."""

    ORIGINATED = "ORIGINATED"
    PROPAGATED = "PROPAGATED"
    AMPLIFIED = "AMPLIFIED"
    CORRECTED = "CORRECTED"


class DivergenceKind(StrEnum):
    EXPANSION = "EXPANSION"
    NARROWING = "NARROWING"
    MIXED = "MIXED"
    UNMEASURED = "UNMEASURED"


class MutationKind(StrEnum):
    """Controlled policy changes. Each is a level of the revocation-mechanism variable."""

    ATTACH_INLINE_DENY = "ATTACH_INLINE_DENY"
    REMOVE_INLINE_POLICY = "REMOVE_INLINE_POLICY"
    REPLACE_INLINE_POLICY = "REPLACE_INLINE_POLICY"
    UPDATE_TRUST_POLICY = "UPDATE_TRUST_POLICY"
    REVOKE_OLDER_SESSIONS = "REVOKE_OLDER_SESSIONS"
    DELETE_SESSION_POLICY_SCOPE = "DELETE_SESSION_POLICY_SCOPE"


class PolicyKind(StrEnum):
    IDENTITY_INLINE = "IDENTITY_INLINE"
    IDENTITY_MANAGED = "IDENTITY_MANAGED"
    TRUST = "TRUST"
    SESSION = "SESSION"
    RESOURCE = "RESOURCE"
    PERMISSION_BOUNDARY = "PERMISSION_BOUNDARY"


class StaleAuthorityClass(StrEnum):
    """Classification of execution-time authority state. See AUTHORIZATION_MODEL 5.2."""

    CURRENT_AUTHORITY = "CURRENT_AUTHORITY"
    STALE_AUTHORITY_LIVE_CREDENTIAL = "STALE_AUTHORITY_LIVE_CREDENTIAL"
    EXPIRED_CREDENTIAL_HONORED = "EXPIRED_CREDENTIAL_HONORED"
    CREDENTIAL_EXPIRED = "CREDENTIAL_EXPIRED"
    SESSION_SCOPE_CACHED = "SESSION_SCOPE_CACHED"
    INDETERMINATE = "INDETERMINATE"


class TaskStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    ABORTED_TIMEOUT = "ABORTED_TIMEOUT"
    ABORTED_SAFETY = "ABORTED_SAFETY"
    ABORTED_ERROR = "ABORTED_ERROR"


class ScoringCategory(StrEnum):
    """Six independent categories. There is no composite score (ADR-010)."""

    DELEGATION_INTEGRITY = "DELEGATION_INTEGRITY"
    SCOPE_ATTENUATION = "SCOPE_ATTENUATION"
    REVOCATION_RESPONSIVENESS = "REVOCATION_RESPONSIVENESS"
    AUTHORITY_FRESHNESS = "AUTHORITY_FRESHNESS"
    FAILURE_TRANSPARENCY = "FAILURE_TRANSPARENCY"
    CREDENTIAL_HYGIENE = "CREDENTIAL_HYGIENE"


class CategoryStatus(StrEnum):
    """A description of the measurement, not a grade. CONSISTENT does not mean 'secure'."""

    CONSISTENT = "CONSISTENT"
    DIVERGENT = "DIVERGENT"
    PARTIAL = "PARTIAL"
    NOT_MEASURED = "NOT_MEASURED"
    DETECTOR_FAILED = "DETECTOR_FAILED"


class NegativeControlKind(StrEnum):
    """Injected defects. See SCENARIO_SPECIFICATION.md section 8."""

    INTENT_EXCEEDS_PARENT = "INTENT_EXCEEDS_PARENT"
    SURVIVING_AUTHORITY = "SURVIVING_AUTHORITY"
    NON_MONOTONE_CHAIN = "NON_MONOTONE_CHAIN"
    NO_REVOCATION = "NO_REVOCATION"
    SILENT_SUCCESS = "SILENT_SUCCESS"
    STALE_CREDENTIAL_REUSE = "STALE_CREDENTIAL_REUSE"


class BenchmarkFamily(StrEnum):
    SCOPE_ATTENUATION = "scope-attenuation"
    DELEGATION_DRIFT = "delegation-drift"
    REVOCATION = "revocation"
    STALE_AUTHORITY = "stale-authority"
    SILENT_NARROWING = "silent-narrowing"
