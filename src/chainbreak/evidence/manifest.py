"""``manifest.json`` construction, sealing and verification (EVIDENCE_SCHEMA.md section 2).

Sealing computes a SHA-256 per artifact plus a root over the sorted
``name:hash`` pairs (F3). This is tamper-*evidence*, not tamper-*proofing*: an
operator who edits a bundle can recompute the root themselves. It defends
against accidental corruption and makes deliberate falsification require
deliberate effort -- the appropriate bar for a self-administered benchmark
(EVIDENCE_SCHEMA.md section 10).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from chainbreak.core.canonical import format_datetime
from chainbreak.core.errors import BundleIntegrityError

BUNDLE_FORMAT_VERSION = 1

#: Ordered set of artifact filenames covered by the integrity root. Matches
#: EVIDENCE_SCHEMA.md section 2's manifest.json example exactly: findings.json
#: and scores.json are produced by `analyze`, not `run`, and are never part of
#: the sealed root (ADR-006 made physical -- they are regenerable).
ARTIFACT_NAMES: tuple[str, ...] = (
    "observations.jsonl",
    "events.jsonl",
    "policy_states.jsonl",
    "credentials.jsonl",
    "graph.json",
    "scenario.json",
    "environment.json",
)


class IntegritySection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: str = "sha256"
    artifacts: dict[str, str] = Field(default_factory=dict)
    root: str | None = None
    sealed_at: str | None = None


class RedactionSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version: str = "1.0.0"
    rules_applied: list[str] = Field(
        default_factory=lambda: ["secret_patterns", "arn_account", "session_names"]
    )
    account_id_treatment: str = "hashed"
    # Always 0 in a sealed bundle: redact() raises and aborts the run on the
    # first hit (S2), so a bundle that reached sealing saw no violation.
    violations_detected: int = 0


class CountsSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observations: int = 0
    events: int = 0
    policy_snapshots: int = 0
    credentials: int = 0


class Manifest(BaseModel):
    """``manifest.json``. Not a ``DomainModel``: this is a bundle-layer
    artifact, not a core algebraic type, so it is intentionally outside
    ``core/models.py`` and the reflection sweep ``test_redaction.py`` runs
    over that package -- it is still redacted explicitly by the writer before
    it touches disk."""

    model_config = ConfigDict(extra="forbid")

    bundle_format_version: int = BUNDLE_FORMAT_VERSION
    run_id: str
    created_at: str
    completed_at: str | None = None
    status: str
    scenario: dict[str, Any]
    provenance: dict[str, Any]
    integrity: IntegritySection = Field(default_factory=IntegritySection)
    redaction: RedactionSection = Field(default_factory=RedactionSection)
    counts: CountsSection = Field(default_factory=CountsSection)
    warnings: list[str] = Field(default_factory=list)
    block_id: str | None = Field(
        default=None,
        description="Control C-7 block grouping for cross-run aggregation; set by the "
        "orchestrator (M10+), not by the writer itself.",
    )


def hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    return hash_bytes(path.read_bytes())


def compute_root(artifact_hashes: dict[str, str]) -> str:
    """SHA-256 over the sorted ``name:hash`` pairs, newline-joined (F3)."""
    joined = "\n".join(f"{name}:{artifact_hashes[name]}" for name in sorted(artifact_hashes))
    return hash_bytes(joined.encode("utf-8"))


def compute_artifact_hashes(
    run_dir: Path, *, names: tuple[str, ...] = ARTIFACT_NAMES
) -> dict[str, str]:
    """Hash every present artifact. Missing files are simply absent from the
    result -- callers that require a complete set check membership themselves."""
    hashes: dict[str, str] = {}
    for name in names:
        path = run_dir / name
        if path.is_file():
            hashes[name] = hash_file(path)
    return hashes


def seal(run_dir: Path, manifest: Manifest) -> Manifest:
    """Compute the integrity section and stamp ``sealed_at`` (F3).

    Requires every artifact in ``ARTIFACT_NAMES`` to be present; a bundle
    missing one (an aborted run, most commonly) is never sealed -- callers
    that want partial evidence read the raw ``.jsonl`` files directly, which
    F2 guarantees are usable even unsealed.
    """
    missing = [name for name in ARTIFACT_NAMES if not (run_dir / name).is_file()]
    if missing:
        raise BundleIntegrityError(
            f"cannot seal an incomplete bundle: missing {missing}", missing=missing
        )
    artifact_hashes = compute_artifact_hashes(run_dir)
    root = compute_root(artifact_hashes)
    manifest.integrity = IntegritySection(
        algorithm="sha256",
        artifacts=artifact_hashes,
        root=root,
        sealed_at=format_datetime(datetime.now(UTC)),
    )
    return manifest


def verify(run_dir: Path, manifest: Manifest) -> bool:
    """Recompute the root and compare against the manifest's stored root.

    Returns ``True`` on a match. Never raises on mismatch -- callers decide
    what a mismatch means (``analyze`` refuses findings; ``--allow-unsealed``
    proceeds anyway and stamps every finding accordingly).
    """
    if manifest.integrity.root is None:
        return False
    current_hashes = compute_artifact_hashes(run_dir)
    if set(current_hashes) != set(manifest.integrity.artifacts):
        return False
    if current_hashes != manifest.integrity.artifacts:
        return False
    return compute_root(current_hashes) == manifest.integrity.root
