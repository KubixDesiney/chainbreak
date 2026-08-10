"""EXPERIMENT_PROTOCOL.md section 7's reporting-language rules
(``reporting/language.py``), M16 acceptance criterion 2: the lint passes on
clean text and demonstrably fails on a planted violation.
"""

from __future__ import annotations

import pytest

from chainbreak.core.errors import ReportLanguageError
from chainbreak.reporting.format import LIMITATIONS
from chainbreak.reporting.language import (
    NOT_MEASURED_SENTENCE,
    check_forbidden_language,
    check_limitations_section,
    check_not_measured_sentence,
    enforce,
    enforce_report,
    lint,
    lint_report,
)

_CLEAN_LINE = "Authorization remained effective for 1.20-3.40s after the mutation request (n=5)."

pytestmark = pytest.mark.unit


class TestForbiddenPhrases:
    def test_clean_text_has_no_forbidden_phrases(self) -> None:
        assert lint(_CLEAN_LINE) == ()

    @pytest.mark.parametrize(
        "sentence",
        [
            "AWS is vulnerable to this attack.",
            "This provider is broken.",
            "The identity was insecure.",
            "This exploit works every time.",
            "The finding proves the provider is flawed.",
            "This test guarantees safety.",
        ],
    )
    def test_a_planted_violation_is_caught(self, sentence: str) -> None:
        violations = lint(sentence)
        assert violations
        assert any(v.rule == "forbidden_phrase" for v in violations)

    def test_removing_the_planted_violation_makes_it_pass(self) -> None:
        planted = "AWS is vulnerable to this attack."
        assert lint(planted) != ()
        fixed = "This is consistent with documented behavior in this environment."
        assert lint(fixed) == ()

    def test_case_insensitive(self) -> None:
        assert lint("This is VULNERABLE.") != ()

    def test_forbidden_language_check_is_the_only_rule_applied_to_finding_text(self) -> None:
        # A bare duration/percentage would trip the stricter checks in
        # lint(), but check_forbidden_language only looks for the phrases.
        text = "credential requested 3600s, granted 3600s (100% capped)"
        assert check_forbidden_language(text) == ()


class TestTimingWithoutInterval:
    def test_a_bare_duration_with_no_interval_indicator_is_flagged(self) -> None:
        violations = lint("Revocation happened within 3s.")
        assert any(v.rule == "timing_without_interval" for v in violations)

    def test_an_interval_range_passes(self) -> None:
        assert lint("The transition window was 1.20-3.40s (n=5).") == ()

    def test_the_word_window_is_an_accepted_indicator(self) -> None:
        assert lint("No transition observed within a 4.0s window (10 polls).") == ()

    def test_planted_violation_then_fixed(self) -> None:
        planted = "Authorization was revoked within 3s."
        assert any(v.rule == "timing_without_interval" for v in lint(planted))
        fixed = "Authorization was revoked within a 2.50-3.50s window (n=5)."
        assert lint(fixed) == ()


class TestPercentageWithoutDenominator:
    def test_a_bare_percentage_is_flagged(self) -> None:
        violations = lint("Coverage was 70% for this category.")
        assert any(v.rule == "percentage_without_denominator" for v in violations)

    def test_a_percentage_with_a_fraction_denominator_passes(self) -> None:
        assert lint("Coverage was 70% (7/10 cells measured).") == ()

    def test_a_percentage_with_an_of_denominator_passes(self) -> None:
        assert lint("3 of 6 categories were not exercised (50%).") == ()

    def test_planted_violation_then_fixed(self) -> None:
        planted = "35% of runs diverged."
        assert any(v.rule == "percentage_without_denominator" for v in lint(planted))
        fixed = "35% of runs diverged (7/20)."
        assert lint(fixed) == ()


class TestLimitationsSection:
    def test_full_limitations_text_passes(self) -> None:
        text = "\n".join(LIMITATIONS)
        assert check_limitations_section(text) == ()

    def test_missing_a_term_is_flagged(self) -> None:
        text = "\n".join(line for line in LIMITATIONS if "small n" not in line.lower())
        violations = check_limitations_section(text)
        assert violations
        assert "small n" in violations[0].detail

    def test_empty_text_flags_all_five(self) -> None:
        violations = check_limitations_section("")
        assert len(violations) == 1
        terms = (
            "single account",
            "single region",
            "simple polic",
            "deterministic worker",
            "small n",
        )
        for term in terms:
            assert term in violations[0].detail


class TestNotMeasuredSentence:
    def test_present_when_required_passes(self) -> None:
        text = f"three categories were skipped. {NOT_MEASURED_SENTENCE}"
        assert check_not_measured_sentence(text, has_not_measured=True) == ()

    def test_absent_when_required_is_flagged(self) -> None:
        violations = check_not_measured_sentence("all categories measured", has_not_measured=True)
        assert violations
        assert violations[0].rule == "missing_not_measured_sentence"

    def test_present_when_not_required_is_flagged(self) -> None:
        text = f"everything was measured. {NOT_MEASURED_SENTENCE}"
        violations = check_not_measured_sentence(text, has_not_measured=False)
        assert violations
        assert violations[0].rule == "spurious_not_measured_sentence"

    def test_absent_when_not_required_passes(self) -> None:
        assert check_not_measured_sentence("all categories measured", has_not_measured=False) == ()


class TestLintReportAndEnforce:
    def _clean_report(self, *, has_not_measured: bool) -> str:
        notice = (
            f"1 of 6 categories were not exercised. {NOT_MEASURED_SENTENCE}"
            if has_not_measured
            else ""
        )
        return "\n".join([_CLEAN_LINE, notice, *LIMITATIONS])

    def test_a_clean_report_passes(self) -> None:
        assert lint_report(self._clean_report(has_not_measured=True), has_not_measured=True) == ()

    def test_enforce_raises_on_a_planted_violation(self) -> None:
        broken = self._clean_report(has_not_measured=True) + "\nThis provider is vulnerable."
        with pytest.raises(ReportLanguageError) as exc_info:
            enforce(broken, has_not_measured=True)
        assert exc_info.value.context["violations"]

    def test_enforce_passes_once_the_violation_is_removed(self) -> None:
        enforce(self._clean_report(has_not_measured=True), has_not_measured=True)  # no raise


class TestEnforceReport:
    """The renderer-facing entry point: full lint on structural text,
    forbidden-phrases-only on finding text (``enforce_report``'s own
    docstring)."""

    def _clean(self) -> str:
        return "\n".join([_CLEAN_LINE, *LIMITATIONS])

    def test_a_clean_report_does_not_raise(self) -> None:
        enforce_report(structural_text=self._clean(), finding_text="", has_not_measured=False)

    def test_a_forbidden_word_in_structural_text_raises(self) -> None:
        with pytest.raises(ReportLanguageError):
            enforce_report(
                structural_text=self._clean() + "\nThis provider is broken.",
                finding_text="",
                has_not_measured=False,
            )

    def test_a_forbidden_word_in_finding_text_raises(self) -> None:
        with pytest.raises(ReportLanguageError):
            enforce_report(
                structural_text=self._clean(),
                finding_text="this identity is insecure",
                has_not_measured=False,
            )

    def test_a_bare_timing_value_in_finding_text_does_not_raise(self) -> None:
        # The timing/percentage heuristics are deliberately not applied to
        # finding text (evidence-derived prose from earlier milestones) --
        # only check_forbidden_language is.
        enforce_report(
            structural_text=self._clean(),
            finding_text="credential requested 3600s, granted 3600s",
            has_not_measured=False,
        )
