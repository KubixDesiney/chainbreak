"""``scenarios/policy_synthesis.py``: the provider-neutral, size-checked,
fingerprinted placeholder policy artifact (SCENARIO_SPECIFICATION.md section
10, F7). Exercised directly here rather than only incidentally through
``compiler.py``, since the size-limit error path is compile-time-critical
and easy to leave untested by scenario fixtures that never approach it.
"""

from __future__ import annotations

import pytest

from chainbreak.core.errors import ScenarioSemanticError
from chainbreak.core.models import AuthoritySet
from chainbreak.scenarios.policy_synthesis import (
    AWS_INLINE_SESSION_POLICY_LIMIT_BYTES,
    synthesize_policy,
)

pytestmark = pytest.mark.unit


class TestSynthesizePolicy:
    def test_synthesizes_a_sized_and_fingerprinted_policy(self) -> None:
        capabilities = AuthoritySet.of("objectstore.read", "queue.send")
        policy = synthesize_policy("principal", capabilities, edge_id="e-1")

        assert policy.identity_id == "principal"
        assert policy.edge_id == "e-1"
        assert policy.capabilities == capabilities
        assert policy.document_size_bytes > 0
        assert policy.fingerprint

    def test_omitted_edge_id_defaults_to_none(self) -> None:
        policy = synthesize_policy("principal", AuthoritySet.of("objectstore.read"))
        assert policy.edge_id is None

    def test_fingerprint_is_deterministic_for_the_same_capability_set(self) -> None:
        capabilities = AuthoritySet.of("objectstore.read", "queue.send")
        first = synthesize_policy("principal", capabilities)
        second = synthesize_policy("principal", capabilities)
        assert first.fingerprint == second.fingerprint
        assert first.document_size_bytes == second.document_size_bytes

    def test_empty_capability_set_still_synthesizes_a_policy(self) -> None:
        """No capabilities is a legal edge (e.g. an intersection that resolves
        to nothing) -- it must not be rejected as if it were oversized."""
        policy = synthesize_policy("principal", AuthoritySet.of())
        assert policy.capabilities == AuthoritySet.of()
        assert policy.document_size_bytes > 0  # the empty-list document itself, "[]"
        assert policy.fingerprint

    def test_default_size_limit_is_the_documented_aws_inline_ceiling(self) -> None:
        assert AWS_INLINE_SESSION_POLICY_LIMIT_BYTES == 2048

    def test_exceeding_the_size_limit_raises_at_compile_time_naming_the_limit(self) -> None:
        capabilities = AuthoritySet.of("objectstore.read", "queue.send")
        with pytest.raises(ScenarioSemanticError, match="exceeding the 10-byte limit") as excinfo:
            synthesize_policy("principal", capabilities, edge_id="e-1", size_limit_bytes=10)

        error = excinfo.value
        assert error.context["identity_id"] == "principal"
        assert error.context["edge_id"] == "e-1"
        assert error.context["size_limit_bytes"] == 10
        assert error.context["size_bytes"] > 10

    def test_exceeding_the_size_limit_without_an_edge_id_still_raises(self) -> None:
        """The error path must not assume an edge is always present -- root-node
        policy synthesis has no edge to attribute the failure to."""
        with pytest.raises(ScenarioSemanticError) as excinfo:
            synthesize_policy("principal", AuthoritySet.of("objectstore.read"), size_limit_bytes=1)
        assert excinfo.value.context["edge_id"] is None
