"""M11 acceptance criteria 1 and 4: depths 2-6 all run against the fake and
produce correct per-hop attribution, and the depth-sweep output includes
divergence rate per hop and exclusions per depth (F6).

``analysis/drift.py``'s own confound-detection logic (both rates rising
together -> ``INCONCLUSIVE``) is already exhaustively unit-tested against
synthetic :class:`~chainbreak.analysis.drift.DepthResult` objects in
``tests/unit/test_drift_aggregation.py``; this file's job is the
integration this milestone's own acceptance criteria actually require --
that a real depth sweep, run end to end through the real orchestrator,
produces correct :class:`DepthResult`\\s from real bundles, and that the
``chainbreak analyze --aggregate`` CLI path glues it all together.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from chainbreak.analysis.drift import DepthResult, depth_result_from_bundle, summarize_depth_sweep
from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.enums import RunStatus
from chainbreak.core.models import CompiledScenario, SafetyEnvelope
from chainbreak.evidence.writer import BundleWriter
from chainbreak.execution.orchestrator import orchestrate
from chainbreak.providers.fake.probes import build_fake_preconditions
from chainbreak.providers.fake.profiles import deterministic_profile
from chainbreak.providers.fake.session import virtual_ms_to_datetime
from chainbreak.scenarios.loader import load_and_compile

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIFT_DIR = REPO_ROOT / "scenarios" / "delegation-drift"
DEPTH_SCENARIOS = {
    2: DRIFT_DIR / "two-hop.yaml",
    3: DRIFT_DIR / "three-hop.yaml",
    4: DRIFT_DIR / "four-hop.yaml",
    5: DRIFT_DIR / "five-hop.yaml",
    6: DRIFT_DIR / "six-hop.yaml",
}


def _run_depth(depth: int, tmp_path: Path, registry: BindingRegistry, *, seed: int = 23) -> Path:
    scenario_path = DEPTH_SCENARIOS[depth]
    compiled: CompiledScenario = load_and_compile(scenario_path, registry=registry)
    adapter = deterministic_profile(seed=seed)
    envelope = SafetyEnvelope(
        allowed_account_ids=(adapter.account_ref,),
        allowed_regions=(adapter.region,),
        namespace=adapter.namespace,
        namespace_pattern=f"^{adapter.namespace}$",
    )
    run_id = f"run-depth-{depth}"
    writer = BundleWriter(
        tmp_path,
        run_id,
        scenario_ref={
            "id": compiled.scenario_id,
            "version": compiled.scenario_version,
            "family": "delegation-drift",
            "api_version": "chainbreak.dev/v1alpha1",
            "compiled_hash": compiled.compiled_hash,
        },
        provenance={
            "chainbreak_version": "0.1.0a0",
            "capability_catalog_version": compiled.catalog_version,
            "provider": "fake",
            "provider_adapter_version": compiled.adapter_version,
            "python_version": "3.12",
            "config_fingerprint": "sha256:" + ("3" * 64),
        },
    )
    with writer as sink:
        result = orchestrate(
            compiled,
            adapter,
            sink,
            build_fake_preconditions(adapter.markers),
            run_id=run_id,
            envelope=envelope,
            seed=seed,
            max_duration_seconds=1200,
            now=lambda: virtual_ms_to_datetime(adapter.clock.now_ms),
        )
    assert result.status is RunStatus.COMPLETED
    return tmp_path / run_id


class TestDepthsTwoThroughSixRunAndAttributeCorrectly:
    """Acceptance criterion 1."""

    @pytest.mark.parametrize("depth", [2, 3, 4, 5, 6])
    def test_each_depth_runs_and_the_bundle_yields_a_correct_depth_result(
        self, depth: int, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        run_dir = _run_depth(depth, tmp_path, synthetic_aws_registry)
        result = depth_result_from_bundle(run_dir)

        assert result.depth == depth
        assert result.total_hops == depth  # one non-root node per hop
        assert result.diverged_hops == 0  # every depth-sweep scenario is clean by design
        assert result.excluded_cells == 0
        assert result.total_cells == depth * 8  # eight capabilities x depth hops


class TestDepthSweepAggregationEndToEnd:
    """Acceptance criterion 4: the sweep's own output includes divergence
    rate per hop and exclusions per depth, built from real bundles."""

    def test_clean_sweep_across_all_five_depths_is_not_inconclusive(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        results = [
            depth_result_from_bundle(_run_depth(depth, tmp_path, synthetic_aws_registry))
            for depth in (2, 3, 4, 5, 6)
        ]
        report = summarize_depth_sweep(results)

        assert [r.depth for r in report.results] == [2, 3, 4, 5, 6]
        assert all(r.divergence_rate_per_hop == 0.0 for r in report.results)
        assert report.inconclusive is False

    def test_a_confounded_sweep_built_from_real_bundles_is_inconclusive(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        """Glue test between real-bundle DepthResults and the confound
        detector: appends one synthetic high-divergence, high-exclusion
        DepthResult (F6's actual failure mode requires a defect-injectable,
        multi-depth ROLE_CHAIN family this corpus does not ship, per
        test_delegation_drift.py's own docstring on why) to two real, clean
        results, and confirms summarize_depth_sweep still correctly flags
        the combination as inconclusive."""
        real_results = [
            depth_result_from_bundle(_run_depth(depth, tmp_path, synthetic_aws_registry))
            for depth in (2, 4)
        ]
        confounded = DepthResult(
            depth=6,
            scenario_id="synthetic-confound",
            total_hops=6,
            diverged_hops=4,
            excluded_cells=10,
            total_cells=48,
        )
        report = summarize_depth_sweep([*real_results, confounded])

        assert report.inconclusive is True
        assert "F6" in report.inconclusive_reason


class TestAggregateCliCommand:
    """The milestone's own verification command:
    `chainbreak analyze --aggregate --scenario-family delegation-drift`."""

    def test_runs_all_depths_then_aggregates_via_the_cli(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from chainbreak.cli.main import app

        monkeypatch.chdir(tmp_path)
        runs_root = tmp_path / "runs"
        runner = CliRunner()

        for depth_name in ("two", "three", "four", "five", "six"):
            result = runner.invoke(
                app,
                [
                    "run",
                    str(DRIFT_DIR / f"{depth_name}-hop.yaml"),
                    "--provider",
                    "fake",
                    "--seed",
                    "23",
                    "--runs-root",
                    str(runs_root),
                ],
            )
            assert result.exit_code == 0, result.output

        aggregate_result = runner.invoke(
            app,
            [
                "analyze",
                "--aggregate",
                "--scenario-family",
                "delegation-drift",
                "--runs-root",
                str(runs_root),
            ],
        )
        assert aggregate_result.exit_code == 0, aggregate_result.output
        assert "depth sweep (5 depth(s))" in aggregate_result.output
        for depth in (2, 3, 4, 5, 6):
            assert f"depth {depth}:" in aggregate_result.output
        assert "no divergence/exclusion confound detected" in aggregate_result.output

    def test_missing_scenario_family_exits_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from chainbreak.cli.main import app

        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(app, ["analyze", "--aggregate"])
        assert result.exit_code == 2
        assert "--scenario-family is required" in result.output

    def test_no_matching_runs_exits_one(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from chainbreak.cli.main import app

        monkeypatch.chdir(tmp_path)
        (tmp_path / "runs").mkdir()
        result = CliRunner().invoke(
            app,
            [
                "analyze",
                "--aggregate",
                "--scenario-family",
                "no-such-family",
                "--runs-root",
                str(tmp_path / "runs"),
            ],
        )
        assert result.exit_code == 1
        assert "no runs" in result.output
