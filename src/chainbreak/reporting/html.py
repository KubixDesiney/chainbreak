"""Self-contained HTML report (M16 F2), rendered from
``templates/report.html.j2`` via Jinja2 with autoescape on and no ``|safe``
anywhere in the template (S1/T-10) -- a third-party evidence bundle's
``security_interpretation`` is a plausible XSS vector into this exact
output, and every finding field reaches the template as a plain
autoescaped string.

The one thing this module *does* mark safe is each :class:`Figure`'s own
``svg`` string -- code-generated, self-escaping XML this process just built
(see ``figures.py``'s module docstring), never evidence free text. It is
wrapped in ``markupsafe.Markup`` here, in Python, at the one place the
string is known to be safe -- not via a template ``|safe`` filter, which is
the pattern the milestone's own grep-based test (S1) exists to keep out of
the template file itself: a future template edit reusing ``|safe`` could
just as easily be applied to an untrusted field, where marking safety in
Python at construction time cannot.
"""

from __future__ import annotations

import re
from pathlib import Path

import jinja2
from markupsafe import Markup

from chainbreak.reporting.data import ReportData
from chainbreak.reporting.language import enforce_report
from chainbreak.reporting.render_context import build_context

__all__ = ["render_html"]

_TEMPLATES_DIR = Path(__file__).parent / "templates"

#: The report-language rules (EXPERIMENT_PROTOCOL §7) are about prose the
#: report writes describing the run -- not the page's own presentation CSS
#: (which legitimately contains e.g. ``width: 100%`` with no "denominator"
#: to speak of). Stripped before linting only; never from the real output.
_STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)


def _environment() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _mark_figures_safe(context: dict[str, object]) -> dict[str, object]:
    figures: list[dict[str, object]] = context["figures"]  # type: ignore[assignment]
    # This module's own docstring explains why: the string is code-generated,
    # self-escaping SVG (figures.py escapes every label it interpolates),
    # never evidence free text.
    marked = [
        {**fig, "svg": Markup(fig["svg"])}  # noqa: S704  # nosec B704
        for fig in figures
    ]
    return {**context, "figures": marked}


def render_html(data: ReportData) -> str:
    template = _environment().get_template("report.html.j2")
    text = template.render(**_mark_figures_safe(build_context(data)))

    structural_context = _mark_figures_safe(build_context(data, blank_findings=True))
    structural_text = _STYLE_BLOCK_RE.sub("", template.render(**structural_context))
    finding_text = "\n".join(
        f"{f.observation} {f.security_interpretation} {' '.join(f.caveats)}" for f in data.findings
    )
    enforce_report(
        structural_text=structural_text,
        finding_text=finding_text,
        has_not_measured=data.has_not_measured,
    )
    return text
