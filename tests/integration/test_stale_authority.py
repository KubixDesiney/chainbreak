"""M13 acceptance criteria: the stale-authority benchmark (Family D), driven
through the real ``execution/orchestrator.py`` (``execution/deferred.py``,
``execution/credential_store.py``, ``analysis/stale.py``) rather than a
hand-built bundle.

Setup mirrors ``test_revocation.py``'s own ``_run`` helper, which itself
mirrors ``test_scope_attenuation.py``'s -- the same orchestrator entry point
every family after M10 uses.

Acceptance criterion 1 (all six ``StaleAuthorityClass`` rows reachable and
tested against the fake): three rows come from real scenario runs below
(``STALE_AUTHORITY_LIVE_CREDENTIAL``, ``CREDENTIAL_EXPIRED``,
``INDETERMINATE`` -- the ambiguous "not propagated" case, reached for
free by identity.whoami in the very same runs, since it was never
mutated). ``CURRENT_AUTHORITY`` and ``SESSION_SCOPE_CACHED`` are exercised
directly against ``execution/deferred.py`` and the fake adapter without a
full YAML scenario, matching ``test_mutation.py``'s own precedent for
testing an ``execution/`` module's specific branch directly rather than
only through a scenario corpus. ``EXPIRED_CREDENTIAL_HONORED`` is the one
row a *correctly behaving* fake adapter can never produce by construction
(the fake's own liveness check refuses an expired credential before
anything else runs); its classification is covered at the pure-function
level by ``test_stale_classification.py`` (M7). ``TestExpiredCredentialHonoredWiring``
below proves the *pipeline* wiring around it anyway, by corrupting one real
observation the way only a genuine provider defect could -- the one thing
the fake's own correctness cannot demonstrate on its own.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from chainbreak.analysis.pipeline import analyze
from chainbreak.analysis.stale import stale_authority_measurements
from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.enums import (
    DelegationMechanism,
    FindingType,
    MutationKind,
    OutcomeClass,
    RunStatus,
    StaleAuthorityClass,
)
from chainbreak.core.models import (
    EMPTY_AUTHORITY,
    AuthoritySet,
    CompiledScenario,
    DeferredExecutionPlan,
    DelegationEdge,
    PolicyMutation,
    SafetyEnvelope,
)
from chainbreak.evidence.reader import (
    read_credentials,
    read_events,
    read_graph,
    read_observations,
    read_scenario,
)
from chainbreak.evidence.writer import BundleWriter
from chainbreak.execution.credential_store import CredentialStore
from chainbreak.execution.deferred import run_deferred_execution_phase
from chainbreak.execution.delegation import MaterializedGraph
from chainbreak.execution.orchestrator import OrchestrationResult, orchestrate
from chainbreak.providers.base.types import DelegationRequest
from chainbreak.providers.fake.adapter import FakeProviderAdapter
from chainbreak.providers.fake.probes import build_fake_preconditions
from chainbreak.providers.fake.session import virtual_ms_to_datetime
from chainbreak.scenarios.loader import load_and_compile

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
STALE_DIR = REPO_ROOT / "scenarios" / "stale-authority"


def _run(
    scenario_path: Path,
    tmp_path: Path,
    registry: BindingRegistry,
    *,
    run_id: str,
    adapter: FakeProviderAdapter,
) -> tuple[Path, OrchestrationResult]:
    compiled: CompiledScenario = load_and_compile(scenario_path, registry=registry)
    envelope = SafetyEnvelope(
        allowed_account_ids=(adapter.account_ref,),
        allowed_regions=(adapter.region,),
        namespace=adapter.namespace,
        namespace_pattern=f"^{adapter.namespace}$",
    )
    writer = BundleWriter(
        tmp_path,
        run_id,
        scenario_ref={
            "id": compiled.scenario_id,
            "version": compiled.scenario_version,
            "family": "stale-authority",
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
    with writer as sink:
        result = orchestrate(
            compiled,
            adapter,
            sink,
            build_fake_preconditions(adapter.markers),
            run_id=run_id,
            envelope=envelope,
            seed=13,
            max_duration_seconds=900,
            now=lambda: virtual_ms_to_datetime(adapter.clock.now_ms),
        )
    return tmp_path / run_id, result


def _measurement(run_dir: Path, capability_id: str):
    events = list(read_events(run_dir))
    observations = list(read_observations(run_dir))
    credentials = list(read_credentials(run_dir))
    measurements = stale_authority_measurements(events, observations, credentials)
    by_capability = {m.capability_id: m for m in measurements}
    return by_capability[capability_id]


class TestShortDefer:
    PATH = STALE_DIR / "short-defer.yaml"

    def test_completes(self, tmp_path: Path, synthetic_aws_registry: BindingRegistry) -> None:
        adapter = FakeProviderAdapter(seed=13)
        _run_dir, result = _run(
            self.PATH, tmp_path, synthetic_aws_registry, run_id="run-short", adapter=adapter
        )
        assert result.status is RunStatus.COMPLETED

    def test_mutated_capability_classifies_stale_authority_live_credential(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        adapter = FakeProviderAdapter(seed=13)
        run_dir, _ = _run(
            self.PATH, tmp_path, synthetic_aws_registry, run_id="run-short", adapter=adapter
        )
        measurement = _measurement(run_dir, "objectstore.read")
        assert measurement.classification is StaleAuthorityClass.STALE_AUTHORITY_LIVE_CREDENTIAL
        assert measurement.paired_fresh_credential_outcome is OutcomeClass.DENIED_EXPLICIT
        assert measurement.credential_expired_at_execution is False

    def test_unmutated_capability_classifies_indeterminate_not_stale(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        """The ambiguous case, reached for free: identity.whoami was never
        touched by the mutation, so both the pinned and fresh probes agree
        (ALLOWED). This must NOT be reported as stale -- exactly the
        confusion F3's pairing exists to prevent."""
        adapter = FakeProviderAdapter(seed=13)
        run_dir, _ = _run(
            self.PATH, tmp_path, synthetic_aws_registry, run_id="run-short", adapter=adapter
        )
        measurement = _measurement(run_dir, "identity.whoami")
        assert measurement.classification is StaleAuthorityClass.INDETERMINATE
        assert measurement.classification is not StaleAuthorityClass.STALE_AUTHORITY_LIVE_CREDENTIAL

    def test_findings_json_reports_stale_authority_with_documented_behavior_note(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        """Acceptance criterion 5: the report states, in the same paragraph
        as the result, that this is documented bearer-token behavior."""
        adapter = FakeProviderAdapter(seed=13)
        run_dir, _ = _run(
            self.PATH, tmp_path, synthetic_aws_registry, run_id="run-short", adapter=adapter
        )
        result = analyze(run_dir)
        stale_findings = [f for f in result.findings if f.type is FindingType.STALE_AUTHORITY]
        assert len(stale_findings) == 1
        finding = stale_findings[0]
        assert finding.identity_id == "agent-c"
        assert "documented" in finding.security_interpretation.lower()
        assert "not a" in finding.security_interpretation.lower()  # "not a vulnerability"

    def test_credential_expired_never_true_here(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        adapter = FakeProviderAdapter(seed=13)
        run_dir, _ = _run(
            self.PATH, tmp_path, synthetic_aws_registry, run_id="run-short", adapter=adapter
        )
        result = analyze(run_dir)
        assert not any(f.type is FindingType.EXPIRED_CREDENTIAL_ACCEPTED for f in result.findings)


class TestLongDefer:
    """F6: the deferral sweep's longest interval (600 s). Same credential
    lifetime as short-defer.yaml (3600 s, comfortably unexpired) -- the
    point is that classification does not change merely because more time
    passed, which is what distinguishes this from post-expiry.yaml."""

    PATH = STALE_DIR / "long-defer.yaml"

    def test_still_classifies_stale_authority_live_credential(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        adapter = FakeProviderAdapter(seed=13)
        run_dir, result = _run(
            self.PATH, tmp_path, synthetic_aws_registry, run_id="run-long", adapter=adapter
        )
        assert result.status is RunStatus.COMPLETED
        measurement = _measurement(run_dir, "objectstore.read")
        assert measurement.classification is StaleAuthorityClass.STALE_AUTHORITY_LIVE_CREDENTIAL
        assert measurement.deferral_seconds >= 600.0


class TestPostExpiry:
    """F7/H6: no mutation at all -- the credential itself outlives its own
    lifetime. Acceptance criterion 4."""

    PATH = STALE_DIR / "post-expiry.yaml"

    def test_classifies_credential_expired(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        adapter = FakeProviderAdapter(seed=13)
        run_dir, result = _run(
            self.PATH, tmp_path, synthetic_aws_registry, run_id="run-expired", adapter=adapter
        )
        assert result.status is RunStatus.COMPLETED
        measurement = _measurement(run_dir, "objectstore.read")
        assert measurement.classification is StaleAuthorityClass.CREDENTIAL_EXPIRED
        assert measurement.credential_expired_at_execution is True

    def test_never_expired_credential_honored(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        """The fake correctly refuses to honor the expired credential --
        EXPIRED_CREDENTIAL_HONORED (the one row that would contradict
        documented behavior) must not appear."""
        adapter = FakeProviderAdapter(seed=13)
        run_dir, _ = _run(
            self.PATH, tmp_path, synthetic_aws_registry, run_id="run-expired", adapter=adapter
        )
        result = analyze(run_dir)
        assert not any(f.type is FindingType.EXPIRED_CREDENTIAL_ACCEPTED for f in result.findings)
        assert not any(f.type is FindingType.STALE_AUTHORITY for f in result.findings)


def _materialize_single_hop(
    adapter: FakeProviderAdapter, *, mechanism: DelegationMechanism = DelegationMechanism.ROLE_CHAIN
) -> tuple[MaterializedGraph, DelegationEdge]:
    """A minimal one-hop graph, built by hand against a real
    ``FakeProviderAdapter`` -- ``CURRENT_AUTHORITY``/``SESSION_SCOPE_CACHED``
    below don't need a full compiled scenario, only a real delegated
    identity and a real ``execution/deferred.py`` call, matching
    ``test_mutation.py``'s own precedent for exercising one ``execution/``
    module directly."""
    materialized = MaterializedGraph()
    root_ref = adapter.register_identity("principal", allow=AuthoritySet.of("identity.delegate"))
    materialized.refs["principal"] = root_ref
    materialized.credentials["principal"] = None
    materialized.edges_by_target["principal"] = None

    edge = DelegationEdge(
        edge_id="hop-1",
        source_id="principal",
        target_id="agent-c",
        mechanism=mechanism,
        requested_capabilities=AuthoritySet.of("objectstore.read", "identity.whoami"),
        intended_capabilities=AuthoritySet.of("objectstore.read", "identity.whoami"),
        expected_effective=AuthoritySet.of("objectstore.read", "identity.whoami"),
        credential_lifetime_s=3600,
    )
    result = adapter.delegate(
        DelegationRequest(
            source_identity=root_ref,
            target_identity_id="agent-c",
            mechanism=edge.mechanism,
            requested_duration_s=edge.credential_lifetime_s,
            intended_capabilities=edge.intended_capabilities,
        )
    )
    materialized.refs["agent-c"] = result.identity_ref
    materialized.credentials["agent-c"] = result.record
    materialized.edges_by_target["agent-c"] = edge
    return materialized, edge


class TestCurrentAuthorityDirectlyAgainstTheFake:
    """A capability agent-c was never granted classifies CURRENT_AUTHORITY
    (denied, consistent with policy, credential unexpired) -- no mutation
    needed at all, since it was never allowed in the first place."""

    def test_never_granted_capability_is_current_authority(self) -> None:
        adapter = FakeProviderAdapter(seed=1)
        materialized, _edge = _materialize_single_hop(adapter)
        credential_store = CredentialStore()
        credential_store.record("after-delegation", "agent-c", materialized.credentials["agent-c"])

        pinned_credential = materialized.credentials["agent-c"]
        plan = DeferredExecutionPlan(
            phase_name="deferred-1",
            target_identity="agent-c",
            capabilities=AuthoritySet.of("identity.delegate"),  # never granted to agent-c
            credential_source="phase:after-delegation",
        )
        run = run_deferred_execution_phase(
            adapter,
            materialized,
            credential_store,
            plan,
            run_id="run-current",
            now=lambda: datetime.now(UTC),
            salt="test-salt",
            namespace=adapter.namespace,
            sequence_start=0,
        )
        pinned = next(o for o in run.observations if o.phase.value == "DEFERRED_EXECUTION")
        assert pinned.outcome.outcome_class.is_denial

        credentials = [pinned_credential, materialized.credentials["agent-c"]]
        measurement = stale_authority_measurements([], list(run.observations), credentials)[0]
        assert measurement.classification is StaleAuthorityClass.CURRENT_AUTHORITY


class TestSessionScopeCachedDirectlyAgainstTheFake:
    """DELETE_SESSION_POLICY_SCOPE is a documented no-op on live authority
    (M12's delete-session-scope.yaml): nothing about the *outcome* alone
    distinguishes this from ordinary staleness, only the mutation record
    does (analysis/stale.py's own docstring) -- this is what
    ``session_scope_removed`` exists to carry."""

    def test_delete_session_policy_scope_mutation_classifies_session_scope_cached(self) -> None:
        adapter = FakeProviderAdapter(seed=1)
        materialized, _edge = _materialize_single_hop(
            adapter, mechanism=DelegationMechanism.SESSION_POLICY_SCOPED
        )
        credential_store = CredentialStore()
        credential_store.record("after-delegation", "agent-c", materialized.credentials["agent-c"])

        mutation = PolicyMutation(
            mutation_id="mut_test",
            kind=MutationKind.DELETE_SESSION_POLICY_SCOPE,
            target_identity="agent-c",
            denies_capabilities=EMPTY_AUTHORITY,
            grants_capabilities=EMPTY_AUTHORITY,
        )
        adapter.apply_policy_mutation(mutation)
        event = {
            "kind": "POLICY_MUTATION_APPLIED",
            "mutation_kind": "DELETE_SESSION_POLICY_SCOPE",
            "target_identity": "agent-c",
        }

        pinned_credential = materialized.credentials["agent-c"]
        plan = DeferredExecutionPlan(
            phase_name="deferred-1",
            target_identity="agent-c",
            capabilities=AuthoritySet.of("objectstore.read"),
            credential_source="phase:after-delegation",
        )
        run = run_deferred_execution_phase(
            adapter,
            materialized,
            credential_store,
            plan,
            run_id="run-scope",
            now=lambda: datetime.now(UTC),
            salt="test-salt",
            namespace=adapter.namespace,
            sequence_start=0,
        )
        credentials = [pinned_credential, materialized.credentials["agent-c"]]
        measurement = stale_authority_measurements([event], list(run.observations), credentials)[0]
        assert measurement.classification is StaleAuthorityClass.SESSION_SCOPE_CACHED


class TestExpiredCredentialHonoredWiring:
    """A correctly behaving fake can never produce this row (module
    docstring above). This test proves ``analysis/pipeline.py``'s own
    wiring around ``rule_expired_credential_accepted`` fires correctly if a
    provider ever did honor an expired credential, by corrupting one real
    ``post-expiry.yaml`` observation the way only a genuine defect could --
    flipping a correctly-DENIED, correctly-expired observation to ALLOWED --
    and re-sealing a bundle from the corrupted data."""

    def test_corrupted_observation_produces_expired_credential_accepted_finding(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        adapter = FakeProviderAdapter(seed=13)
        source_run_dir, _ = _run(
            STALE_DIR / "post-expiry.yaml",
            tmp_path,
            synthetic_aws_registry,
            run_id="run-source",
            adapter=adapter,
        )
        observations = list(read_observations(source_run_dir))
        corrupted = [
            (
                o.model_copy(
                    update={
                        "outcome": o.outcome.model_copy(
                            update={
                                "outcome_class": OutcomeClass.ALLOWED,
                                "denial_attribution": None,
                            }
                        )
                    }
                )
                if o.phase.value == "DEFERRED_EXECUTION" and o.capability_id == "objectstore.read"
                else o
            )
            for o in observations
        ]

        scenario = read_scenario(source_run_dir)
        graph = read_graph(source_run_dir)
        run_id = "run-corrupted"
        writer = BundleWriter(
            tmp_path,
            run_id,
            scenario_ref={
                "id": scenario.scenario_id,
                "version": scenario.scenario_version,
                "family": "stale-authority",
                "api_version": "chainbreak.dev/v1alpha1",
                "compiled_hash": scenario.compiled_hash,
            },
            provenance={
                "chainbreak_version": "0.1.0a0",
                "capability_catalog_version": scenario.catalog_version,
                "provider": "fake",
                "provider_adapter_version": scenario.adapter_version,
                "python_version": "3.12",
                "config_fingerprint": "sha256:" + ("3" * 64),
            },
        )
        with writer as sink:
            sink.write_scenario(scenario)
            sink.write_graph(graph)
            sink.write_environment({"host": {"os": "test"}})
            for observation in corrupted:
                sink.write_observation(observation)
            for credential in read_credentials(source_run_dir):
                sink.write_credential(credential)
            for event in read_events(source_run_dir):
                sink.write_event(event)
            sink.finalize(status="COMPLETED")

        result = analyze(tmp_path / run_id)
        measurement = next(
            m
            for m in stale_authority_measurements(
                list(read_events(tmp_path / run_id)),
                list(read_observations(tmp_path / run_id)),
                list(read_credentials(tmp_path / run_id)),
            )
            if m.capability_id == "objectstore.read"
        )
        assert measurement.classification is StaleAuthorityClass.EXPIRED_CREDENTIAL_HONORED
        assert any(f.type is FindingType.EXPIRED_CREDENTIAL_ACCEPTED for f in result.findings)
