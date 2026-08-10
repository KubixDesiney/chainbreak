"""``execution/``'s top-level entry point (ARCHITECTURE.md section 3.11):
preflight -> materialize identities -> walk delegation edges -> run probe
matrices / mutations / polls -> revert -> cleanup.

The phase loop is written against the *full* ``PhaseKind`` enum from the
start (M10's own stated risk to avoid), even though a scope-attenuation
scenario only ever contains ``PROBE`` phases: every kind has had an
explicit branch since M14 (``PROBE``, ``SNAPSHOT``, ``MUTATE``, ``POLL``,
``WAIT``, ``DEFERRED_EXECUTION``, ``TASK``); the trailing ``else`` is
structurally unreachable today and exists only to fail loudly, rather than
silently doing nothing, the day a new ``PhaseKind`` member is added without
a branch here.

**Concurrency (F7).** ``ScenarioSpec.execution.concurrency`` is a scenario-
authoring concern this milestone does not yet read; every probe here runs
strictly serially. This is a deliberate, documented scope reduction, not an
oversight: the fake provider's ``PolicyEngine``/``SessionStore``/
``VirtualClock`` have no internal locking, and executing concurrently
against them correctly would be its own milestone's worth of work for a
scenario corpus that, per M10's own non-functional requirement, already
finishes well under 5s serially. ``timing_sensitive`` scenarios (ADR-011)
would need to run serially regardless, so this is only a simplification for
the *non*-timing-sensitive case, and only until a milestone actually needs
the concurrency to run in reasonable time.

**Revert (M12, F8/F9, S3).** Every ``MUTATE`` step's revert log is written
*before* ``mutation.apply_mutation`` is called (so a killed run still leaves
actionable recovery information), and the mutation itself is reverted from
the ``finally`` block below regardless of how the run ended -- a clean
completion, a raised ``ChainbreakError``, or an uncaught exception all run
the same reversion path.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from chainbreak.capabilities.loader import load_catalog
from chainbreak.capabilities.preconditions import PreconditionRegistry
from chainbreak.core.clock import RunClock
from chainbreak.core.enums import PhaseKind, PlanPhase, RunStatus
from chainbreak.core.errors import (
    ControlCapabilityFailedError,
    ExecutionError,
    PreconditionFailedError,
    SafetyEnvelopeError,
)
from chainbreak.core.ids import new_event_id, run_salt
from chainbreak.core.models import (
    CompiledScenario,
    CredentialRecord,
    Observation,
    PolicyStateSnapshot,
    SafetyEnvelope,
)
from chainbreak.core.safety import SafetyGate
from chainbreak.execution import (
    chain,
    deferred,
    delegation,
    matrix,
    mutation,
    polling,
    revert,
    task_runner,
)
from chainbreak.execution.credential_store import CredentialStore
from chainbreak.providers.base.protocol import ProviderAdapter

__all__ = [
    "PHASE_NAME_TO_PLAN_PHASE",
    "DiscardedMatrix",
    "EvidenceSink",
    "OrchestrationResult",
    "orchestrate",
    "resolve_plan_phase",
]


@runtime_checkable
class EvidenceSink(Protocol):  # pragma: no cover -- structural interface, never instantiated
    """Exactly the subset of :class:`~chainbreak.evidence.writer.BundleWriter`'s
    public surface this package uses.

    ``execution/`` may not import ``evidence/`` (ARCH-1's layering has
    ``evidence`` above ``execution``, not below it): a real ``BundleWriter``
    satisfies this Protocol structurally, and the caller that *can* import
    both (``cli/run.py``) is what constructs one and passes it in.
    """

    def write_observation(self, observation: Observation) -> None: ...
    def write_event(self, event: Mapping[str, Any]) -> None: ...
    def write_credential(self, credential: CredentialRecord) -> None: ...
    def write_policy_state(self, snapshot: PolicyStateSnapshot) -> None: ...
    def write_scenario(self, compiled_scenario: Any) -> None: ...
    def write_environment(self, environment: Mapping[str, Any]) -> None: ...
    def write_graph(self, graph: Any) -> None: ...
    def finalize(self, *, status: str, warnings: Sequence[str] = ()) -> Any: ...


#: PROBE-kind phase names actually used across the shipped scenario corpus,
#: mapped to the fixed ``PlanPhase`` vocabulary ``Observation.phase`` uses.
#: Deliberately explicit rather than a heuristic (CAP-1's "never silently
#: guess" philosophy applies here too): a scenario author introducing a new
#: PROBE phase name gets a clear error naming the phase, not a
#: mis-attributed observation. Extend this table -- never fall back to a
#: default -- when a later milestone's scenario needs a phase name not
#: listed here.
PHASE_NAME_TO_PLAN_PHASE: dict[str, PlanPhase] = {
    "baseline": PlanPhase.BASELINE,
    "confirm-present": PlanPhase.BASELINE,
    "after-delegation": PlanPhase.POST_DELEGATION,
    "final": PlanPhase.FINAL,
}


def resolve_plan_phase(phase_name: str) -> PlanPhase:
    try:
        return PHASE_NAME_TO_PLAN_PHASE[phase_name]
    except KeyError:
        raise ExecutionError(
            f"no PlanPhase mapping for scenario phase name {phase_name!r}; add one to "
            "execution.orchestrator.PHASE_NAME_TO_PLAN_PHASE rather than guessing",
            phase_name=phase_name,
        ) from None


@dataclass(frozen=True, slots=True)
class DiscardedMatrix:
    """A matrix C-1 or C-2 discarded (F4/F5) -- recorded so a run that hit
    one is visibly distinguishable from a clean run, never silently absorbed."""

    matrix_id: str
    phase_name: str
    reason: str


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    run_id: str
    status: RunStatus
    discarded_matrices: tuple[DiscardedMatrix, ...] = ()


def orchestrate(
    compiled: CompiledScenario,
    adapter: ProviderAdapter,
    sink: EvidenceSink,
    precondition_registry: PreconditionRegistry,
    *,
    run_id: str,
    envelope: SafetyEnvelope,
    seed: int,
    max_duration_seconds: int,
    now: Callable[[], datetime],
    cost_table: dict[str, float] | None = None,
) -> OrchestrationResult:
    """F1: preflight, materialize identities, walk the compiled plan, clean
    up. Writes every observation/event/credential to ``sink`` as it goes
    (F2's crash-safety) and calls ``sink.finalize()`` only on a clean
    completion -- an aborted run's caller is expected to have opened ``sink``
    in a ``with`` block, so ``close()`` (never ``finalize()``) still runs
    when an exception propagates out of here (S2).
    """
    catalog = load_catalog()
    clock = RunClock(max_duration_seconds)
    salt = run_salt(run_id)  # type: ignore[arg-type]
    discarded: list[DiscardedMatrix] = []
    # Visible to the `finally` block below regardless of how far the `try`
    # got: `materialized is None` means nothing was ever mutated, so there
    # is nothing to revert; `pending_reverts` only grows after a mutation
    # actually succeeded (M12, F8/F9).
    materialized: delegation.MaterializedGraph | None = None
    pending_reverts: list[revert.RevertPlan] = []
    sequence = 0
    # M13, F1: which credential was current for each identity as of each
    # phase that actually ran against it -- what a later DEFERRED_EXECUTION
    # phase's credential_source resolves against.
    credential_store = CredentialStore()

    try:
        environment = adapter.describe_environment()

        # SI-5/SI-6/SI-8: the SafetyGate, before anything else happens.
        SafetyGate().authorize(
            envelope,
            account_id=environment.account_ref,
            region=environment.region,
            namespace=environment.namespace,
            compiled=compiled,
            cost_table=cost_table,
        )

        clock.check()
        preflight_report = adapter.preflight(envelope)
        if not preflight_report.passed:
            failed = tuple(c.name for c in preflight_report.checks if not c.passed)
            raise SafetyEnvelopeError(f"preflight failed: {failed}", failed_checks=list(failed))

        sink.write_scenario(compiled)
        sink.write_environment(environment.model_dump())
        sink.write_graph(compiled.graph)

        clock.check()
        materialized = chain.materialize_chain(
            adapter, compiled.graph, max_delegation_depth=envelope.max_delegation_depth
        )
        for credential in materialized.credentials.values():
            if credential is not None:
                sink.write_credential(credential)

        provisioning_ref = adapter.register_identity("bootstrap")

        matrices_by_phase_name = {m.phase_name: m for m in compiled.probe_matrices}
        mutation_plans_by_name = {m.phase_name: m for m in compiled.mutation_plans}
        poll_plans_by_name = {p.phase_name: p for p in compiled.poll_plans}
        wait_plans_by_name = {w.phase_name: w for w in compiled.wait_plans}
        deferred_plans_by_name = {d.phase_name: d for d in compiled.deferred_execution_plans}
        task_plans_by_name = {t.phase_name: t for t in compiled.task_plans}

        for step in compiled.plan:
            clock.check()  # S1/SI-7: deadline checked at every phase boundary.

            if step.kind is PhaseKind.PROBE:
                probe_matrix = matrices_by_phase_name.get(step.phase_name)
                if probe_matrix is None:  # pragma: no cover -- compiler's own invariant
                    raise ExecutionError(
                        f"compiled plan step {step.phase_name!r} is PROBE but no "
                        "matching ProbeMatrix exists -- a compiler invariant was violated",
                        phase_name=step.phase_name,
                    )
                plan_phase = resolve_plan_phase(step.phase_name)
                current_time = now()

                estimated_duration_s = matrix.estimate_matrix_duration_s(probe_matrix)
                for identity_id in probe_matrix.identities:
                    # A matrix identity always has a materialized ref: an unreachable
                    # identity is a compile-time ScenarioSemanticError ("never reached"),
                    # never a compiled matrix (G-2's own reachability guarantee).
                    if identity_id not in materialized.refs:  # pragma: no cover
                        continue
                    _, _, redelegation_event = delegation.ensure_fresh_credential(
                        adapter,
                        materialized,
                        identity_id,
                        now=current_time,
                        estimated_matrix_duration_s=estimated_duration_s,
                        sequence=sequence,
                    )
                    if redelegation_event is not None:
                        sink.write_event(redelegation_event)
                        sequence += 1
                    # M13, F1: whatever credential is current for this
                    # identity as of this phase is what a later
                    # credential_source: phase:<name> reference resolves to.
                    credential_store.record(
                        step.phase_name, identity_id, materialized.credentials.get(identity_id)
                    )

                try:
                    matrix_run = matrix.run_probe_matrix(
                        adapter,
                        probe_matrix,
                        materialized,
                        catalog,
                        precondition_registry,
                        run_id=run_id,
                        phase=plan_phase,
                        seed=seed,
                        provisioning_ref=provisioning_ref,
                        now=current_time,
                        salt=salt,
                        namespace=environment.namespace,
                        sequence_start=sequence,
                    )
                except (PreconditionFailedError, ControlCapabilityFailedError) as exc:
                    discarded.append(
                        DiscardedMatrix(
                            matrix_id=probe_matrix.matrix_id,
                            phase_name=step.phase_name,
                            reason=str(exc),
                        )
                    )
                    sink.write_event(
                        {
                            "event_id": f"ev_discard_{probe_matrix.matrix_id}",
                            "sequence": sequence,
                            "kind": "MATRIX_DISCARDED",
                            "matrix_id": probe_matrix.matrix_id,
                            "phase_name": step.phase_name,
                            "reason": str(exc),
                        }
                    )
                    sequence += 1
                    continue

                for observation in matrix_run.observations:
                    sink.write_observation(observation)
                for event in matrix_run.events:
                    sink.write_event(event)
                sequence = matrix_run.next_sequence

            elif step.kind is PhaseKind.SNAPSHOT:
                # Auto-inserted by scenarios/plan.py immediately before and
                # after every MUTATE step (F4); the base MUTATE phase name is
                # recovered by stripping the suffix plan.py added.
                base_name = step.phase_name.removesuffix("-pre-snapshot").removesuffix(
                    "-post-snapshot"
                )
                mutation_plan = mutation_plans_by_name.get(base_name)
                if mutation_plan is None:
                    # Reachable in practice only via a synthetic/injected
                    # SNAPSHOT step with no matching MUTATE (plan.py's real
                    # compiler always inserts these paired) -- a harmless
                    # no-op rather than an invariant violation, since a
                    # SNAPSHOT alone can't corrupt anything.
                    continue
                if mutation_plan.target_identity in materialized.refs:
                    target_ref = materialized.refs[mutation_plan.target_identity]
                    sink.write_policy_state(adapter.snapshot_policy_state(target_ref))

            elif step.kind is PhaseKind.MUTATE:
                mutation_plan = mutation_plans_by_name.get(step.phase_name)
                if mutation_plan is None:  # pragma: no cover -- compiler's own invariant
                    raise ExecutionError(
                        f"compiled plan step {step.phase_name!r} is MUTATE but no "
                        "matching MutationPlan exists -- a compiler invariant was violated",
                        phase_name=step.phase_name,
                    )
                revert_plan = revert.build_revert_plan(
                    compiled.graph, mutation_plan.target_identity, mutation_plan.kind
                )
                # F8: the revert log is written *before* the mutation runs,
                # so a killed run still leaves actionable recovery
                # information on disk even if nothing further executes.
                sink.write_event(revert.build_revert_log_event(revert_plan, sequence=sequence))
                sequence += 1

                outcome = mutation.apply_mutation(
                    adapter, materialized, mutation_plan, sequence=sequence
                )
                pending_reverts.append(revert_plan)
                sink.write_event(outcome.event)
                sequence += 1

            elif step.kind is PhaseKind.POLL:
                poll_plan = poll_plans_by_name.get(step.phase_name)
                if poll_plan is None:  # pragma: no cover -- compiler's own invariant
                    raise ExecutionError(
                        f"compiled plan step {step.phase_name!r} is POLL but no "
                        "matching PollPlan exists -- a compiler invariant was violated",
                        phase_name=step.phase_name,
                    )
                poll_run = polling.run_poll_phase(
                    adapter,
                    materialized,
                    poll_plan,
                    run_id=run_id,
                    matrix_id=f"pm-poll-{step.phase_name}",
                    now=now,
                    salt=salt,
                    namespace=environment.namespace,
                    sequence_start=sequence,
                )
                for observation in poll_run.observations:
                    sink.write_observation(observation)
                sequence = poll_run.next_sequence
                sink.write_event(
                    {
                        "event_id": new_event_id(),
                        "sequence": sequence,
                        "kind": "POLL_STOPPED",
                        "phase_name": step.phase_name,
                        "stop_reason": poll_run.stop_reason,
                        "poll_count": poll_run.poll_count,
                    }
                )
                sequence += 1

            elif step.kind is PhaseKind.WAIT:
                wait_plan = wait_plans_by_name.get(step.phase_name)
                if wait_plan is None:  # pragma: no cover -- compiler's own invariant
                    raise ExecutionError(
                        f"compiled plan step {step.phase_name!r} is WAIT but no "
                        "matching WaitPlan exists -- a compiler invariant was violated",
                        phase_name=step.phase_name,
                    )
                sink.write_event(deferred.run_wait_phase(adapter, wait_plan, sequence=sequence))
                sequence += 1

            elif step.kind is PhaseKind.DEFERRED_EXECUTION:
                deferred_plan = deferred_plans_by_name.get(step.phase_name)
                if deferred_plan is None:  # pragma: no cover -- compiler's own invariant
                    raise ExecutionError(
                        f"compiled plan step {step.phase_name!r} is DEFERRED_EXECUTION but no "
                        "matching DeferredExecutionPlan exists -- a compiler invariant was "
                        "violated",
                        phase_name=step.phase_name,
                    )
                deferred_run = deferred.run_deferred_execution_phase(
                    adapter,
                    materialized,
                    credential_store,
                    deferred_plan,
                    run_id=run_id,
                    now=now,
                    salt=salt,
                    namespace=environment.namespace,
                    sequence_start=sequence,
                )
                for observation in deferred_run.observations:
                    sink.write_observation(observation)
                for event in deferred_run.events:
                    sink.write_event(event)
                sequence = deferred_run.next_sequence
                # The paired fresh credential is a new, live materialization
                # for this identity -- record it too (S1: pinned credential
                # material is scrubbed by run_deferred_execution_phase
                # itself the same way materialize_chain scrubs every other
                # hop's; this is the safe CredentialRecord projection).
                # Always present: run_deferred_execution_phase already
                # requires a delegation edge for this identity (never the
                # root), so a credential was necessarily just minted -- the
                # None branch is unreachable by that guarantee, kept only
                # because MaterializedGraph.credentials' declared type is
                # Optional for the root's own sake.
                fresh_credential = materialized.credentials[deferred_plan.target_identity]
                if fresh_credential is not None:  # pragma: no branch
                    sink.write_credential(fresh_credential)

            elif step.kind is PhaseKind.TASK:
                task_plan = task_plans_by_name.get(step.phase_name)
                if task_plan is None:  # pragma: no cover -- compiler's own invariant
                    raise ExecutionError(
                        f"compiled plan step {step.phase_name!r} is TASK but no "
                        "matching TaskPlan exists -- a compiler invariant was violated",
                        phase_name=step.phase_name,
                    )
                task_run = task_runner.run_task(
                    adapter,
                    materialized,
                    task_plan,
                    run_id=run_id,
                    provisioning_ref=provisioning_ref,
                    now=now,
                    salt=salt,
                    namespace=environment.namespace,
                    sequence_start=sequence,
                )
                for observation in task_run.observations:
                    sink.write_observation(observation)
                for event in task_run.events:
                    sink.write_event(event)
                sequence = task_run.next_sequence

            else:  # pragma: no cover -- every PhaseKind member has its own branch above (M14)
                raise ExecutionError(
                    f"phase {step.phase_name!r} ({step.kind}) has no orchestrator branch -- "
                    "a new PhaseKind member was added without one",
                    phase_name=step.phase_name,
                    phase_kind=str(step.kind),
                )

        status = RunStatus.COMPLETED
    finally:
        # F8/F9: revert every mutation this run actually applied, in reverse
        # order, regardless of whether the run completed, raised a
        # ChainbreakError, or an uncaught exception propagated out of here.
        if materialized is not None:
            for plan in reversed(pending_reverts):
                revert_event = revert.revert_mutation(adapter, plan, sequence=sequence)
                if revert_event is not None:
                    sink.write_event(revert_event)
                    sequence += 1

    manifest_warnings = [
        f"matrix {d.matrix_id!r} (phase {d.phase_name!r}) discarded: {d.reason}" for d in discarded
    ]
    sink.finalize(status=status.value, warnings=manifest_warnings)
    return OrchestrationResult(run_id=run_id, status=status, discarded_matrices=tuple(discarded))
