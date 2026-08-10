"""M16 S1/T-10: no ``|safe`` anywhere in the template directory. A
third-party evidence bundle's ``security_interpretation`` is a plausible XSS
vector into a generated HTML report; the one thing that would let it through
Jinja2's autoescape is a template using ``|safe`` on that field (or any
field), so this asserts the filter never appears in the template source at
all -- not just that today's templates happen not to misuse it.

Matched with a regex tolerant of whitespace around the pipe (``| safe``,
``|safe``, ``| safe  `` before the closing braces) rather than a bare
substring check -- Jinja2 itself does not care about the spacing, so a scan
that only caught one spelling would miss a template written with the other.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "chainbreak" / "reporting" / "templates"
)

_SAFE_FILTER_RE = re.compile(r"\|\s*safe\b")


def test_templates_directory_exists() -> None:
    assert _TEMPLATES_DIR.is_dir()
    assert list(_TEMPLATES_DIR.glob("*.j2"))


def test_no_safe_filter_anywhere_in_the_template_directory() -> None:
    offenders = []
    for path in _TEMPLATES_DIR.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if _SAFE_FILTER_RE.search(text):
            offenders.append(path.name)
    assert offenders == [], f"|safe found in: {offenders}"


@pytest.mark.parametrize(
    "snippet",
    [
        "{{ finding.security_interpretation | safe }}",
        "{{ finding.security_interpretation|safe }}",
        "{{ finding.security_interpretation |safe}}",
    ],
)
def test_a_planted_safe_filter_would_be_caught(snippet: str) -> None:
    """Negative control for the check above: every spelling of ``|safe`` a
    template author might plausibly write must be caught by the same regex
    the real scan uses -- not just the exact substring ``|safe``."""
    assert _SAFE_FILTER_RE.search(snippet) is not None
