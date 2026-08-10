"""C-1 (RESEARCH_METHODOLOGY.md section 4; M10 acceptance criterion 3):
``identity.whoami`` calibrates every matrix, and its failure is an apparatus
fault -- discarded, never reported as a wave of denials.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.enums import OutcomeClass, PlanPhase, RunStatus
from chainbreak.core.errors import ControlCapabilityFailedError
from chainbreak.core.models import SafetyEnvelope
from chainbreak.evidence.writer import BundleWriter
from chainbreak.execution import delegation
from chainbreak.execution.control import calibrate_matrix
from chainbreak.execution.orchestrator import orchestrate
from chainbreak.providers.fake.adapter import FakeProviderAdapter
from chainbreak.providers.fake.probes import build_fake_preconditions
from chainbreak.providers.fake.session import virtual_ms_to_datetime
from chainbreak.scenarios.loader import load_and_compile

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
BASIC_SCENARIO = REPO_ROOT / "scenarios" / "scope-attenuation" / "basic.yaml"


class TestCalibrateMatrixUnit:
    def test_succeeds_and_returns_one_observation_per_control_capability(
        self, synthetic_aws_registry: BindingRegistry
    ) -> None:
        from chainbreak.capabilities.loader import load_catalog

        adapter = FakeProviderAdapter(seed=1)
        ref = adapter.register_identity("principal")
        catalog = load_catalog()

        observations = calibrate_matrix(
            adapter,
            catalog,
            ref=ref,
            identity_id="principal",
            run_id="run-cal-1",
            phase=PlanPhase.BASELINE,
            matrix_id="pm-cal",
            sequence=0,
            credential=None,
            now=datetime.now(UTC),
            salt="test-salt:",
            namespace=adapter.namespace,
        )
        assert len(observations) == len(catalog.controls())
        assert all(o.outcome.outcome_class is OutcomeClass.ALLOWED for o in observations)

    def test_raises_control_capability_failed_when_whoami_is_not_allowed(
        self, synthetic_aws_registry: BindingRegistry
    ) -> None:
        from chainbreak.capabilities.loader import load_catalog

        # Every call, including identity.whoami's own, is thrown as a
        # transient fault from the very first probe -- the fake's own
        # documented way to make even the control capability fail without
        # needing a real IAM misconfiguration.
        adapter = FakeProviderAdapter(seed=1, throttle_after_n_calls=0)
        ref = adapter.register_identity("principal")
        catalog = load_catalog()

        with pytest.raises(ControlCapabilityFailedError) as excinfo:
            calibrate_matrix(
                adapter,
                catalog,
                ref=ref,
                identity_id="principal",
                run_id="run-cal-2",
                phase=PlanPhase.BASELINE,
                matrix_id="pm-cal-fail",
                sequence=0,
                credential=None,
                now=datetime.now(UTC),
                salt="test-salt:",
                namespace=adapter.namespace,
            )
        assert excinfo.value.context["identity_id"] == "principal"
        assert excinfo.value.context["matrix_id"] == "pm-cal-fail"


class TestOrchestratorDiscardsTheWholeMatrix:
    """Acceptance criterion 3, at the orchestrator level: a broken control
    capability discards the whole matrix rather than reporting the other
    capabilities' outcomes as if they were real denials."""

    def test_a_throttled_apparatus_discards_every_matrix_not_just_one_identity(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        compiled = load_and_compile(BASIC_SCENARIO, registry=synthetic_aws_registry)
        adapter = FakeProviderAdapter(seed=1, throttle_after_n_calls=0)

        envelope = SafetyEnvelope(
            allowed_account_ids=(adapter.account_ref,),
            allowed_regions=(adapter.region,),
            namespace=adapter.namespace,
            namespace_pattern=f"^{adapter.namespace}$",
        )
        writer = BundleWriter(
            tmp_path,
            "run-discard-1",
            scenario_ref={
                "id": compiled.scenario_id,
                "version": compiled.scenario_version,
                "family": "scope-attenuation",
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
                run_id="run-discard-1",
                envelope=envelope,
                seed=1,
                max_duration_seconds=600,
                # Virtual clock, not real wall time -- see cli/run.py's
                # identical fix and test_scope_attenuation.py's note.
                now=lambda: virtual_ms_to_datetime(adapter.clock.now_ms),
            )

        # The run still completes -- discarding a matrix is not a run-level
        # abort, it is a recorded, visible exclusion.
        assert result.status is RunStatus.COMPLETED
        assert len(result.discarded_matrices) == len(compiled.probe_matrices)
        for discarded in result.discarded_matrices:
            assert "control capability" in discarded.reason

        run_dir = tmp_path / "run-discard-1"
        events_path = run_dir / "events.jsonl"
        import json

        with events_path.open(encoding="utf-8") as handle:
            events = [json.loads(line) for line in handle if line.strip()]
        assert any(e["kind"] == "MATRIX_DISCARDED" for e in events)

        # The discarded matrices' capabilities never appear as observations
        # at all -- never mind as denials.
        observations_path = run_dir / "observations.jsonl"
        with observations_path.open(encoding="utf-8") as handle:
            observations = [json.loads(line) for line in handle if line.strip()]
        assert observations == []


class TestDelegationEstimatorIsUnaffected:
    """Sanity check that `delegation.needs_redelegation` doesn't accidentally
    fire during a normal, fresh-credential control-capability test above --
    protects against a false-positive re-delegation masking the discard."""

    def test_fresh_credential_never_needs_redelegation(self) -> None:
        from datetime import timedelta

        from chainbreak.core.enums import DelegationMechanism
        from chainbreak.core.ids import digest_ref
        from chainbreak.core.models import CredentialRecord

        now = datetime.now(UTC)
        credential = CredentialRecord(
            credential_id="cred_1",
            identity_id="agent-a",
            mechanism=DelegationMechanism.ROLE_CHAIN,
            issued_at=now,
            expires_at=now + timedelta(hours=1),
            requested_duration_s=3600,
            granted_duration_s=3600,
            session_name_hash=digest_ref("session", "salt:"),
            access_key_id_hash=digest_ref("key", "salt:"),
        )
        assert not delegation.needs_redelegation(
            credential, now=now, estimated_matrix_duration_s=1.0
        )
