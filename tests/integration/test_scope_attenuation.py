"""M10 acceptance criteria: the scope-attenuation benchmark, driven through
the real ``execution/orchestrator.py`` rather than the M10-standing-in
``tests/fixtures/mini_orchestrator.py``.

Negative-control defects are injected the same way
``tests/integration/test_negative_controls.py`` already does for the fake
provider -- ``PolicyEngine.register_identity``/``apply_allow`` -- since
there is no machine-readable defect-injection instruction in a scenario's
own YAML (a real AWS run would need the corresponding Terraform-provisioned
role instead, out of scope until M17). Here the defect must be seeded
*before* ``orchestrate()`` runs (it drives delegation internally, with no
extension point mid-run): pre-registering the target identity with its
normal intended capabilities *plus* the defect makes
``FakeProviderAdapter.delegate``'s own "register only if not already
registered" guard preserve it, which is semantically equivalent to
``test_negative_controls.py``'s post-hoc ``apply_allow`` call.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

from chainbreak.analysis.pipeline import analyze
from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.enums import RunStatus
from chainbreak.core.models import AuthoritySet, CompiledScenario, SafetyEnvelope
from chainbreak.evidence.writer import BundleWriter
from chainbreak.execution.orchestrator import OrchestrationResult, orchestrate
from chainbreak.providers.fake.probes import build_fake_preconditions
from chainbreak.providers.fake.profiles import deterministic_profile
from chainbreak.providers.fake.session import virtual_ms_to_datetime
from chainbreak.scenarios.loader import load_and_compile

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
NC_DIR = REPO_ROOT / "scenarios" / "_negative-controls"
BASIC_SCENARIO = REPO_ROOT / "scenarios" / "scope-attenuation" / "basic.yaml"


def _run(
    scenario_path: Path,
    tmp_path: Path,
    registry: BindingRegistry,
    *,
    run_id: str,
    seed: int = 11,
    inject_defect: tuple[str, str] | None = None,
) -> tuple[Path, OrchestrationResult]:
    compiled: CompiledScenario = load_and_compile(scenario_path, registry=registry)
    adapter = deterministic_profile(seed=seed)

    if inject_defect is not None:
        identity_id, extra_capability = inject_defect
        edge = next(e for e in compiled.graph.edges if e.target_id == identity_id)
        adapter.engine.register_identity(
            identity_id, allow=edge.intended_capabilities | AuthoritySet.of(extra_capability)
        )

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
            run_id=run_id,
            envelope=envelope,
            seed=seed,
            max_duration_seconds=600,
            # The fake's CredentialRecord timestamps live on its own virtual
            # clock (an arbitrary fixed epoch), not real wall time -- F6's
            # remaining-lifetime check must be measured against that same
            # virtual "now" (see cli/run.py's identical fix).
            now=lambda: virtual_ms_to_datetime(adapter.clock.now_ms),
        )
    return tmp_path / run_id, result


def _events(run_dir: Path) -> Iterable[dict[str, object]]:
    import json

    events_path = run_dir / "events.jsonl"
    if not events_path.is_file():
        return []
    with events_path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class TestBasicScenario:
    """Acceptance criterion 1: runs end to end and produces a sealed bundle
    plus findings; correct attenuation must not produce AUTHORITY_EXPANSION."""

    def test_runs_end_to_end_and_produces_a_sealed_bundle(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        run_dir, result = _run(
            BASIC_SCENARIO, tmp_path, synthetic_aws_registry, run_id="run-basic-1"
        )

        assert result.status is RunStatus.COMPLETED
        assert result.discarded_matrices == ()
        assert (run_dir / "manifest.json").is_file()
        assert (run_dir / "observations.jsonl").is_file()

        analysis = analyze(run_dir)
        assert analysis.bundle_root_verified is True
        assert analysis.findings
        assert all(f.type.value != "AUTHORITY_EXPANSION" for f in analysis.findings)

    def test_probe_order_seed_is_recorded_and_replaying_it_reproduces_the_order(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        """Acceptance criterion 4."""
        run_dir_a, _ = _run(
            BASIC_SCENARIO, tmp_path, synthetic_aws_registry, run_id="run-seed-a", seed=42
        )
        run_dir_b, _ = _run(
            BASIC_SCENARIO, tmp_path, synthetic_aws_registry, run_id="run-seed-b", seed=42
        )
        run_dir_c, _ = _run(
            BASIC_SCENARIO, tmp_path, synthetic_aws_registry, run_id="run-seed-c", seed=7
        )

        def _orders(run_dir: Path) -> list[tuple[object, object]]:
            return [
                (event["seed"], tuple(event["capability_order"]))
                for event in _events(run_dir)
                if event["kind"] == "PROBE_ORDER_SHUFFLED"
            ]

        orders_a = _orders(run_dir_a)
        orders_b = _orders(run_dir_b)
        orders_c = _orders(run_dir_c)

        assert orders_a  # the scenario has at least one identity row to shuffle
        assert orders_a == orders_b  # same seed -> byte-identical recorded order
        assert orders_a != orders_c  # different seed -> different order


class TestScopeExpansionThroughTheRealOrchestrator:
    PATH = NC_DIR / "nc-scope-expansion.yaml"

    def test_defect_present_is_detected(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        run_dir, result = _run(
            self.PATH,
            tmp_path,
            synthetic_aws_registry,
            run_id="run-nc-scope-1",
            inject_defect=("agent-b", "keyvalue.read"),
        )
        assert result.status is RunStatus.COMPLETED
        analysis = analyze(run_dir)
        checks = {c.negative_control_id: c.result for c in analysis.detector_checks}
        assert checks["nc-scope-expansion"] == "DETECTOR_OK"

    def test_defect_fixed_is_a_detector_failure(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        run_dir, _ = _run(self.PATH, tmp_path, synthetic_aws_registry, run_id="run-nc-scope-2")
        analysis = analyze(run_dir)
        checks = {c.negative_control_id: c.result for c in analysis.detector_checks}
        assert checks["nc-scope-expansion"] == "DETECTOR_FAILURE"


class TestSurvivingAuthorityThroughTheRealOrchestrator:
    """The important negative control (M10-scope-attenuation.md): it fails
    if divergence is computed only at node level, since a node's derived
    expectation can coincide with the observed set while the *edge*'s intent
    was violated."""

    PATH = NC_DIR / "nc-surviving-authority.yaml"

    def test_defect_present_is_detected(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        run_dir, result = _run(
            self.PATH,
            tmp_path,
            synthetic_aws_registry,
            run_id="run-nc-surv-1",
            inject_defect=("agent-b", "function.invoke"),
        )
        assert result.status is RunStatus.COMPLETED
        analysis = analyze(run_dir)
        checks = {c.negative_control_id: c.result for c in analysis.detector_checks}
        assert checks["nc-surviving-authority"] == "DETECTOR_OK"

    def test_defect_fixed_is_a_detector_failure(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        run_dir, _ = _run(self.PATH, tmp_path, synthetic_aws_registry, run_id="run-nc-surv-2")
        analysis = analyze(run_dir)
        checks = {c.negative_control_id: c.result for c in analysis.detector_checks}
        assert checks["nc-surviving-authority"] == "DETECTOR_FAILURE"


class TestFakeProviderAdapterType:
    def test_fake_adapter_satisfies_the_provider_adapter_protocol(self) -> None:
        from chainbreak.providers.base.protocol import ProviderAdapter

        assert isinstance(deterministic_profile(seed=1), ProviderAdapter)
