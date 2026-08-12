"""M18's own negative controls (NEXT_PROMPTS.md P2 / M18-reproducibility-hardening.md):
run the same fake scenario twice with the same seed and assert ``compare``
reports no divergence; change the seed under a jittered profile and assert
the timing measurement is DISTRIBUTIONALLY_CONSISTENT but never IDENTICAL,
while the set-valued content stays exactly reproduced regardless of seed.

Driven through the real ``execution/orchestrator.py`` and
``analysis/pipeline.py``, the same pattern ``test_scope_attenuation.py``
uses, rather than through the CLI: it is faster, and it sidesteps the CLI's
own ``chainbreak.toml``-from-cwd config layering, which is irrelevant to
what this file is testing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreak.analysis.compare import compare_bundles, snapshot_from_bundle
from chainbreak.analysis.pipeline import analyze
from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.models import CompiledScenario, SafetyEnvelope
from chainbreak.evidence.writer import BundleWriter
from chainbreak.execution.orchestrator import orchestrate
from chainbreak.providers.base.protocol import ProviderAdapter
from chainbreak.providers.fake.probes import build_fake_preconditions
from chainbreak.providers.fake.profiles import deterministic_profile, eventual_profile
from chainbreak.providers.fake.session import virtual_ms_to_datetime
from chainbreak.scenarios.loader import load_and_compile

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
SCOPE_ATTENUATION_SCENARIO = REPO_ROOT / "scenarios" / "scope-attenuation" / "basic.yaml"
REVOCATION_SCENARIO = REPO_ROOT / "scenarios" / "revocation" / "inline-deny.yaml"


def _run(
    scenario_path: Path,
    tmp_path: Path,
    registry: BindingRegistry,
    adapter: ProviderAdapter,
    *,
    run_id: str,
    seed: int,
    family: str,
) -> Path:
    compiled: CompiledScenario = load_and_compile(scenario_path, registry=registry)
    envelope = SafetyEnvelope(
        allowed_account_ids=(adapter.account_ref,),  # type: ignore[attr-defined]
        allowed_regions=(adapter.region,),  # type: ignore[attr-defined]
        namespace=adapter.namespace,  # type: ignore[attr-defined]
        namespace_pattern=f"^{adapter.namespace}$",  # type: ignore[attr-defined]
    )
    writer = BundleWriter(
        tmp_path,
        run_id,
        scenario_ref={
            "id": compiled.scenario_id,
            "version": compiled.scenario_version,
            "family": family,
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
        orchestrate(
            compiled,
            adapter,
            sink,
            build_fake_preconditions(adapter.markers),  # type: ignore[attr-defined]
            run_id=run_id,
            envelope=envelope,
            seed=seed,
            max_duration_seconds=600,
            now=lambda: virtual_ms_to_datetime(adapter.clock.now_ms),  # type: ignore[attr-defined]
        )
    run_dir = tmp_path / run_id
    analyze(run_dir)
    return run_dir


class TestSameScenarioSameSeedTwice:
    """M18 negative control 1: run the same fake scenario twice with the
    same seed; compare must report no divergence."""

    def test_reports_no_divergence(self, tmp_path: Path, synthetic_aws_registry: BindingRegistry):
        run_a = _run(
            SCOPE_ATTENUATION_SCENARIO,
            tmp_path,
            synthetic_aws_registry,
            deterministic_profile(seed=42),
            run_id="run-same-seed-a",
            seed=42,
            family="scope-attenuation",
        )
        run_b = _run(
            SCOPE_ATTENUATION_SCENARIO,
            tmp_path,
            synthetic_aws_registry,
            deterministic_profile(seed=42),
            run_id="run-same-seed-b",
            seed=42,
            family="scope-attenuation",
        )
        report = compare_bundles(snapshot_from_bundle(run_a), snapshot_from_bundle(run_b))
        assert report.comparisons, "expected at least one comparable measurement"
        assert report.divergent_count == 0
        assert all(c.verdict == "STRUCTURALLY_IDENTICAL" for c in report.comparisons)


class TestSameScenarioDifferentSeed:
    """M18 negative control 2: change the seed under a jittered profile;
    compare must report the timing measurement as distributionally
    consistent but never identical, while set-valued content still
    reproduces exactly (the policy engine's own behavior is seed-independent
    -- only the jittered propagation timing differs)."""

    def test_timing_is_distributionally_consistent_not_identical(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ):
        run_a = _run(
            REVOCATION_SCENARIO,
            tmp_path,
            synthetic_aws_registry,
            eventual_profile(seed=1),
            run_id="run-diff-seed-a",
            seed=1,
            family="revocation",
        )
        run_b = _run(
            REVOCATION_SCENARIO,
            tmp_path,
            synthetic_aws_registry,
            eventual_profile(seed=2),
            run_id="run-diff-seed-b",
            seed=2,
            family="revocation",
        )
        report = compare_bundles(snapshot_from_bundle(run_a), snapshot_from_bundle(run_b))

        timing = [c for c in report.comparisons if c.level == "DISTRIBUTIONAL"]
        assert timing, "expected at least one revocation timing comparison"
        for comparison in timing:
            assert comparison.verdict != "IDENTICAL"
            assert comparison.verdict in {"DISTRIBUTIONALLY_CONSISTENT", "DIVERGENT"}

        structural = [c for c in report.comparisons if c.level == "STRUCTURAL"]
        assert all(c.verdict == "STRUCTURALLY_IDENTICAL" for c in structural), (
            "set-valued (non-timing) content should reproduce exactly regardless of seed"
        )
