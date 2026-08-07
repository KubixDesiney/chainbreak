"""Domain exceptions.

Every failure mode CHAINBREAK can encounter has a named exception. Bare
``Exception`` is banned by CONTRIBUTING.md, and exceptions carrying a
``machine_reason`` are recorded verbatim in evidence so a failed measurement is
still an interpretable data point.
"""

from __future__ import annotations

from typing import Any


class ChainbreakError(Exception):
    """Base for every CHAINBREAK error."""

    machine_reason: str = "CHAINBREAK_ERROR"

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context = context

    def as_record(self) -> dict[str, Any]:
        """Serializable form for evidence. Context must already be redaction-safe."""
        return {
            "error_type": type(self).__name__,
            "machine_reason": self.machine_reason,
            "message": self.message,
            "context": self.context,
        }


# --- Security invariants -----------------------------------------------------


class SecurityInvariantError(ChainbreakError):
    """Base for violations of an SI-* invariant. Always aborts the run."""

    machine_reason = "SECURITY_INVARIANT_VIOLATION"


class SecretSerializationError(SecurityInvariantError):
    """SI-1: something attempted to render secret material as text."""

    machine_reason = "SECRET_SERIALIZATION_ATTEMPT"


class SecretLeakError(SecurityInvariantError):
    """SI-1: a secret-shaped value reached the redaction choke point.

    Deliberately fatal. A leak is a bug to fix, not a value to sanitize.
    """

    machine_reason = "SECRET_LEAK_DETECTED"


class NamespaceViolationError(SecurityInvariantError):
    """SI-2: an operation targeted a resource outside the benchmark namespace."""

    machine_reason = "NAMESPACE_VIOLATION"


class CapabilityBroadeningError(SecurityInvariantError):
    """SI-3: an adapter invoked an operation outside its binding's declared set."""

    machine_reason = "CAPABILITY_BROADENING"


class AccountNotAllowedError(SecurityInvariantError):
    """SI-6: the resolved account is not in the operator's allowlist."""

    machine_reason = "ACCOUNT_NOT_ALLOWED"


class RegionNotAllowedError(SecurityInvariantError):
    """SI-5: the target region is not in the envelope's allowlist."""

    machine_reason = "REGION_NOT_ALLOWED"


class MutationTargetForbiddenError(SecurityInvariantError):
    """SI-12: refused to mutate bootstrap or principal."""

    machine_reason = "MUTATION_TARGET_FORBIDDEN"


class DangerousCapabilityError(SecurityInvariantError):
    """SI-9: a DANGEROUS capability was requested without the double opt-in."""

    machine_reason = "DANGEROUS_CAPABILITY_REFUSED"


# --- Configuration and definition -------------------------------------------


class ConfigurationError(ChainbreakError):
    machine_reason = "CONFIGURATION_ERROR"


class SafetyEnvelopeError(ConfigurationError):
    """SI-5: no resolved safety envelope, or the envelope rejected the run."""

    machine_reason = "SAFETY_ENVELOPE_REJECTED"


class ScenarioError(ChainbreakError):
    machine_reason = "SCENARIO_ERROR"


class ScenarioSyntaxError(ScenarioError):
    machine_reason = "SCENARIO_SYNTAX_ERROR"


class ScenarioSemanticError(ScenarioError):
    """Graph invariants G-1..G-5, unresolved references, phase ordering."""

    machine_reason = "SCENARIO_SEMANTIC_ERROR"


class ScenarioSafetyError(ScenarioError):
    """SI-11: literal ARNs, account IDs, regions, or an unsafe YAML construct."""

    machine_reason = "SCENARIO_SAFETY_ERROR"


class CapabilityResolutionError(ChainbreakError):
    """CAP-1: a capability has no binding in the active provider. Never a silent skip."""

    machine_reason = "CAPABILITY_UNRESOLVED"


class BindingValidationError(ChainbreakError):
    machine_reason = "BINDING_INVALID"


# --- Execution ---------------------------------------------------------------


class ExecutionError(ChainbreakError):
    machine_reason = "EXECUTION_ERROR"


class PreconditionFailedError(ExecutionError):
    """A marker was absent or did not match. The matrix is CONFIGURATION_ERROR."""

    machine_reason = "PRECONDITION_FAILED"


class ControlCapabilityFailedError(ExecutionError):
    """identity.whoami failed: apparatus fault, not a denial. Discard the matrix."""

    machine_reason = "CONTROL_CAPABILITY_FAILED"


class RunDurationExceededError(ExecutionError):
    """SI-7: the run deadline elapsed."""

    machine_reason = "RUN_DURATION_EXCEEDED"


class CostEstimateExceededError(ExecutionError):
    """SI-8: estimated cost above the configured ceiling."""

    machine_reason = "COST_ESTIMATE_EXCEEDED"


class DelegationError(ExecutionError):
    machine_reason = "DELEGATION_FAILED"


class MutationNotConfirmedError(ExecutionError):
    """Read-after-write did not confirm; any resulting timing measurement is inconclusive."""

    machine_reason = "MUTATION_NOT_CONFIRMED"


# --- Evidence and analysis ---------------------------------------------------


class EvidenceError(ChainbreakError):
    machine_reason = "EVIDENCE_ERROR"


class BundleIntegrityError(EvidenceError):
    """Recomputed root differs from the manifest."""

    machine_reason = "BUNDLE_INTEGRITY_FAILED"


class AnalysisError(ChainbreakError):
    machine_reason = "ANALYSIS_ERROR"


class HeterogeneousComparisonError(AnalysisError):
    """Refused to aggregate runs with differing compiled/adapter/catalog versions."""

    machine_reason = "HETEROGENEOUS_COMPARISON_REFUSED"
