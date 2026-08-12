"""``evidence/archive.py`` direct tests (M18 F4, S1)."""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from chainbreak.capabilities.loader import DEFAULT_CATALOG_PATH, load_catalog
from chainbreak.core.errors import EvidenceError
from chainbreak.evidence.archive import create_archive
from chainbreak.evidence.manifest import ARTIFACT_NAMES, hash_file
from chainbreak.evidence.writer import BundleWriter

pytestmark = pytest.mark.unit

_REAL_CATALOG_VERSION = load_catalog().version


def _build_bundle(tmp_path: Path, run_id: str = "01J8XKARCHIVE0000000000000") -> Path:
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
            "capability_catalog_version": _REAL_CATALOG_VERSION,
            "capability_catalog_fingerprint": hash_file(DEFAULT_CATALOG_PATH),
            "provider": "fake",
            "provider_adapter_version": "0.1.0",
            "python_version": "3.12.7",
            "config_fingerprint": "sha256:" + "b" * 64,
            "seed": 1729,
        },
    )
    writer.write_environment({"host": {"os": "linux"}})
    writer.write_scenario({"id": "basic"})
    writer.write_graph({"nodes": [], "edges": []})
    writer.finalize(status="COMPLETED")
    return tmp_path / run_id


class TestCreateArchive:
    def test_produces_a_tarball(self, tmp_path: Path):
        run_dir = _build_bundle(tmp_path)
        report = create_archive(run_dir)
        assert report.archive_path.is_file()
        assert report.archive_path.suffixes[-2:] == [".tar", ".gz"]
        assert report.catalog_version == _REAL_CATALOG_VERSION
        assert report.schema_files

    def test_respects_explicit_output_path(self, tmp_path: Path):
        run_dir = _build_bundle(tmp_path)
        target = tmp_path / "custom" / "a.tar.gz"
        report = create_archive(run_dir, output_path=target)
        assert report.archive_path == target
        assert target.is_file()

    def test_no_staging_directory_left_behind(self, tmp_path: Path):
        """--archive promises exactly one artifact: the tarball, not also a
        permanent scrubbed sibling directory (export_public's own default)."""
        run_dir = _build_bundle(tmp_path)
        create_archive(run_dir)
        siblings = {p.name for p in tmp_path.iterdir()}
        assert not any(name.endswith("-public") for name in siblings)

    def test_refuses_on_catalog_version_mismatch(self, tmp_path: Path):
        run_dir = _build_bundle(tmp_path, run_id="01J8XKARCHIVEBADCATALOG000")
        # Overwrite the run's recorded catalog version to something the
        # on-disk catalog.yaml (version _REAL_CATALOG_VERSION) does not match.
        import json

        manifest_path = run_dir / "manifest.json"
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
        document["provenance"]["capability_catalog_version"] = "999.0.0"
        manifest_path.write_text(json.dumps(document), encoding="utf-8")

        with pytest.raises(EvidenceError, match="capability_catalog_version"):
            create_archive(run_dir)

    def test_refuses_on_same_version_catalog_content_mismatch(self, tmp_path: Path):
        run_dir = _build_bundle(tmp_path, run_id="01J8XKARCHIVEHASHMISMATCH00")
        import json

        manifest_path = run_dir / "manifest.json"
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
        document["provenance"]["capability_catalog_fingerprint"] = "sha256:" + "f" * 64
        manifest_path.write_text(json.dumps(document), encoding="utf-8")

        with pytest.raises(EvidenceError, match="content has changed"):
            create_archive(run_dir)


class TestArchiveSelfContainment:
    """Acceptance criterion 2: a fresh machine can interpret the archive
    with no repository access. Extracts into an isolated directory and
    verifies every file the bundle needs is present inside the archive
    itself -- nothing is resolved against the source repository."""

    def test_extraction_into_an_empty_directory_is_complete(self, tmp_path: Path):
        run_dir = _build_bundle(tmp_path)
        report = create_archive(run_dir)

        extract_dir = tmp_path / "extracted-no-repo"
        extract_dir.mkdir()
        with tarfile.open(report.archive_path, "r:gz") as tar:
            tar.extractall(extract_dir, filter="data")

        root = extract_dir / report.run_id
        assert root.is_dir()

        bundle_dir = root / "bundle"
        for name in ARTIFACT_NAMES:
            assert (bundle_dir / name).is_file(), f"missing {name} in extracted archive"
        assert (bundle_dir / "manifest.json").is_file()

        assert (root / "catalog.yaml").is_file()
        assert (root / "catalog.yaml").read_text(encoding="utf-8") == (
            (Path(__file__).resolve().parents[2] / "src" / "chainbreak" / "capabilities")
            / "catalog.yaml"
        ).read_text(encoding="utf-8")

        schemas_dir = root / "schemas"
        assert schemas_dir.is_dir()
        extracted_schema_names = {p.name for p in schemas_dir.iterdir()}
        assert extracted_schema_names == set(report.schema_files)
        assert len(extracted_schema_names) > 0

        reproduce_md = (root / "REPRODUCE.md").read_text(encoding="utf-8")
        assert report.run_id in reproduce_md
        assert "chainbreak run" in reproduce_md
        assert "chainbreak analyze" in reproduce_md
        assert "chainbreak compare" in reproduce_md
        assert "--seed 1729" in reproduce_md

    def test_archive_is_scrubbed_even_without_explicit_public_flag(self, tmp_path: Path):
        """S1: --archive implies --public; there is no unscrubbed archive
        path. Seed an ARN and confirm it does not survive into the tarball."""
        run_id = "01J8XKARCHIVESCRUBTEST0000"
        writer = BundleWriter(
            tmp_path,
            run_id,
            scenario_ref={"id": "basic", "compiled_hash": "sha256:" + "c" * 64},
            provenance={
                "chainbreak_version": "0.1.0a0",
                "capability_catalog_version": _REAL_CATALOG_VERSION,
                "config_fingerprint": "sha256:" + "d" * 64,
            },
        )
        writer.write_event(
            {
                "event_id": "ev_seed",
                "sequence": 0,
                "kind": "POLICY_MUTATION_APPLIED",
                "message": "User: arn:aws:iam::123456789012:role/agent-a is not authorized",
            }
        )
        writer.write_environment({"host": {"os": "linux"}})
        writer.write_scenario({"id": "basic"})
        writer.write_graph({"nodes": [], "edges": []})
        writer.finalize(status="COMPLETED")
        run_dir = tmp_path / run_id

        report = create_archive(run_dir)
        with tarfile.open(report.archive_path, "r:gz") as tar:
            events_member = tar.extractfile(f"{run_id}/bundle/events.jsonl")
            assert events_member is not None
            content = events_member.read().decode("utf-8")
        assert "123456789012" not in content
        assert "arn:aws:iam" not in content
