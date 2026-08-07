"""Scenario document schema -- chainbreak.dev/v1alpha1.

Structural layer of the five-stage validation pipeline described in
SCENARIO_SPECIFICATION.md section 9. Stage 5 (safety) lives in ``safety.py``
and runs even in offline mode; it cannot be skipped.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from chainbreak.core.enums import (
    BenchmarkFamily,
    Confidence,
    DelegationMechanism,
    FindingType,
    MutationKind,
    NegativeControlKind,
    PhaseKind,
    Provider,
)
from chainbreak.core.ids import CapabilityId, IdentityId, ScenarioId

API_VERSION = "chainbreak.dev/v1alpha1"

# Mechanisms reserved for future versions; the v0.1 compiler rejects them.
_UNSUPPORTED_MECHANISMS = frozenset(
    {DelegationMechanism.FEDERATED_TOKEN, DelegationMechanism.WORKLOAD_IDENTITY}
)


class ScenarioModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class Metadata(ScenarioModel):
    id: ScenarioId
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    family: BenchmarkFamily
    title: str = Field(min_length=8, max_length=200)
    description: str = Field(min_length=20, max_length=4000)
    authors: tuple[str, ...] = ()
    tags: tuple[str, ...] = Field(default=(), max_length=16)


class Requires(ScenarioModel):
    catalog_version: str = ">=1.0.0,<2.0.0"
    adapter_version: str = ">=0.1.0"
    infrastructure_profile: str = "standard"


class Execution(ScenarioModel):
    trials: int = Field(default=3, ge=1, le=25)
    timing_sensitive: bool = False
    max_duration_seconds: int = Field(default=900, ge=10, le=14_400)
    probe_universe: Literal["declared", "scenario", "catalog"] = "scenario"
    concurrency: int = Field(default=4, ge=1, le=16)

    @model_validator(mode="after")
    def _timing_sensitive_is_serial(self) -> Self:
        # Concurrency destroys a timing measurement (ADR-011).
        if self.timing_sensitive and self.concurrency != 1:
            raise ValueError("timing_sensitive scenarios must set concurrency: 1")
        return self


class ProviderBinding(ScenarioModel):
    """Indirection only: names a Terraform output, never an ARN."""

    terraform_output: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)


class IdentitySpec(ScenarioModel):
    id: IdentityId
    role: Literal["root", "agent"]
    provider_binding: ProviderBinding
    capabilities: tuple[CapabilityId, ...] | None = None
    expect_capabilities: tuple[CapabilityId, ...] | None = None

    @model_validator(mode="after")
    def _root_declares_capabilities(self) -> Self:
        if self.role == "root" and not self.capabilities:
            raise ValueError(f"{self.id}: root identity must declare its capabilities")
        if self.role == "agent" and self.capabilities:
            raise ValueError(
                f"{self.id}: agent authority is derived from its inbound edge; use "
                "expect_capabilities for a redundant assertion"
            )
        return self


class CredentialSpec(ScenarioModel):
    requested_lifetime_seconds: int = Field(default=900, ge=900, le=43_200)


class SessionPolicySpec(ScenarioModel):
    derive_from: Literal["intended_capabilities"] | None = "intended_capabilities"
    inline_ref: str | None = None

    @model_validator(mode="after")
    def _exactly_one_source(self) -> Self:
        if bool(self.derive_from) == bool(self.inline_ref):
            raise ValueError("session_policy requires exactly one of derive_from or inline_ref")
        return self


class DelegationSpec(ScenarioModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$", max_length=64)
    from_: IdentityId = Field(alias="from")
    to: IdentityId
    mechanism: DelegationMechanism
    intended_capabilities: tuple[CapabilityId, ...] = Field(min_length=1)
    credential: CredentialSpec = Field(default_factory=CredentialSpec)
    session_policy: SessionPolicySpec | None = None
    session_name: str | None = None
    session_tags: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _mechanism_supported(self) -> Self:
        if self.mechanism in _UNSUPPORTED_MECHANISMS:
            raise ValueError(f"{self.mechanism} is reserved for a future version")
        if self.from_ == self.to:
            raise ValueError(f"{self.id}: self-delegation is not a delegation")
        scoped = self.mechanism in {
            DelegationMechanism.SESSION_POLICY_SCOPED,
            DelegationMechanism.ROLE_CHAIN_WITH_SESSION_POLICY,
        }
        if scoped and self.session_policy is None:
            raise ValueError(f"{self.id}: {self.mechanism} requires a session_policy block")
        return self


class MutationSpec(ScenarioModel):
    target_identity: IdentityId
    kind: MutationKind
    denies: tuple[CapabilityId, ...] = ()
    grants: tuple[CapabilityId, ...] = ()
    record_receipt: bool = True


class PhaseSpec(ScenarioModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]*$", max_length=64)
    kind: PhaseKind
    targets: tuple[IdentityId, ...] = ()
    target_identity: IdentityId | None = None
    capability: CapabilityId | None = None
    mutation: MutationSpec | None = None
    # Floor of 100 ms bounds cost and prevents a pathological poll loop (T-07).
    interval_ms: int = Field(default=500, ge=100, le=60_000)
    max_duration_seconds: int = Field(default=300, ge=1, le=14_400)
    stop_on: Literal["STABLE_DENIAL", "STABLE_ALLOW", "TIMEOUT"] = "STABLE_DENIAL"
    stability_count: int = Field(default=3, ge=1, le=10)
    wait_seconds: int = Field(default=0, ge=0, le=14_400)
    credential_source: str | None = Field(default=None, pattern=r"^phase:[a-z][a-z0-9-]*$")
    task: str | None = None

    @model_validator(mode="after")
    def _kind_requirements(self) -> Self:
        if self.kind is PhaseKind.PROBE and not self.targets:
            raise ValueError(f"phase {self.name}: PROBE requires targets")
        if self.kind is PhaseKind.MUTATE and self.mutation is None:
            raise ValueError(f"phase {self.name}: MUTATE requires a mutation block")
        if self.kind is PhaseKind.POLL and not (self.target_identity and self.capability):
            raise ValueError(f"phase {self.name}: POLL requires target_identity and capability")
        if self.kind is PhaseKind.DEFERRED_EXECUTION and not self.credential_source:
            raise ValueError(
                f"phase {self.name}: DEFERRED_EXECUTION requires credential_source "
                "(the point is to reuse an earlier credential)"
            )
        if self.kind is PhaseKind.TASK and not self.task:
            raise ValueError(f"phase {self.name}: TASK requires a task reference")
        return self


class TaskStepSpec(ScenarioModel):
    use: CapabilityId
    on_failure: Literal["continue", "abort", "retry"] = "continue"


class CompletionContract(ScenarioModel):
    must_report_partial: bool = True
    must_not_substitute: bool = True
    must_not_redelegate: bool = True


class TaskSpec(ScenarioModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$", max_length=64)
    worker: str = Field(default="deterministic.sequential", max_length=64)
    identity: IdentityId
    requires_capabilities: tuple[CapabilityId, ...] = Field(min_length=1)
    steps: tuple[TaskStepSpec, ...] = Field(min_length=1)
    completion_contract: CompletionContract = Field(default_factory=CompletionContract)


class ExpectationSpec(ScenarioModel):
    kind: Literal[
        "node_authority",
        "attenuation_monotone",
        "no_first_divergence",
        "revocation_within",
        "task_contract",
    ]
    identity: IdentityId | None = None
    phase: str | None = None
    allow: tuple[CapabilityId, ...] = ()
    deny: tuple[CapabilityId, ...] = ()
    path: tuple[IdentityId, ...] = ()
    mode: Literal["set", "cardinality"] = "set"
    capability: CapabilityId | None = None
    max_seconds: float | None = None
    # Timing expectations default to informational: CHAINBREAK does not know
    # what a "correct" propagation time is and will not assert one.
    severity: Literal["informational", "assertive"] = "informational"
    justification: str = ""
    task: str | None = None

    @model_validator(mode="after")
    def _kind_requirements(self) -> Self:
        if self.kind == "node_authority":
            if not self.identity:
                raise ValueError("node_authority requires an identity")
            if not self.deny:
                raise ValueError(
                    "node_authority requires a non-empty deny list: you cannot detect "
                    "authority expansion by listing only what should be allowed"
                )
            overlap = set(self.allow) & set(self.deny)
            if overlap:
                raise ValueError(f"capability in both allow and deny: {sorted(overlap)}")
        if self.kind in {"attenuation_monotone", "no_first_divergence"} and len(self.path) < 2:
            raise ValueError(f"{self.kind} requires a path of at least two identities")
        if self.kind == "revocation_within":
            if self.max_seconds is None or not self.identity or not self.capability:
                raise ValueError("revocation_within requires identity, capability and max_seconds")
            if self.severity == "assertive" and len(self.justification) < 20:
                raise ValueError(
                    "an assertive timing threshold requires a justification; CHAINBREAK "
                    "does not assert normative propagation times without one"
                )
        if self.kind == "task_contract" and not self.task:
            raise ValueError("task_contract requires a task reference")
        return self


class ExpectedFindingSpec(ScenarioModel):
    type: FindingType
    identity: IdentityId | None = None
    capabilities: tuple[CapabilityId, ...] = ()
    min_confidence: Confidence = Confidence.MEDIUM


class NegativeControlSpec(ScenarioModel):
    kind: NegativeControlKind
    rationale: str = Field(min_length=40, max_length=2000)
    expect_finding: ExpectedFindingSpec
    suppress_graph_check: tuple[str, ...] = ()


class ScenarioSpec(ScenarioModel):
    provider: Provider
    requires: Requires = Field(default_factory=Requires)
    execution: Execution = Field(default_factory=Execution)
    identities: tuple[IdentitySpec, ...] = Field(min_length=1, max_length=32)
    delegations: tuple[DelegationSpec, ...] = Field(default=(), max_length=32)
    phases: tuple[PhaseSpec, ...] = Field(min_length=1, max_length=64)
    tasks: tuple[TaskSpec, ...] = Field(default=(), max_length=16)
    expectations: tuple[ExpectationSpec, ...] = Field(default=(), max_length=64)
    negative_control: NegativeControlSpec | None = None

    @model_validator(mode="after")
    def _referential_integrity(self) -> Self:
        identity_ids = {i.id for i in self.identities}
        if len(identity_ids) != len(self.identities):
            raise ValueError("duplicate identity ids")

        roots = [i for i in self.identities if i.role == "root"]
        if len(roots) != 1:
            raise ValueError(f"G-2: exactly one root identity required, found {len(roots)}")

        for delegation in self.delegations:
            for ref in (delegation.from_, delegation.to):
                if ref not in identity_ids:
                    raise ValueError(f"delegation {delegation.id} references unknown {ref!r}")

        phase_names = {p.name for p in self.phases}
        if len(phase_names) != len(self.phases):
            raise ValueError("duplicate phase names")

        task_ids = {t.id for t in self.tasks}
        for phase in self.phases:
            for target in phase.targets:
                if target not in identity_ids:
                    raise ValueError(f"phase {phase.name} targets unknown identity {target!r}")
            if phase.target_identity and phase.target_identity not in identity_ids:
                raise ValueError(
                    f"phase {phase.name} targets unknown identity {phase.target_identity!r}"
                )
            if phase.mutation and phase.mutation.target_identity not in identity_ids:
                raise ValueError(f"phase {phase.name} mutates unknown identity")
            if phase.task and phase.task not in task_ids:
                raise ValueError(f"phase {phase.name} references unknown task {phase.task!r}")
            if phase.credential_source:
                source = phase.credential_source.removeprefix("phase:")
                if source not in phase_names:
                    raise ValueError(
                        f"phase {phase.name} credential_source references unknown phase {source!r}"
                    )

        for task in self.tasks:
            if task.identity not in identity_ids:
                raise ValueError(f"task {task.id} references unknown identity {task.identity!r}")

        for expectation in self.expectations:
            if expectation.identity and expectation.identity not in identity_ids:
                raise ValueError(
                    f"expectation references unknown identity {expectation.identity!r}"
                )
            for hop in expectation.path:
                if hop not in identity_ids:
                    raise ValueError(f"expectation path references unknown identity {hop!r}")
            if expectation.task and expectation.task not in task_ids:
                raise ValueError(f"expectation references unknown task {expectation.task!r}")

        return self


class ScenarioDocument(ScenarioModel):
    api_version: Literal["chainbreak.dev/v1alpha1"] = Field(alias="apiVersion")
    kind: Literal["Scenario"] = "Scenario"
    metadata: Metadata
    spec: ScenarioSpec

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _negative_controls_are_marked(self) -> Self:
        if self.spec.negative_control and not self.metadata.id.startswith("nc-"):
            raise ValueError(
                "negative-control scenarios must use an id beginning with 'nc-' so a "
                "reviewer cannot mistake one for a health check"
            )
        if self.metadata.id.startswith("nc-") and not self.spec.negative_control:
            raise ValueError("scenario id begins with 'nc-' but declares no negative_control")
        return self
