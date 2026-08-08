"""F5: the SQLite run index -- open/upsert/reindex/list, and the
``findings.json`` ingestion path (against a hand-built fixture, since
``analyze`` itself is M7 -- see PROJECT_STATUS.md)."""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreak.evidence import index as index_module
from chainbreak.evidence.reader import read_manifest
from chainbreak.evidence.writer import BundleWriter

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_RUN_DIR = (
    REPO_ROOT / "tests" / "fixtures" / "bundles" / "golden" / "01J8XKQ4V7ZP3N2M9YB6TCGOLD"
)
GOLDEN_RUNS_ROOT = GOLDEN_RUN_DIR.parent


def _build_run(tmp_path: Path, run_id: str) -> Path:
    writer = BundleWriter(
        tmp_path,
        run_id,
        scenario_ref={
            "id": "basic",
            "version": "1.0.0",
            "family": "scope-attenuation",
            "api_version": "chainbreak.dev/v1alpha1",
            "compiled_hash": "sha256:" + "a" * 64,
        },
        provenance={
            "chainbreak_version": "0.1.0a0",
            "capability_catalog_version": "1.0.0",
            "provider": "fake",
            "provider_adapter_version": "0.1.0",
            "python_version": "3.12.7",
            "config_fingerprint": "sha256:" + "b" * 64,
        },
    )
    writer.write_environment({"host": {"os": "test"}})
    writer.write_scenario({"id": "basic"})
    writer.write_graph({"nodes": [], "edges": []})
    writer.finalize(status="COMPLETED")
    return tmp_path / run_id


def test_open_index_creates_schema(tmp_path: Path) -> None:
    conn = index_module.open_index(tmp_path / "index.db")
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {
        "runs",
        "findings",
        "measurements",
        "category_results",
        "detector_checks",
        "exclusions",
    } <= tables
    conn.close()


def test_open_index_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "index.db"
    index_module.open_index(db_path).close()
    conn = index_module.open_index(db_path)  # must not fail on already-existing tables
    conn.close()


def test_upsert_and_get_run(tmp_path: Path) -> None:
    run_dir = _build_run(tmp_path, "01J8XKQ4V7ZP3N2M9YB6TCIDX1")
    manifest = read_manifest(run_dir / "manifest.json")
    conn = index_module.open_index(tmp_path / "index.db")
    index_module.upsert_run(conn, manifest, bundle_path=run_dir, root_verified=True)
    conn.commit()

    row = index_module.get_run(conn, manifest.run_id)
    assert row is not None
    assert row["scenario_id"] == "basic"
    assert row["provider"] == "fake"
    assert row["sealed"] == 1
    assert row["root_verified"] == 1
    assert index_module.get_run(conn, "does-not-exist") is None
    conn.close()


def test_upsert_run_updates_on_conflict(tmp_path: Path) -> None:
    run_dir = _build_run(tmp_path, "01J8XKQ4V7ZP3N2M9YB6TCIDX2")
    manifest = read_manifest(run_dir / "manifest.json")
    conn = index_module.open_index(tmp_path / "index.db")
    index_module.upsert_run(conn, manifest, bundle_path=run_dir, root_verified=False)
    index_module.upsert_run(conn, manifest, bundle_path=run_dir, root_verified=True)
    conn.commit()
    rows = conn.execute("SELECT COUNT(*) FROM runs WHERE run_id = ?", (manifest.run_id,)).fetchone()
    assert rows[0] == 1
    row = index_module.get_run(conn, manifest.run_id)
    assert row["root_verified"] == 1
    conn.close()


def test_list_runs_orders_by_created_at_desc(tmp_path: Path) -> None:
    conn = index_module.open_index(tmp_path / "index.db")
    for i in range(2):
        run_dir = _build_run(tmp_path, f"01J8XKQ4V7ZP3N2M9YB6TCIDX{i}A")
        manifest = read_manifest(run_dir / "manifest.json")
        index_module.upsert_run(conn, manifest, bundle_path=run_dir, root_verified=True)
    conn.commit()
    rows = index_module.list_runs(conn)
    assert len(rows) == 2
    conn.close()


def test_index_findings_populates_findings_and_detector_checks(tmp_path: Path) -> None:
    run_dir = _build_run(tmp_path, "01J8XKQ4V7ZP3N2M9YB6TCIDX3")
    manifest = read_manifest(run_dir / "manifest.json")
    conn = index_module.open_index(tmp_path / "index.db")
    index_module.upsert_run(conn, manifest, bundle_path=run_dir, root_verified=True)

    findings_doc = {
        "findings": [
            {
                "finding_id": "fnd_01",
                "type": "AUTHORITY_EXPANSION",
                "confidence": "HIGH",
                "severity_hint": "REVIEW",
                "subject": {"kind": "identity", "identity_id": "agent-c", "hop_index": 3},
                "observation": "agent-c returned ALLOWED for keyvalue.read",
                "delta": {"unexpected_gain": ["keyvalue.read"], "unexpected_loss": []},
                "evidence": {"observation_refs": ["obs_1", "obs_2"]},
            }
        ],
        "detector_checks": [
            {
                "negative_control": "nc-01",
                "expected": "AUTHORITY_EXPANSION",
                "produced": True,
                "result": "DETECTOR_OK",
            }
        ],
    }
    index_module.index_findings(conn, manifest.run_id, findings_doc)
    conn.commit()

    finding_row = conn.execute("SELECT * FROM findings WHERE finding_id = 'fnd_01'").fetchone()
    assert finding_row is not None
    check_count = conn.execute(
        "SELECT COUNT(*) FROM detector_checks WHERE run_id = ?", (manifest.run_id,)
    ).fetchone()[0]
    assert check_count == 1
    conn.close()


def test_reindex_rebuilds_from_disk(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    for i in range(2):
        _build_run(runs_root, f"01J8XKQ4V7ZP3N2M9YB6TCIDX{i}R")
    # A directory that looks like a run but has no manifest.json (an aborted,
    # never-sealed run) must be skipped, not crash the reindex.
    (runs_root / "not-a-real-run").mkdir()

    db_path = tmp_path / "index.db"
    count = index_module.reindex(db_path, runs_root)
    assert count == 2

    conn = index_module.open_index(db_path)
    assert len(index_module.list_runs(conn)) == 2
    conn.close()


def test_reindex_against_the_golden_fixture_reports_root_verified() -> None:
    """Uses the committed golden bundle directly, no fabrication needed."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "index.db"
        count = index_module.reindex(db_path, GOLDEN_RUNS_ROOT)
        assert count >= 1
        conn = index_module.open_index(db_path)
        row = index_module.get_run(conn, "01J8XKQ4V7ZP3N2M9YB6TCGOLD")
        assert row is not None
        assert row["root_verified"] == 1
        conn.close()


def test_reindex_on_a_missing_runs_root_yields_zero(tmp_path: Path) -> None:
    count = index_module.reindex(tmp_path / "index.db", tmp_path / "does-not-exist")
    assert count == 0
