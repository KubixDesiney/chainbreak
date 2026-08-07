"""Shared fixtures and marker enforcement for the CHAINBREAK test suite.

F5 (M0): the ``aws`` and ``e2e`` markers require a real, operator-owned AWS benchmark
account and cost money to run. They must never execute by accident -- in a default
`pytest` invocation, in CI, or on a contributor's laptop -- so they are force-skipped
here unless the operator explicitly opts in with ``CHAINBREAK_ALLOW_AWS_TESTS=1``.
"""

from __future__ import annotations

import os

import pytest

from chainbreak.core.enums import DelegationMechanism, PlanPhase
from chainbreak.core.models import (
    AuthoritySet,
    AuthorizationGraph,
    DelegationEdge,
    ExpectedAuthority,
    IdentityNode,
    ObservedAuthority,
)

_OPT_IN_ENV_VAR = "CHAINBREAK_ALLOW_AWS_TESTS"
_GATED_MARKERS = ("aws", "e2e")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get(_OPT_IN_ENV_VAR) == "1":
        return

    skip_marker = pytest.mark.skip(
        reason=(
            f"requires a real AWS benchmark account; set {_OPT_IN_ENV_VAR}=1 to opt in "
            "(never set in default CI -- see ARCHITECTURE.md, T-12)"
        )
    )
    for item in items:
        if any(item.get_closest_marker(name) for name in _GATED_MARKERS):
            item.add_marker(skip_marker)


# ---------------------------------------------------------------------------
# AUTHORIZATION_MODEL.md section 7 worked example.
#
# Illustration of the algorithm, not a measured result: no AWS run has been
# performed (see PROJECT_STATUS.md). agent-c is *observed* to hold keyvalue.read
# despite it being outside hop-3's intended_capabilities -- the injected
# divergence the example exists to demonstrate.
# ---------------------------------------------------------------------------

_OS_READ = "objectstore.read"
_OS_WRITE = "objectstore.write"
_OS_LIST = "objectstore.list"
_KV_READ = "keyvalue.read"
_KV_WRITE = "keyvalue.write"
_FN_INVOKE = "function.invoke"


def _expected(*capabilities: str, declared: bool = False) -> ExpectedAuthority:
    return ExpectedAuthority(
        capabilities=AuthoritySet.of(*capabilities),
        phase=PlanPhase.POST_DELEGATION,
        derivation="DECLARED" if declared else "INHERITED_ATTENUATED",
    )


def _observed(*capabilities: str) -> ObservedAuthority:
    return ObservedAuthority(
        capabilities=AuthoritySet.of(*capabilities),
        phase=PlanPhase.POST_DELEGATION,
        probe_matrix_id="pm-worked-example",
        attempted=len(capabilities),
        classified=len(capabilities),
    )


def _edge(edge_id: str, source: str, target: str, *intended: str) -> DelegationEdge:
    caps = AuthoritySet.of(*intended)
    return DelegationEdge(
        edge_id=edge_id,
        source_id=source,
        target_id=target,
        mechanism=DelegationMechanism.ROLE_CHAIN_WITH_SESSION_POLICY,
        requested_capabilities=caps,
        intended_capabilities=caps,
        expected_effective=caps,
        credential_lifetime_s=3600,
    )


@pytest.fixture
def worked_example_graph() -> AuthorizationGraph:
    """The four-hop chain from AUTHORIZATION_MODEL.md section 7, hand-built.

    Hop  Identity   Expected (derived)                                    Observed
    0    principal  os.read,os.write,os.list,kv.read,kv.write,fn.invoke   same (6)
    1    agent-a    os.read,os.write,os.list,kv.read,fn.invoke            same (5)
    2    agent-b    os.read,kv.read                                       same (2)
    3    agent-c    os.read                                               os.read,kv.read (2)
    4    agent-d    os.read                                               os.read,kv.read (2)
    """
    nodes = (
        IdentityNode(
            identity_id="principal",
            is_root=True,
            hop_index=0,
            expected_authority=_expected(
                _OS_READ, _OS_WRITE, _OS_LIST, _KV_READ, _KV_WRITE, _FN_INVOKE, declared=True
            ),
            observed_authority=_observed(
                _OS_READ, _OS_WRITE, _OS_LIST, _KV_READ, _KV_WRITE, _FN_INVOKE
            ),
        ),
        IdentityNode(
            identity_id="agent-a",
            hop_index=1,
            parent_id="principal",
            expected_authority=_expected(_OS_READ, _OS_WRITE, _OS_LIST, _KV_READ, _FN_INVOKE),
            observed_authority=_observed(_OS_READ, _OS_WRITE, _OS_LIST, _KV_READ, _FN_INVOKE),
        ),
        IdentityNode(
            identity_id="agent-b",
            hop_index=2,
            parent_id="agent-a",
            expected_authority=_expected(_OS_READ, _KV_READ),
            observed_authority=_observed(_OS_READ, _KV_READ),
        ),
        IdentityNode(
            identity_id="agent-c",
            hop_index=3,
            parent_id="agent-b",
            expected_authority=_expected(_OS_READ),
            observed_authority=_observed(_OS_READ, _KV_READ),
        ),
        IdentityNode(
            identity_id="agent-d",
            hop_index=4,
            parent_id="agent-c",
            expected_authority=_expected(_OS_READ),
            observed_authority=_observed(_OS_READ, _KV_READ),
        ),
    )
    edges = (
        _edge("hop-1", "principal", "agent-a", _OS_READ, _OS_WRITE, _OS_LIST, _KV_READ, _FN_INVOKE),
        _edge("hop-2", "agent-a", "agent-b", _OS_READ, _KV_READ),
        _edge("hop-3", "agent-b", "agent-c", _OS_READ),
        _edge("hop-4", "agent-c", "agent-d", _OS_READ),
    )
    return AuthorizationGraph(nodes=nodes, edges=edges)
