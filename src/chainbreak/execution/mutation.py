"""Applies one scenario ``MUTATE`` phase's policy change through the
provider adapter, and builds the ``POLICY_MUTATION_APPLIED`` evidence event
(EVIDENCE_SCHEMA.md section 4) that :func:`chainbreak.analysis.pipeline
._revocation_findings` reads back to compute a revocation window.

SI-12 (S1): a mutation targeting ``bootstrap``/``principal`` is refused by
the adapter itself (``MutationTargetForbiddenError``, both adapters'
``protected_identities``); this module does not duplicate that check, only
lets it propagate.

SI-2 (S2): the mutation's target must already be a materialized identity in
*this run's own graph* -- never a name a scenario, or a defect injected into
one, could otherwise reach unchecked.

F4: ``receipt.monotonic_sent_ns`` (``t_M``) is the instant the mutation
*request was sent*, deliberately conservative (AUTHORIZATION_MODEL.md
section 5.1). An unconfirmed receipt makes the resulting timing measurement
uninterpretable, so a ``MutationPlan`` that asked for a receipt
(``record_receipt: true``, the corpus default) and did not get a confirmed
one aborts the run via :class:`~chainbreak.core.errors
.MutationNotConfirmedError` rather than silently producing a measurement
with no evidentiary basis.

Takes the compiled :class:`~chainbreak.core.models.MutationPlan`, never the
scenario-layer ``MutationSpec`` it was built from -- ``execution/`` sits
below ``scenarios/`` in ARCH-1's layering and must not import it; everything
this module needs has already been flattened into the compiled form by
``scenarios/compiler.py`` (the same discipline ``execution/matrix.py``
already applies to ``ProbeMatrix``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chainbreak.core.errors import ExecutionError, MutationNotConfirmedError
from chainbreak.core.ids import IdentityId, new_event_id, new_ulid
from chainbreak.core.models import MutationPlan, MutationReceipt, PolicyMutation
from chainbreak.execution.delegation import MaterializedGraph
from chainbreak.providers.base.protocol import ProviderAdapter

__all__ = ["MutationOutcome", "apply_mutation"]


@dataclass(frozen=True, slots=True)
class MutationOutcome:
    mutation: PolicyMutation
    receipt: MutationReceipt
    event: dict[str, Any]


def apply_mutation(
    adapter: ProviderAdapter,
    materialized: MaterializedGraph,
    plan: MutationPlan,
    *,
    sequence: int,
) -> MutationOutcome:
    target: IdentityId = plan.target_identity
    if target not in materialized.refs:
        raise ExecutionError(
            f"mutation target {target!r} is not a materialized identity in this run (SI-2)",
            target_identity=target,
        )

    mutation = PolicyMutation(
        mutation_id=f"mut_{new_ulid()}",
        kind=plan.kind,
        target_identity=target,
        denies_capabilities=plan.denies_capabilities,
        grants_capabilities=plan.grants_capabilities,
    )
    receipt = adapter.apply_policy_mutation(mutation)

    if plan.record_receipt and not receipt.confirmed:
        raise MutationNotConfirmedError(
            f"mutation {mutation.mutation_id!r} on {target!r} was not confirmed; any "
            "timing measurement derived from it would be uninterpretable (F4)",
            target_identity=target,
            mutation_id=mutation.mutation_id,
        )

    event = {
        "event_id": new_event_id(),
        "sequence": sequence,
        "kind": "POLICY_MUTATION_APPLIED",
        "mutation_id": mutation.mutation_id,
        "mutation_kind": mutation.kind.value,
        "target_identity": target,
        "denies_capabilities": list(plan.denies_capabilities.sorted),
        "grants_capabilities": list(plan.grants_capabilities.sorted),
        "timing": {
            "monotonic_ns": receipt.monotonic_sent_ns,
            "wall": receipt.wall_sent.isoformat(),
        },
        "receipt": {
            "confirmed": receipt.confirmed,
            "confirmation_method": receipt.confirmation_method,
            "confirmation_latency_ms": receipt.confirmation_latency_ms,
        },
    }
    return MutationOutcome(mutation=mutation, receipt=receipt, event=event)
