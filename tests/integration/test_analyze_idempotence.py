"""F8: analyzing the same bundle twice yields byte-identical ``findings.json``."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
import mini_orchestrator as mo

from chainbreak.analysis.pipeline import analyze
from chainbreak.core.enums import PlanPhase
from chainbreak.core.models import AuthoritySet

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_analyze_is_idempotent_on_a_diverging_bundle(tmp_path: Path, synthetic_aws_registry):
    scenario_path = REPO_ROOT / "scenarios" / "_negative-controls" / "nc-scope-expansion.yaml"
    compiled, adapter, refs, credentials = mo.compile_and_delegate(
        scenario_path, synthetic_aws_registry, seed=99
    )
    adapter.engine.apply_allow("agent-b", AuthoritySet.of("keyvalue.read"))
    observations = mo.probe_observations(
        compiled, adapter, refs, "idempotence-01", phase=PlanPhase.POST_DELEGATION
    )
    run_dir = mo.write_bundle(
        tmp_path, "idempotence-01", compiled, observations, credentials=credentials
    )

    analyze(run_dir)
    first_bytes = (run_dir / "findings.json").read_bytes()
    analyze(run_dir)
    second_bytes = (run_dir / "findings.json").read_bytes()

    assert first_bytes == second_bytes


def test_analyze_is_idempotent_on_a_clean_bundle(tmp_path: Path, synthetic_aws_registry):
    scenario_path = REPO_ROOT / "scenarios" / "scope-attenuation" / "basic.yaml"
    compiled, adapter, refs, credentials = mo.compile_and_delegate(
        scenario_path, synthetic_aws_registry, seed=17
    )
    observations = mo.probe_observations(
        compiled, adapter, refs, "idempotence-02", phase=PlanPhase.POST_DELEGATION
    )
    run_dir = mo.write_bundle(
        tmp_path, "idempotence-02", compiled, observations, credentials=credentials
    )

    result_a = analyze(run_dir)
    first_bytes = (run_dir / "findings.json").read_bytes()
    result_b = analyze(run_dir)
    second_bytes = (run_dir / "findings.json").read_bytes()

    assert first_bytes == second_bytes
    assert [f.finding_id for f in result_a.findings] == [f.finding_id for f in result_b.findings]
