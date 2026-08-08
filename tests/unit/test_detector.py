"""``analysis/detector.py`` direct branch coverage, complementing the
end-to-end negative-control tests in ``tests/integration/test_negative_controls.py``."""

from __future__ import annotations

import pytest

from chainbreak.analysis.detector import check_negative_control
from chainbreak.core.enums import Confidence, FindingType, SeverityHint
from chainbreak.core.models import AuthoritySet, CompiledExpectedFinding, Finding, FindingEvidence

pytestmark = pytest.mark.unit


def _finding(
    *,
    type: FindingType = FindingType.AUTHORITY_EXPANSION,  # noqa: A002
    identity_id: str = "agent-b",
    confidence: Confidence = Confidence.HIGH,
    gain: tuple[str, ...] = ("keyvalue.read",),
) -> Finding:
    return Finding(
        finding_id="fnd_test",
        type=type,
        severity_hint=SeverityHint.REVIEW,
        confidence=confidence,
        subject_kind="identity",
        identity_id=identity_id,
        observation="test",
        delta={"unexpected_gain": list(gain), "unexpected_loss": []},
        evidence=FindingEvidence(),
    )


def test_no_expected_capabilities_is_vacuously_satisfied():
    expected = CompiledExpectedFinding(type=FindingType.AUTHORITY_EXPANSION, identity_id="agent-b")
    result = check_negative_control(expected, [_finding()], negative_control_id="nc-test")
    assert result.result == "DETECTOR_OK"


def test_identity_mismatch_is_skipped():
    expected = CompiledExpectedFinding(type=FindingType.AUTHORITY_EXPANSION, identity_id="agent-c")
    result = check_negative_control(
        expected, [_finding(identity_id="agent-b")], negative_control_id="nc-test"
    )
    assert result.result == "DETECTOR_FAILURE"


def test_capability_mismatch_is_skipped():
    expected = CompiledExpectedFinding(
        type=FindingType.AUTHORITY_EXPANSION,
        identity_id="agent-b",
        capabilities=AuthoritySet.of("function.invoke"),
    )
    result = check_negative_control(
        expected, [_finding(gain=("keyvalue.read",))], negative_control_id="nc-test"
    )
    assert result.result == "DETECTOR_FAILURE"


def test_confidence_below_minimum_is_skipped():
    expected = CompiledExpectedFinding(
        type=FindingType.AUTHORITY_EXPANSION, identity_id="agent-b", min_confidence=Confidence.HIGH
    )
    result = check_negative_control(
        expected, [_finding(confidence=Confidence.LOW)], negative_control_id="nc-test"
    )
    assert result.result == "DETECTOR_FAILURE"


def test_no_matching_finding_type_is_failure():
    expected = CompiledExpectedFinding(type=FindingType.AUTHORITY_SURVIVAL, identity_id="agent-b")
    result = check_negative_control(expected, [], negative_control_id="nc-test")
    assert result.produced is False
    assert result.result == "DETECTOR_FAILURE"
    assert result.expected_type is FindingType.AUTHORITY_SURVIVAL


def test_matching_finding_among_several_is_ok():
    expected = CompiledExpectedFinding(
        type=FindingType.AUTHORITY_EXPANSION,
        identity_id="agent-b",
        capabilities=AuthoritySet.of("keyvalue.read"),
    )
    findings = [
        _finding(type=FindingType.AUTHORITY_NARROWING, identity_id="agent-a"),
        _finding(identity_id="agent-b", gain=("keyvalue.read",)),
    ]
    result = check_negative_control(expected, findings, negative_control_id="nc-test")
    assert result.result == "DETECTOR_OK"
    assert result.produced is True
