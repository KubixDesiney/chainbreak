"""SQLite run index (EVIDENCE_SCHEMA.md section 9; F5).

A cache derived from evidence bundles, **never** the source of truth --
``schemas/run-index.sql``'s own header says so explicitly, and nothing in the
analysis path may read a value from here that it did not first read from a
bundle. ``reindex()`` drops and rebuilds every table from the bundles found on
disk; deleting this database must lose nothing but query convenience.

``_SCHEMA_SQL`` is a literal copy of ``schemas/run-index.sql``, not a runtime
read of that file: M3 established the precedent (``scenarios/loader.py``'s
schema check is generated in-memory rather than reading ``schemas/``) that
nothing in this package depends on a repository checkout layout at runtime.
``tests/unit/test_evidence_schema.py`` asserts the two stay byte-identical.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from chainbreak.evidence.manifest import Manifest
from chainbreak.evidence.reader import read_findings, read_manifest

_SCHEMA_SQL = """\
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER NOT NULL PRIMARY KEY,
    applied_at  TEXT    NOT NULL
);
INSERT OR IGNORE INTO schema_version (version, applied_at)
VALUES (1, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));

CREATE TABLE IF NOT EXISTS runs (
    run_id              TEXT PRIMARY KEY,
    created_at          TEXT NOT NULL,
    completed_at        TEXT,
    status              TEXT NOT NULL
        CHECK (status IN ('RUNNING','COMPLETED','ABORTED_TIMEOUT','ABORTED_SAFETY','ABORTED_ERROR')),
    scenario_id         TEXT NOT NULL,
    scenario_version    TEXT NOT NULL,
    family              TEXT NOT NULL,
    api_version         TEXT NOT NULL,
    provider            TEXT NOT NULL,
    adapter_version     TEXT NOT NULL,
    chainbreak_version  TEXT NOT NULL,
    catalog_version     TEXT NOT NULL,
    git_commit          TEXT,
    git_dirty           INTEGER NOT NULL DEFAULT 0,
    compiled_hash       TEXT NOT NULL,
    config_fingerprint  TEXT NOT NULL,
    infra_fingerprint   TEXT,
    block_id            TEXT,
    bundle_path         TEXT NOT NULL,
    bundle_root         TEXT NOT NULL,
    sealed              INTEGER NOT NULL DEFAULT 0,
    root_verified       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS findings (
    finding_id          TEXT PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    type                TEXT NOT NULL,
    confidence          TEXT NOT NULL CHECK (confidence IN ('HIGH','MEDIUM','LOW','INSUFFICIENT')),
    severity_hint       TEXT NOT NULL CHECK (severity_hint IN ('INFORMATIONAL','REVIEW','INVESTIGATE')),
    subject_kind        TEXT NOT NULL,
    identity_id         TEXT,
    edge_id             TEXT,
    hop_index           INTEGER,
    drift_class         TEXT,
    delta_gain_json     TEXT NOT NULL DEFAULT '[]',
    delta_loss_json     TEXT NOT NULL DEFAULT '[]',
    observation_count   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS measurements (
    run_id          TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    metric          TEXT NOT NULL,
    identity_id     TEXT NOT NULL DEFAULT '',
    capability_id   TEXT NOT NULL DEFAULT '',
    value_low       REAL NOT NULL,
    value_point     REAL NOT NULL,
    value_high      REAL NOT NULL,
    unit            TEXT NOT NULL,
    n               INTEGER NOT NULL DEFAULT 1,
    confidence      TEXT NOT NULL,
    mechanism       TEXT,
    PRIMARY KEY (run_id, metric, identity_id, capability_id),
    CHECK (value_low <= value_point AND value_point <= value_high)
);

CREATE TABLE IF NOT EXISTS category_results (
    run_id      TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    category    TEXT NOT NULL,
    status      TEXT NOT NULL
        CHECK (status IN ('CONSISTENT','DIVERGENT','PARTIAL','NOT_MEASURED','DETECTOR_FAILED')),
    coverage    REAL NOT NULL CHECK (coverage BETWEEN 0.0 AND 1.0),
    confidence  TEXT NOT NULL,
    PRIMARY KEY (run_id, category)
);

CREATE TABLE IF NOT EXISTS detector_checks (
    run_id              TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    negative_control_id TEXT NOT NULL,
    expected_type       TEXT NOT NULL,
    produced            INTEGER NOT NULL,
    result              TEXT NOT NULL CHECK (result IN ('DETECTOR_OK','DETECTOR_FAILURE')),
    PRIMARY KEY (run_id, negative_control_id)
);

CREATE TABLE IF NOT EXISTS exclusions (
    run_id          TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    scope           TEXT NOT NULL,
    identity_id     TEXT,
    capability_id   TEXT,
    reason          TEXT NOT NULL,
    count           INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_runs_scenario   ON runs(scenario_id, created_at);
CREATE INDEX IF NOT EXISTS idx_runs_block      ON runs(block_id, created_at);
CREATE INDEX IF NOT EXISTS idx_runs_compiled   ON runs(compiled_hash);
CREATE INDEX IF NOT EXISTS idx_findings_type   ON findings(type, confidence);
CREATE INDEX IF NOT EXISTS idx_findings_run    ON findings(run_id);
CREATE INDEX IF NOT EXISTS idx_measure_metric  ON measurements(metric, mechanism);
CREATE INDEX IF NOT EXISTS idx_detector_result ON detector_checks(result);

CREATE VIEW IF NOT EXISTS comparable_runs AS
SELECT compiled_hash, adapter_version, catalog_version,
       COUNT(*) AS n_runs,
       COUNT(DISTINCT block_id) AS n_blocks,
       MIN(created_at) AS first_run,
       MAX(created_at) AS last_run
FROM runs
WHERE status = 'COMPLETED' AND sealed = 1
GROUP BY compiled_hash, adapter_version, catalog_version;

CREATE VIEW IF NOT EXISTS unvalidated_blocks AS
SELECT DISTINCT r.block_id
FROM runs r
JOIN detector_checks d ON d.run_id = r.run_id
WHERE d.result = 'DETECTOR_FAILURE' AND r.block_id IS NOT NULL;
"""


def open_index(db_path: Path) -> sqlite3.Connection:
    """Open (creating if absent) the run index and ensure its schema exists."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    return conn


def _bool_int(value: bool) -> int:
    return 1 if value else 0


def upsert_run(
    conn: sqlite3.Connection,
    manifest: Manifest,
    *,
    bundle_path: Path,
    root_verified: bool,
) -> None:
    scenario = manifest.scenario
    provenance = manifest.provenance
    conn.execute(
        """
        INSERT INTO runs (
            run_id, created_at, completed_at, status,
            scenario_id, scenario_version, family, api_version,
            provider, adapter_version, chainbreak_version, catalog_version,
            git_commit, git_dirty, compiled_hash, config_fingerprint,
            infra_fingerprint, block_id, bundle_path, bundle_root,
            sealed, root_verified
        ) VALUES (?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?)
        ON CONFLICT(run_id) DO UPDATE SET
            completed_at=excluded.completed_at, status=excluded.status,
            bundle_root=excluded.bundle_root, sealed=excluded.sealed,
            root_verified=excluded.root_verified
        """,
        (
            manifest.run_id,
            manifest.created_at,
            manifest.completed_at,
            manifest.status,
            scenario.get("id", ""),
            scenario.get("version", ""),
            scenario.get("family", ""),
            scenario.get("api_version", ""),
            provenance.get("provider", ""),
            provenance.get("provider_adapter_version", ""),
            provenance.get("chainbreak_version", ""),
            provenance.get("capability_catalog_version", ""),
            provenance.get("git_commit"),
            _bool_int(bool(provenance.get("git_dirty", False))),
            scenario.get("compiled_hash", ""),
            provenance.get("config_fingerprint", ""),
            provenance.get("infrastructure_fingerprint"),
            manifest.block_id,
            str(bundle_path),
            manifest.integrity.root or "",
            _bool_int(manifest.integrity.root is not None),
            _bool_int(root_verified),
        ),
    )


def index_findings(conn: sqlite3.Connection, run_id: str, findings_doc: dict[str, Any]) -> None:
    """Populate ``findings``/``detector_checks`` from a bundle's ``findings.json``.

    A no-op-friendly caller: absent ``findings.json`` (every M6-era bundle, since
    ``analyze`` is M7) simply means this is never called for that run.
    """
    import json as _json

    for finding in findings_doc.get("findings", []):
        delta = finding.get("delta", {})
        evidence = finding.get("evidence", {})
        conn.execute(
            """
            INSERT OR REPLACE INTO findings (
                finding_id, run_id, type, confidence, severity_hint, subject_kind,
                identity_id, edge_id, hop_index, drift_class,
                delta_gain_json, delta_loss_json, observation_count
            ) VALUES (?,?,?,?,?,?, ?,?,?,?, ?,?,?)
            """,
            (
                finding["finding_id"],
                run_id,
                finding["type"],
                finding["confidence"],
                finding["severity_hint"],
                finding.get("subject", {}).get("kind", finding.get("subject_kind", "")),
                finding.get("subject", {}).get("identity_id", finding.get("identity_id")),
                finding.get("edge_id"),
                finding.get("subject", {}).get("hop_index", finding.get("hop_index")),
                finding.get("drift_class"),
                _json.dumps(delta.get("unexpected_gain", [])),
                _json.dumps(delta.get("unexpected_loss", [])),
                len(evidence.get("observation_refs", [])),
            ),
        )
    for check in findings_doc.get("detector_checks", []):
        conn.execute(
            """
            INSERT OR REPLACE INTO detector_checks (
                run_id, negative_control_id, expected_type, produced, result
            ) VALUES (?,?,?,?,?)
            """,
            (
                run_id,
                check["negative_control"],
                check["expected"],
                _bool_int(bool(check["produced"])),
                check["result"],
            ),
        )


def list_runs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()


def get_run(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    return row


def reindex(db_path: Path, runs_root: Path) -> int:
    """Rebuild the index from scratch by scanning every bundle under ``runs_root``.

    Drops and recreates every table so a stale or hand-edited index can never
    linger; the index is disposable by design (F5).
    """
    if db_path.exists():
        db_path.unlink()
    conn = open_index(db_path)
    count = 0
    if not runs_root.is_dir():
        conn.commit()
        conn.close()
        return count
    for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = read_manifest(manifest_path)
        from chainbreak.evidence.manifest import verify as verify_manifest

        root_verified = manifest.integrity.root is not None and verify_manifest(run_dir, manifest)
        upsert_run(conn, manifest, bundle_path=run_dir, root_verified=root_verified)
        findings_path = run_dir / "findings.json"
        if findings_path.is_file():
            index_findings(conn, manifest.run_id, read_findings(findings_path))
        count += 1
    conn.commit()
    conn.close()
    return count
