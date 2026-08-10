"""``execution/deferred.py`` (M13): the branches easiest to exercise
directly rather than through a full scenario run -- a target with no
delegation edge (F3 requires a delegated identity, never the root), and a
provider adapter with no ``enable_authority_caching`` hook (the real-time,
non-fake case, matching ``advance_clock``'s own precedent in
``execution/polling.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from chainbreak.core.enums import DelegationMechanism
from chainbreak.core.errors import ExecutionError
from chainbreak.core.models import AuthoritySet, DeferredExecutionPlan, DelegationEdge
from chainbreak.execution.credential_store import CredentialStore
from chainbreak.execution.deferred import run_deferred_execution_phase
from chainbreak.execution.delegation import MaterializedGraph
from chainbreak.providers.base.types import DelegationRequest
from chainbreak.providers.fake.adapter import FakeProviderAdapter

pytestmark = pytest.mark.unit


def _plan() -> DeferredExecutionPlan:
    return DeferredExecutionPlan(
        phase_name="deferred-1",
        target_identity="agent-c",
        capabilities=AuthoritySet.of("objectstore.read"),
        credential_source="phase:after-delegation",
    )


class TestTargetWithNoEdge:
    def test_root_target_raises(self) -> None:
        adapter = FakeProviderAdapter(seed=1)
        root_ref = adapter.register_identity("agent-c")
        materialized = MaterializedGraph(
            refs={"agent-c": root_ref},
            credentials={"agent-c": None},
            edges_by_target={"agent-c": None},  # a root: no edge to re-delegate along
        )
        credential_store = CredentialStore()
        with pytest.raises(ExecutionError, match="no delegation edge") as excinfo:
            run_deferred_execution_phase(
                adapter,
                materialized,
                credential_store,
                _plan(),
                run_id="run-1",
                now=lambda: datetime.now(UTC),
                salt="test-salt",
                namespace=adapter.namespace,
                sequence_start=0,
            )
        assert excinfo.value.context["target_identity"] == "agent-c"


@dataclass
class _NoAuthorityCachingAdapter:
    """A minimal stand-in without ``enable_authority_caching`` -- the real
    (non-fake) provider shape this milestone's own module docstring says
    ``execution/deferred.py`` must still run correctly against, just
    without the fake-specific control (M17)."""

    inner: FakeProviderAdapter
    namespace: str = field(init=False)

    def __post_init__(self) -> None:
        self.namespace = self.inner.namespace

    def resolve_capability(self, capability_id: str):
        return self.inner.resolve_capability(capability_id)

    def probe(self, request):
        return self.inner.probe(request)

    def delegate(self, request):
        return self.inner.delegate(request)


class TestNoAuthorityCachingHook:
    def test_deferred_execution_still_runs_without_the_fake_specific_hook(self) -> None:
        inner = FakeProviderAdapter(seed=1)
        root_ref = inner.register_identity("principal", allow=AuthoritySet.of("identity.delegate"))
        edge = DelegationEdge(
            edge_id="hop-1",
            source_id="principal",
            target_id="agent-c",
            mechanism=DelegationMechanism.ROLE_CHAIN,
            requested_capabilities=AuthoritySet.of("objectstore.read"),
            intended_capabilities=AuthoritySet.of("objectstore.read"),
            expected_effective=AuthoritySet.of("objectstore.read"),
            credential_lifetime_s=3600,
        )
        result = inner.delegate(
            DelegationRequest(
                source_identity=root_ref,
                target_identity_id="agent-c",
                mechanism=edge.mechanism,
                requested_duration_s=edge.credential_lifetime_s,
                intended_capabilities=edge.intended_capabilities,
            )
        )
        materialized = MaterializedGraph(
            refs={"principal": root_ref, "agent-c": result.identity_ref},
            credentials={"principal": None, "agent-c": result.record},
            edges_by_target={"principal": None, "agent-c": edge},
        )
        credential_store = CredentialStore()
        credential_store.record("after-delegation", "agent-c", result.record)

        adapter = _NoAuthorityCachingAdapter(inner=inner)
        run = run_deferred_execution_phase(
            adapter,
            materialized,
            credential_store,
            _plan(),
            run_id="run-1",
            now=lambda: datetime.now(UTC),
            salt="test-salt",
            namespace=adapter.namespace,
            sequence_start=0,
        )
        assert len(run.observations) == 2  # pinned + paired fresh
