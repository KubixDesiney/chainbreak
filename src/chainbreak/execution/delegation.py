"""Turns a compiled :class:`~chainbreak.core.models.AuthorizationGraph` into
live provider identities: registers the root directly, walks every edge in
compiled order issuing a real delegation, and (F6) re-delegates an edge
whose credential's remaining lifetime has run down before the matrix about
to use it.

ARCHITECTURE.md section 3.7 originally reserved a separate top-level
``delegation/`` package for this; ``docs/implementation/milestones/
M10-scope-attenuation.md`` and ``docs/implementation/NEXT_PROMPTS.md`` (the
current, more specific source for this milestone) both name it
``execution/delegation.py`` instead. Followed here as the more specific and
more recent of the two; the top-level ``chainbreak.delegation`` package is
left untouched rather than silently repurposed. Worth reconciling in
ARCHITECTURE.md at some point, but that is a documentation decision, not one
this milestone should make unilaterally.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from chainbreak.core.ids import IdentityId, new_event_id
from chainbreak.core.models import AuthorizationGraph, CredentialRecord, DelegationEdge, IdentityRef
from chainbreak.providers.base.protocol import ProviderAdapter
from chainbreak.providers.base.types import DelegationRequest

__all__ = [
    "MaterializedGraph",
    "ensure_fresh_credential",
    "estimate_remaining_lifetime_s",
    "materialize_graph",
    "needs_redelegation",
]

#: F6: re-delegate once remaining lifetime drops below this multiple of the
#: matrix's own estimated duration -- comfortably before the credential
#: could expire mid-matrix and turn a real denial into a session-expiry
#: artifact.
_REDELEGATION_LIFETIME_MULTIPLE = 2.0


@dataclass(frozen=True, slots=True)
class MaterializedGraph:
    """Live provider handles for every node in a compiled graph.

    ``credentials``/``edges_by_target`` are ``None`` for the root (registered
    directly, never delegated to -- there is no expiring session and no edge
    to re-delegate along). ``provider_bindings`` preserves the compiled
    provider binding for each materialized identity so re-delegation cannot
    silently fall back to the default physical role. The four dicts are
    mutated in place by
    :func:`ensure_fresh_credential` as re-delegation happens; the dataclass
    itself stays frozen (only its own three attributes are immutable, not
    the dicts they point at).
    """

    refs: dict[IdentityId, IdentityRef] = field(default_factory=dict)
    credentials: dict[IdentityId, CredentialRecord | None] = field(default_factory=dict)
    edges_by_target: dict[IdentityId, DelegationEdge | None] = field(default_factory=dict)
    provider_bindings: dict[IdentityId, str | None] = field(default_factory=dict)


def materialize_graph(adapter: ProviderAdapter, graph: AuthorizationGraph) -> MaterializedGraph:
    """Register the root, then delegate along every edge in the compiled
    graph's own order.

    A compiled graph's edges are already in hop order (G-1/G-3's acyclic,
    monotone construction walks root outward), so a single forward pass
    always delegates a source before any edge that needs it as one.
    """
    materialized = MaterializedGraph()
    root = graph.root
    materialized.refs[root.identity_id] = adapter.register_identity(
        root.identity_id,
        allow=root.expected_authority.capabilities,
        provider_binding=root.provider_binding,
    )
    materialized.credentials[root.identity_id] = None
    materialized.edges_by_target[root.identity_id] = None
    materialized.provider_bindings[root.identity_id] = root.provider_binding

    for edge in graph.edges:
        result = adapter.delegate(
            DelegationRequest(
                source_identity=materialized.refs[edge.source_id],
                target_identity_id=edge.target_id,
                target_provider_binding=next(
                    node.provider_binding
                    for node in graph.nodes
                    if node.identity_id == edge.target_id
                ),
                mechanism=edge.mechanism,
                requested_duration_s=edge.credential_lifetime_s,
                intended_capabilities=edge.intended_capabilities,
            )
        )
        materialized.refs[edge.target_id] = result.identity_ref
        materialized.credentials[edge.target_id] = result.record
        materialized.edges_by_target[edge.target_id] = edge
        materialized.provider_bindings[edge.target_id] = next(
            node.provider_binding for node in graph.nodes if node.identity_id == edge.target_id
        )
        # M11 S2: each hop's raw secret is scrubbed the moment its safe
        # CredentialRecord projection has been extracted -- the identity's
        # own live session (held by the adapter, e.g. FakeProviderAdapter's
        # SessionStore) is what probes actually use from here on, not this
        # reference.
        result.credential.scrub()

    return materialized


def estimate_remaining_lifetime_s(credential: CredentialRecord, *, now: datetime) -> float:
    return (credential.expires_at - now).total_seconds()


def needs_redelegation(
    credential: CredentialRecord, *, now: datetime, estimated_matrix_duration_s: float
) -> bool:
    """F6: re-delegate if the remaining lifetime is under 2x the estimated
    matrix duration about to run against this credential."""
    remaining = estimate_remaining_lifetime_s(credential, now=now)
    return remaining < _REDELEGATION_LIFETIME_MULTIPLE * estimated_matrix_duration_s


def ensure_fresh_credential(
    adapter: ProviderAdapter,
    materialized: MaterializedGraph,
    identity_id: IdentityId,
    *,
    now: datetime,
    estimated_matrix_duration_s: float,
    sequence: int,
) -> tuple[IdentityRef, CredentialRecord | None, dict[str, Any] | None]:
    """F6, checked before every matrix. A root identity (no edge, nothing to
    re-delegate) is returned unchanged. Returns the possibly-updated
    ``(ref, credential)`` and, if a re-delegation happened, the event
    recording it -- ``None`` otherwise, so the caller only writes an event
    when something actually happened.
    """
    edge = materialized.edges_by_target.get(identity_id)
    credential = materialized.credentials.get(identity_id)
    if edge is None or credential is None:
        return materialized.refs[identity_id], credential, None

    if not needs_redelegation(
        credential, now=now, estimated_matrix_duration_s=estimated_matrix_duration_s
    ):
        return materialized.refs[identity_id], credential, None

    result = adapter.delegate(
        DelegationRequest(
            source_identity=materialized.refs[edge.source_id],
            target_identity_id=edge.target_id,
            target_provider_binding=materialized.provider_bindings.get(edge.target_id),
            mechanism=edge.mechanism,
            requested_duration_s=edge.credential_lifetime_s,
            intended_capabilities=edge.intended_capabilities,
        )
    )
    materialized.refs[identity_id] = result.identity_ref
    materialized.credentials[identity_id] = result.record
    result.credential.scrub()  # M11 S2 -- see materialize_graph's identical comment

    event = {
        "event_id": new_event_id(),
        "sequence": sequence,
        "kind": "CREDENTIAL_REDELEGATED",
        "identity_id": identity_id,
        "edge_id": edge.edge_id,
        "reason": "remaining_lifetime_below_2x_estimated_matrix_duration",
        "previous_credential_id": credential.credential_id,
        "new_credential_id": result.record.credential_id,
    }
    return result.identity_ref, result.record, event
