"""M6 acceptance criterion 5 / F6 / T-13: ``evidence export --public`` strips
every identifier-shaped value listed in F6 and prints a diff of what it
stripped.

Seeds a bundle with an ARN, a bare account ID, a hostname, and a policy
document in several places, then asserts ``export_public`` removes every one
and the resulting files contain none of the original values (the negative
control M06-evidence-pipeline.md's own "Negative controls" section
describes).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chainbreak.core.errors import BundleIntegrityError, EvidenceError
from chainbreak.evidence.export import export_public
from chainbreak.evidence.writer import BundleWriter

pytestmark = pytest.mark.unit

_ARN = "arn:aws:iam::123456789012:role/agent-a"
_ACCOUNT_ID = "123456789012"
_HOSTNAME = "ip-10-0-1-2.ec2.internal"
_NAMESPACE = "cb-a1b2c3d4"
_SESSION_NAME = "cb-a1b2c3d4-session-abc123"
_POLICY_DOCUMENT = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow"}]}'


def _build_seeded_bundle(tmp_path: Path) -> Path:
    writer = BundleWriter(
        tmp_path,
        "01J8XKQ4V7ZP3N2M9YB6TCSEED",
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
            # Not a real provenance field -- seeded here specifically because
            # Manifest.provenance is a free-form dict, exactly the kind of
            # field a literal identifier could leak through if it were never
            # supposed to be there in the first place.
            "debug_note": f"observed on {_HOSTNAME} in account {_ACCOUNT_ID}",
        },
    )
    writer.write_event(
        {
            "event_id": "ev_seed",
            "sequence": 0,
            "kind": "POLICY_MUTATION_APPLIED",
            "message": f"User: {_ARN} is not authorized",
            "policy_document": _POLICY_DOCUMENT,
        }
    )
    writer.write_environment(
        {
            "host": {"hostname_hint": _HOSTNAME},
            "provider_environment": {"namespace": _NAMESPACE},
        }
    )
    writer.write_scenario({"id": "basic", "note": _ARN, "session_name": _SESSION_NAME})
    writer.write_graph({"nodes": [], "edges": [], "note": _ACCOUNT_ID})
    writer.finalize(status="COMPLETED")
    return tmp_path / "01J8XKQ4V7ZP3N2M9YB6TCSEED"


def test_export_public_strips_arn_account_hostname_and_prints_a_diff(tmp_path: Path) -> None:
    run_dir = _build_seeded_bundle(tmp_path)
    output_dir = tmp_path / "public"
    report = export_public(run_dir, output_dir=output_dir, dry_run=False)

    patterns_hit = {hit.pattern for hit in report.stripped}
    assert "arn" in patterns_hit
    assert "hostname" in patterns_hit
    assert "account_id" in patterns_hit
    assert "namespace" in patterns_hit
    assert "session_name" in patterns_hit
    assert "policy_document" in patterns_hit
    assert report.violations > 0

    diff_text = report.render_diff()
    assert "arn" in diff_text
    assert str(report.violations) in diff_text

    for artifact in output_dir.glob("*"):
        text = artifact.read_text(encoding="utf-8")
        assert _ARN not in text
        assert _HOSTNAME not in text
        assert _POLICY_DOCUMENT not in text
        # The bare account id inside the (already redacted) ARN placeholder
        # text must not survive either.
        assert _ACCOUNT_ID not in text
        assert _NAMESPACE not in text
        assert _SESSION_NAME not in text
        if artifact.suffix == ".json":
            json.loads(text)


def test_export_public_dry_run_writes_nothing(tmp_path: Path) -> None:
    run_dir = _build_seeded_bundle(tmp_path)
    output_dir = tmp_path / "public-dry"
    report = export_public(run_dir, output_dir=output_dir, dry_run=True)
    assert report.violations > 0
    assert not output_dir.exists()


def test_export_public_include_policy_documents_opt_in(tmp_path: Path) -> None:
    run_dir = _build_seeded_bundle(tmp_path)
    output_dir = tmp_path / "public-with-policy"
    report = export_public(
        run_dir, output_dir=output_dir, dry_run=False, include_policy_documents=True
    )
    assert "policy_document" not in {hit.pattern for hit in report.stripped}
    event = json.loads((output_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert event["policy_document"] == _POLICY_DOCUMENT


def test_export_public_on_a_clean_bundle_strips_nothing(tmp_path: Path) -> None:
    writer = BundleWriter(
        tmp_path,
        "01J8XKQ4V7ZP3N2M9YB6TCCLN0",
        scenario_ref={"id": "basic", "compiled_hash": "sha256:" + "c" * 64},
        provenance={"chainbreak_version": "0.1.0a0", "config_fingerprint": "sha256:" + "d" * 64},
    )
    writer.write_environment({"host": {"os": "linux"}})
    writer.write_scenario({"id": "basic"})
    writer.write_graph({"nodes": [], "edges": []})
    writer.finalize(status="COMPLETED")
    run_dir = tmp_path / "01J8XKQ4V7ZP3N2M9YB6TCCLN0"

    report = export_public(run_dir, output_dir=tmp_path / "public-clean", dry_run=True)
    assert report.violations == 0
    assert "nothing to strip" in report.render_diff()


def test_export_public_does_not_corrupt_decimal_timing_values(tmp_path: Path) -> None:
    writer = BundleWriter(
        tmp_path,
        "01J8XKQ4V7ZP3N2M9YB6TCCDEC",
        scenario_ref={"id": "basic"},
        provenance={"chainbreak_version": "0.1.0a0"},
    )
    writer.write_environment({"timing": {"credential_age_ms": 5138.123456789012}})
    writer.write_scenario({"id": "basic"})
    writer.write_graph({"nodes": [], "edges": []})
    writer.finalize(status="COMPLETED")

    output_dir = tmp_path / "public-decimal"
    report = export_public(
        tmp_path / "01J8XKQ4V7ZP3N2M9YB6TCCDEC", output_dir=output_dir, dry_run=False
    )
    assert report.violations == 0
    json.loads((output_dir / "environment.json").read_text(encoding="utf-8"))


def test_export_public_refuses_an_unsealed_bundle(tmp_path: Path) -> None:
    writer = BundleWriter(
        tmp_path,
        "01J8XKQ4V7ZP3N2M9YB6TCUNSL",
        scenario_ref={"id": "basic"},
        provenance={"chainbreak_version": "0.1.0a0"},
    )
    writer.close()  # never finalized/sealed
    run_dir = tmp_path / "01J8XKQ4V7ZP3N2M9YB6TCUNSL"
    with pytest.raises(EvidenceError):
        export_public(run_dir)


def test_export_public_refuses_a_manifest_that_was_never_sealed(tmp_path: Path) -> None:
    """Distinct from ``test_export_public_refuses_an_unsealed_bundle``: here
    ``manifest.json`` exists on disk (a hand-written, never-sealed one) rather
    than being absent entirely, which exercises the ``integrity.root is None``
    branch inside ``export_public`` itself instead of ``read_manifest``'s own
    missing-file guard."""
    from chainbreak.evidence.manifest import Manifest

    run_dir = tmp_path / "01J8XKQ4V7ZP3N2M9YB6TCNVRS"
    run_dir.mkdir()
    manifest = Manifest(
        run_id="01J8XKQ4V7ZP3N2M9YB6TCNVRS",
        created_at="2026-01-01T00:00:00.000000Z",
        status="RUNNING",
        scenario={},
        provenance={},
    )
    (run_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    with pytest.raises(EvidenceError):
        export_public(run_dir)


def test_assert_clean_raises_on_a_residual_arn(tmp_path: Path) -> None:
    """Defensive self-check, exercised directly: if scrubbing ever left an
    ARN-shaped string behind, export must refuse rather than publish it."""
    from chainbreak.evidence.export import _assert_clean

    with pytest.raises(EvidenceError):
        _assert_clean(f"still contains {_ARN}", "some-file.json")


def test_export_public_refuses_a_tampered_bundle() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    tampered = (
        repo_root / "tests" / "fixtures" / "bundles" / "tampered" / "01J8XKQ4V7ZP3N2M9YB6TCGOLD"
    )
    with pytest.raises(BundleIntegrityError):
        export_public(tampered, output_dir=repo_root / "should-not-be-written")
