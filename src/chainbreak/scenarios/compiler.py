"""``ScenarioDocument`` -> ``CompiledScenario`` (SCENARIO_SPECIFICATION.md section 10).

Stages 3 (semantic) and 4 (provider binding) of the five-stage validation
pipeline are, in practice, what this module's graph-building and
binding-resolution steps surface: a ``ScenarioSemanticError`` raised here
*is* a stage-3 failure, a ``CapabilityResolutionError``/
``BindingValidationError`` raised here *is* a stage-4 failure.
``scenarios/loader.py`` (stages 1-2 plus overall orchestration) is what maps
these to the documented exit codes.
"""

from __future__ import annotations

from chainbreak.capabilities.loader import resolve_bindings
from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.canonical import dumps
from chainbreak.core.enums import PhaseKind, PlanPhase
from chainbreak.core.errors import ScenarioSemanticError
from chainbreak.core.ids import fingerprint_json
from chainbreak.core.models import (
    AuthoritySet,
    AuthorizationGraph,
    CapabilityCatalog,
    CompiledExpectation,
    CompiledExpectedFinding,
    CompiledScenario,
    CompileWarning,
    DeferredExecutionPlan,
    DelegationEdge,
    ExpectedAuthority,
    IdentityNode,
    MutationPlan,
    PollPlan,
    ProbeMatrix,
    TaskPlan,
    TaskStepPlan,
    WaitPlan,
)
from chainbreak.graph.builder import build_graph
from chainbreak.scenarios.plan import build_plan
from chainbreak.scenarios.policy_synthesis import synthesize_policy
from chainbreak.scenarios.schema import DelegationSpec, ScenarioDocument, ScenarioSpec

_WHOAMI = "identity.whoami"


def compile_scenario(
    document: ScenarioDocument,
    *,
    catalog: CapabilityCatalog,
    registry: BindingRegistry,
    adapter_version: str = "0.1.0",
    max_delegation_depth: int = 6,
) -> CompiledScenario:
    spec = document.spec

    nodes, edges = _build_nodes_and_edges(spec)

    downgrade_g3 = bool(
        spec.negative_control and "G-3" in spec.negative_control.suppress_graph_check
    )
    graph, graph_warnings = build_graph(
        nodes,
        edges,
        catalog=catalog,
        max_delegation_depth=max_delegation_depth,
        downgrade_intent_exceeds_parent=downgrade_g3,
    )

    # Stage 4: every capability named anywhere must have a binding in the
    # declared provider.
    referenced = _named_capabilities(spec)
    resolve_bindings(catalog, referenced, registry.for_provider(spec.provider), spec.provider)

    probe_matrices = _build_probe_matrices(spec, graph, catalog)
    mutation_plans = _build_mutation_plans(spec)
    poll_plans = _build_poll_plans(spec)
    wait_plans = _build_wait_plans(spec)
    deferred_execution_plans = _build_deferred_execution_plans(spec, graph, catalog)
    task_plans = _build_task_plans(spec)
    plan = build_plan(spec.phases)

    edges_by_id = {edge.edge_id: edge for edge in edges}
    policy_artifacts = tuple(
        synthesize_policy(
            delegation.to,
            edges_by_id[delegation.id].expected_effective,
            edge_id=delegation.id,
        )
        for delegation in spec.delegations
    )

    warnings = tuple(CompileWarning(code="G-3", message=message) for message in graph_warnings)

    return CompiledScenario(
        compiled_hash=_compiled_hash(document, catalog.version, adapter_version),
        scenario_id=document.metadata.id,
        scenario_version=document.metadata.version,
        catalog_version=catalog.version,
        adapter_version=adapter_version,
        graph=graph,
        probe_matrices=probe_matrices,
        mutation_plans=mutation_plans,
        poll_plans=poll_plans,
        wait_plans=wait_plans,
        deferred_execution_plans=deferred_execution_plans,
        task_plans=task_plans,
        plan=plan,
        policy_artifacts=policy_artifacts,
        warnings=warnings,
        expected_finding=_compiled_expected_finding(spec),
        expectations=_compiled_expectations(spec),
    )


def _build_nodes_and_edges(
    spec: ScenarioSpec,
) -> tuple[tuple[IdentityNode, ...], tuple[DelegationEdge, ...]]:
    """Expected-authority derivation is intersection, not assignment (F2):
    ``node.expected = parent.expected & edge.intended``. A redundant
    ``expect_capabilities`` declaration is checked for agreement and the
    error names both values on mismatch.
    """
    identities_by_id = {identity.id: identity for identity in spec.identities}
    root_spec = next(identity for identity in spec.identities if identity.role == "root")

    children_by_parent: dict[str, list[str]] = {}
    delegation_by_id: dict[str, DelegationSpec] = {}
    targets_seen: dict[str, str] = {}
    for delegation in spec.delegations:
        if delegation.to in targets_seen:
            raise ScenarioSemanticError(
                f"{delegation.to}: targeted by more than one delegation "
                f"({targets_seen[delegation.to]!r} and {delegation.id!r})",
                identity_id=delegation.to,
            )
        targets_seen[delegation.to] = delegation.id
        children_by_parent.setdefault(delegation.from_, []).append(delegation.id)
        delegation_by_id[delegation.id] = delegation

    nodes: dict[str, IdentityNode] = {}
    edges: list[DelegationEdge] = []

    def visit(
        identity_id: str, hop_index: int, parent_id: str | None, expected: AuthoritySet
    ) -> None:
        identity_spec = identities_by_id[identity_id]
        if identity_spec.expect_capabilities is not None:
            declared = AuthoritySet.of(*identity_spec.expect_capabilities)
            if declared != expected:
                raise ScenarioSemanticError(
                    f"{identity_id}: declared expect_capabilities {declared.sorted} "
                    f"disagrees with derived expected authority {expected.sorted}",
                    identity_id=identity_id,
                    declared=list(declared.sorted),
                    derived=list(expected.sorted),
                )

        nodes[identity_id] = IdentityNode(
            identity_id=identity_id,
            is_root=(parent_id is None),
            hop_index=hop_index,
            parent_id=parent_id,
            expected_authority=ExpectedAuthority(
                capabilities=expected,
                phase=PlanPhase.POST_DELEGATION,
                derivation="DECLARED" if parent_id is None else "INHERITED_ATTENUATED",
            ),
        )

        for delegation_id in children_by_parent.get(identity_id, ()):
            delegation = delegation_by_id[delegation_id]
            intended = AuthoritySet.of(*delegation.intended_capabilities)
            child_expected = expected & intended
            edges.append(
                DelegationEdge(
                    edge_id=delegation.id,
                    source_id=delegation.from_,
                    target_id=delegation.to,
                    mechanism=delegation.mechanism,
                    requested_capabilities=intended,
                    intended_capabilities=intended,
                    expected_effective=child_expected,
                    credential_lifetime_s=delegation.credential.requested_lifetime_seconds,
                )
            )
            visit(delegation.to, hop_index + 1, identity_id, child_expected)

    visit(root_spec.id, 0, None, AuthoritySet.of(*(root_spec.capabilities or ())))

    unreached = set(identities_by_id) - set(nodes)
    if unreached:
        raise ScenarioSemanticError(
            f"identities never reached by a delegation from the root: {sorted(unreached)}",
            unreached=sorted(unreached),
        )

    return tuple(nodes[identity.id] for identity in spec.identities), tuple(edges)


def _named_capabilities(spec: ScenarioSpec) -> AuthoritySet:
    """The union of every capability named anywhere in the scenario -- the
    default probe universe (F3). Testing only what a node is *expected* to
    hold cannot detect authority expansion; testing everything the scenario
    ever mentions can."""
    caps: set[str] = set()
    for identity in spec.identities:
        caps |= set(identity.capabilities or ())
        caps |= set(identity.expect_capabilities or ())
    for delegation in spec.delegations:
        caps |= set(delegation.intended_capabilities)
    for phase in spec.phases:
        if phase.capability:
            caps.add(phase.capability)
        if phase.mutation:
            caps |= set(phase.mutation.denies) | set(phase.mutation.grants)
    for task in spec.tasks:
        caps |= set(task.requires_capabilities) | {step.use for step in task.steps}
    for expectation in spec.expectations:
        caps |= set(expectation.allow) | set(expectation.deny)
        if expectation.capability:
            caps.add(expectation.capability)
    return AuthoritySet.from_iterable(caps)


def _capability_universe(
    spec: ScenarioSpec,
    graph: AuthorizationGraph,
    catalog: CapabilityCatalog,
    named: AuthoritySet,
    identities: tuple[str, ...],
) -> AuthoritySet:
    """F3's probe-universe selection, shared by ``_build_probe_matrices`` and
    ``_build_deferred_execution_plans``: every capability the scenario
    names, not only what a node is expected to hold -- you cannot detect
    expansion by testing only for what you expect."""
    if spec.execution.probe_universe == "catalog":
        capabilities = catalog.ids()
    elif spec.execution.probe_universe == "declared":
        declared: set[str] = set()
        for identity_id in identities:
            declared |= set(graph.node(identity_id).expected_authority.capabilities)
        capabilities = AuthoritySet.from_iterable(declared)
    else:
        capabilities = named
    return capabilities | AuthoritySet.of(_WHOAMI)


def _build_probe_matrices(
    spec: ScenarioSpec, graph: AuthorizationGraph, catalog: CapabilityCatalog
) -> tuple[ProbeMatrix, ...]:
    named = _named_capabilities(spec)
    matrices: list[ProbeMatrix] = []

    for phase in spec.phases:
        if phase.kind not in (PhaseKind.PROBE, PhaseKind.DEFERRED_EXECUTION):
            continue
        identities = phase.targets or ((phase.target_identity,) if phase.target_identity else ())
        if not identities:
            continue

        capabilities = _capability_universe(spec, graph, catalog, named, identities)
        matrices.append(
            ProbeMatrix(
                matrix_id=f"pm-{phase.name}",
                phase_name=phase.name,
                identities=identities,
                capabilities=capabilities,
                # DEFERRED_EXECUTION issues two real probes per capability
                # (pinned credential, then a freshly minted one -- F3): S4's
                # "never underestimate" applies to this matrix's own
                # contribution to estimate_cost even though
                # execution/deferred.py, not this matrix, actually runs it.
                trials=2 if phase.kind is PhaseKind.DEFERRED_EXECUTION else spec.execution.trials,
            )
        )
    return tuple(matrices)


def _build_wait_plans(spec: ScenarioSpec) -> tuple[WaitPlan, ...]:
    """M13: strips each ``WAIT`` phase down to exactly what
    ``execution/deferred.py`` needs."""
    return tuple(
        WaitPlan(phase_name=phase.name, wait_seconds=phase.wait_seconds)
        for phase in spec.phases
        if phase.kind is PhaseKind.WAIT
    )


def _build_deferred_execution_plans(
    spec: ScenarioSpec, graph: AuthorizationGraph, catalog: CapabilityCatalog
) -> tuple[DeferredExecutionPlan, ...]:
    """M13: strips each ``DEFERRED_EXECUTION`` phase down to exactly what
    ``execution/deferred.py`` needs -- the compiler's own analogue of
    :class:`MutationPlan`/:class:`PollPlan` for the stale-authority family."""
    named = _named_capabilities(spec)
    plans: list[DeferredExecutionPlan] = []
    for phase in spec.phases:
        if phase.kind is not PhaseKind.DEFERRED_EXECUTION:
            continue
        if phase.target_identity is None or phase.credential_source is None:
            continue  # pragma: no cover -- PhaseSpec's own validator guarantees this
        capabilities = _capability_universe(spec, graph, catalog, named, (phase.target_identity,))
        plans.append(
            DeferredExecutionPlan(
                phase_name=phase.name,
                target_identity=phase.target_identity,
                capabilities=capabilities,
                credential_source=phase.credential_source,
            )
        )
    return tuple(plans)


def _build_task_plans(spec: ScenarioSpec) -> tuple[TaskPlan, ...]:
    """M14: strips each ``TASK`` phase down to exactly what
    ``execution/task_runner.py`` needs -- the compiler's own analogue of
    :class:`MutationPlan`/:class:`PollPlan`/:class:`DeferredExecutionPlan`
    for the silent-narrowing family. Keyed by ``phase_name``, not
    ``task_id``: a scenario's ``tasks`` list is declared separately from the
    ``phases`` list that references it by name (``phase.task``), matching
    how ``ScenarioSpec._referential_integrity`` already validates that
    reference exists before compilation reaches here."""
    tasks_by_id = {task.id: task for task in spec.tasks}
    plans: list[TaskPlan] = []
    for phase in spec.phases:
        if phase.kind is not PhaseKind.TASK:
            continue
        if phase.task is None:  # pragma: no cover -- PhaseSpec's own validator guarantees this
            continue
        task = tasks_by_id[phase.task]
        plans.append(
            TaskPlan(
                phase_name=phase.name,
                task_id=task.id,
                worker=task.worker,
                target_identity=task.identity,
                requires_capabilities=AuthoritySet.of(*task.requires_capabilities),
                steps=tuple(
                    TaskStepPlan(capability_id=step.use, on_failure=step.on_failure)
                    for step in task.steps
                ),
                must_report_partial=task.completion_contract.must_report_partial,
                must_not_substitute=task.completion_contract.must_not_substitute,
                must_not_redelegate=task.completion_contract.must_not_redelegate,
            )
        )
    return tuple(plans)


def _build_mutation_plans(spec: ScenarioSpec) -> tuple[MutationPlan, ...]:
    """M12: strips each ``MUTATE`` phase down to exactly what
    ``execution/mutation.py`` needs -- the same "compile once, execute from
    the compiled form only" discipline ``_build_probe_matrices`` already
    applies to ``PROBE`` phases."""
    plans: list[MutationPlan] = []
    for phase in spec.phases:
        if phase.kind is not PhaseKind.MUTATE:
            continue
        mutation = phase.mutation
        if mutation is None:  # pragma: no cover -- PhaseSpec's own validator guarantees this
            continue
        plans.append(
            MutationPlan(
                phase_name=phase.name,
                target_identity=mutation.target_identity,
                kind=mutation.kind,
                denies_capabilities=AuthoritySet.of(*mutation.denies),
                grants_capabilities=AuthoritySet.of(*mutation.grants),
                record_receipt=mutation.record_receipt,
            )
        )
    return tuple(plans)


def _build_poll_plans(spec: ScenarioSpec) -> tuple[PollPlan, ...]:
    """M12: strips each ``POLL`` phase down to exactly what
    ``execution/polling.py`` needs."""
    plans: list[PollPlan] = []
    for phase in spec.phases:
        if phase.kind is not PhaseKind.POLL:
            continue
        if phase.target_identity is None or phase.capability is None:
            continue  # pragma: no cover -- PhaseSpec's own validator guarantees this
        plans.append(
            PollPlan(
                phase_name=phase.name,
                target_identity=phase.target_identity,
                capability_id=phase.capability,
                interval_ms=phase.interval_ms,
                max_duration_seconds=phase.max_duration_seconds,
                stop_on=phase.stop_on,
                stability_count=phase.stability_count,
            )
        )
    return tuple(plans)


def _compiled_expected_finding(spec: ScenarioSpec) -> CompiledExpectedFinding | None:
    if spec.negative_control is None:
        return None
    expectation = spec.negative_control.expect_finding
    return CompiledExpectedFinding(
        type=expectation.type,
        identity_id=expectation.identity,
        capabilities=AuthoritySet.of(*expectation.capabilities),
        min_confidence=expectation.min_confidence,
    )


def _compiled_expectations(spec: ScenarioSpec) -> tuple[CompiledExpectation, ...]:
    return tuple(
        CompiledExpectation(
            kind=expectation.kind,
            identity_id=expectation.identity,
            phase=expectation.phase,
            allow=AuthoritySet.of(*expectation.allow),
            deny=AuthoritySet.of(*expectation.deny),
            path=expectation.path,
            mode=expectation.mode,
            capability_id=expectation.capability,
            max_seconds=expectation.max_seconds,
            severity=expectation.severity,
            justification=expectation.justification,
            task_id=expectation.task,
        )
        for expectation in spec.expectations
    )


def _compiled_hash(document: ScenarioDocument, catalog_version: str, adapter_version: str) -> str:
    """SHA-256 over canonical spec + catalog version + adapter version (F5).

    Uses ``core/canonical.py`` exclusively -- never ``json.dumps`` directly --
    so the hash is byte-identical for identical input across processes.
    """
    payload = {
        "spec": document,
        "catalog_version": catalog_version,
        "adapter_version": adapter_version,
    }
    return fingerprint_json(dumps(payload))
