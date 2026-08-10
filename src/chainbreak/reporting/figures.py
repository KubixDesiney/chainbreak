"""Figures generated **from evidence**, never from hand-written numbers (M16 F3).

Design note -- a deliberate deviation from the milestone text's "(Plotly)"
parenthetical, recorded here the same way M4 recorded its
``rich_markup_mode`` finding: Plotly's only two paths to a genuinely
self-contained, no-CDN report both fail a harder requirement the milestone
states in the same breath. ``include_plotlyjs="inline"`` embeds a
multi-megabyte minified library *per report*, which alone exceeds the
milestone's own "HTML report under 2 MB" non-functional requirement before a
single data point is drawn. Static image export (``kaleido``) needs a
headless-browser binary that is not installed in, and cannot be downloaded
into, this offline development environment -- the same "no network fetches"
constraint S2 states as a *report-render-time* requirement would be violated
at *build* time instead. Hand-built inline SVG, generated programmatically
from the same evidence Plotly would have been fed, satisfies F3's actual
requirement (structured, evidence-derived charts, never hand-written
numbers) without either conflict, and is furthermore readable without
JavaScript (the milestone's own NFR) where a Plotly ``<div>`` is not.

Every label interpolated into the hand-built SVG markup below is escaped
with :func:`xml.sax.saxutils.escape` at the point of construction -- this
module builds raw XML by string concatenation, outside Jinja2's own
autoescape, so escaping here is this module's own responsibility (T-10: a
capability or identity id ultimately originates from a scenario document or
provider response, not a value CHAINBREAK invented).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

# Escaping only (plain-text labels into XML/SVG output), never parsing
# untrusted XML input -- the vulnerability B406 is about; defusedxml has no
# equivalent escaping helper.
from xml.sax.saxutils import escape as _esc  # nosec B406

from chainbreak.core.enums import OutcomeClass, Provider
from chainbreak.core.models import (
    AuthorizationGraph,
    EdgeDivergence,
    Interval,
    RevocationMeasurement,
    StaleAuthorityMeasurement,
)

__all__ = [
    "Figure",
    "authorization_graph_figure",
    "gain_loss_per_hop_figure",
    "per_hop_authority_figure",
    "repeatability_figure",
    "revocation_timeline_figure",
    "scenario_comparison_figure",
    "stale_authority_window_figure",
]

#: F6: stamped into every figure caption for a `provider: fake` run, in
#: addition to the report header -- enforced here in the rendering layer,
#: not left to operator discipline.
_FAKE_PROVIDER_STAMP = "FAKE-PROVIDER APPARATUS CHECK -- not a measurement of any real provider."

_WIDTH = 640
_HEIGHT = 260
_MARGIN = 40
_AXIS_COLOR = "#8a8a8a"
_BAR_COLORS = ("#4c78a8", "#e45756", "#54a24b", "#f2b701")


@dataclass(frozen=True, slots=True)
class Figure:
    key: str
    title: str
    caption: str
    svg: str
    applicable: bool


def _not_applicable(key: str, title: str, reason: str, *, provider: Provider) -> Figure:
    caption = reason if provider is not Provider.FAKE else f"{reason} {_FAKE_PROVIDER_STAMP}"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_WIDTH} 80" '
        f'role="img" aria-label="{_esc(title)}: not applicable">'
        f'<text x="12" y="40" font-family="monospace" font-size="13" fill="{_AXIS_COLOR}">'
        f"{_esc(reason)}</text></svg>"
    )
    return Figure(key=key, title=title, caption=caption, svg=svg, applicable=False)


def _caption(text: str, *, provider: Provider) -> str:
    return text if provider is not Provider.FAKE else f"{text} {_FAKE_PROVIDER_STAMP}"


def _svg_open(width: int, height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="none"/>'
    )


def _bar_group_chart(
    title: str,
    categories: Sequence[str],
    series: Mapping[str, Sequence[float]],
    *,
    unit: str = "",
) -> str:
    """A grouped vertical bar chart. One bar cluster per category, one bar
    per series within the cluster. All values are non-negative counts or
    durations read from evidence -- never invented here."""
    width, height = _WIDTH, _HEIGHT
    plot_h = height - 2 * _MARGIN
    plot_w = width - 2 * _MARGIN
    series_names = list(series)
    n_cat = max(len(categories), 1)
    n_series = max(len(series_names), 1)
    cluster_w = plot_w / n_cat
    bar_w = cluster_w / (n_series + 1)
    max_value = max((v for values in series.values() for v in values), default=0.0) or 1.0

    parts = [_svg_open(width, height)]
    parts.append(
        f'<text x="{width / 2}" y="20" text-anchor="middle" font-family="sans-serif" '
        f'font-size="14" font-weight="bold">{_esc(title)}</text>'
    )
    # axis
    parts.append(
        f'<line x1="{_MARGIN}" y1="{height - _MARGIN}" x2="{width - _MARGIN}" '
        f'y2="{height - _MARGIN}" stroke="{_AXIS_COLOR}"/>'
    )
    for c_idx, category in enumerate(categories):
        cluster_x = _MARGIN + c_idx * cluster_w
        for s_idx, name in enumerate(series_names):
            value = series[name][c_idx] if c_idx < len(series[name]) else 0.0
            bar_h = (value / max_value) * plot_h if max_value else 0.0
            x = cluster_x + (s_idx + 0.25) * bar_w
            y = height - _MARGIN - bar_h
            color = _BAR_COLORS[s_idx % len(_BAR_COLORS)]
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w * 0.8:.1f}" '
                f'height="{bar_h:.1f}" fill="{color}"><title>{_esc(name)}: '
                f"{value:g}{_esc(unit)}</title></rect>"
            )
            parts.append(
                f'<text x="{x + bar_w * 0.4:.1f}" y="{y - 4:.1f}" text-anchor="middle" '
                f'font-family="monospace" font-size="10">{value:g}</text>'
            )
        label_x = cluster_x + cluster_w / 2
        parts.append(
            f'<text x="{label_x:.1f}" y="{height - _MARGIN + 14}" text-anchor="middle" '
            f'font-family="monospace" font-size="10">{_esc(str(category))}</text>'
        )
    if n_series > 1:
        for s_idx, name in enumerate(series_names):
            legend_x = _MARGIN + s_idx * 120
            parts.append(
                f'<rect x="{legend_x}" y="{_MARGIN - 22}" width="10" height="10" '
                f'fill="{_BAR_COLORS[s_idx % len(_BAR_COLORS)]}"/>'
            )
            parts.append(
                f'<text x="{legend_x + 14}" y="{_MARGIN - 13}" font-family="sans-serif" '
                f'font-size="10">{_esc(name)}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def authorization_graph_figure(graph: AuthorizationGraph | None, *, provider: Provider) -> Figure:
    key, title = "authorization_graph", "Authorization graph"
    if graph is None or not graph.nodes:
        reason = "No authorization graph in this bundle."
        return _not_applicable(key, title, reason, provider=provider)

    by_hop: dict[int, list[str]] = {}
    for node in graph.nodes:
        by_hop.setdefault(node.hop_index, []).append(str(node.identity_id))
    max_hop = max(by_hop)
    col_w = 150
    row_h = 50
    width = _MARGIN * 2 + (max_hop + 1) * col_w
    height = _MARGIN * 2 + max(len(v) for v in by_hop.values()) * row_h + 20

    positions: dict[str, tuple[float, float]] = {}
    for hop, ids in sorted(by_hop.items()):
        for row, identity_id in enumerate(sorted(ids)):
            positions[identity_id] = (
                _MARGIN + hop * col_w + col_w / 2,
                _MARGIN + row * row_h + row_h / 2 + 20,
            )

    parts = [_svg_open(width, height)]
    parts.append(
        f'<text x="{width / 2}" y="20" text-anchor="middle" font-family="sans-serif" '
        f'font-size="14" font-weight="bold">{_esc(title)}</text>'
    )
    for edge in graph.edges:
        src = positions.get(str(edge.source_id))
        dst = positions.get(str(edge.target_id))
        if src is None or dst is None:
            # Defensive only: AuthorizationGraph's own validator rejects an
            # edge referencing an identity outside graph.nodes, so `positions`
            # (built from every node) always has both endpoints in practice.
            continue  # pragma: no cover
        parts.append(
            f'<line x1="{src[0]:.1f}" y1="{src[1]:.1f}" x2="{dst[0]:.1f}" y2="{dst[1]:.1f}" '
            f'stroke="{_AXIS_COLOR}" marker-end="url(#arrow)"/>'
        )
        mid_x, mid_y = (src[0] + dst[0]) / 2, (src[1] + dst[1]) / 2
        parts.append(
            f'<text x="{mid_x:.1f}" y="{mid_y - 4:.1f}" text-anchor="middle" '
            f'font-family="monospace" font-size="8" fill="{_AXIS_COLOR}">'
            f"{_esc(edge.mechanism.value)}</text>"
        )
    parts.append(
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="8" refY="4" '
        f'orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="{_AXIS_COLOR}"/></marker></defs>'
    )
    for node in graph.nodes:
        x, y = positions[str(node.identity_id)]
        color = "#4c78a8" if node.is_root else "#54a24b"
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{color}"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{y + 18:.1f}" text-anchor="middle" font-family="monospace" '
            f'font-size="9">{_esc(str(node.identity_id))}</text>'
        )
    parts.append("</svg>")
    return Figure(
        key=key,
        title=title,
        caption=_caption(
            f"{len(graph.nodes)} identities, {len(graph.edges)} delegation edges.",
            provider=provider,
        ),
        svg="".join(parts),
        applicable=True,
    )


def per_hop_authority_figure(graph: AuthorizationGraph | None, *, provider: Provider) -> Figure:
    key, title = "per_hop_intended_vs_effective", "Intended vs. effective authority per hop"
    if graph is None:
        reason = "No authorization graph in this bundle."
        return _not_applicable(key, title, reason, provider=provider)
    measured = [n for n in graph.nodes if n.observed_authority is not None]
    if not measured:
        return _not_applicable(
            key, title, "No node in this bundle has an observed-authority phase.", provider=provider
        )
    measured.sort(key=lambda n: (n.hop_index, str(n.identity_id)))
    categories = [f"{n.identity_id} (hop {n.hop_index})" for n in measured]
    intended = [float(len(n.expected_authority.capabilities.capabilities)) for n in measured]
    effective = [float(len(n.observed_authority.capabilities.capabilities)) for n in measured]  # type: ignore[union-attr]
    svg = _bar_group_chart(
        title, categories, {"intended": intended, "effective": effective}, unit=" capabilities"
    )
    caption_text = f"{len(measured)} hop(s) with an observed-authority phase."
    caption = _caption(caption_text, provider=provider)
    return Figure(key=key, title=title, caption=caption, svg=svg, applicable=True)


def gain_loss_per_hop_figure(
    edge_divergences: Sequence[EdgeDivergence], *, provider: Provider
) -> Figure:
    key, title = "gain_loss_per_hop", "Excess / missing capabilities per hop"
    measured = list(edge_divergences)
    if not measured:
        return _not_applicable(
            key, title, "No edge in this bundle has both endpoints measured.", provider=provider
        )
    categories = [e.edge_id for e in measured]
    excess = [float(len(e.survived_incorrectly.capabilities)) for e in measured]
    missing = [float(len(e.dropped_incorrectly.capabilities)) for e in measured]
    svg = _bar_group_chart(title, categories, {"excess": excess, "missing": missing})
    return Figure(
        key=key,
        title=title,
        caption=_caption(f"{len(measured)} edge(s) evaluated.", provider=provider),
        svg=svg,
        applicable=True,
    )


def revocation_timeline_figure(
    measurements: Sequence[RevocationMeasurement], *, provider: Provider
) -> Figure:
    key, title = "revocation_timeline", "Revocation timeline (transition window shaded)"
    with_window = [m for m in measurements if m.transition_window is not None]
    if not with_window:
        return _not_applicable(
            key,
            title,
            "No revocation transition was observed within any polled window.",
            provider=provider,
        )

    width, height = _WIDTH, 100 * len(with_window) + _MARGIN
    parts = [_svg_open(width, height)]
    parts.append(
        f'<text x="{width / 2}" y="20" text-anchor="middle" font-family="sans-serif" '
        f'font-size="14" font-weight="bold">{_esc(title)}</text>'
    )
    max_high = max(m.transition_window.high for m in with_window if m.transition_window)
    scale = (width - 2 * _MARGIN) / max_high if max_high else 1.0
    for row, m in enumerate(with_window):
        window: Interval = m.transition_window  # type: ignore[assignment]
        y = 40 + row * 90
        x_low = _MARGIN + window.low * scale
        x_high = _MARGIN + window.high * scale
        parts.append(
            f'<rect x="{x_low:.1f}" y="{y:.1f}" width="{max(x_high - x_low, 1):.1f}" '
            f'height="30" fill="#f2b70166" stroke="#f2b701">'
            f"<title>transition window [{window.low:.2f}, {window.high:.2f}] s, "
            f"n={m.poll_count}</title></rect>"
        )
        marker = "non-monotonic" if m.non_monotonic else "monotonic"
        parts.append(
            f'<text x="{_MARGIN}" y="{y - 4:.1f}" font-family="monospace" font-size="10">'
            f"{_esc(str(m.identity_id))}/{_esc(str(m.capability_id))} "
            f"[{window.low:.2f}-{window.high:.2f}]s n={m.poll_count} "
            f"({_esc(m.mutation_kind.value)}, {_esc(marker)})</text>"
        )
    parts.append("</svg>")
    return Figure(
        key=key,
        title=title,
        caption=_caption(f"{len(with_window)} transition window(s) observed.", provider=provider),
        svg="".join(parts),
        applicable=True,
    )


def stale_authority_window_figure(
    measurements: Sequence[StaleAuthorityMeasurement], *, provider: Provider
) -> Figure:
    key, title = "stale_authority_window", "Stale-authority window"
    with_window = [m for m in measurements if m.stale_window_seconds is not None]
    if not with_window:
        return _not_applicable(
            key,
            title,
            "stale_window_seconds is not populated in v0.1 (no mutation-timing input to "
            "compute it from) -- omitted rather than approximated from a different instant.",
            provider=provider,
        )
    categories = [f"{m.identity_id}/{m.capability_id}" for m in with_window]
    values = [float(m.stale_window_seconds) for m in with_window]  # type: ignore[arg-type]
    svg = _bar_group_chart(title, categories, {"stale window (s)": values})
    return Figure(
        key=key,
        title=title,
        caption=_caption(f"{len(with_window)} measurement(s).", provider=provider),
        svg=svg,
        applicable=True,
    )


def repeatability_figure(
    cells: Mapping[tuple[str, str], Sequence[OutcomeClass]], *, provider: Provider
) -> Figure:
    """M15/ADR-012's own unanimity requirement, shown as evidence: for each
    probed (identity, capability) cell, the fraction of trials that agreed
    with the cell's own majority outcome -- 1.0 everywhere is what
    "unanimous or excluded, never averaged" (ADR-012) predicts."""
    key, title = "repeatability_across_trials", "Repeatability across trials"
    multi_trial = {k: v for k, v in cells.items() if len(v) > 1}
    if not multi_trial:
        return _not_applicable(
            key, title, "No probed cell in this bundle has more than one trial.", provider=provider
        )
    categories = [f"{identity}/{capability}" for identity, capability in multi_trial]
    agreement: list[float] = []
    labels: list[str] = []
    for outcomes in multi_trial.values():
        majority = max(set(outcomes), key=outcomes.count)
        agree = sum(1 for o in outcomes if o == majority)
        agreement.append(agree / len(outcomes))
        labels.append(f"{agree}/{len(outcomes)}")
    svg = _bar_group_chart(title, categories, {"agreement fraction": agreement})
    caption = ", ".join(f"{c}: {label}" for c, label in zip(categories, labels, strict=True))
    return Figure(
        key=key,
        title=title,
        caption=_caption(f"trial agreement per cell -- {caption}", provider=provider),
        svg=svg,
        applicable=True,
    )


def scenario_comparison_figure(
    comparison: Mapping[str, float] | None, *, provider: Provider, denominator: int | None = None
) -> Figure:
    """Cross-run comparison (SCORING_MODEL §5). A single-run report has
    nothing to compare -- ``chainbreak analyze --aggregate-scores`` is the
    only path that produces the ``comparison`` mapping this figure needs."""
    key, title = "scenario_comparison", "Scenario comparison across runs"
    if not comparison:
        return _not_applicable(
            key,
            title,
            "Single-run report -- no cross-run comparison available "
            "(see `chainbreak analyze --aggregate-scores`).",
            provider=provider,
        )
    categories = list(comparison)
    values = [comparison[c] for c in categories]
    svg = _bar_group_chart(title, categories, {"median": values})
    denom_note = f" of {denominator} run(s)" if denominator else ""
    return Figure(
        key=key,
        title=title,
        caption=_caption(f"median per category{denom_note}.", provider=provider),
        svg=svg,
        applicable=True,
    )
