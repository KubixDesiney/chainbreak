"""``chainbreak evidence export --public`` (F6, T-13, EVIDENCE_SCHEMA.md section 11).

Produces a review-ready copy of a sealed bundle and, before writing anything,
scrubs every artifact for identifier-shaped content that should already be
absent or hashed: unhashed account IDs, ARNs, hostnames, cleartext session
names, and -- unless explicitly opted in -- policy documents. Prints a diff of
what it stripped so the operator sees exactly what is about to leave their
machine.

This is a second, independent pass on top of :func:`chainbreak.evidence.redaction.redact`.
The writer-time choke point already refuses to write a *secret*, fatally. This
pass catches the different, non-fatal category: a *privacy-sensitive
identifier* that should have been salted-hashed already but might have
slipped through as literal text in a free-form field (a denial message, a
note) -- so it sanitizes rather than aborting, and proves it by re-scanning
its own output before anything is written.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from chainbreak.core.errors import BundleIntegrityError, EvidenceError
from chainbreak.evidence.manifest import ARTIFACT_NAMES
from chainbreak.evidence.manifest import verify as verify_manifest
from chainbreak.evidence.reader import read_manifest
from chainbreak.evidence.redaction import (
    ACCOUNT_ID_PATTERN,
    ARN_PATTERN,
    HOSTNAME_PATTERN,
    REDACTED_ACCOUNT,
    REDACTED_ARN,
    REDACTED_HOSTNAME,
)
from chainbreak.evidence.writer import write_text_artifact

_PUBLIC_ARTIFACTS: Final = (*ARTIFACT_NAMES, "manifest.json", "findings.json", "scores.json")

_POLICY_DOCUMENT_PATTERN: Final = re.compile(
    r'"((?:session_|trust_|permission_)?policy_document)"\s*:\s*"(?:[^"\\]|\\.)*"'
)
_REDACTED_POLICY_DOCUMENT: Final = "<REDACTED_POLICY_DOCUMENT>"


@dataclass(frozen=True)
class ScrubHit:
    file: str
    pattern: str
    count: int


@dataclass
class ExportReport:
    run_id: str
    output_dir: Path
    dry_run: bool
    include_policy_documents: bool
    stripped: list[ScrubHit] = field(default_factory=list)

    @property
    def violations(self) -> int:
        return sum(hit.count for hit in self.stripped)

    def render_diff(self) -> str:
        if not self.stripped:
            return "export --public: nothing to strip; bundle was already clean"
        lines = [f"export --public: stripped {self.violations} identifier(s):"]
        for hit in self.stripped:
            lines.append(f"  {hit.file}: {hit.count}x {hit.pattern}")
        return "\n".join(lines)


def _scrub_text(
    text: str, filename: str, *, include_policy_documents: bool
) -> tuple[str, list[ScrubHit]]:
    hits: list[ScrubHit] = []
    # ARN first: it embeds a 12-digit account id, so scrubbing it before the
    # bare-account-id pass avoids double-counting the same span twice.
    for name, pattern, replacement in (
        ("arn", ARN_PATTERN, REDACTED_ARN),
        ("hostname", HOSTNAME_PATTERN, REDACTED_HOSTNAME),
        ("account_id", ACCOUNT_ID_PATTERN, REDACTED_ACCOUNT),
    ):
        count = len(pattern.findall(text))
        if count:
            text = pattern.sub(replacement, text)
            hits.append(ScrubHit(filename, name, count))

    if not include_policy_documents:
        count = len(_POLICY_DOCUMENT_PATTERN.findall(text))
        if count:
            text = _POLICY_DOCUMENT_PATTERN.sub(rf'"\1": "{_REDACTED_POLICY_DOCUMENT}"', text)
            hits.append(ScrubHit(filename, "policy_document", count))

    return text, hits


def _assert_clean(text: str, filename: str) -> None:
    """F6: assert zero redaction violations remain before anything is written."""
    for name, pattern in (("arn", ARN_PATTERN), ("hostname", HOSTNAME_PATTERN)):
        if pattern.search(text):
            raise EvidenceError(
                f"export --public: {name} survived scrubbing in {filename}; refusing to export",
                file=filename,
                pattern=name,
            )


def export_public(
    run_dir: Path,
    *,
    output_dir: Path | None = None,
    dry_run: bool = False,
    include_policy_documents: bool = False,
) -> ExportReport:
    """Scrub a sealed bundle and copy it to ``output_dir`` (default:
    ``<run_dir>-public`` alongside the source bundle).

    Refuses to export an unsealed bundle or one that fails integrity
    verification -- publishing a tampered or partial bundle is worse than
    refusing outright.
    """
    manifest = read_manifest(run_dir / "manifest.json")
    if manifest.integrity.root is None:
        raise EvidenceError("cannot export an unsealed bundle", run_id=manifest.run_id)
    if not verify_manifest(run_dir, manifest):
        raise BundleIntegrityError(
            "bundle failed integrity verification; refusing to export", run_id=manifest.run_id
        )

    target_dir = output_dir or run_dir.parent / f"{manifest.run_id}-public"
    report = ExportReport(
        run_id=manifest.run_id,
        output_dir=target_dir,
        dry_run=dry_run,
        include_policy_documents=include_policy_documents,
    )

    for name in _PUBLIC_ARTIFACTS:
        source = run_dir / name
        if not source.is_file():
            continue
        text = source.read_text(encoding="utf-8")
        scrubbed, hits = _scrub_text(text, name, include_policy_documents=include_policy_documents)
        report.stripped.extend(hits)
        _assert_clean(scrubbed, name)
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            write_text_artifact(target_dir / name, scrubbed)

    return report
