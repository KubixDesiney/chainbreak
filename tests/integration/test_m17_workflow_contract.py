"""M17 workflow contract: every negative control uses production orchestration."""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreak.analysis.pipeline import analyze
from chainbreak.core.enums import RunStatus
from chainbreak.core.models import SafetyEnvelope
from chainbreak.evidence.writer import BundleWriter
from chainbreak.execution.orchestrator import orchestrate
from chainbreak.providers.fake.adapter import FakeProviderAdapter
from chainbreak.providers.fake.probes import build_fake_preconditions
from chainbreak.providers.fake.session import virtual_ms_to_datetime
from chainbreak.scenarios.loader import load_and_compile

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
NEGATIVE_CONTROLS = sorted((REPO_ROOT / "scenarios" / "_negative-controls").glob("*.yaml"))


@pytest.mark.parametrize("scenario_path", NEGATIVE_CONTROLS, ids=lambda path: path.stem)
def test_negative_control_runs_through_production_orchestrator(
    scenario_path: Path, tmp_path: Path, synthetic_aws_registry
) -> None:
    run_id = scenario_path.stem + "-production"
    compiled = load_and_compile(scenario_path, registry=synthetic_aws_registry)
    # This adapter configuration represents the optional defective Terraform
    # role outputs; orchestration itself still follows the production path.
    adapter = FakeProviderAdapter(seed=17, negative_control_bindings=True)
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
            "family": scenario_path.parent.name,
            "api_version": "chainbreak.dev/v1alpha1",
            "compiled_hash": compiled.compiled_hash,
        },
        provenance={
            "chainbreak_version": "0.1.0a0",
            "capability_catalog_version": compiled.catalog_version,
            "provider": "fake",
            "provider_adapter_version": compiled.adapter_version,
            "python_version": "3.12",
            "config_fingerprint": "sha256:" + "2" * 64,
            "region": adapter.region,
            "seed": 17,
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
            seed=17,
            max_duration_seconds=600,
            now=lambda: virtual_ms_to_datetime(adapter.clock.now_ms),
        )

    assert result.status is RunStatus.COMPLETED
    analysis = analyze(tmp_path / run_id)
    assert analysis.detector_checks
    assert analysis.detector_checks[0].result == "DETECTOR_OK"
