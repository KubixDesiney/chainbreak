"""``reporting/terminal.py`` driven directly against hand-built
:class:`ReportData` (``test_report_generation.py`` covers the end-to-end
path through a real orchestrated bundle; this file's job is the branches a
delegation-drift run never exercises -- ``git_dirty``, an unsealed bundle,
an AWS-provider run with no fake-provider banner, revocation/stale
measurement lines, and an empty findings list).
"""

from __future__ import annotations

import pytest

from chainbreak.core.enums import (
    CategoryStatus,
    Confidence,
    MutationKind,
    Provider,
    ScoringCategory,
    StaleAuthorityClass,
)
from chainbreak.core.ids import CapabilityId, IdentityId
from chainbreak.core.models import (
    CategoryResult,
    Interval,
    RevocationMeasurement,
    StaleAuthorityMeasurement,
)
from chainbreak.reporting.data import ReportData
from chainbreak.reporting.terminal import render_terminal

pytestmark = pytest.mark.unit


def _category(status: CategoryStatus = CategoryStatus.CONSISTENT) -> CategoryResult:
    coverage = 0.0 if status is CategoryStatus.NOT_MEASURED else 1.0
    confidence = (
        Confidence.INSUFFICIENT if status is CategoryStatus.NOT_MEASURED else Confidence.HIGH
    )
    return CategoryResult(
        category=ScoringCategory.DELEGATION_INTEGRITY,
        status=status,
        coverage=coverage,
        confidence=confidence,
    )


def _base_data(**overrides: object) -> ReportData:
    defaults: dict[str, object] = {
        "run_id": "run-terminal-test",
        "status": "COMPLETED",
        "created_at": "2026-01-01T00:00:00Z",
        "completed_at": "2026-01-01T00:01:00Z",
        "scenario": {"id": "test-scenario", "version": "1.0.0"},
        "provenance": {"provider_adapter_version": "0.1.0"},
        "provider": Provider.FAKE,
        "git_dirty": False,
        "bundle_root_verified": True,
        "warnings": (),
        "findings": (),
        "detector_checks": (),
        "categories": (_category(),),
        "not_measured_notice": None,
        "figures": (),
        "revocation_measurements": (),
        "stale_measurements": (),
    }
    defaults.update(overrides)
    return ReportData(**defaults)  # type: ignore[arg-type]


class TestProviderBanner:
    def test_fake_provider_is_banner_stamped(self) -> None:
        text = render_terminal(_base_data(provider=Provider.FAKE))
        assert "FAKE-PROVIDER APPARATUS CHECK" in text

    def test_aws_provider_has_no_banner(self) -> None:
        text = render_terminal(_base_data(provider=Provider.AWS))
        assert "FAKE-PROVIDER APPARATUS CHECK" not in text


class TestGitDirtyAndIntegrity:
    def test_git_dirty_renders_prominently(self) -> None:
        text = render_terminal(_base_data(git_dirty=True))
        assert "git_dirty: true" in text

    def test_clean_git_state_has_no_warning(self) -> None:
        text = render_terminal(_base_data(git_dirty=False))
        assert "git_dirty: true" not in text

    def test_unverified_bundle_root_renders_prominently(self) -> None:
        text = render_terminal(_base_data(bundle_root_verified=False))
        assert "bundle_root_verified: false" in text

    def test_verified_bundle_root_has_no_warning(self) -> None:
        text = render_terminal(_base_data(bundle_root_verified=True))
        assert "integrity check failed" not in text


class TestFindingsSection:
    def test_no_findings_renders_none(self) -> None:
        text = render_terminal(_base_data(findings=()))
        assert "FINDINGS" in text
        assert "none" in text

    def test_a_finding_with_caveats_renders_them(self) -> None:
        from chainbreak.core.enums import Confidence, FindingType, SeverityHint
        from chainbreak.core.models import Finding

        finding = Finding(
            finding_id="finding-test-0001",
            type=FindingType.LIFETIME_CAPPED,
            severity_hint=SeverityHint.INFORMATIONAL,
            confidence=Confidence.HIGH,
            subject_kind="credential",
            observation="credential requested 3600s, granted 3600s",
            security_interpretation="Documented behavior, recorded as data.",
            caveats=("documented AWS chained-role-session behavior, not a defect",),
        )
        text = render_terminal(_base_data(findings=(finding,)))
        assert "caveats: documented AWS chained-role-session behavior" in text


class TestNotMeasuredCategory:
    def test_not_measured_category_shows_dashes(self) -> None:
        data = _base_data(
            categories=(_category(CategoryStatus.NOT_MEASURED),),
            not_measured_notice="NOT_MEASURED is not a pass. 1 of 1 category was not exercised "
            "by this scenario.",
        )
        text = render_terminal(data)
        assert "NOT_MEASURED" in text
        assert "NOT_MEASURED is not a pass." in text


class TestMeasurementsSection:
    def test_revocation_and_stale_measurements_render_with_n_interval_mechanism(self) -> None:
        revocation = RevocationMeasurement(
            identity_id=IdentityId("agent-b"),
            capability_id=CapabilityId("objectstore.read"),
            mutation_kind=MutationKind.ATTACH_INLINE_DENY,
            transition_window=Interval(low=2.0, point=2.25, high=2.5),
            transition_observed=True,
            poll_interval_ms=100,
            poll_count=10,
            window_length_s=5.0,
            mutation_receipt_confirmed=True,
        )
        stale = StaleAuthorityMeasurement(
            identity_id=IdentityId("agent-a"),
            capability_id=CapabilityId("objectstore.read"),
            classification=StaleAuthorityClass.STALE_AUTHORITY_LIVE_CREDENTIAL,
            deferral_seconds=5.0,
            stale_window_seconds=3.2,
            credential_expired_at_execution=False,
        )
        data = _base_data(revocation_measurements=(revocation,), stale_measurements=(stale,))
        text = render_terminal(data)
        assert "MEASUREMENTS" in text
        assert "n=10, mechanism=ATTACH_INLINE_DENY" in text
        assert "n=1, mechanism=STALE_AUTHORITY_LIVE_CREDENTIAL" in text

    def test_no_measurements_section_when_there_are_none(self) -> None:
        text = render_terminal(_base_data())
        assert "MEASUREMENTS" not in text
