"""M16 acceptance criteria, driven through the real
``execution/orchestrator.py`` the same way ``test_scope_attenuation.py``
(M10) does -- a real fake-provider bundle, not a hand-built fixture, for
every criterion except the XSS negative control (criterion 3), which
constructs a :class:`ReportData` directly so a specific hostile string can
be placed in ``security_interpretation`` without depending on which finding
rule happens to produce free text today.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from chainbreak.capabilities.registry import BindingRegistry
from chainbreak.core.enums import (
    CategoryStatus,
    Confidence,
    FindingType,
    Provider,
    ScoringCategory,
    SeverityHint,
)
from chainbreak.core.models import CategoryResult, CompiledScenario, Finding, SafetyEnvelope
from chainbreak.evidence.writer import BundleWriter
from chainbreak.execution.orchestrator import orchestrate
from chainbreak.providers.fake.probes import build_fake_preconditions
from chainbreak.providers.fake.profiles import deterministic_profile
from chainbreak.providers.fake.session import virtual_ms_to_datetime
from chainbreak.reporting.data import ReportData, gather_report_data
from chainbreak.reporting.html import render_html
from chainbreak.reporting.language import LIMITATIONS_TERMS, NOT_MEASURED_SENTENCE
from chainbreak.reporting.markdown import render_markdown
from chainbreak.reporting.terminal import render_terminal
from chainbreak.scenarios.loader import load_and_compile

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO = REPO_ROOT / "scenarios" / "delegation-drift" / "four-hop.yaml"


def _run_bundle(tmp_path: Path, registry: BindingRegistry, *, run_id: str, seed: int = 29) -> Path:
    compiled: CompiledScenario = load_and_compile(SCENARIO, registry=registry)
    adapter = deterministic_profile(seed=seed)
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
        orchestrate(
            compiled,
            adapter,
            sink,
            build_fake_preconditions(adapter.markers),
            run_id=run_id,
            envelope=envelope,
            seed=seed,
            max_duration_seconds=600,
            now=lambda: virtual_ms_to_datetime(adapter.clock.now_ms),
        )
    return tmp_path / run_id


@pytest.fixture
def report_data(tmp_path: Path, synthetic_aws_registry: BindingRegistry) -> ReportData:
    run_dir = _run_bundle(tmp_path, synthetic_aws_registry, run_id="run-report-1")
    return gather_report_data(run_dir)


class TestAllThreeFormatsRender:
    """Acceptance criterion 1."""

    def test_terminal(self, report_data: ReportData) -> None:
        text = render_terminal(report_data)
        assert report_data.run_id in text
        assert "CATEGORY RESULTS" in text

    def test_markdown(self, report_data: ReportData) -> None:
        text = render_markdown(report_data)
        assert report_data.run_id in text
        assert "## Category results" in text

    def test_html(self, report_data: ReportData) -> None:
        text = render_html(report_data)
        assert report_data.run_id in text
        assert "<html" in text


class TestFakeProviderStamp:
    """Acceptance criterion 4: stamped in the header and every figure caption."""

    def test_terminal_header_is_stamped(self, report_data: ReportData) -> None:
        text = render_terminal(report_data)
        assert "FAKE-PROVIDER APPARATUS CHECK" in text

    def test_html_header_and_every_caption_is_stamped(self, report_data: ReportData) -> None:
        text = render_html(report_data)
        assert text.count("FAKE-PROVIDER APPARATUS CHECK") >= 1 + len(report_data.figures)
        for figure in report_data.figures:
            assert "FAKE-PROVIDER APPARATUS CHECK" in figure.caption


class TestLimitationsSection:
    """Acceptance criterion 5: present in every format."""

    @pytest.mark.parametrize("render", [render_terminal, render_markdown, render_html])
    def test_all_five_limitation_terms_present(self, report_data: ReportData, render) -> None:
        text = render(report_data).lower()
        for term in LIMITATIONS_TERMS:
            assert term in text


class TestNotMeasuredNotice:
    def test_literal_sentence_present_when_a_category_is_not_measured(
        self, report_data: ReportData
    ) -> None:
        assert report_data.has_not_measured  # delegation-drift exercises 3 of 6 categories
        text = render_terminal(report_data)
        assert NOT_MEASURED_SENTENCE in text


class TestXssEscaping:
    """Acceptance criterion 3 / M16's own negative control: a bundle whose
    ``security_interpretation`` contains ``<script>`` renders escaped."""

    def _hostile_data(self) -> ReportData:
        hostile = Finding(
            finding_id="finding-hostile-0001",
            type=FindingType.EXPECTED_BEHAVIOR,
            severity_hint=SeverityHint.INFORMATIONAL,
            confidence=Confidence.HIGH,
            subject_kind="identity",
            observation="synthetic finding for the XSS negative control",
            security_interpretation="<script>alert('xss')</script>",
        )
        category = CategoryResult(
            category=ScoringCategory.DELEGATION_INTEGRITY,
            status=CategoryStatus.CONSISTENT,
            coverage=1.0,
            confidence=Confidence.HIGH,
        )
        return ReportData(
            run_id="run-hostile",
            status="COMPLETED",
            created_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:01:00Z",
            scenario={"id": "hostile-scenario", "version": "1.0.0"},
            provenance={"provider_adapter_version": "0.1.0"},
            provider=Provider.FAKE,
            git_dirty=False,
            bundle_root_verified=True,
            warnings=(),
            findings=(hostile,),
            detector_checks=(),
            categories=(category,),
            not_measured_notice=None,
            figures=(),
            revocation_measurements=(),
            stale_measurements=(),
        )

    def test_script_tag_is_escaped_in_html(self) -> None:
        text = render_html(self._hostile_data())
        assert "<script>alert" not in text
        assert "&lt;script&gt;" in text

    def test_terminal_and_markdown_are_unaffected_by_html_escaping_concerns(self) -> None:
        # Not an XSS surface, but must not crash and must still carry the
        # forbidden-phrase bar findings get (there is none planted here).
        data = self._hostile_data()
        render_terminal(data)
        render_markdown(data)


class TestHtmlNonFunctionalRequirements:
    def test_under_2mb_and_under_3_seconds(self, report_data: ReportData) -> None:
        start = time.monotonic()
        text = render_html(report_data)
        elapsed = time.monotonic() - start
        assert len(text.encode("utf-8")) < 2 * 1024 * 1024
        assert elapsed < 3.0
