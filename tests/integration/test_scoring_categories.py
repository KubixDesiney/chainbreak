"""M15 acceptance criterion 1: all six category evaluators, driven through
the real ``execution/orchestrator.py`` against real fake-provider runs of
one scenario per family -- not hand-built ``Finding``/``CategoryResult``
objects (those live in ``tests/unit/test_scoring.py``).

Setup mirrors ``test_scope_attenuation.py``/``test_stale_authority.py``'s
own ``_run`` helper, the same orchestrator entry point every family after
M10 uses.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.enums import CategoryStatus, RunStatus
from chainbreak.core.models import CategoryResult, CompiledScenario, SafetyEnvelope
from chainbreak.evidence.writer import BundleWriter
from chainbreak.execution.orchestrator import OrchestrationResult, orchestrate
from chainbreak.providers.fake.adapter import FakeProviderAdapter
from chainbreak.providers.fake.probes import build_fake_preconditions
from chainbreak.providers.fake.session import virtual_ms_to_datetime
from chainbreak.scenarios.loader import load_and_compile
from chainbreak.scoring.categories import score_bundle

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = REPO_ROOT / "scenarios"


def _run(
    scenario_path: Path,
    tmp_path: Path,
    registry: BindingRegistry,
    *,
    run_id: str,
    family: str,
    seed: int,
) -> tuple[Path, OrchestrationResult]:
    compiled: CompiledScenario = load_and_compile(scenario_path, registry=registry)
    adapter = FakeProviderAdapter(seed=seed)
    envelope = SafetyEnvelope(
        allowed_account_ids=(adapter.account_ref,),
        allowed_regions=(adapter.region,),
        namespace=adapter.namespace,
        namespace_pattern=f"^{adapter.namespace}$",
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
        result = orchestrate(
            compiled,
            adapter,
            sink,
            build_fake_preconditions(adapter.markers),
            run_id=run_id,
            envelope=envelope,
            seed=seed,
            max_duration_seconds=900,
            now=lambda: virtual_ms_to_datetime(adapter.clock.now_ms),
        )
    return tmp_path / run_id, result


def _by_category(results: tuple[CategoryResult, ...]) -> dict[str, CategoryResult]:
    return {r.category.value: r for r in results}


class TestDelegationDriftScenarioExercisesGraphAxisCategories:
    """Delegation Integrity, Scope Attenuation and Credential Hygiene are
    measured and CONSISTENT on a clean multi-hop chain; the three families
    this scenario never touches stay NOT_MEASURED."""

    PATH = SCENARIOS / "delegation-drift" / "four-hop.yaml"

    def test_categories(self, tmp_path: Path, synthetic_aws_registry: BindingRegistry) -> None:
        run_dir, result = _run(
            self.PATH,
            tmp_path,
            synthetic_aws_registry,
            run_id="run-drift",
            family="delegation-drift",
            seed=29,
        )
        assert result.status is RunStatus.COMPLETED

        results = _by_category(score_bundle(run_dir))

        assert results["DELEGATION_INTEGRITY"].status is CategoryStatus.CONSISTENT
        assert results["DELEGATION_INTEGRITY"].coverage == pytest.approx(1.0)
        assert results["SCOPE_ATTENUATION"].status is CategoryStatus.CONSISTENT
        assert results["SCOPE_ATTENUATION"].coverage == pytest.approx(1.0)
        assert results["CREDENTIAL_HYGIENE"].status is CategoryStatus.CONSISTENT

        for category in (
            "REVOCATION_RESPONSIVENESS",
            "AUTHORITY_FRESHNESS",
            "FAILURE_TRANSPARENCY",
        ):
            assert results[category].status is CategoryStatus.NOT_MEASURED
            assert results[category].coverage == 0.0


class TestRevocationScenarioExercisesRevocationResponsiveness:
    PATH = SCENARIOS / "revocation" / "inline-deny.yaml"

    def test_categories(self, tmp_path: Path, synthetic_aws_registry: BindingRegistry) -> None:
        run_dir, result = _run(
            self.PATH,
            tmp_path,
            synthetic_aws_registry,
            run_id="run-revocation",
            family="revocation",
            seed=7,
        )
        assert result.status is RunStatus.COMPLETED

        results = _by_category(score_bundle(run_dir))

        revocation = results["REVOCATION_RESPONSIVENESS"]
        assert revocation.status is not CategoryStatus.NOT_MEASURED
        assert revocation.coverage > 0.0
        # The fake's own propagation model always eventually settles on a
        # denial for this scenario -- a genuine positive result, not a
        # tautology of the harness (AUTHORIZATION_MODEL.md section 5.1).
        assert revocation.status in (CategoryStatus.CONSISTENT, CategoryStatus.PARTIAL)


class TestStaleAuthorityScenarioExercisesAuthorityFreshness:
    PATH = SCENARIOS / "stale-authority" / "short-defer.yaml"

    def test_categories(self, tmp_path: Path, synthetic_aws_registry: BindingRegistry) -> None:
        run_dir, result = _run(
            self.PATH,
            tmp_path,
            synthetic_aws_registry,
            run_id="run-stale",
            family="stale-authority",
            seed=7,
        )
        assert result.status is RunStatus.COMPLETED

        results = _by_category(score_bundle(run_dir))

        freshness = results["AUTHORITY_FRESHNESS"]
        assert freshness.status is not CategoryStatus.NOT_MEASURED
        assert freshness.coverage == pytest.approx(1.0)
        # EXPIRED_CREDENTIAL_HONORED is the only outcome that would make
        # this DIVERGENT -- a correctly-behaving fake adapter never
        # produces it (see test_stale_authority.py's own docstring).
        assert freshness.status is CategoryStatus.CONSISTENT


class TestSilentNarrowingScenarioExercisesFailureTransparency:
    PATH = SCENARIOS / "silent-narrowing" / "two-step-pipeline.yaml"

    def test_categories(self, tmp_path: Path, synthetic_aws_registry: BindingRegistry) -> None:
        run_dir, result = _run(
            self.PATH,
            tmp_path,
            synthetic_aws_registry,
            run_id="run-silent-narrowing",
            family="silent-narrowing",
            seed=3,
        )
        assert result.status is RunStatus.COMPLETED

        results = _by_category(score_bundle(run_dir))

        transparency = results["FAILURE_TRANSPARENCY"]
        assert transparency.status is not CategoryStatus.NOT_MEASURED
        assert transparency.coverage == pytest.approx(1.0)
        assert any(
            "synthetic implementation of the TaskWorker Protocol" in caveat
            for caveat in transparency.caveats
        )
