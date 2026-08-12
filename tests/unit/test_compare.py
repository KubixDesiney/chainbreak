"""``analysis/compare.py`` direct tests (M18 F1-F3)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from chainbreak.analysis.compare import (
    RunSnapshot,
    compare_bundles,
    snapshot_from_bundle,
)
from chainbreak.core.enums import Confidence, FindingType, MutationKind, SeverityHint
from chainbreak.core.errors import HeterogeneousComparisonError
from chainbreak.core.models import Finding, Interval, RevocationMeasurement

pytestmark = pytest.mark.unit

_DEFAULT_VERSION_KEY = {
    "compiled_hash": "sha256:" + "a" * 64,
    "adapter_version": "0.1.0",
    "catalog_version": "1.0.0",
}


def _finding(
    *,
    finding_id: str,
    type: FindingType = FindingType.AUTHORITY_EXPANSION,  # noqa: A002
    identity_id: str = "agent-a",
    observation: str = "agent-a returned ALLOWED for objectstore.read in all trials",
    observation_refs: tuple[str, ...] = (),
) -> Finding:
    from chainbreak.core.models import FindingEvidence

    return Finding(
        finding_id=finding_id,
        type=type,
        severity_hint=SeverityHint.REVIEW,
        confidence=Confidence.HIGH,
        subject_kind="identity",
        identity_id=identity_id,
        observation=observation,
        expected_state={"capabilities": ["objectstore.write"]},
        observed_state={"capabilities": ["objectstore.read", "objectstore.write"]},
        delta={"unexpected_gain": ["objectstore.read"], "unexpected_loss": []},
        evidence=FindingEvidence(observation_refs=observation_refs),
    )


def _revocation(
    *,
    identity_id: str = "agent-a",
    capability_id: str = "objectstore.read",
    low: float = 30.0,
    high: float = 40.0,
    transition_observed: bool = True,
) -> RevocationMeasurement:
    window = Interval.from_bounds(low, high) if transition_observed else None
    return RevocationMeasurement(
        identity_id=identity_id,
        capability_id=capability_id,
        mutation_kind=MutationKind.ATTACH_INLINE_DENY,
        transition_window=window,
        transition_observed=transition_observed,
        poll_interval_ms=500,
        poll_count=10,
        window_length_s=high if transition_observed else 5.0,
        mutation_receipt_confirmed=True,
    )


def _snapshot(
    run_id: str,
    *,
    findings: tuple[Finding, ...] = (),
    revocation_measurements: tuple[RevocationMeasurement, ...] = (),
    infrastructure_fingerprint: str | None = None,
    **version_overrides: str,
) -> RunSnapshot:
    version = {**_DEFAULT_VERSION_KEY, **version_overrides}
    return RunSnapshot(
        run_id=run_id,
        findings=findings,
        revocation_measurements=revocation_measurements,
        infrastructure_fingerprint=infrastructure_fingerprint,
        **version,
    )


class TestSetValuedComparison:
    def test_matching_content_with_different_run_specific_ids_is_structurally_identical(self):
        # Same logical finding, different runs: finding_id and observation_refs
        # differ (both are salted/derived per run, ADR-013) but everything
        # about WHAT was measured is identical.
        run_a = _snapshot(
            "run-a",
            findings=(_finding(finding_id="fnd_aaa", observation_refs=("obs_1", "obs_2")),),
        )
        run_b = _snapshot(
            "run-b",
            findings=(_finding(finding_id="fnd_bbb", observation_refs=("obs_9", "obs_8")),),
        )
        report = compare_bundles(run_a, run_b)
        assert len(report.comparisons) == 1
        assert report.comparisons[0].verdict == "STRUCTURALLY_IDENTICAL"
        assert report.comparisons[0].level == "STRUCTURAL"
        assert report.divergent_count == 0

    def test_self_comparison_reports_identical_not_structurally_identical(self):
        findings = (_finding(finding_id="fnd_aaa", observation_refs=("obs_1",)),)
        run_a = _snapshot("run-a", findings=findings)
        run_a_again = _snapshot("run-a", findings=findings)
        report = compare_bundles(run_a, run_a_again)
        assert report.comparisons[0].verdict == "IDENTICAL"

    def test_content_difference_is_divergent_not_an_exception(self):
        run_a = _snapshot(
            "run-a", findings=(_finding(finding_id="fnd_aaa", identity_id="agent-a"),)
        )
        run_b = _snapshot(
            "run-b", findings=(_finding(finding_id="fnd_bbb", identity_id="agent-b"),)
        )
        report = compare_bundles(run_a, run_b)
        # Each run's finding has no exact match in the other -> two DIVERGENT entries.
        assert report.divergent_count == 2
        assert all(c.verdict == "DIVERGENT" for c in report.comparisons)

    def test_finding_present_only_in_one_run_is_divergent(self):
        run_a = _snapshot("run-a", findings=(_finding(finding_id="fnd_aaa"),))
        run_b = _snapshot("run-b", findings=())
        report = compare_bundles(run_a, run_b)
        assert len(report.comparisons) == 1
        assert report.comparisons[0].verdict == "DIVERGENT"
        assert "run A" in report.comparisons[0].detail

    def test_no_findings_in_either_run_compares_cleanly(self):
        report = compare_bundles(_snapshot("run-a"), _snapshot("run-b"))
        assert report.comparisons == ()
        assert report.divergent_count == 0


class TestRevocationComparison:
    def test_overlapping_windows_are_distributionally_consistent(self):
        run_a = _snapshot("run-a", revocation_measurements=(_revocation(low=30.0, high=40.0),))
        run_b = _snapshot("run-b", revocation_measurements=(_revocation(low=35.0, high=45.0),))
        report = compare_bundles(run_a, run_b)
        assert len(report.comparisons) == 1
        assert report.comparisons[0].verdict == "DISTRIBUTIONALLY_CONSISTENT"
        assert report.comparisons[0].level == "DISTRIBUTIONAL"

    def test_overlapping_windows_never_report_identical_across_different_runs(self):
        """REPRODUCIBILITY.md section 1: timing across two different runs is never
        claimed exact, even when the bounds happen to coincide bit-for-bit."""
        run_a = _snapshot("run-a", revocation_measurements=(_revocation(low=30.0, high=40.0),))
        run_b = _snapshot("run-b", revocation_measurements=(_revocation(low=30.0, high=40.0),))
        report = compare_bundles(run_a, run_b)
        assert report.comparisons[0].verdict == "DISTRIBUTIONALLY_CONSISTENT"

    def test_non_overlapping_windows_are_divergent(self):
        run_a = _snapshot("run-a", revocation_measurements=(_revocation(low=10.0, high=20.0),))
        run_b = _snapshot("run-b", revocation_measurements=(_revocation(low=100.0, high=110.0),))
        report = compare_bundles(run_a, run_b)
        assert report.comparisons[0].verdict == "DIVERGENT"

    def test_self_comparison_of_timing_is_identical(self):
        measurements = (_revocation(low=30.0, high=40.0),)
        run_a = _snapshot("run-a", revocation_measurements=measurements)
        run_a_again = _snapshot("run-a", revocation_measurements=measurements)
        report = compare_bundles(run_a, run_a_again)
        assert report.comparisons[0].verdict == "IDENTICAL"

    def test_no_transition_observed_on_both_sides_matches(self):
        run_a = _snapshot(
            "run-a", revocation_measurements=(_revocation(transition_observed=False),)
        )
        run_b = _snapshot(
            "run-b", revocation_measurements=(_revocation(transition_observed=False),)
        )
        report = compare_bundles(run_a, run_b)
        assert report.comparisons[0].verdict == "STRUCTURALLY_IDENTICAL" or (
            report.comparisons[0].verdict == "DISTRIBUTIONALLY_CONSISTENT"
        )

    def test_transition_observed_mismatch_is_divergent(self):
        run_a = _snapshot("run-a", revocation_measurements=(_revocation(transition_observed=True),))
        run_b = _snapshot(
            "run-b", revocation_measurements=(_revocation(transition_observed=False),)
        )
        report = compare_bundles(run_a, run_b)
        assert report.comparisons[0].verdict == "DIVERGENT"

    def test_polled_in_one_run_only_is_divergent(self):
        run_a = _snapshot("run-a", revocation_measurements=(_revocation(),))
        run_b = _snapshot("run-b", revocation_measurements=())
        report = compare_bundles(run_a, run_b)
        assert report.comparisons[0].verdict == "DIVERGENT"

    def test_revocation_delay_and_no_transition_findings_excluded_from_set_valued_pass(self):
        """These two finding types are timing-derived; including them in the
        generic Finding comparison would double-count against the dedicated
        RevocationMeasurement comparison above and could report a spurious
        DIVERGENT purely from differing observation text across two runs."""
        finding_a = _finding(
            finding_id="fnd_a", type=FindingType.NO_TRANSITION_OBSERVED, observation="window A"
        )
        finding_b = _finding(
            finding_id="fnd_b", type=FindingType.NO_TRANSITION_OBSERVED, observation="window B"
        )
        run_a = _snapshot("run-a", findings=(finding_a,))
        run_b = _snapshot("run-b", findings=(finding_b,))
        report = compare_bundles(run_a, run_b)
        assert report.comparisons == ()


class TestHeterogeneousRefusal:
    def test_differing_compiled_hash_refused_by_default(self):
        run_a = _snapshot("run-a")
        run_b = _snapshot("run-b", compiled_hash="sha256:" + "b" * 64)
        with pytest.raises(HeterogeneousComparisonError):
            compare_bundles(run_a, run_b)

    def test_differing_adapter_version_refused_by_default(self):
        run_a = _snapshot("run-a")
        run_b = _snapshot("run-b", adapter_version="9.9.9")
        with pytest.raises(HeterogeneousComparisonError):
            compare_bundles(run_a, run_b)

    def test_differing_catalog_version_refused_by_default(self):
        run_a = _snapshot("run-a")
        run_b = _snapshot("run-b", catalog_version="9.9.9")
        with pytest.raises(HeterogeneousComparisonError):
            compare_bundles(run_a, run_b)

    def test_allow_heterogeneous_lets_it_through_and_marks_the_result(self):
        run_a = _snapshot("run-a")
        run_b = _snapshot("run-b", catalog_version="9.9.9")
        report = compare_bundles(run_a, run_b, allow_heterogeneous=True)
        assert report.heterogeneous is True
        assert any("HETEROGENEOUS" in note for note in report.notes)

    def test_allow_heterogeneous_never_upgrades_a_divergent_verdict(self):
        run_a = _snapshot("run-a", findings=(_finding(finding_id="fnd_a", identity_id="agent-a"),))
        run_b = _snapshot(
            "run-b",
            catalog_version="9.9.9",
            findings=(_finding(finding_id="fnd_b", identity_id="agent-b"),),
        )
        report = compare_bundles(run_a, run_b, allow_heterogeneous=True)
        assert report.divergent_count == 2


class TestEnvironmentGate:
    def test_differing_infrastructure_fingerprint_refused_by_default(self):
        run_a = _snapshot("run-a", infrastructure_fingerprint="sha256:" + "1" * 64)
        run_b = _snapshot("run-b", infrastructure_fingerprint="sha256:" + "2" * 64)
        with pytest.raises(HeterogeneousComparisonError):
            compare_bundles(run_a, run_b)

    def test_cross_operator_relaxes_the_environment_check(self):
        run_a = _snapshot("run-a", infrastructure_fingerprint="sha256:" + "1" * 64)
        run_b = _snapshot("run-b", infrastructure_fingerprint="sha256:" + "2" * 64)
        report = compare_bundles(run_a, run_b, cross_operator=True)
        assert report.cross_operator is True
        assert any("UNVERIFIED" in note for note in report.notes)

    def test_missing_fingerprint_on_either_side_does_not_trigger_the_gate(self):
        """Fake-provider runs never set infrastructure_fingerprint at all --
        there is no infrastructure. Nothing to compare is not a mismatch."""
        run_a = _snapshot("run-a", infrastructure_fingerprint=None)
        run_b = _snapshot("run-b", infrastructure_fingerprint="sha256:" + "1" * 64)
        report = compare_bundles(run_a, run_b)
        assert report.heterogeneous is False


class TestSnapshotFromBundle:
    def test_missing_findings_json_raises_a_clear_error(self, tmp_path: Path):
        from chainbreak.core.errors import EvidenceError
        from chainbreak.evidence.manifest import Manifest
        from chainbreak.evidence.writer import write_text_artifact

        run_dir = tmp_path / "run-a"
        run_dir.mkdir()
        manifest = Manifest(
            run_id="run-a",
            created_at="2026-08-11T00:00:00.000000Z",
            status="COMPLETED",
            scenario={"id": "scn_test", "compiled_hash": "sha256:" + "a" * 64},
            provenance={"provider_adapter_version": "0.1.0", "capability_catalog_version": "1.0.0"},
        )
        write_text_artifact(run_dir / "manifest.json", manifest.model_dump_json())

        with pytest.raises(EvidenceError, match=r"findings\.json"):
            snapshot_from_bundle(run_dir)


class TestCompareCli:
    def test_missing_run_ids_exits_two(self):
        from chainbreak.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["compare"])
        assert result.exit_code == 2
        assert result.exception is None or isinstance(result.exception, SystemExit)

    def test_unknown_run_exits_one_with_a_clear_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from chainbreak.cli.main import app

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(app, ["compare", "no-such-run-a", "no-such-run-b"])
        assert result.exit_code == 1
        assert "chainbreak compare:" in result.output
