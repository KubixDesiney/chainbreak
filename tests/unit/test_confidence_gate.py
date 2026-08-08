"""``analysis/confidence.py``: the gate, exactly as AUTHORIZATION_MODEL.md
section 6 (F3)."""

from __future__ import annotations

import pytest

from chainbreak.analysis.confidence import confidence_rationale, gate_confidence
from chainbreak.core.enums import Confidence, OutcomeClass, PlanPhase
from chainbreak.core.models import ProbeCellResult

pytestmark = pytest.mark.unit


def _cell(*trials: OutcomeClass, capability: str = "objectstore.read") -> ProbeCellResult:
    return ProbeCellResult(
        identity_id="a", capability_id=capability, phase=PlanPhase.BASELINE, trials=trials
    )


class TestGateConfidence:
    def test_high_requires_full_coverage_unanimous_no_error_snapshot_ok(self):
        cells = [_cell(OutcomeClass.ALLOWED, OutcomeClass.ALLOWED, OutcomeClass.ALLOWED)]
        assert (
            gate_confidence(coverage=1.0, cells=cells, policy_snapshot_ok=True) is Confidence.HIGH
        )

    def test_full_coverage_but_policy_snapshot_failed_is_not_high(self):
        cells = [_cell(OutcomeClass.ALLOWED, OutcomeClass.ALLOWED, OutcomeClass.ALLOWED)]
        result = gate_confidence(coverage=1.0, cells=cells, policy_snapshot_ok=False)
        assert result is not Confidence.HIGH

    def test_full_coverage_but_non_unanimous_cell_is_not_high(self):
        cells = [_cell(OutcomeClass.ALLOWED, OutcomeClass.DENIED_EXPLICIT, OutcomeClass.ALLOWED)]
        result = gate_confidence(coverage=1.0, cells=cells, policy_snapshot_ok=True)
        assert result is not Confidence.HIGH

    def test_full_coverage_but_error_outcome_is_not_high(self):
        cells = [
            _cell(
                OutcomeClass.ERROR_TRANSIENT,
                OutcomeClass.ERROR_TRANSIENT,
                OutcomeClass.ERROR_TRANSIENT,
            )
        ]
        result = gate_confidence(coverage=1.0, cells=cells, policy_snapshot_ok=True)
        assert result is not Confidence.HIGH

    def test_medium_at_ninety_percent_coverage_no_indeterminate(self):
        cells = [_cell(OutcomeClass.ALLOWED, OutcomeClass.ALLOWED, OutcomeClass.ALLOWED)]
        assert gate_confidence(coverage=0.9, cells=cells) is Confidence.MEDIUM

    def test_high_coverage_but_indeterminate_cell_caps_at_low(self):
        cells = [
            _cell(OutcomeClass.ALLOWED, OutcomeClass.DENIED_EXPLICIT, OutcomeClass.ERROR_TRANSIENT)
        ]
        result = gate_confidence(coverage=0.95, cells=cells)
        assert result is Confidence.LOW

    def test_low_at_seventy_percent_coverage(self):
        cells = [_cell(OutcomeClass.ALLOWED)]
        assert gate_confidence(coverage=0.7, cells=cells) is Confidence.LOW

    def test_insufficient_below_seventy_percent(self):
        cells = [_cell(OutcomeClass.ALLOWED)]
        assert gate_confidence(coverage=0.69, cells=cells) is Confidence.INSUFFICIENT

    def test_empty_cells_is_always_insufficient_regardless_of_claimed_coverage(self):
        assert gate_confidence(coverage=1.0, cells=[]) is Confidence.INSUFFICIENT


class TestConfidenceRationale:
    def test_empty_cells_rationale(self):
        assert confidence_rationale(coverage=1.0, cells=[]) == "no contributing observations"

    def test_rationale_mentions_coverage_and_unanimity(self):
        cells = [_cell(OutcomeClass.ALLOWED, OutcomeClass.ALLOWED, OutcomeClass.ALLOWED)]
        text = confidence_rationale(coverage=1.0, cells=cells, policy_snapshot_ok=True)
        assert "coverage=1.00" in text
        assert "1/1 cells unanimous" in text
        assert "no ERROR outcomes" in text
        assert "policy snapshots succeeded" in text

    def test_rationale_reports_error_outcomes_present(self):
        cells = [
            _cell(
                OutcomeClass.ERROR_TRANSIENT,
                OutcomeClass.ERROR_TRANSIENT,
                OutcomeClass.ERROR_TRANSIENT,
            )
        ]
        text = confidence_rationale(coverage=1.0, cells=cells)
        assert "ERROR outcomes present" in text

    def test_rationale_reports_policy_snapshot_failure(self):
        cells = [_cell(OutcomeClass.ALLOWED)]
        text = confidence_rationale(coverage=1.0, cells=cells, policy_snapshot_ok=False)
        assert "policy snapshot missing or failed" in text
