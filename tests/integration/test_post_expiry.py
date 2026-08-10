"""M13 acceptance criterion 4: the post-expiry scenario (F7/H6) correctly
yields ``CREDENTIAL_EXPIRED`` -- a credential that has genuinely passed its
own ``expires_at``, with no policy mutation involved at all, must be
correctly denied and correctly attributed to expiry, never honored.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreak.analysis.pipeline import analyze
from chainbreak.analysis.stale import stale_authority_measurements
from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.enums import FindingType, OutcomeClass, RunStatus, StaleAuthorityClass
from chainbreak.core.models import CompiledScenario, SafetyEnvelope
from chainbreak.evidence.reader import read_credentials, read_events, read_observations
from chainbreak.evidence.writer import BundleWriter
from chainbreak.execution.orchestrator import orchestrate
from chainbreak.providers.fake.adapter import FakeProviderAdapter
from chainbreak.providers.fake.probes import build_fake_preconditions
from chainbreak.providers.fake.session import virtual_ms_to_datetime
from chainbreak.scenarios.loader import load_and_compile

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO = REPO_ROOT / "scenarios" / "stale-authority" / "post-expiry.yaml"


def _run(tmp_path: Path, registry: BindingRegistry) -> Path:
    adapter = FakeProviderAdapter(seed=13)
    compiled: CompiledScenario = load_and_compile(SCENARIO, registry=registry)
    envelope = SafetyEnvelope(
        allowed_account_ids=(adapter.account_ref,),
        allowed_regions=(adapter.region,),
        namespace=adapter.namespace,
        namespace_pattern=f"^{adapter.namespace}$",
    )
    run_id = "run-post-expiry"
    writer = BundleWriter(
        tmp_path,
        run_id,
        scenario_ref={
            "id": compiled.scenario_id,
            "version": compiled.scenario_version,
            "family": "stale-authority",
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
            seed=13,
            max_duration_seconds=900,
            now=lambda: virtual_ms_to_datetime(adapter.clock.now_ms),
        )
    assert result.status is RunStatus.COMPLETED
    return tmp_path / run_id


class TestPostExpiry:
    def test_deferred_probe_denied_with_credential_expired(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        run_dir = _run(tmp_path, synthetic_aws_registry)
        observations = list(read_observations(run_dir))
        deferred = [o for o in observations if o.phase.value == "DEFERRED_EXECUTION"]
        assert deferred
        for observation in deferred:
            assert observation.outcome.outcome_class.is_denial

    def test_classifies_credential_expired_for_every_probed_capability(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        run_dir = _run(tmp_path, synthetic_aws_registry)
        events = list(read_events(run_dir))
        observations = list(read_observations(run_dir))
        credentials = list(read_credentials(run_dir))
        measurements = stale_authority_measurements(events, observations, credentials)
        assert measurements
        for measurement in measurements:
            assert measurement.classification is StaleAuthorityClass.CREDENTIAL_EXPIRED
            assert measurement.credential_expired_at_execution is True

    def test_fresh_credential_still_works(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        """The expiry is specific to the pinned credential, not the
        identity: a freshly minted one is unaffected."""
        run_dir = _run(tmp_path, synthetic_aws_registry)
        observations = list(read_observations(run_dir))
        fresh = [o for o in observations if o.phase.value == "PAIRED_FRESH_CREDENTIAL"]
        assert fresh
        for observation in fresh:
            assert observation.outcome.outcome_class is OutcomeClass.ALLOWED

    def test_no_stale_authority_or_expired_credential_accepted_finding(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        """CREDENTIAL_EXPIRED is expected lifetime behavior (AUTHORIZATION_
        MODEL.md section 5.2) -- it produces no finding at all, unlike
        EXPIRED_CREDENTIAL_HONORED (the row that would)."""
        run_dir = _run(tmp_path, synthetic_aws_registry)
        result = analyze(run_dir)
        assert not any(f.type is FindingType.STALE_AUTHORITY for f in result.findings)
        assert not any(f.type is FindingType.EXPIRED_CREDENTIAL_ACCEPTED for f in result.findings)
