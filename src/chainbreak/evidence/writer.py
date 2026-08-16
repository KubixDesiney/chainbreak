"""Evidence bundle writer (EVIDENCE_SCHEMA.md section 1; F1, F2, F3).

``.jsonl`` streams are append-only and flushed per record, so a process killed
mid-run still leaves a usable partial bundle (F2) -- a crash is a data point,
not data loss. Every record passes through :func:`chainbreak.evidence.redaction.redact`
before a byte of it reaches disk (S1); this is the *only* module in
``evidence/`` allowed to open a file for writing (S1's lint rule -- see
``tests/unit/test_redaction.py::test_no_unsafe_file_writes_outside_writer``).
"""

from __future__ import annotations

import io
import json
import tarfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import IO, Any, Literal, Self

from chainbreak.core import canonical
from chainbreak.core.errors import EvidenceError
from chainbreak.core.models import CredentialRecord, Observation, PolicyStateSnapshot
from chainbreak.evidence.manifest import CountsSection, Manifest, seal
from chainbreak.evidence.redaction import redact

_JSONL_ARTIFACTS: tuple[str, ...] = (
    "observations.jsonl",
    "events.jsonl",
    "policy_states.jsonl",
    "credentials.jsonl",
)


def write_text_artifact(path: Path, text: str) -> None:
    """The one place outside a live run's own streams that touches a
    filesystem write (S1's lint rule -- see
    ``tests/unit/test_redaction.py::test_no_unsafe_file_writes_outside_writer``).
    ``evidence/export.py`` calls this rather than opening a file itself, so
    every evidence-bundle write in the package funnels through this module.

    ``newline=""`` disables Python's universal-newline translation, which
    would otherwise write ``\\r\\n`` on Windows and silently desync the
    written bytes from what got hashed and sealed on a Windows development
    machine versus what a Linux CI runner checks out from git (git's own
    ``core.autocrlf`` normalizes line endings in the *stored blob*, not in a
    freshly-written working-tree file) -- REPRODUCIBILITY.md requires evidence
    bytes to be platform-independent, not just the values they encode.
    """
    path.write_text(text, encoding="utf-8", newline="")


def write_bytes_artifact(path: Path, data: bytes) -> None:
    """Binary counterpart to :func:`write_text_artifact`, for the non-JSON
    artifacts ``evidence/archive.py`` copies verbatim (the capability catalog
    YAML, JSON Schema files) -- same choke point, same S1 lint rule."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def create_tar_archive(archive_path: Path, members: Mapping[str, Path | bytes]) -> None:
    """Write a gzip tarball. Each member is either a ``Path`` to copy from
    disk (already-scrubbed staging output, an already-committed schema file)
    or literal ``bytes`` (a generated document such as ``REPRODUCE.md``) --
    the caller decides *what* goes in; this function only ever writes.
    ``evidence/archive.py`` is the only caller (S1's choke point, same rule
    as every other write in this package)."""
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w:gz") as tar:
        for arcname, source in members.items():
            if isinstance(source, Path):
                tar.add(source, arcname=arcname)
            else:
                info = tarfile.TarInfo(name=arcname)
                info.size = len(source)
                tar.addfile(info, io.BytesIO(source))


class BundleWriter:
    """Writes one run's evidence bundle to ``<runs_root>/<run_id>/``."""

    def __init__(
        self,
        runs_root: Path,
        run_id: str,
        *,
        scenario_ref: Mapping[str, Any],
        provenance: Mapping[str, Any],
        block_id: str | None = None,
    ) -> None:
        self.run_id = run_id
        self.run_dir = Path(runs_root) / run_id
        if self.run_dir.exists():
            raise EvidenceError(f"run directory is already present: {self.run_dir}", run_id=run_id)
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "logs").mkdir()

        self._scenario_ref = dict(scenario_ref)
        self._provenance = dict(provenance)
        self._block_id = block_id
        self._created_at = canonical.format_datetime(datetime.now(UTC))
        self._counts = {"observations": 0, "events": 0, "policy_snapshots": 0, "credentials": 0}
        self._closed = False
        self._finalized = False

        # newline="" -- see write_text_artifact's docstring for why: without
        # it, Python's universal-newline translation writes "\r\n" on
        # Windows, and the sealed hash would no longer match what a Linux CI
        # runner checks out from git.
        self._streams: dict[str, IO[str]] = {
            name: (self.run_dir / name).open("a", encoding="utf-8", newline="")
            for name in _JSONL_ARTIFACTS
        }

    # -- context manager --------------------------------------------------

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        if not self._finalized:
            self.close()
        return False

    # -- JSONL streams ------------------------------------------------------

    def _append_jsonl(self, filename: str, record: Any) -> None:
        if self._closed:
            raise EvidenceError(f"writer for {self.run_id} is closed", run_id=self.run_id)
        redact(record)
        line = canonical.dumps(record)
        stream = self._streams[filename]
        stream.write(line + "\n")
        stream.flush()

    def write_observation(self, observation: Observation) -> None:
        self._append_jsonl("observations.jsonl", observation)
        self._counts["observations"] += 1

    def write_event(self, event: Mapping[str, Any]) -> None:
        self._append_jsonl("events.jsonl", dict(event))
        self._counts["events"] += 1

    def write_policy_state(self, snapshot: PolicyStateSnapshot) -> None:
        self._append_jsonl("policy_states.jsonl", snapshot)
        self._counts["policy_snapshots"] += 1

    def write_credential(self, credential: CredentialRecord) -> None:
        self._append_jsonl("credentials.jsonl", credential)
        self._counts["credentials"] += 1

    # -- single JSON documents ----------------------------------------------

    def _write_json_artifact(self, filename: str, document: Any) -> None:
        redact(document)
        write_text_artifact(self.run_dir / filename, canonical.dumps(document))

    def write_scenario(self, compiled_scenario: Any) -> None:
        self._write_json_artifact("scenario.json", compiled_scenario)

    def write_environment(self, environment: Mapping[str, Any]) -> None:
        self._write_json_artifact("environment.json", dict(environment))

    def write_graph(self, graph: Any) -> None:
        self._write_json_artifact("graph.json", graph)

    # -- lifecycle ------------------------------------------------------

    def close(self) -> None:
        if self._closed:
            return
        for stream in self._streams.values():
            stream.close()
        self._closed = True

    def finalize(self, *, status: str, warnings: Sequence[str] = ()) -> Manifest:
        """Close the streams, build ``manifest.json``, and seal the bundle.

        Never called on a run that aborted mid-flight -- an aborted run is
        exactly the case F2 exists for: its ``.jsonl`` files remain on disk,
        readable, just never sealed.
        """
        self.close()
        manifest = Manifest(
            run_id=self.run_id,
            created_at=self._created_at,
            completed_at=canonical.format_datetime(datetime.now(UTC)),
            status=status,
            scenario=self._scenario_ref,
            provenance=self._provenance,
            counts=CountsSection(**self._counts),
            warnings=list(warnings),
            block_id=self._block_id,
        )
        redact(manifest.model_dump())
        manifest = seal(self.run_dir, manifest)
        write_text_artifact(
            self.run_dir / "manifest.json",
            json.dumps(manifest.model_dump(), indent=2, sort_keys=True) + "\n",
        )
        self._finalized = True
        return manifest


def write_findings(run_dir: Path, findings_document: Mapping[str, Any]) -> None:
    """``findings.json`` -- produced by ``analyze``, never by ``run`` (EVIDENCE_SCHEMA.md
    section 1). Deliberately **not** part of ``evidence/manifest.py``'s ``ARTIFACT_NAMES``:
    it is regenerable from ``observations.jsonl`` and is never covered by the sealed root
    (ADR-006 made physical). Still funnels through :func:`redact` and
    :func:`write_text_artifact` like every other evidence-bundle write (S1)."""
    document = dict(findings_document)
    redact(document)
    write_text_artifact(run_dir / "findings.json", canonical.dumps(document))


def write_scores(run_dir: Path, scores_document: Mapping[str, Any]) -> None:
    """``scores.json`` (M15) -- produced by ``analyze`` alongside
    ``findings.json``, from which it is entirely regenerable (it is a pure
    function of the same sealed bundle -- ``scoring/categories.py`` reads no
    other input). Not part of ``ARTIFACT_NAMES`` for the same reason
    ``findings.json`` is not (ADR-006 made physical). Same redact-then-write
    path as every other evidence-bundle write (S1)."""
    document = dict(scores_document)
    redact(document)
    write_text_artifact(run_dir / "scores.json", canonical.dumps(document))
