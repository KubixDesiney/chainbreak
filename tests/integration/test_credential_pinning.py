"""M13 acceptance criterion 2: credential pinning verified from the
**evidence stream** (the deferred observation's ``credential_id``), never
from the code path -- a refactor of ``execution/deferred.py`` or
``providers/fake/adapter.py`` must not be able to silently break this while
the test still passes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.enums import RunStatus
from chainbreak.core.models import CompiledScenario, SafetyEnvelope
from chainbreak.evidence.reader import read_credentials, read_observations
from chainbreak.evidence.writer import BundleWriter
from chainbreak.execution.orchestrator import orchestrate
from chainbreak.providers.fake.adapter import FakeProviderAdapter
from chainbreak.providers.fake.probes import build_fake_preconditions
from chainbreak.providers.fake.session import virtual_ms_to_datetime
from chainbreak.scenarios.loader import load_and_compile

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO = REPO_ROOT / "scenarios" / "stale-authority" / "short-defer.yaml"


def _run(tmp_path: Path, registry: BindingRegistry) -> Path:
    adapter = FakeProviderAdapter(seed=13)
    compiled: CompiledScenario = load_and_compile(SCENARIO, registry=registry)
    envelope = SafetyEnvelope(
        allowed_account_ids=(adapter.account_ref,),
        allowed_regions=(adapter.region,),
        namespace=adapter.namespace,
        namespace_pattern=f"^{adapter.namespace}$",
    )
    run_id = "run-pinning"
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


class TestCredentialPinningVerifiedFromEvidence:
    def test_deferred_observation_uses_the_after_delegation_credential(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        run_dir = _run(tmp_path, synthetic_aws_registry)
        observations = list(read_observations(run_dir))
        credentials = {c.credential_id: c for c in read_credentials(run_dir)}

        after_delegation = [o for o in observations if o.phase.value == "POST_DELEGATION"]
        assert after_delegation, "after-delegation phase produced no observations"
        pinned_credential_id = after_delegation[0].credential_id
        assert pinned_credential_id is not None
        assert pinned_credential_id in credentials

        deferred = [o for o in observations if o.phase.value == "DEFERRED_EXECUTION"]
        assert deferred, "DEFERRED_EXECUTION phase produced no observations"
        for observation in deferred:
            assert observation.credential_id == pinned_credential_id, (
                "F1: the deferred probe must use exactly the credential minted at the "
                "referenced phase, not a refreshed one"
            )

    def test_paired_fresh_observation_uses_a_different_credential(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        run_dir = _run(tmp_path, synthetic_aws_registry)
        observations = list(read_observations(run_dir))
        credentials = {c.credential_id: c for c in read_credentials(run_dir)}

        deferred_credential_id = next(
            o.credential_id for o in observations if o.phase.value == "DEFERRED_EXECUTION"
        )
        fresh = [o for o in observations if o.phase.value == "PAIRED_FRESH_CREDENTIAL"]
        assert fresh, "PAIRED_FRESH_CREDENTIAL phase produced no observations"
        for observation in fresh:
            assert observation.credential_id is not None
            assert observation.credential_id != deferred_credential_id, (
                "F3: the paired probe must use a freshly minted credential, never the pinned one"
            )
            assert observation.credential_id in credentials

    def test_pinned_and_fresh_credentials_were_both_recorded_for_the_same_identity(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        run_dir = _run(tmp_path, synthetic_aws_registry)
        credentials = [c for c in read_credentials(run_dir) if c.identity_id == "agent-c"]
        assert len(credentials) == 2, (
            "agent-c should have exactly two recorded credentials: the one minted at "
            "after-delegation, and the freshly minted paired one"
        )
        assert credentials[0].credential_id != credentials[1].credential_id
        assert credentials[0].issued_at < credentials[1].issued_at
