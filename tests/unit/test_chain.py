"""``execution/chain.py`` (M11): the delegation-drift family's own entry
point over ``delegation.materialize_graph`` -- S1's redundant, execution-
layer depth check and S2's credential scrubbing (exercised indirectly via
``materialize_graph`` itself, tested in ``test_probe_matrix_execution.py``).
"""

from __future__ import annotations

import pytest

from chainbreak.core.enums import PlanPhase
from chainbreak.core.errors import ExecutionError
from chainbreak.core.models import (
    AuthoritySet,
    AuthorizationGraph,
    ExpectedAuthority,
    IdentityNode,
)
from chainbreak.execution.chain import materialize_chain
from chainbreak.providers.fake.adapter import FakeProviderAdapter

pytestmark = pytest.mark.unit


def _single_node_graph() -> AuthorizationGraph:
    root = IdentityNode(
        identity_id="principal",
        is_root=True,
        hop_index=0,
        expected_authority=ExpectedAuthority(
            capabilities=AuthoritySet.of("objectstore.read"),
            phase=PlanPhase.BASELINE,
            derivation="DECLARED",
        ),
    )
    return AuthorizationGraph(nodes=(root,))


class TestMaterializeChainDepthGuard:
    def test_within_bound_delegates_to_materialize_graph_normally(self) -> None:
        adapter = FakeProviderAdapter(seed=1)
        materialized = materialize_chain(adapter, _single_node_graph(), max_delegation_depth=6)
        assert "principal" in materialized.refs

    def test_over_bound_raises_a_named_execution_error(self) -> None:
        # depth 0 (a single, root-only graph) exceeding a max of -1 is the
        # simplest way to exercise the guard without needing a genuinely
        # deep graph -- the guard only compares graph.depth against
        # whatever bound it is given, it does not care how either number
        # was produced.
        adapter = FakeProviderAdapter(seed=1)
        with pytest.raises(ExecutionError, match="exceeds max_delegation_depth") as excinfo:
            materialize_chain(adapter, _single_node_graph(), max_delegation_depth=-1)
        assert excinfo.value.context["depth"] == 0
        assert excinfo.value.context["max_delegation_depth"] == -1
