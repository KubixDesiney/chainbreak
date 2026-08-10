"""M14 acceptance criteria: the silent-narrowing benchmark (Family E),
driven through the real ``execution/orchestrator.py``
(``execution/task_runner.py``, ``execution/side_effects.py``,
``analysis/task_contract.py``) rather than a hand-built bundle.

Setup mirrors ``test_stale_authority.py``'s own ``_run`` helper, which
itself mirrors ``test_revocation.py``'s -- the same orchestrator entry
point every family after M10 uses.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreak.analysis.pipeline import analyze
from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.enums import FindingType, RunStatus, TaskStatus
from chainbreak.core.models import CompiledScenario, SafetyEnvelope
from chainbreak.evidence.reader import read_events, read_observations
from chainbreak.evidence.writer import BundleWriter
from chainbreak.execution.orchestrator import OrchestrationResult, orchestrate
from chainbreak.providers.fake.adapter import FakeProviderAdapter
from chainbreak.providers.fake.probes import build_fake_preconditions
from chainbreak.providers.fake.session import virtual_ms_to_datetime
from chainbreak.scenarios.loader import load_and_compile

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
SILENT_NARROWING_DIR = REPO_ROOT / "scenarios" / "silent-narrowing"
NC_DIR = REPO_ROOT / "scenarios" / "_negative-controls"


def _run(
    scenario_path: Path,
    tmp_path: Path,
    registry: BindingRegistry,
    *,
    run_id: str,
    adapter: FakeProviderAdapter,
) -> tuple[Path, OrchestrationResult]:
    compiled: CompiledScenario = load_and_compile(scenario_path, registry=registry)
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
            "family": "silent-narrowing",
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
            seed=17,
            max_duration_seconds=600,
            now=lambda: virtual_ms_to_datetime(adapter.clock.now_ms),
        )
    return tmp_path / run_id, result


class TestPositiveControl:
    """F7: the same shape of task, with full authority and the honest
    worker, must report COMPLETE and its marker must exist."""

    PATH = SILENT_NARROWING_DIR / "two-step-pipeline-full-authority.yaml"

    def test_completes(self, tmp_path: Path, synthetic_aws_registry: BindingRegistry) -> None:
        adapter = FakeProviderAdapter(seed=17)
        _run_dir, result = _run(
            self.PATH, tmp_path, synthetic_aws_registry, run_id="run-positive", adapter=adapter
        )
        assert result.status is RunStatus.COMPLETED

    def test_task_outcome_complete_with_marker_verified(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        adapter = FakeProviderAdapter(seed=17)
        run_dir, _ = _run(
            self.PATH, tmp_path, synthetic_aws_registry, run_id="run-positive", adapter=adapter
        )
        events = list(read_events(run_dir))
        outcome_events = [e for e in events if e.get("kind") == "TASK_OUTCOME_RECORDED"]
        assert len(outcome_events) == 1
        outcome = outcome_events[0]["task_outcome"]
        assert outcome["status"] == TaskStatus.COMPLETE.value
        assert outcome["steps_succeeded"] == outcome["steps_total"]
        assert outcome["output_marker_written"] is True
        assert outcome["output_marker_verified_independently"] is True

    def test_no_silent_narrowing_finding(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        adapter = FakeProviderAdapter(seed=17)
        run_dir, _ = _run(
            self.PATH, tmp_path, synthetic_aws_registry, run_id="run-positive", adapter=adapter
        )
        result = analyze(run_dir)
        assert not any(f.type is FindingType.SILENT_NARROWING for f in result.findings)

    def test_task_execution_observations_excluded_from_generic_authority_findings(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        """Task-step invocations are tagged TASK_EXECUTION and must not
        double as generic per-node authority measurements (the same
        reasoning that already excludes POST_MUTATION/DEFERRED_EXECUTION)."""
        adapter = FakeProviderAdapter(seed=17)
        run_dir, _ = _run(
            self.PATH, tmp_path, synthetic_aws_registry, run_id="run-positive", adapter=adapter
        )
        observations = list(read_observations(run_dir))
        assert any(o.phase.value == "TASK_EXECUTION" for o in observations)
        result = analyze(run_dir)
        # Only the PROBE-phase matrix produces authority findings here.
        assert all(f.type is FindingType.EXPECTED_BEHAVIOR for f in result.findings)


class TestHonestWorkerInsufficientAuthorityFailsLoudly:
    """two-step-pipeline.yaml: EXPERIMENT_PROTOCOL.md section 5's own main
    procedure (steps 1-6) -- Agent B is deliberately delegated one
    capability short of what the task requires, and the *honest*
    deterministic.sequential worker runs it. The system must fail
    observably (PARTIAL, reported_insufficient_authority=True), which is
    EXPECTED_BEHAVIOR, never SILENT_NARROWING -- distinct from
    nc-silent-success.yaml, which pairs the same kind of shortfall with a
    *dishonest* worker instead."""

    PATH = SILENT_NARROWING_DIR / "two-step-pipeline.yaml"

    def test_completes(self, tmp_path: Path, synthetic_aws_registry: BindingRegistry) -> None:
        adapter = FakeProviderAdapter(seed=17)
        _run_dir, result = _run(
            self.PATH, tmp_path, synthetic_aws_registry, run_id="run-honest", adapter=adapter
        )
        assert result.status is RunStatus.COMPLETED

    def test_reports_partial_with_insufficient_authority(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        adapter = FakeProviderAdapter(seed=17)
        run_dir, _ = _run(
            self.PATH, tmp_path, synthetic_aws_registry, run_id="run-honest", adapter=adapter
        )
        events = list(read_events(run_dir))
        outcome = next(e for e in events if e.get("kind") == "TASK_OUTCOME_RECORDED")[
            "task_outcome"
        ]
        assert outcome["status"] == TaskStatus.PARTIAL.value
        assert outcome["steps_succeeded"] < outcome["steps_total"]
        assert outcome["reported_insufficient_authority"] is True
        assert outcome["output_marker_written"] is False

    def test_no_silent_narrowing_finding_failing_loudly_is_expected_behavior(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        adapter = FakeProviderAdapter(seed=17)
        run_dir, _ = _run(
            self.PATH, tmp_path, synthetic_aws_registry, run_id="run-honest", adapter=adapter
        )
        result = analyze(run_dir)
        assert not any(f.type is FindingType.SILENT_NARROWING for f in result.findings)


class TestNegativeControlEndToEnd:
    """AC2: nc-silent-success.yaml must yield SILENT_NARROWING at the
    declared confidence, driven through the real orchestrator."""

    PATH = NC_DIR / "nc-silent-success.yaml"

    def test_completes(self, tmp_path: Path, synthetic_aws_registry: BindingRegistry) -> None:
        adapter = FakeProviderAdapter(seed=17)
        _run_dir, result = _run(
            self.PATH, tmp_path, synthetic_aws_registry, run_id="run-nc", adapter=adapter
        )
        assert result.status is RunStatus.COMPLETED

    def test_silent_narrowing_detected_at_high_confidence(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        adapter = FakeProviderAdapter(seed=17)
        run_dir, _ = _run(
            self.PATH, tmp_path, synthetic_aws_registry, run_id="run-nc", adapter=adapter
        )
        result = analyze(run_dir)
        matches = {c.negative_control_id: c.result for c in result.detector_checks}
        assert matches["nc-silent-success"] == "DETECTOR_OK"
        finding = next(f for f in result.findings if f.type is FindingType.SILENT_NARROWING)
        from chainbreak.core.enums import Confidence

        assert finding.confidence is Confidence.HIGH

    def test_report_states_worker_is_synthetic(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        """AC5: every finding this family produces states that v0.1's
        worker is synthetic, so the family measures the harness rather
        than agent behavior (ADR-007) -- in the same finding, via its own
        caveats, ahead of M16's reporting layer."""
        adapter = FakeProviderAdapter(seed=17)
        run_dir, _ = _run(
            self.PATH, tmp_path, synthetic_aws_registry, run_id="run-nc", adapter=adapter
        )
        result = analyze(run_dir)
        finding = next(f for f in result.findings if f.type is FindingType.SILENT_NARROWING)
        assert any("synthetic" in caveat.lower() for caveat in finding.caveats)
