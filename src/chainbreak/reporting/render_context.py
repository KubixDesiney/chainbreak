"""Builds the one template context ``markdown.py`` and ``html.py`` both
render from -- so the two formats can never structurally disagree about what
a category or finding looks like, and so the "blanked finding text" trick
that lets each renderer lint its own authored prose separately from
evidence-derived prose (see ``language.py::enforce_report``) lives in one
place instead of two.

``blank_findings=True`` renders the *same* template with every finding's
free-text fields (``observation``/``expected_state``/``observed_state``/
``security_interpretation``/``caveats``) replaced by an empty string. The
resulting text is structurally identical to the real report (same headings,
same category table, same limitations section) but contains zero
evidence-derived prose -- exactly the text ``enforce_report``'s
``structural_text`` argument should be linted against, computed by actually
re-rendering the template rather than by pattern-matching the real output
apart after the fact (which would be fragile against a template edit).
"""

from __future__ import annotations

import json
from typing import Any

from chainbreak.core.models import Interval
from chainbreak.reporting.data import ReportData
from chainbreak.reporting.format import LIMITATIONS, format_timing_result

__all__ = ["build_context"]

_FAKE_PROVIDER_BANNER = (
    "FAKE-PROVIDER APPARATUS CHECK -- this is not a measurement of any real provider."
)


def _dict_text(d: dict[str, Any]) -> str:
    return json.dumps(d, sort_keys=True, default=str) if d else "{}"


def _measurement_lines(data: ReportData) -> list[str]:
    lines = [
        format_timing_result(
            f"revocation_window {m.identity_id}/{m.capability_id}",
            m.transition_window,
            n=m.poll_count,
            mechanism=m.mutation_kind.value,
        )
        for m in data.revocation_measurements
        if m.transition_window is not None
    ]
    lines += [
        format_timing_result(
            f"stale_window {m.identity_id}/{m.capability_id}",
            Interval(
                low=m.stale_window_seconds,
                point=m.stale_window_seconds,
                high=m.stale_window_seconds,
            ),
            n=1,
            mechanism=m.classification.value,
        )
        for m in data.stale_measurements
        if m.stale_window_seconds is not None
    ]
    return lines


def build_context(data: ReportData, *, blank_findings: bool = False) -> dict[str, Any]:
    findings = []
    for finding in data.findings:
        if blank_findings:
            findings.append(
                {
                    "type": finding.type.value,
                    "severity_hint": finding.severity_hint.value,
                    "confidence": finding.confidence.value,
                    "observation": "",
                    "expected_state": "",
                    "observed_state": "",
                    "security_interpretation": "",
                    "caveats": "",
                }
            )
        else:
            findings.append(
                {
                    "type": finding.type.value,
                    "severity_hint": finding.severity_hint.value,
                    "confidence": finding.confidence.value,
                    "observation": finding.observation,
                    "expected_state": _dict_text(finding.expected_state),
                    "observed_state": _dict_text(finding.observed_state),
                    "security_interpretation": finding.security_interpretation,
                    "caveats": "; ".join(finding.caveats),
                }
            )

    categories = [
        {
            "category": c.category.value,
            "status": c.status.value,
            "not_measured": c.status.value == "NOT_MEASURED",
            "coverage": f"{c.coverage:.2f}",
            "confidence": c.confidence.value,
            "caveats": "; ".join(c.caveats),
        }
        for c in data.categories
    ]

    figures = [
        {
            "key": f.key,
            "title": f.title,
            "caption": f.caption,
            "svg": f.svg,
            "applicable": f.applicable,
        }
        for f in data.figures
    ]

    return {
        "run_id": data.run_id,
        "status": data.status,
        "created_at": data.created_at,
        "completed_at": data.completed_at,
        "scenario_id": data.scenario.get("id"),
        "scenario_version": data.scenario.get("version"),
        "scenario_family": data.scenario.get("family"),
        "provider": data.provider.value,
        "adapter_version": data.provenance.get("provider_adapter_version"),
        "is_fake_provider": data.is_fake_provider,
        "fake_provider_banner": _FAKE_PROVIDER_BANNER if data.is_fake_provider else None,
        "git_dirty": data.git_dirty,
        "bundle_root_verified": data.bundle_root_verified,
        "warnings": list(data.warnings),
        "categories": categories,
        "not_measured_notice": data.not_measured_notice,
        "findings": findings,
        # Not finding-derived (built from RevocationMeasurement/
        # StaleAuthorityMeasurement, this module's own formatting) --
        # always present, including in the blanked-findings structural pass.
        "measurement_lines": _measurement_lines(data),
        "figures": figures,
        "limitations": list(LIMITATIONS),
    }
