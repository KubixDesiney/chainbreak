"""``evidence/migrate.py`` direct tests (M18 F5).

``BUNDLE_FORMAT_VERSION`` has been 1 since M6 and no format change has ever
shipped (see the module docstring), so there is no real migration to test
against yet. These tests register a synthetic v1->v99 migration through the
module's own public API to prove the mechanism -- registry, dispatch,
preserve-the-original -- works, then unregister it in a fixture teardown so
it cannot leak into any other test.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from chainbreak.core.errors import EvidenceError
from chainbreak.evidence.manifest import BUNDLE_FORMAT_VERSION
from chainbreak.evidence.migrate import (
    copy_bundle_verbatim,
    migrate_bundle,
    register_migration,
    registered_migrations,
)
from chainbreak.evidence.writer import BundleWriter

pytestmark = pytest.mark.unit

_SYNTHETIC_TO_VERSION = 99


def _build_bundle(tmp_path: Path, run_id: str = "01J8XKMIGRATE00000000000B") -> Path:
    writer = BundleWriter(
        tmp_path,
        run_id,
        scenario_ref={"id": "basic", "compiled_hash": "sha256:" + "a" * 64},
        provenance={"chainbreak_version": "0.1.0a0", "config_fingerprint": "sha256:" + "b" * 64},
    )
    writer.write_environment({"host": {"os": "linux"}})
    writer.write_scenario({"id": "basic"})
    writer.write_graph({"nodes": [], "edges": []})
    writer.finalize(status="COMPLETED")
    return tmp_path / run_id


def _hash_tree(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.fixture
def synthetic_migration():
    register_migration(BUNDLE_FORMAT_VERSION, _SYNTHETIC_TO_VERSION, copy_bundle_verbatim)
    yield
    from chainbreak.evidence import migrate as migrate_module

    migrate_module._MIGRATIONS.pop((BUNDLE_FORMAT_VERSION, _SYNTHETIC_TO_VERSION), None)


class TestRegistry:
    def test_starts_with_no_real_migrations_registered(self):
        # BUNDLE_FORMAT_VERSION has never changed -- nothing to migrate from.
        assert registered_migrations() == ()

    def test_register_migration_appears_in_registered_migrations(self, synthetic_migration):
        assert (BUNDLE_FORMAT_VERSION, _SYNTHETIC_TO_VERSION) in registered_migrations()

    def test_double_registration_is_refused(self, synthetic_migration):
        with pytest.raises(ValueError, match="already registered"):
            register_migration(BUNDLE_FORMAT_VERSION, _SYNTHETIC_TO_VERSION, copy_bundle_verbatim)


class TestMigrateBundle:
    def test_already_at_target_version_is_refused(self, tmp_path: Path):
        run_dir = _build_bundle(tmp_path)
        with pytest.raises(EvidenceError, match="already at bundle format version"):
            migrate_bundle(run_dir, to_version=BUNDLE_FORMAT_VERSION)

    def test_no_registered_path_is_refused(self, tmp_path: Path):
        run_dir = _build_bundle(tmp_path)
        with pytest.raises(EvidenceError, match="no migration registered"):
            migrate_bundle(run_dir, to_version=12345)

    def test_migration_writes_a_new_directory(self, tmp_path: Path, synthetic_migration):
        run_dir = _build_bundle(tmp_path)
        result = migrate_bundle(run_dir, to_version=_SYNTHETIC_TO_VERSION)
        assert result.target_dir != run_dir
        assert result.target_dir.is_dir()
        assert (result.target_dir / "manifest.json").is_file()
        assert result.from_version == BUNDLE_FORMAT_VERSION
        assert result.to_version == _SYNTHETIC_TO_VERSION

    def test_original_bundle_is_byte_for_byte_unchanged(self, tmp_path: Path, synthetic_migration):
        run_dir = _build_bundle(tmp_path)
        before = _hash_tree(run_dir)
        migrate_bundle(run_dir, to_version=_SYNTHETIC_TO_VERSION)
        after = _hash_tree(run_dir)
        assert before == after

    def test_migrated_bundle_matches_the_original_content(
        self, tmp_path: Path, synthetic_migration
    ):
        run_dir = _build_bundle(tmp_path)
        result = migrate_bundle(run_dir, to_version=_SYNTHETIC_TO_VERSION)
        assert _hash_tree(run_dir) == _hash_tree(result.target_dir)

    def test_explicit_target_dir_is_respected(self, tmp_path: Path, synthetic_migration):
        run_dir = _build_bundle(tmp_path)
        target = tmp_path / "custom-migration-target"
        result = migrate_bundle(run_dir, to_version=_SYNTHETIC_TO_VERSION, target_dir=target)
        assert result.target_dir == target
        assert target.is_dir()


class TestCopyBundleVerbatim:
    def test_refuses_an_existing_target(self, tmp_path: Path):
        run_dir = _build_bundle(tmp_path)
        target = tmp_path / "already-exists"
        target.mkdir()
        with pytest.raises(EvidenceError, match="already exists"):
            copy_bundle_verbatim(run_dir, target)
