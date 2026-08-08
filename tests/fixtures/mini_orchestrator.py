"""A test-only stand-in for the M10 orchestrator (``execution/orchestrator.py``
does not exist yet).

Extends the walk ``tests/integration/test_fake_scenario_compatibility.py``
established at M5 (compile a real scenario, delegate along every edge,
probe every matrix cell through the fake adapter) in two directions M7's
tests need that M5's crash-only check did not:

1. Collects real :class:`Observation`/:class:`CredentialRecord` records
   (with proper trial repetition) instead of only proving nothing raises,
   and assembles them into a real, sealed evidence bundle via
   :class:`chainbreak.evidence.writer.BundleWriter`.
2. Drives a policy mutation plus a serial poll sequence for revocation-
   family scenarios, using the fake adapter's virtual clock directly rather
   than parsing a scenario's ``POLL``/``MUTATE`` phase specs (that
   parsing -- ``execution/polling.py``, ``execution/mutation.py`` -- is
   M12's job).

This module produces data through the *same* fake-adapter code path M5's
own tests exercise; nothing here is synthetic beyond the choice of which
adapter calls to make and in what order.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from chainbreak.capabilities.loader import load_catalog
from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.enums import PlanPhase
from chainbreak.core.ids import new_ulid
from chainbreak.core.models import (
    CompiledScenario,
    CredentialRecord,
    IdentityRef,
    MutationKind,
    Observation,
    PolicyMutation,
)
from chainbreak.evidence.writer import BundleWriter
from chainbreak.providers.base.types import DelegationRequest, ProbeRequest
from chainbreak.providers.fake.adapter import FakeProviderAdapter
from chainbreak.providers.fake.profiles import deterministic_profile
from chainbreak.scenarios.compiler import compile_scenario
from chainbreak.scenarios.safety import load_scenario_yaml
from chainbreak.scenarios.schema import ScenarioDocument


def compile_and_delegate(
    scenario_path: Path,
    registry: BindingRegistry,
    *,
    seed: int = 1,
    profile: Any = deterministic_profile,
) -> tuple[CompiledScenario, FakeProviderAdapter, dict[str, IdentityRef], list[CredentialRecord]]:
    """Compile ``scenario_path`` and delegate along every edge, exactly as
    ``test_fake_scenario_compatibility.py``'s ``_walk`` does."""
    catalog = load_catalog()
    document = ScenarioDocument(**load_scenario_yaml(scenario_path))
    compiled = compile_scenario(document, catalog=catalog, registry=registry)

    adapter = profile(seed=seed)
    refs: dict[str, IdentityRef] = {}
    credentials: list[CredentialRecord] = []
    nodes_by_id = {node.identity_id: node for node in compiled.graph.nodes}

    for node in compiled.graph.nodes:
        if node.is_root:
            refs[node.identity_id] = adapter.register_identity(
                node.identity_id, allow=node.expected_authority.capabilities
            )

    for edge in compiled.graph.edges:
        source_ref = refs[edge.source_id]
        result = adapter.delegate(
            DelegationRequest(
                source_identity=source_ref,
                target_identity_id=edge.target_id,
                mechanism=edge.mechanism,
                requested_duration_s=edge.credential_lifetime_s,
                intended_capabilities=edge.intended_capabilities,
            )
        )
        refs[edge.target_id] = result.identity_ref
        credentials.append(result.record)
        target_node = nodes_by_id[edge.target_id]
        if not adapter.engine.is_registered(edge.target_id):
            adapter.register_identity(
                edge.target_id, allow=target_node.expected_authority.capabilities
            )

    return compiled, adapter, refs, credentials


def probe_observations(
    compiled: CompiledScenario,
    adapter: FakeProviderAdapter,
    refs: dict[str, IdentityRef],
    run_id: str,
    *,
    phase: PlanPhase,
    sequence_start: int = 0,
) -> list[Observation]:
    """Probe every cell of every compiled matrix, ``matrix.trials`` times
    each (ADR-012's unanimity needs real trial repetition, not a single
    call), tagged with the caller-supplied semantic ``phase``: a scenario's
    own free-form phase *name* (``matrix.phase_name``, e.g.
    ``"after-delegation"``) is not the same vocabulary as
    ``Observation.phase``'s fixed ``PlanPhase`` enum, and resolving that
    mapping in general is the same M10 orchestration job this module stands
    in for -- callers of this helper choose the phase explicitly instead.
    """
    observations: list[Observation] = []
    sequence = sequence_start
    for matrix in compiled.probe_matrices:
        for identity_id in matrix.identities:
            if identity_id not in refs:
                continue
            for capability_id in matrix.capabilities:
                binding = adapter.resolve_capability(capability_id)
                for trial in range(1, matrix.trials + 1):
                    result = adapter.probe(
                        ProbeRequest(
                            identity_ref=refs[identity_id],
                            capability_id=capability_id,
                            binding=binding,
                            namespace=adapter.namespace,
                            trial=trial,
                        )
                    )
                    sequence += 1
                    observations.append(
                        Observation(
                            observation_id=f"obs_{new_ulid()}",
                            run_id=run_id,
                            sequence=sequence,
                            phase=phase,
                            probe_matrix_id=matrix.matrix_id,
                            identity_id=identity_id,
                            identity_ref_hash="sha256:" + ("0" * 64),
                            capability_id=capability_id,
                            trial=trial,
                            trial_count=matrix.trials,
                            request=_request_record(binding, capability_id, adapter),
                            timing=result.timing,
                            outcome=result.outcome,
                            preconditions_verified=True,
                        )
                    )
    return observations


def _request_record(binding: Any, capability_id: str, adapter: FakeProviderAdapter) -> Any:
    from chainbreak.core.models import ProbeRequestRecord

    return ProbeRequestRecord(
        probe_kind=binding.probe_kind,
        binding_actions=binding.actions,
        target_ref_hash="sha256:" + ("1" * 64),
        target_namespace=adapter.namespace,
        parameters_fingerprint="sha256:" + ("2" * 64),
    )


def mutate_and_poll(
    adapter: FakeProviderAdapter,
    target_identity: str,
    *,
    denies: tuple[str, ...],
    mutation_kind: MutationKind = MutationKind.ATTACH_INLINE_DENY,
    baseline_poll_count: int = 3,
    poll_count: int = 6,
    poll_interval_ms: int = 500,
) -> tuple[dict[str, Any], list[tuple[str, Any]]]:
    """Warm a stable-ALLOW baseline (``baseline_poll_count`` polls -- a real
    transition measurement needs samples on both sides of the mutation, not
    only after it), apply a policy mutation, then serially poll every denied
    capability ``poll_count`` more times, advancing the adapter's virtual
    clock by ``poll_interval_ms`` before each poll -- the same serial,
    single-concurrency discipline ADR-011 requires of a real timing scenario.

    Returns ``(mutation_event, [(capability_id, ProbeResult), ...])`` for
    *every* poll, baseline included, in chronological order; the event dict
    matches EVIDENCE_SCHEMA.md section 4's ``POLICY_MUTATION_APPLIED`` shape
    so :mod:`chainbreak.analysis.pipeline` can read it back exactly as it
    would from a real bundle.
    """
    ref = adapter._make_ref(target_identity)

    baseline_results: list[tuple[str, Any]] = []
    for _ in range(baseline_poll_count):
        adapter.advance_clock(poll_interval_ms)
        for capability_id in denies:
            binding = adapter.resolve_capability(capability_id)
            result = adapter.probe(
                ProbeRequest(
                    identity_ref=ref,
                    capability_id=capability_id,
                    binding=binding,
                    namespace=adapter.namespace,
                    trial=1,
                )
            )
            baseline_results.append((capability_id, result))

    mutation = PolicyMutation(
        mutation_id=f"mut_{new_ulid()}",
        kind=mutation_kind,
        target_identity=target_identity,
        denies_capabilities=denies,
    )
    receipt = adapter.apply_policy_mutation(mutation)

    event = {
        "event_id": f"ev_{new_ulid()}",
        "sequence": 0,
        "kind": "POLICY_MUTATION_APPLIED",
        "mutation_kind": mutation_kind.value,
        "target_identity": target_identity,
        "denies_capabilities": list(denies),
        "timing": {
            "monotonic_ns": receipt.monotonic_sent_ns,
            "wall": receipt.wall_sent.isoformat(),
        },
        "receipt": {
            "confirmed": receipt.confirmed,
            "confirmation_method": receipt.confirmation_method,
        },
        "outcome": "SUCCESS",
    }

    results: list[tuple[str, Any]] = []
    for _ in range(poll_count):
        adapter.advance_clock(poll_interval_ms)
        for capability_id in denies:
            binding = adapter.resolve_capability(capability_id)
            result = adapter.probe(
                ProbeRequest(
                    identity_ref=ref,
                    capability_id=capability_id,
                    binding=binding,
                    namespace=adapter.namespace,
                    trial=1,
                )
            )
            results.append((capability_id, result))

    return event, baseline_results + results


def poll_results_to_observations(
    results: list[tuple[str, Any]], target_identity: str, run_id: str, *, sequence_start: int = 0
) -> list[Observation]:
    from chainbreak.core.models import ProbeRequestRecord

    observations = []
    for index, (capability_id, result) in enumerate(results, start=sequence_start + 1):
        observations.append(
            Observation(
                observation_id=f"obs_{new_ulid()}",
                run_id=run_id,
                sequence=index,
                phase=PlanPhase.POST_MUTATION,
                probe_matrix_id="pm-poll-transition",
                identity_id=target_identity,
                identity_ref_hash="sha256:" + ("0" * 64),
                capability_id=capability_id,
                trial=1,
                trial_count=1,
                request=ProbeRequestRecord(
                    probe_kind="READ_MARKER",
                    binding_actions=("fake:poll",),
                    target_ref_hash="sha256:" + ("1" * 64),
                    target_namespace="cb-00000000",
                    parameters_fingerprint="sha256:" + ("2" * 64),
                ),
                timing=result.timing,
                outcome=result.outcome,
                preconditions_verified=True,
            )
        )
    return observations


def write_bundle(
    runs_root: Path,
    run_id: str,
    compiled: CompiledScenario,
    observations: list[Observation],
    *,
    events: list[dict[str, Any]] = (),  # type: ignore[assignment]
    credentials: list[CredentialRecord] = (),  # type: ignore[assignment]
    status: str = "COMPLETED",
) -> Path:
    writer = BundleWriter(
        runs_root,
        run_id,
        scenario_ref={
            "id": compiled.scenario_id,
            "version": compiled.scenario_version,
            "family": "test",
            "api_version": "chainbreak.dev/v1alpha1",
            "compiled_hash": compiled.compiled_hash,
        },
        provenance={
            "chainbreak_version": "0.1.0a0",
            "capability_catalog_version": compiled.catalog_version,
            "provider": "fake",
            "provider_adapter_version": compiled.adapter_version,
            "python_version": "3.12",
            "config_fingerprint": "sha256:" + ("3" * 64),
        },
    )
    for observation in observations:
        writer.write_observation(observation)
    for event in events:
        writer.write_event(event)
    for credential in credentials:
        writer.write_credential(credential)
    writer.write_environment({"host": {"os": "test"}})
    writer.write_scenario(compiled)
    writer.write_graph(compiled.graph)
    writer.finalize(status=status)
    return runs_root / run_id
