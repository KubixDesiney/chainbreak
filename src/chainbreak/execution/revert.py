"""F8/F9, S3: mutation reversion with a human-actionable revert log written
*before* the mutation runs, so a killed run still leaves complete recovery
information (T-06/R-7) -- ``orchestrator.py`` writes the log event this
module builds immediately before calling ``execution.mutation.apply_mutation``,
then calls :func:`revert_mutation` from its own ``finally`` block regardless
of how the run ended.

Reverting means restoring the target identity's *declared* (intended)
authority from the compiled graph, not literally replaying whatever the
adapter's own internal pre-mutation state was: exposing that state would
mean carrying an unredacted policy document through the evidence pipeline,
which the redaction choke point (SI-1) is built to prevent. Every ``MUTATE``
phase in this benchmark only ever moves a target *away* from its own
declared authority, so "restore declared authority" is always the correct
undo for the mutation kinds that touch live-session authority at all.

Two mutation kinds cannot be programmatically reverted, and the log says so
rather than pretending otherwise:

- ``REVOKE_OLDER_SESSIONS`` revokes credentials outright; a revoked session
  cannot be un-revoked, only replaced by delegating a fresh one.
- ``UPDATE_TRUST_POLICY`` and ``DELETE_SESSION_POLICY_SCOPE`` never touch a
  live session's authority in the first place (both are built-in negative
  controls, AWS_PROVIDER_SPEC section 4) -- there is nothing to revert.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chainbreak.core.enums import MutationKind
from chainbreak.core.ids import IdentityId, new_event_id, new_ulid
from chainbreak.core.models import AuthoritySet, AuthorizationGraph, PolicyMutation
from chainbreak.providers.base.protocol import ProviderAdapter

__all__ = ["RevertPlan", "build_revert_log_event", "build_revert_plan", "revert_mutation"]

#: Mutation kinds that actually change what a live session may do -- the
#: only ones a revert can meaningfully counteract with a policy write.
_LIVE_STATE_KINDS = frozenset(
    {
        MutationKind.ATTACH_INLINE_DENY,
        MutationKind.REMOVE_INLINE_POLICY,
        MutationKind.REPLACE_INLINE_POLICY,
    }
)


@dataclass(frozen=True, slots=True)
class RevertPlan:
    target_identity: IdentityId
    mutation_kind: MutationKind
    declared_capabilities: AuthoritySet
    actionable: bool
    action: str


def build_revert_plan(
    graph: AuthorizationGraph, target_identity: IdentityId, mutation_kind: MutationKind
) -> RevertPlan:
    declared = graph.node(target_identity).expected_authority.capabilities

    if mutation_kind in _LIVE_STATE_KINDS:
        return RevertPlan(
            target_identity=target_identity,
            mutation_kind=mutation_kind,
            declared_capabilities=declared,
            actionable=True,
            action=(
                f"REPLACE_INLINE_POLICY on {target_identity!r}: grants="
                f"{list(declared.sorted)}, denies=[] -- restores declared authority"
            ),
        )
    if mutation_kind is MutationKind.REVOKE_OLDER_SESSIONS:
        return RevertPlan(
            target_identity=target_identity,
            mutation_kind=mutation_kind,
            declared_capabilities=declared,
            actionable=False,
            action=(
                f"cannot be reverted: sessions revoked for {target_identity!r} cannot be "
                "un-revoked -- delegate a fresh credential to restore access"
            ),
        )
    if mutation_kind is MutationKind.UPDATE_TRUST_POLICY:
        return RevertPlan(
            target_identity=target_identity,
            mutation_kind=mutation_kind,
            declared_capabilities=declared,
            actionable=True,
            action=(f"restore the Terraform-declared trust policy on {target_identity!r}"),
        )
    return RevertPlan(
        target_identity=target_identity,
        mutation_kind=mutation_kind,
        declared_capabilities=declared,
        actionable=False,
        action=(
            f"no action required: {mutation_kind.value} does not affect the live session "
            f"authority of {target_identity!r} (AWS_PROVIDER_SPEC section 4)"
        ),
    )


def build_revert_log_event(plan: RevertPlan, *, sequence: int) -> dict[str, Any]:
    return {
        "event_id": new_event_id(),
        "sequence": sequence,
        "kind": "REVERT_LOG_WRITTEN",
        "target_identity": plan.target_identity,
        "mutation_kind": plan.mutation_kind.value,
        "actionable": plan.actionable,
        "action": plan.action,
        "declared_capabilities": list(plan.declared_capabilities.sorted),
    }


def revert_mutation(
    adapter: ProviderAdapter, plan: RevertPlan, *, sequence: int
) -> dict[str, Any] | None:
    """Issues the actual reversion call and returns a ``MUTATION_REVERTED``
    event, or ``None`` when ``plan.actionable`` is ``False`` (nothing to call
    -- the log entry already recorded why)."""
    if not plan.actionable:
        return None
    if plan.mutation_kind is MutationKind.UPDATE_TRUST_POLICY:
        restore = getattr(adapter, "restore_trust_policy", None)
        if not callable(restore):  # pragma: no cover - compatibility fallback
            return None
        receipt = restore(plan.target_identity)
    else:
        restore = getattr(adapter, "restore_declared_policy", None)
        if callable(restore):
            receipt = restore(plan.target_identity, plan.declared_capabilities)
        else:  # pragma: no cover - compatibility for third-party adapters
            mutation = PolicyMutation(
                mutation_id=f"mut_{new_ulid()}",
                kind=MutationKind.REPLACE_INLINE_POLICY,
                target_identity=plan.target_identity,
                grants_capabilities=plan.declared_capabilities,
            )
            receipt = adapter.apply_policy_mutation(mutation)
    return {
        "event_id": new_event_id(),
        "sequence": sequence,
        "kind": "MUTATION_REVERTED",
        "target_identity": plan.target_identity,
        "original_mutation_kind": plan.mutation_kind.value,
        "receipt": {"confirmed": receipt.confirmed},
    }
