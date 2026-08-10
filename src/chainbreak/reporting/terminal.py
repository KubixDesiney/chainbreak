"""Terminal report (M16 F1), matching SCORING_MODEL.md section 4's report
shape exactly -- category rows with status/coverage/confidence, the literal
"NOT_MEASURED is not a pass." line, and (added here, beyond section 4's own
minimal example) the finding detail and limitations sections every format
must carry (F4, F5).

Built with ``rich`` rendered to plain text (``Console(record=True,
no_color=True)``) rather than printed directly, so the same function is
testable by string assertion and the CLI layer decides how the result
reaches the terminal (``typer.echo``), matching every other renderer in
this package returning a string rather than performing I/O itself.

Rendered in three independent buffers -- header/table/notice, findings,
limitations -- concatenated for the text this function returns, but linted
separately (see ``language.py::enforce_report``'s docstring for why
evidence-derived finding text gets a narrower bar than the report's own
authored prose).
"""

from __future__ import annotations

import io

from rich.console import Console
from rich.table import Table

from chainbreak.core.models import Interval
from chainbreak.reporting.data import ReportData
from chainbreak.reporting.format import LIMITATIONS, format_timing_result
from chainbreak.reporting.language import enforce_report

__all__ = ["render_terminal"]


def _console() -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    return Console(file=buffer, record=True, no_color=True, width=100), buffer


def _fake_provider_banner(data: ReportData) -> str | None:
    if not data.is_fake_provider:
        return None
    return (
        "*** provider: fake -- FAKE-PROVIDER APPARATUS CHECK. "
        "This is not a measurement of any real provider. ***"
    )


def _render_header(data: ReportData) -> str:
    console, _ = _console()
    adapter_version = data.provenance.get("provider_adapter_version")
    header = (
        f"CHAINBREAK -- run {data.run_id}\n"
        f"scenario {data.scenario.get('id')} v{data.scenario.get('version')}    "
        f"provider {data.provider.value} (adapter {adapter_version})"
    )
    banner = _fake_provider_banner(data)
    if banner is not None:
        header = f"{banner}\n{header}"
    console.print(header)
    console.print(f"status {data.status}    bundle_root_verified {data.bundle_root_verified}")
    if data.git_dirty:
        console.print("*** git_dirty: true -- this run's code state was not clean ***")
    if not data.bundle_root_verified:
        console.print("*** bundle_root_verified: false -- integrity check failed ***")

    table = Table(title="CATEGORY RESULTS", show_lines=False)
    table.add_column("category")
    table.add_column("status")
    table.add_column("coverage")
    table.add_column("confidence")
    for category in data.categories:
        if category.status.value == "NOT_MEASURED":
            table.add_row(category.category.value, category.status.value, "--", "--")
        else:
            table.add_row(
                category.category.value,
                category.status.value,
                f"{category.coverage:.2f}",
                category.confidence.value,
            )
    console.print(table)
    if data.not_measured_notice is not None:
        console.print(data.not_measured_notice)

    measurement_lines = [
        format_timing_result(
            f"revocation_window {m.identity_id}/{m.capability_id}",
            m.transition_window,
            n=m.poll_count,
            mechanism=m.mutation_kind.value,
        )
        for m in data.revocation_measurements
        if m.transition_window is not None
    ] + [
        format_timing_result(
            f"stale_window {m.identity_id}/{m.capability_id}",
            Interval(
                low=m.stale_window_seconds,
                point=m.stale_window_seconds,
                high=m.stale_window_seconds,
            ),
            n=1,
            mechanism=m.classification.value,
        )
        for m in data.stale_measurements
        if m.stale_window_seconds is not None
    ]
    if measurement_lines:
        console.print("\nMEASUREMENTS")
        for line in measurement_lines:
            console.print(f"  {line}")
    return console.export_text()


def _render_findings(data: ReportData) -> str:
    console, _ = _console()
    console.print("\nFINDINGS")
    if not data.findings:
        console.print("  none")
    for finding in data.findings:
        console.print(
            f"  [{finding.type.value}] {finding.severity_hint.value} "
            f"confidence={finding.confidence.value}"
        )
        console.print(f"    observation: {finding.observation}")
        console.print(f"    expected_state: {finding.expected_state}")
        console.print(f"    observed_state: {finding.observed_state}")
        console.print(f"    security_interpretation: {finding.security_interpretation}")
        if finding.caveats:
            console.print(f"    caveats: {'; '.join(finding.caveats)}")
    return console.export_text()


def _render_limitations() -> str:
    console, _ = _console()
    console.print("\nLIMITATIONS")
    for line in LIMITATIONS:
        console.print(f"  - {line}")
    return console.export_text()


def render_terminal(data: ReportData) -> str:
    header_text = _render_header(data)
    findings_text = _render_findings(data)
    limitations_text = _render_limitations()

    enforce_report(
        structural_text=header_text + limitations_text,
        finding_text=findings_text,
        has_not_measured=data.has_not_measured,
    )
    return header_text + findings_text + limitations_text
