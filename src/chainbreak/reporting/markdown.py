"""Markdown report (M16 F2), rendered from ``templates/report.md.j2`` via
Jinja2 (autoescape is irrelevant for plain-text Markdown, but reusing Jinja2
for both text formats means one template mechanism instead of two).
"""

from __future__ import annotations

from pathlib import Path

import jinja2

from chainbreak.reporting.data import ReportData
from chainbreak.reporting.language import enforce_report
from chainbreak.reporting.render_context import build_context

__all__ = ["render_markdown"]

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _environment() -> jinja2.Environment:
    # autoescape=False is correct here, not an oversight: this environment
    # renders plain-text Markdown, never HTML, so there is no HTML-escaping
    # (or XSS) concern for it to guard against -- S1/T-10 apply to html.py,
    # which does keep autoescape on.
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=False,  # noqa: S701  # nosec B701
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_markdown(data: ReportData) -> str:
    template = _environment().get_template("report.md.j2")
    text = template.render(**build_context(data))

    # See render_context.py's module docstring: re-render with finding text
    # blanked to get a lint target with zero evidence-derived prose.
    structural_text = template.render(**build_context(data, blank_findings=True))
    finding_text = "\n".join(
        f"{f.observation} {f.security_interpretation} {' '.join(f.caveats)}" for f in data.findings
    )
    enforce_report(
        structural_text=structural_text,
        finding_text=finding_text,
        has_not_measured=data.has_not_measured,
    )
    return text
