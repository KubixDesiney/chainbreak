"""EXPERIMENT_PROTOCOL.md section 7's reporting-language rules, implemented as
a checkable lint over both templates and generated text -- not a style guide
that renderers are merely asked to follow.

``enforce()`` is called at the end of every renderer in this package
(``terminal.py``, ``markdown.py``, ``html.py``) immediately before the
rendered text is returned, so a violation can never reach a caller silently
-- "enforced by lint rather than good intentions" (M16 purpose statement)
is made physical here, not just documented.

Two independent checkers exist deliberately: :func:`lint` is generic (any
report text, including a hand-planted violation in a raw template string,
with no bundle-shaped context available) -- this is what
``tests/unit/test_report_language.py`` drives directly, matching the
milestone's own negative-control instruction ("hand-edit a template ... assert
the language test fails"). :func:`enforce` wraps it with the one piece of
context a lint pass cannot infer on its own -- whether this report actually
has a NOT_MEASURED category to announce -- and is what the renderers call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from chainbreak.core.errors import ReportLanguageError

__all__ = [
    "FORBIDDEN_PHRASES",
    "LIMITATIONS_TERMS",
    "NOT_MEASURED_SENTENCE",
    "LintViolation",
    "check_forbidden_language",
    "enforce",
    "enforce_report",
    "lint",
]

#: EXPERIMENT_PROTOCOL.md section 7, "Forbidden in generated text". Matched
#: case-insensitively as whole words/phrases -- a report is free to discuss
#: findings in any other terms, but never these, applied to a provider.
FORBIDDEN_PHRASES: tuple[str, ...] = (
    "vulnerable",
    "vulnerability",
    "vulnerabilities",
    "exploit",
    "exploited",
    "exploitable",
    "broken",
    "insecure",
    "flaw",
    "flawed",
    "proves",
    "proven",
    "demonstrates conclusively",
    "guarantees",
    "guaranteed",
)

#: SCORING_MODEL §4 / EXPERIMENT_PROTOCOL §7: printed literally whenever at
#: least one category was not exercised (mirrors
#: ``scoring/categories.py::not_measured_notice``'s own wording exactly, so
#: the lint and the generator can never drift apart).
NOT_MEASURED_SENTENCE = "NOT_MEASURED is not a pass."

#: F5: the five things every report's limitations section must name.
LIMITATIONS_TERMS: tuple[str, ...] = (
    "single account",
    "single region",
    "simple polic",  # matches "policy"/"policies"
    "deterministic worker",
    "small n",
)

_FORBIDDEN_RE = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in FORBIDDEN_PHRASES) + r")\b", re.IGNORECASE
)

#: A bare duration: a number immediately followed by a time unit. Deliberately
#: narrow (ms/s/sec/seconds/minute(s)/hour(s)) -- this is a lint over report
#: prose, not a general-purpose unit parser.
_TIMING_VALUE_RE = re.compile(
    r"(?<![\d.\-])\d+(?:\.\d+)?\s?(?:ms|s|sec|secs|seconds|minutes?|min|hours?)\b",
    re.IGNORECASE,
)

#: An interval indicator on the same line as a timing value: an en-dash
#: (U+2013, written as an escape rather than the literal character so it
#: stays unambiguous in source -- RUF001) or hyphenated range between two
#: numbers, "n=", or the word "to" used as a range joiner. A line carrying
#: one of these is read as reporting an interval, not a bare scalar.
_INTERVAL_INDICATOR_RE = re.compile(
    r"\d\s*(?:\u2013|-|to)\s*\d|\bn\s*=\s*\d|\binterval\b|\bwindow\b", re.IGNORECASE
)

_PERCENT_RE = re.compile(r"\d+(?:\.\d+)?\s?%")

#: A denominator alongside a percentage: "(3/6)", "3 of 6", "3/6".
_DENOMINATOR_RE = re.compile(r"\(\s*\d+\s*/\s*\d+\s*\)|\b\d+\s*/\s*\d+\b|\bof\s+\d+\b", re.I)


@dataclass(frozen=True, slots=True)
class LintViolation:
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.detail}"


def _check_forbidden_phrases(text: str) -> list[LintViolation]:
    return [
        LintViolation("forbidden_phrase", f"{match.group(0)!r} applied in generated text")
        for match in _FORBIDDEN_RE.finditer(text)
    ]


def check_forbidden_language(text: str) -> tuple[LintViolation, ...]:
    """The one absolute bar: never let a forbidden phrase reach a report,
    including inside evidence-derived free text (a ``Finding``'s own
    ``observation``/``security_interpretation``/``caveats``) that the
    stricter timing/percentage heuristics below are deliberately not
    applied to -- see :func:`enforce_report`'s docstring."""
    return tuple(_check_forbidden_phrases(text))


def _check_timing_without_interval(text: str) -> list[LintViolation]:
    violations: list[LintViolation] = []
    for line in text.splitlines():
        if not _TIMING_VALUE_RE.search(line):
            continue
        if _INTERVAL_INDICATOR_RE.search(line):
            continue
        violations.append(LintViolation("timing_without_interval", line.strip()[:200]))
    return violations


def _check_percentage_without_denominator(text: str) -> list[LintViolation]:
    violations: list[LintViolation] = []
    for line in text.splitlines():
        if not _PERCENT_RE.search(line):
            continue
        if _DENOMINATOR_RE.search(line):
            continue
        violations.append(LintViolation("percentage_without_denominator", line.strip()[:200]))
    return violations


def lint(text: str) -> tuple[LintViolation, ...]:
    """Rules checkable with no bundle-shaped context: forbidden phrases, a
    timing value with no interval indicator on its line, a percentage with
    no denominator on its line. Runs over any text -- a full rendered
    report, a single planted sentence, or a template's static prose."""
    violations = [
        *_check_forbidden_phrases(text),
        *_check_timing_without_interval(text),
        *_check_percentage_without_denominator(text),
    ]
    return tuple(violations)


def check_limitations_section(text: str) -> tuple[LintViolation, ...]:
    """F5: every report names all five limitations. Checked as a distinct
    function (rather than folded into :func:`lint`) because a bare sentence
    fragment -- the shape every other check above operates on -- has no
    "report" to carry a limitations section at all; this only makes sense
    against a full rendered report."""
    lowered = text.lower()
    missing = [term for term in LIMITATIONS_TERMS if term not in lowered]
    if not missing:
        return ()
    return (LintViolation("missing_limitation", ", ".join(missing)),)


def check_not_measured_sentence(text: str, *, has_not_measured: bool) -> tuple[LintViolation, ...]:
    """SCORING_MODEL §4: the literal sentence, present if and only if at
    least one category is NOT_MEASURED. Absence when required is the
    documented failure mode (letting absence of measurement read as absence
    of problems); presence when nothing was skipped would just be noise, so
    it is flagged too rather than silently tolerated."""
    present = NOT_MEASURED_SENTENCE in text
    if has_not_measured and not present:
        return (
            LintViolation(
                "missing_not_measured_sentence",
                "at least one category is NOT_MEASURED but the literal sentence is absent",
            ),
        )
    if not has_not_measured and present:
        return (
            LintViolation(
                "spurious_not_measured_sentence",
                "no category is NOT_MEASURED but the literal sentence is present",
            ),
        )
    return ()


def lint_report(text: str, *, has_not_measured: bool) -> tuple[LintViolation, ...]:
    """The full report-level lint: everything :func:`lint` checks, plus the
    two checks that need to know about the whole report (limitations
    section, NOT_MEASURED sentence)."""
    return (
        *lint(text),
        *check_limitations_section(text),
        *check_not_measured_sentence(text, has_not_measured=has_not_measured),
    )


def enforce(text: str, *, has_not_measured: bool) -> None:
    """Called by every renderer immediately before returning rendered text.
    Raises rather than returns a diagnostic -- a report that fails its own
    language rules must never reach a caller, sealed bundle or not."""
    violations = lint_report(text, has_not_measured=has_not_measured)
    if violations:
        raise ReportLanguageError(
            f"{len(violations)} report-language violation(s)",
            violations=tuple(str(v) for v in violations),
        )


def enforce_report(*, structural_text: str, finding_text: str, has_not_measured: bool) -> None:
    """The renderer-facing entry point, applying two different bars to two
    different kinds of text in the same report.

    ``structural_text`` is everything the reporting layer itself authored --
    headers, the category table, the limitations section, a rendered timing
    measurement's own "n=.../mechanism=.../region=..." line -- and gets the
    full :func:`lint_report`: forbidden phrases, no bare timing value, no
    bare percentage, the limitations section, the NOT_MEASURED sentence.

    ``finding_text`` is every ``Finding``'s own ``observation``/
    ``security_interpretation``/``caveats`` (ADR-006/F4: rendered verbatim
    under their own headings, never rewritten by the reporting layer). Only
    :func:`check_forbidden_language` applies to it -- the timing/percentage
    heuristics below are calibrated against report-authored prose, and
    retrofitting them onto evidence text several earlier milestones already
    wrote and tested is out of this milestone's scope. The one rule that is
    not negotiable for *any* text a report ever shows, evidence-derived or
    not, is that a forbidden phrase never appears -- confirmed by fixing the
    one real pre-existing hit this design decision surfaced
    (``analysis/rules.py``'s stale-authority caveat used to say
    "Not a vulnerability"; it now says "Not a defect").
    """
    violations = (
        *lint_report(structural_text, has_not_measured=has_not_measured),
        *check_forbidden_language(finding_text),
    )
    if violations:
        raise ReportLanguageError(
            f"{len(violations)} report-language violation(s)",
            violations=tuple(str(v) for v in violations),
        )
