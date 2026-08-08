"""M07's differential control (C-9): configure the fake with a *known*
authority mismatch, run it through the real fake-adapter code path, analyze
the resulting bundle, and assert exactly the expected findings at exactly
the expected confidence. No AWS run can validate this -- only a provider
whose ground truth is known in advance can.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
import mini_orchestrator as mo

from chainbreak.analysis.pipeline import analyze
from chainbreak.core.enums import FindingType, PlanPhase
from chainbreak.core.models import AuthoritySet

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_known_authority_expansion_produces_exactly_the_expected_finding(
    tmp_path: Path, synthetic_aws_registry
):
    scenario_path = REPO_ROOT / "scenarios" / "_negative-controls" / "nc-scope-expansion.yaml"
    compiled, adapter, refs, credentials = mo.compile_and_delegate(
        scenario_path, synthetic_aws_registry, seed=42
    )
    # The known mismatch: agent-b's role carries an inline grant hop-2 never
    # intended (the scenario's own negative_control.rationale).
    adapter.engine.apply_allow("agent-b", AuthoritySet.of("keyvalue.read"))

    observations = mo.probe_observations(
        compiled, adapter, refs, "known-truth-01", phase=PlanPhase.POST_DELEGATION
    )
    run_dir = mo.write_bundle(
        tmp_path, "known-truth-01", compiled, observations, credentials=credentials
    )

    result = analyze(run_dir)

    expansions = [f for f in result.findings if f.type is FindingType.AUTHORITY_EXPANSION]
    assert len(expansions) == 1
    finding = expansions[0]
    assert finding.identity_id == "agent-b"
    assert finding.delta["unexpected_gain"] == ["keyvalue.read"]
    assert finding.confidence.value in (
        "HIGH",
        "MEDIUM",
    )  # >= the scenario's declared min_confidence

    detector_results = {c.negative_control_id: c.result for c in result.detector_checks}
    assert detector_results["nc-scope-expansion"] == "DETECTOR_OK"


def test_no_mismatch_produces_no_expansion_finding(tmp_path: Path, synthetic_aws_registry):
    """The inverse of the known-truth case: without the injected mismatch,
    the same scenario must not report one -- this is what proves the
    previous test's positive result isn't just always-on noise."""
    scenario_path = REPO_ROOT / "scenarios" / "_negative-controls" / "nc-scope-expansion.yaml"
    compiled, adapter, refs, credentials = mo.compile_and_delegate(
        scenario_path, synthetic_aws_registry, seed=42
    )
    observations = mo.probe_observations(
        compiled, adapter, refs, "known-truth-02", phase=PlanPhase.POST_DELEGATION
    )
    run_dir = mo.write_bundle(
        tmp_path, "known-truth-02", compiled, observations, credentials=credentials
    )

    result = analyze(run_dir)

    expansions = [f for f in result.findings if f.type is FindingType.AUTHORITY_EXPANSION]
    assert expansions == []
    detector_results = {c.negative_control_id: c.result for c in result.detector_checks}
    assert detector_results["nc-scope-expansion"] == "DETECTOR_FAILURE"
