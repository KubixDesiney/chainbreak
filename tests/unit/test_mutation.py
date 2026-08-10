"""``execution/mutation.py`` (M12): SI-2's materialized-target check and
F4's unconfirmed-receipt abort, both easiest to exercise directly rather
than through a full scenario run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from chainbreak.core.enums import MutationKind
from chainbreak.core.errors import ExecutionError, MutationNotConfirmedError
from chainbreak.core.models import EMPTY_AUTHORITY, MutationPlan, MutationReceipt
from chainbreak.execution.delegation import MaterializedGraph
from chainbreak.execution.mutation import apply_mutation
from chainbreak.providers.fake.adapter import FakeProviderAdapter

pytestmark = pytest.mark.unit


@dataclass
class _UnconfirmingAdapter:
    """A minimal stand-in whose ``apply_policy_mutation`` always returns an
    unconfirmed receipt -- the real fake adapter never does this (F4's abort
    path has no fake-adapter trigger), so it must be stubbed to exercise it.
    """

    calls: list[object] = field(default_factory=list)

    def apply_policy_mutation(self, mutation: object) -> MutationReceipt:
        self.calls.append(mutation)
        return MutationReceipt(
            confirmed=False,
            confirmation_method="api_ack_only",
            monotonic_sent_ns=0,
            wall_sent=datetime.now(UTC),
        )


def _plan(*, record_receipt: bool = True) -> MutationPlan:
    return MutationPlan(
        phase_name="revoke",
        target_identity="agent-b",
        kind=MutationKind.ATTACH_INLINE_DENY,
        denies_capabilities=EMPTY_AUTHORITY,
        grants_capabilities=EMPTY_AUTHORITY,
        record_receipt=record_receipt,
    )


class TestNamespaceGuard:
    def test_target_not_in_materialized_graph_is_rejected(self) -> None:
        adapter = FakeProviderAdapter(seed=1)
        materialized = MaterializedGraph()  # empty: nothing materialized
        with pytest.raises(ExecutionError, match="not a materialized identity") as excinfo:
            apply_mutation(adapter, materialized, _plan(), sequence=0)
        assert excinfo.value.context["target_identity"] == "agent-b"


class TestUnconfirmedReceipt:
    def test_record_receipt_true_and_unconfirmed_raises(self) -> None:
        adapter = _UnconfirmingAdapter()
        materialized = MaterializedGraph(refs={"agent-b": object()})  # type: ignore[dict-item]
        with pytest.raises(MutationNotConfirmedError):
            apply_mutation(adapter, materialized, _plan(record_receipt=True), sequence=0)
        assert len(adapter.calls) == 1

    def test_record_receipt_false_and_unconfirmed_does_not_raise(self) -> None:
        adapter = _UnconfirmingAdapter()
        materialized = MaterializedGraph(refs={"agent-b": object()})  # type: ignore[dict-item]
        outcome = apply_mutation(adapter, materialized, _plan(record_receipt=False), sequence=0)
        assert outcome.receipt.confirmed is False
        assert outcome.event["kind"] == "POLICY_MUTATION_APPLIED"
