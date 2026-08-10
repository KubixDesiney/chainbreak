"""M11 acceptance criteria: the delegation-drift benchmark, driven through
the real ``execution/orchestrator.py`` (via ``execution/chain.py``) rather
than ``tests/fixtures/mini_orchestrator.py``.

Defects are injected the same way ``test_scope_attenuation.py`` and
``test_negative_controls.py`` already do for the fake provider: pre-register
an identity with its normal intended capabilities *plus* the defect,
before ``orchestrate()`` runs (it drives delegation internally with no
extension point mid-run) -- ``FakeProviderAdapter.delegate``'s own "register
only if not already registered" guard then preserves it.

Every identity-policy-level injection test below uses
``role-chain-five-hop.yaml``, not the depth-sweep scenarios
(``two``/``three``/``four``/``five``/``six-hop.yaml``): a session-policy-
scoped hop's effective authority is intersected with *that hop's own
declared* ``intended_capabilities`` (PROV-1 -- a session can only narrow,
never grant), so an excess capability injected into a downstream identity's
policy is silently narrowed away the moment it crosses a
``ROLE_CHAIN_WITH_SESSION_POLICY`` hop, no matter what that identity's own
policy says. This is correct behavior, not a bug -- it is the exact
mechanism nc-scope-expansion.yaml's own docstring explains -- and it is why
``role-chain-five-hop.yaml`` uses plain ``ROLE_CHAIN`` throughout instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreak.analysis.pipeline import analyze
from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.enums import DriftClass, FindingType, RunStatus
from chainbreak.core.models import AuthoritySet, CompiledScenario, SafetyEnvelope
from chainbreak.evidence.writer import BundleWriter
from chainbreak.execution.orchestrator import orchestrate
from chainbreak.providers.fake.adapter import FakeProviderAdapter
from chainbreak.providers.fake.probes import build_fake_preconditions
from chainbreak.providers.fake.profiles import deterministic_profile
from chainbreak.providers.fake.session import virtual_ms_to_datetime
from chainbreak.scenarios.loader import load_and_compile

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIFT_DIR = REPO_ROOT / "scenarios" / "delegation-drift"
NC_DIR = REPO_ROOT / "scenarios" / "_negative-controls"
ROLE_CHAIN_FIVE_HOP = DRIFT_DIR / "role-chain-five-hop.yaml"


def _run(
    scenario_path: Path,
    tmp_path: Path,
    registry: BindingRegistry,
    *,
    run_id: str,
    seed: int = 23,
    inject_defects: tuple[tuple[str, str], ...] = (),
):
    compiled: CompiledScenario = load_and_compile(scenario_path, registry=registry)
    adapter: FakeProviderAdapter = deterministic_profile(seed=seed)

    for identity_id, extra_capability in inject_defects:
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
    return tmp_path / run_id, result


class TestWorkedExampleEndToEnd:
    """AUTHORIZATION_MODEL.md section 7's worked example (hop N originates,
    hop N+1 propagates), reproduced through a real compile -> orchestrate ->
    analyze pass, not only the hand-built graph `test_divergence.py` already
    covers. `role-chain-five-hop.yaml`'s hop-3/hop-4 play the worked
    example's own agent-c/agent-d roles."""

    def test_hop_3_originates_hop_4_propagates_with_citation(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        run_dir, result = _run(
            ROLE_CHAIN_FIVE_HOP,
            tmp_path,
            synthetic_aws_registry,
            run_id="run-worked-example",
            inject_defects=(
                ("agent-c", "keyvalue.write"),
                ("agent-d", "keyvalue.write"),
            ),
        )
        assert result.status is RunStatus.COMPLETED

        analysis = analyze(run_dir)
        by_identity_and_type = {(f.identity_id, f.type): f for f in analysis.findings}

        expansion = by_identity_and_type[("agent-c", FindingType.AUTHORITY_EXPANSION)]
        assert "keyvalue.write" in expansion.delta["unexpected_gain"]

        origin_drift = by_identity_and_type[("agent-c", FindingType.DELEGATION_DRIFT)]
        assert origin_drift.drift_class is DriftClass.ORIGINATED
        assert expansion.finding_id not in origin_drift.security_interpretation

        propagated_drift = by_identity_and_type[("agent-d", FindingType.DELEGATION_DRIFT)]
        assert propagated_drift.drift_class is DriftClass.PROPAGATED
        assert expansion.finding_id in propagated_drift.security_interpretation

        # agent-d must not ALSO get its own AUTHORITY_EXPANSION -- the rule's
        # own predicate excludes PROPAGATED, matching the worked example's
        # "one AUTHORITY_EXPANSION, two DELEGATION_DRIFT findings" shape.
        assert ("agent-d", FindingType.AUTHORITY_EXPANSION) not in by_identity_and_type

        after_delegation_paths = analysis.path_analyses["POST_DELEGATION"]
        path = next(p for p in after_delegation_paths if p.path[-1] == "agent-e")
        assert path.first_divergence is not None
        assert path.first_divergence.hop_index == 3
        assert path.first_divergence.identity_id == "agent-c"

    def test_hop_4_corrects_hop_3s_gain(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        """The case a naive implementation gets wrong: hop 3 gains a
        capability, hop 4 does not carry it forward. Must classify
        CORRECTED and raise no finding at all for hop 4 -- reporting this
        as a failure would flag working defense-in-depth as a problem."""
        run_dir, result = _run(
            ROLE_CHAIN_FIVE_HOP,
            tmp_path,
            synthetic_aws_registry,
            run_id="run-corrected",
            inject_defects=(("agent-c", "keyvalue.write"),),
        )
        assert result.status is RunStatus.COMPLETED

        analysis = analyze(run_dir)
        by_identity_and_type = {(f.identity_id, f.type): f for f in analysis.findings}

        assert (
            by_identity_and_type[("agent-c", FindingType.DELEGATION_DRIFT)].drift_class
            is DriftClass.ORIGINATED
        )
        assert ("agent-d", FindingType.DELEGATION_DRIFT) not in by_identity_and_type
        assert ("agent-d", FindingType.AUTHORITY_EXPANSION) not in by_identity_and_type


class TestCitationSurvivesMultiplePropagatedHops:
    """The gap M11 found and fixed in `analysis/pipeline.py`: citation must
    survive more than one propagated hop past the origin, not only the
    origin's immediate child (the only case a 2-propagated-hop scenario can
    exercise)."""

    def test_citation_reaches_the_third_hop_past_the_origin(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        # agent-b (hop 2) originates; agent-c, agent-d, agent-e (hops 3-5)
        # all carry the same excess capability forward unchanged, so
        # agent-e's citation is three propagated hops past the origin.
        defect_identities = ("agent-b", "agent-c", "agent-d", "agent-e")
        run_dir, result = _run(
            ROLE_CHAIN_FIVE_HOP,
            tmp_path,
            synthetic_aws_registry,
            run_id="run-deep-propagation",
            inject_defects=tuple((identity, "keyvalue.write") for identity in defect_identities),
        )
        assert result.status is RunStatus.COMPLETED

        analysis = analyze(run_dir)
        by_identity_and_type = {(f.identity_id, f.type): f for f in analysis.findings}

        origin = by_identity_and_type[("agent-b", FindingType.AUTHORITY_EXPANSION)]
        for identity_id in ("agent-c", "agent-d", "agent-e"):
            drift = by_identity_and_type[(identity_id, FindingType.DELEGATION_DRIFT)]
            assert drift.drift_class is DriftClass.PROPAGATED, identity_id
            assert origin.finding_id in drift.security_interpretation, (
                f"{identity_id}'s citation was lost -- expected {origin.finding_id!r} in "
                f"{drift.security_interpretation!r}"
            )


class TestPathAnalysisWiredEndToEnd:
    """Acceptance criterion 3: first divergence is reported per root-to-leaf
    path in real analysis output, not only computed by `graph/paths.py` and
    left unwired (the gap M11 found and fixed in `analysis/pipeline.py`).
    Branching-graph correctness itself (independent divergence per branch)
    is already proven at the unit level by
    `test_paths.py`/`test_first_divergence.py`, which construct branching
    graphs directly; no scenario in this corpus branches, so this test's
    job is proving the *wiring* through a real run, on the one path a
    linear chain has."""

    def test_first_divergence_reaches_analysis_output_through_a_real_run(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        run_dir, result = _run(
            ROLE_CHAIN_FIVE_HOP,
            tmp_path,
            synthetic_aws_registry,
            run_id="run-path-analysis",
            inject_defects=(("agent-c", "keyvalue.write"),),
        )
        assert result.status is RunStatus.COMPLETED

        analysis = analyze(run_dir)
        paths = analysis.path_analyses["POST_DELEGATION"]
        assert len(paths) == 1
        path = paths[0]
        assert path.first_divergence is not None
        assert path.first_divergence.identity_id == "agent-c"
        assert path.first_divergence.hop_index == 3
        assert path.attenuation_monotone_set is False


class TestNonMonotoneChainNegativeControl:
    PATH = NC_DIR / "nc-non-monotone-chain.yaml"

    def test_defect_present_is_detected(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        run_dir, result = _run(
            self.PATH,
            tmp_path,
            synthetic_aws_registry,
            run_id="run-nc-nonmono-1",
            inject_defects=(("agent-c", "keyvalue.write"),),
        )
        assert result.status is RunStatus.COMPLETED
        analysis = analyze(run_dir)
        checks = {c.negative_control_id: c.result for c in analysis.detector_checks}
        assert checks["nc-non-monotone-chain"] == "DETECTOR_OK"

    def test_defect_fixed_is_a_detector_failure(
        self, tmp_path: Path, synthetic_aws_registry: BindingRegistry
    ) -> None:
        run_dir, _ = _run(self.PATH, tmp_path, synthetic_aws_registry, run_id="run-nc-nonmono-2")
        analysis = analyze(run_dir)
        checks = {c.negative_control_id: c.result for c in analysis.detector_checks}
        assert checks["nc-non-monotone-chain"] == "DETECTOR_FAILURE"
