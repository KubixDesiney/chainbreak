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
    CompiledExpectedFinding,
    CompiledScenario,
    CompileWarning,
    DelegationEdge,
    ExpectedAuthority,
    IdentityNode,
    ProbeMatrix,
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
        plan=plan,
        policy_artifacts=policy_artifacts,
        warnings=warnings,
        expected_finding=_compiled_expected_finding(spec),
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

        if spec.execution.probe_universe == "catalog":
            capabilities = catalog.ids()
        elif spec.execution.probe_universe == "declared":
            declared: set[str] = set()
            for identity_id in identities:
                declared |= set(graph.node(identity_id).expected_authority.capabilities)
            capabilities = AuthoritySet.from_iterable(declared)
        else:
            capabilities = named

        capabilities = capabilities | AuthoritySet.of(_WHOAMI)
        matrices.append(
            ProbeMatrix(
                matrix_id=f"pm-{phase.name}",
                phase_name=phase.name,
                identities=identities,
                capabilities=capabilities,
                trials=spec.execution.trials,
            )
        )
    return tuple(matrices)


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
