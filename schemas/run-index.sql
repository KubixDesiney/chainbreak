-- CHAINBREAK local run index
--
-- This database is a CACHE DERIVED FROM EVIDENCE BUNDLES, never the source of
-- truth. `chainbreak runs reindex` rebuilds it from disk. Nothing in the
-- analysis path may read a value from here that it did not first read from a
-- bundle. Deleting this file must lose nothing but query convenience.
--
-- Applies to: EVIDENCE_SCHEMA.md section 9.

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
    -- block_id supports control C-7 (block randomization across time): timing
    -- trials must be distributed across blocks, and the analysis needs to know
    -- which block each run belongs to.
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

-- Every timing result is a TRIPLE. There is deliberately no column for a bare
-- scalar: uncertainty is not optional metadata, it is part of the value.
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

-- Negative-control outcomes. A DETECTOR_FAILURE invalidates every positive
-- result produced in the same block, so this table is queried before any
-- cross-run aggregation.
CREATE TABLE IF NOT EXISTS detector_checks (
    run_id              TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    negative_control_id TEXT NOT NULL,
    expected_type       TEXT NOT NULL,
    produced            INTEGER NOT NULL,
    result              TEXT NOT NULL CHECK (result IN ('DETECTOR_OK','DETECTOR_FAILURE')),
    PRIMARY KEY (run_id, negative_control_id)
);

-- Excluded trials are recorded, never silently dropped. Silent exclusion is the
-- classic way to manufacture a clean result (RESEARCH_METHODOLOGY section 8).
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

-- Comparable runs share compiled_hash, adapter_version and catalog_version.
-- `analyze --aggregate` refuses to pool anything this view separates.
CREATE VIEW IF NOT EXISTS comparable_runs AS
SELECT compiled_hash, adapter_version, catalog_version,
       COUNT(*) AS n_runs,
       COUNT(DISTINCT block_id) AS n_blocks,
       MIN(created_at) AS first_run,
       MAX(created_at) AS last_run
FROM runs
WHERE status = 'COMPLETED' AND sealed = 1
GROUP BY compiled_hash, adapter_version, catalog_version;

-- Any run in a block that contains a DETECTOR_FAILURE is unvalidated and must
-- not be published (EXPERIMENT_PROTOCOL section 6).
CREATE VIEW IF NOT EXISTS unvalidated_blocks AS
SELECT DISTINCT r.block_id
FROM runs r
JOIN detector_checks d ON d.run_id = r.run_id
WHERE d.result = 'DETECTOR_FAILURE' AND r.block_id IS NOT NULL;
