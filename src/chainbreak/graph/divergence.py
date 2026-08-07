"""Divergence algorithms (AUTHORIZATION_MODEL.md section 4).

Pure functions over :class:`AuthorizationGraph`. No I/O, no logging. Per-node
divergence (``unexpected_gain``/``unexpected_loss``/``agreement``) already
lives on :class:`IdentityNode` in ``core/models.py`` -- this module builds the
per-edge, per-path and per-hop-drift algorithms on top of it.
"""

from __future__ import annotations

from collections.abc import Sequence

from chainbreak.core.enums import DivergenceKind, DriftClass
from chainbreak.core.models import (
    EMPTY_AUTHORITY,
    AuthorizationGraph,
    DelegationEdge,
    DivergencePoint,
    EdgeDivergence,
    IdentityNode,
)


def edge_divergence(graph: AuthorizationGraph, edge: DelegationEdge) -> EdgeDivergence:
    """Per-edge attenuation correctness (AUTHORIZATION_MODEL 4.2).

    Requires both endpoints to have been measured; a caller that has not yet
    probed both sides of the edge should not be asking whether the hop
    attenuated correctly.
    """
    source = graph.node(edge.source_id)
    target = graph.node(edge.target_id)
    if source.observed_authority is None:
        raise ValueError(f"edge {edge.edge_id}: source {source.identity_id} is unmeasured")
    if target.observed_authority is None:
        raise ValueError(f"edge {edge.edge_id}: target {target.identity_id} is unmeasured")

    src_obs = source.observed_authority.capabilities
    src_expected = source.expected_authority.capabilities
    dst_obs = target.observed_authority.capabilities
    intended = edge.intended_capabilities

    expected_at_target_observed = src_obs & intended
    expected_at_target_intended = src_expected & intended

    return EdgeDivergence(
        edge_id=edge.edge_id,
        expected_at_target_observed=expected_at_target_observed,
        expected_at_target_intended=expected_at_target_intended,
        attenuation_correct=(dst_obs == expected_at_target_observed),
        attenuation_correct_vs_intent=(dst_obs == expected_at_target_intended),
        survived_incorrectly=dst_obs - intended,
        dropped_incorrectly=expected_at_target_observed - dst_obs,
        dropped_incorrectly_vs_intent=expected_at_target_intended - dst_obs,
    )


def first_divergence(graph: AuthorizationGraph, path: Sequence[str]) -> DivergencePoint | None:
    """First point along a root-to-leaf path where observed authority diverges.

    An unmeasured node is reported as ``UNMEASURED`` rather than skipped
    (AUTHORIZATION_MODEL 4.3): silently skipping it would let a gap in
    probing masquerade as agreement.
    """
    for identity_id in path:
        node = graph.node(identity_id)
        if node.observed_authority is None:
            return DivergencePoint(
                hop_index=node.hop_index,
                identity_id=node.identity_id,
                kind=DivergenceKind.UNMEASURED,
            )

        gain = node.unexpected_gain
        loss = node.unexpected_loss
        if not gain and not loss:
            continue

        kind = (
            DivergenceKind.MIXED
            if gain and loss
            else DivergenceKind.EXPANSION
            if gain
            else DivergenceKind.NARROWING
        )
        return DivergencePoint(
            hop_index=node.hop_index,
            identity_id=node.identity_id,
            kind=kind,
            gain=gain,
            loss=loss,
        )
    return None


def classify_drift(node: IdentityNode, parent: IdentityNode | None) -> DriftClass | None:
    """How this node's authority-expansion gain relates to its parent's (4.4).

    Returns ``None`` when there is nothing to classify: neither node nor
    parent gained unexpected authority. This is what keeps every
    non-diverging hop out of the drift table, rather than every hop being
    mechanically labelled PROPAGATED because the empty set is technically a
    subset of the empty set.
    """
    gain_node = node.unexpected_gain
    gain_parent = parent.unexpected_gain if parent is not None else EMPTY_AUTHORITY

    if gain_parent.is_empty() and gain_node.is_empty():
        return None
    if not gain_parent.is_empty() and gain_node.is_empty():
        return DriftClass.CORRECTED
    if (
        not gain_parent.is_empty()
        and gain_node.is_superset_of(gain_parent)
        and gain_node != gain_parent
    ):
        return DriftClass.AMPLIFIED
    if gain_node.is_subset_of(gain_parent):
        return DriftClass.PROPAGATED
    return DriftClass.ORIGINATED
