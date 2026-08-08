"""Bounded, streaming, schema-validated ingest of a possibly-untrusted bundle (T-10).

A bundle received from someone else is untrusted input by construction --
this is the read path the reader-side half of threat T-10 (malicious or
malformed evidence input) is written against. Every entry point here:

* bounds the bytes it will read before parsing anything,
* parses with ``json.loads`` only -- never ``eval``, never a dynamic import,
* validates structure with the same Pydantic domain models the writer used,
  so a hostile field name or type is a validation error, not a crash, and
* streams ``.jsonl`` files line by line with a per-line cap, so a bundle with
  one absurd line cannot exhaust memory before the size check on that line
  even runs.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError

from chainbreak.core.errors import EvidenceError
from chainbreak.core.models import CredentialRecord, Observation, PolicyStateSnapshot
from chainbreak.evidence.manifest import Manifest

#: A single JSONL line (one observation, one event, ...) beyond this is
#: rejected before ``json.loads`` ever sees it.
MAX_LINE_BYTES: Final = 1 << 20  # 1 MiB

#: A single-document JSON artifact (manifest.json, graph.json, scenario.json,
#: environment.json, findings.json) beyond this is rejected outright.
MAX_JSON_DOCUMENT_BYTES: Final = 8 << 20  # 8 MiB


def _read_bounded(path: Path, *, max_bytes: int) -> str:
    if not path.is_file():
        raise EvidenceError(f"{path.name} does not exist", path=str(path))
    size = path.stat().st_size
    if size > max_bytes:
        raise EvidenceError(
            f"{path.name} exceeds {max_bytes} bytes ({size} bytes)", path=str(path), size=size
        )
    return path.read_text(encoding="utf-8")


def _load_json_document(path: Path, *, max_bytes: int = MAX_JSON_DOCUMENT_BYTES) -> Any:
    text = _read_bounded(path, max_bytes=max_bytes)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"{path.name}: invalid JSON: {exc}", path=str(path)) from exc


def read_manifest(path: Path) -> Manifest:
    document = _load_json_document(path)
    try:
        return Manifest.model_validate(document)
    except ValidationError as exc:
        raise EvidenceError(f"{path.name}: does not conform to Manifest", path=str(path)) from exc


def read_findings(path: Path) -> dict[str, Any]:
    """Structural validation only: each finding/detector-check entry is
    revalidated against the domain models that produced it, so a hostile or
    corrupted bundle fails closed rather than being trusted verbatim."""
    from chainbreak.core.models import DetectorCheck, Finding

    document = _load_json_document(path)
    if not isinstance(document, dict):
        raise EvidenceError(f"{path.name}: expected a JSON object", path=str(path))
    for entry in document.get("findings", []):
        try:
            Finding.model_validate(entry)
        except ValidationError as exc:
            raise EvidenceError(
                f"{path.name}: invalid finding entry: {exc}", path=str(path)
            ) from exc
    for entry in document.get("detector_checks", []):
        try:
            DetectorCheck.model_validate(
                {
                    "negative_control_id": entry.get(
                        "negative_control", entry.get("negative_control_id")
                    ),
                    "expected_type": entry["expected"]
                    if "expected" in entry
                    else entry.get("expected_type"),
                    "produced": entry["produced"],
                    "result": entry["result"],
                }
            )
        except (ValidationError, KeyError) as exc:
            raise EvidenceError(
                f"{path.name}: invalid detector_check entry: {exc}", path=str(path)
            ) from exc
    return document


def _stream_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if not path.is_file():
        return
    with path.open("r", encoding="utf-8") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            line = raw_line.rstrip("\n")
            if not line:
                continue
            if len(line.encode("utf-8")) > MAX_LINE_BYTES:
                raise EvidenceError(
                    f"{path.name}:{line_number} exceeds {MAX_LINE_BYTES} bytes",
                    path=str(path),
                    line=line_number,
                )
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvidenceError(
                    f"{path.name}:{line_number}: invalid JSON: {exc}",
                    path=str(path),
                    line=line_number,
                ) from exc


def read_observations(run_dir: Path) -> Iterator[Observation]:
    for record in _stream_jsonl(run_dir / "observations.jsonl"):
        try:
            yield Observation.model_validate(record)
        except ValidationError as exc:
            raise EvidenceError(f"observations.jsonl: invalid record: {exc}") from exc


def read_events(run_dir: Path) -> Iterator[dict[str, Any]]:
    """Events have no dedicated domain model (execution/orchestration is M10+);
    bounded streaming JSON parsing is the full extent of validation available
    today."""
    yield from _stream_jsonl(run_dir / "events.jsonl")


def read_policy_states(run_dir: Path) -> Iterator[PolicyStateSnapshot]:
    for record in _stream_jsonl(run_dir / "policy_states.jsonl"):
        try:
            yield PolicyStateSnapshot.model_validate(record)
        except ValidationError as exc:
            raise EvidenceError(f"policy_states.jsonl: invalid record: {exc}") from exc


def read_credentials(run_dir: Path) -> Iterator[CredentialRecord]:
    for record in _stream_jsonl(run_dir / "credentials.jsonl"):
        try:
            yield CredentialRecord.model_validate(record)
        except ValidationError as exc:
            raise EvidenceError(f"credentials.jsonl: invalid record: {exc}") from exc


def verify_integrity(run_dir: Path) -> bool:
    """Recompute the sealed root and compare. See ``evidence.manifest.verify``."""
    from chainbreak.evidence.manifest import verify as verify_manifest

    manifest = read_manifest(run_dir / "manifest.json")
    return verify_manifest(run_dir, manifest)
