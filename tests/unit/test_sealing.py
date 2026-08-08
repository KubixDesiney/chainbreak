"""M6 acceptance criterion 3: sealing and tamper detection (F3, F4).

``analyze --allow-unsealed`` stamping every finding is M7's job (``analyze``
does not exist yet -- PROJECT_STATUS.md known issue 10); what M6 owns is the
root computation and verification that stamping would be built on, which is
what this file actually exercises.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from chainbreak.core.errors import BundleIntegrityError, EvidenceError
from chainbreak.evidence import manifest as manifest_module
from chainbreak.evidence.reader import read_manifest, verify_integrity
from chainbreak.evidence.writer import BundleWriter

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_RUN_DIR = (
    REPO_ROOT / "tests" / "fixtures" / "bundles" / "golden" / "01J8XKQ4V7ZP3N2M9YB6TCGOLD"
)
TAMPERED_RUN_DIR = (
    REPO_ROOT / "tests" / "fixtures" / "bundles" / "tampered" / "01J8XKQ4V7ZP3N2M9YB6TCGOLD"
)


def test_golden_bundle_verifies() -> None:
    assert verify_integrity(GOLDEN_RUN_DIR) is True


def test_tampered_bundle_fails_verification() -> None:
    manifest = read_manifest(TAMPERED_RUN_DIR / "manifest.json")
    assert manifest_module.verify(TAMPERED_RUN_DIR, manifest) is False


def test_tampered_bundle_hash_differs_from_golden() -> None:
    golden = read_manifest(GOLDEN_RUN_DIR / "manifest.json")
    tampered_current = manifest_module.compute_artifact_hashes(TAMPERED_RUN_DIR)
    assert (
        tampered_current["observations.jsonl"] != golden.integrity.artifacts["observations.jsonl"]
    )


def test_seal_refuses_an_incomplete_bundle(tmp_path: Path) -> None:
    """F1/F3: a bundle missing an artifact is never sealed -- the unsealed
    ``.jsonl`` files it does have remain directly readable (F2)."""
    incomplete = tmp_path / "incomplete-run"
    shutil.copytree(GOLDEN_RUN_DIR, incomplete)
    (incomplete / "graph.json").unlink()
    manifest = read_manifest(incomplete / "manifest.json")
    with pytest.raises(BundleIntegrityError):
        manifest_module.seal(incomplete, manifest)


def test_writer_never_writes_crlf(tmp_path: Path) -> None:
    """REPRODUCIBILITY.md: evidence bytes must be platform-independent.

    Without ``newline=""`` on every write, Python's universal-newline
    translation writes ``\\r\\n`` on Windows -- silently desyncing a bundle
    sealed on a Windows machine from what a Linux CI runner checks out from
    git, which stores line endings as pushed rather than re-normalizing them
    on checkout. Caught by CI run 31240770166 failing on a fresh Linux
    checkout of a bundle sealed on Windows; regenerating the fixtures with
    this fix made local and CI verification agree.
    """
    writer = BundleWriter(
        tmp_path,
        "01J8XKQ4V7ZP3N2M9YB6TCCRLF",
        scenario_ref={"id": "basic", "compiled_hash": "sha256:" + "a" * 64},
        provenance={"chainbreak_version": "0.1.0a0", "config_fingerprint": "sha256:" + "b" * 64},
    )
    writer.write_event({"kind": "RUN_STARTED"})
    writer.write_event({"kind": "RUN_COMPLETED"})
    writer.write_environment({"host": {"os": "test"}})
    writer.write_scenario({"id": "basic"})
    writer.write_graph({"nodes": [], "edges": []})
    writer.finalize(status="COMPLETED")

    run_dir = tmp_path / "01J8XKQ4V7ZP3N2M9YB6TCCRLF"
    for artifact in run_dir.iterdir():
        if artifact.is_file():
            assert b"\r" not in artifact.read_bytes(), f"{artifact.name} contains a CR byte"


def test_writer_produces_a_bundle_that_verifies(tmp_path: Path) -> None:
    """End-to-end at the layer that exists today: write, finalize, verify.
    Stands in for ``chainbreak run ... && python -m chainbreak.evidence.verify``
    (the orchestrator behind the first half is M10 -- see PROJECT_STATUS.md
    known issue 10)."""
    writer = BundleWriter(
        tmp_path,
        "01J8XKQ4V7ZP3N2M9YB6TCFRESH",
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
    manifest = writer.finalize(status="COMPLETED")

    run_dir = tmp_path / "01J8XKQ4V7ZP3N2M9YB6TCFRESH"
    assert manifest.integrity.root is not None
    assert verify_integrity(run_dir) is True
    assert manifest.counts.observations == 0


def test_writer_refuses_a_duplicate_run_directory(tmp_path: Path) -> None:
    BundleWriter(tmp_path, "01J8XKQ4V7ZP3N2M9YB6TCDUP0", scenario_ref={}, provenance={}).close()
    with pytest.raises(EvidenceError):
        BundleWriter(tmp_path, "01J8XKQ4V7ZP3N2M9YB6TCDUP0", scenario_ref={}, provenance={})


def test_writer_as_a_context_manager_closes_on_normal_exit(tmp_path: Path) -> None:
    with BundleWriter(
        tmp_path, "01J8XKQ4V7ZP3N2M9YB6TCCTX0", scenario_ref={}, provenance={}
    ) as writer:
        assert writer._closed is False
    assert writer._closed is True


def test_writer_as_a_context_manager_closes_on_exception(tmp_path: Path) -> None:
    with (
        pytest.raises(ValueError),
        BundleWriter(
            tmp_path, "01J8XKQ4V7ZP3N2M9YB6TCCTX1", scenario_ref={}, provenance={}
        ) as writer,
    ):
        raise ValueError("boom")
    assert writer._closed is True


def test_writer_context_manager_after_finalize_does_not_reclose(tmp_path: Path) -> None:
    with BundleWriter(
        tmp_path, "01J8XKQ4V7ZP3N2M9YB6TCCTX2", scenario_ref={}, provenance={}
    ) as writer:
        writer.write_environment({})
        writer.write_scenario({})
        writer.write_graph({})
        writer.finalize(status="COMPLETED")
    assert writer._finalized is True


def test_writer_double_close_is_a_no_op(tmp_path: Path) -> None:
    writer = BundleWriter(tmp_path, "01J8XKQ4V7ZP3N2M9YB6TCDBL0", scenario_ref={}, provenance={})
    writer.close()
    writer.close()  # must not raise


def test_write_after_close_raises(tmp_path: Path) -> None:
    writer = BundleWriter(tmp_path, "01J8XKQ4V7ZP3N2M9YB6TCAFT0", scenario_ref={}, provenance={})
    writer.close()
    with pytest.raises(EvidenceError):
        writer.write_event({"kind": "RUN_STARTED"})


def test_write_policy_state_and_credential_are_counted(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from chainbreak.core.enums import DelegationMechanism, PolicyKind
    from chainbreak.core.models import CredentialRecord, PolicyFingerprint, PolicyStateSnapshot

    writer = BundleWriter(
        tmp_path,
        "01J8XKQ4V7ZP3N2M9YB6TCCNT0",
        scenario_ref={"id": "basic", "compiled_hash": "sha256:" + "a" * 64},
        provenance={"chainbreak_version": "0.1.0a0", "config_fingerprint": "sha256:" + "b" * 64},
    )
    now = datetime(2026, 8, 7, 12, 0, 0, tzinfo=UTC)
    writer.write_policy_state(
        PolicyStateSnapshot(
            snapshot_id="ps_01",
            identity_id="principal",
            taken_at=now,
            monotonic_ns=0,
            policies=(
                PolicyFingerprint(
                    policy_kind=PolicyKind.IDENTITY_INLINE,
                    name_hash="sha256:" + "c" * 64,
                    document_sha256="sha256:" + "d" * 64,
                    statement_count=1,
                    has_explicit_deny=False,
                ),
            ),
        )
    )
    writer.write_credential(
        CredentialRecord(
            credential_id="cred_01",
            identity_id="principal",
            mechanism=DelegationMechanism.DIRECT_ROLE_ASSUMPTION,
            issued_at=now,
            expires_at=now.replace(hour=13),
            requested_duration_s=900,
            granted_duration_s=900,
            session_name_hash="sha256:" + "e" * 64,
            access_key_id_hash="sha256:" + "f" * 64,
        )
    )
    writer.write_environment({})
    writer.write_scenario({})
    writer.write_graph({})
    manifest = writer.finalize(status="COMPLETED")
    assert manifest.counts.policy_snapshots == 1
    assert manifest.counts.credentials == 1


def test_manifest_verify_returns_false_when_unsealed() -> None:
    from chainbreak.evidence.manifest import Manifest

    unsealed = Manifest(
        run_id="x",
        created_at="2026-01-01T00:00:00.000000Z",
        status="RUNNING",
        scenario={},
        provenance={},
    )
    assert manifest_module.verify(GOLDEN_RUN_DIR, unsealed) is False


def test_manifest_verify_returns_false_on_artifact_set_mismatch(tmp_path: Path) -> None:
    incomplete = tmp_path / "incomplete-for-verify"
    shutil.copytree(GOLDEN_RUN_DIR, incomplete)
    (incomplete / "graph.json").unlink()
    manifest = read_manifest(incomplete / "manifest.json")  # still claims graph.json in its root
    assert manifest_module.verify(incomplete, manifest) is False


def test_writer_leaves_usable_partial_evidence_if_never_finalized(tmp_path: Path) -> None:
    """F2: a process killed before ``finalize()`` still leaves readable,
    flushed ``.jsonl`` streams -- simulated here by simply never calling
    ``finalize()`` and reading the raw file back."""
    writer = BundleWriter(
        tmp_path,
        "01J8XKQ4V7ZP3N2M9YB6TCPART",
        scenario_ref={"id": "basic"},
        provenance={"chainbreak_version": "0.1.0a0"},
    )
    from datetime import UTC, datetime

    from chainbreak.core.enums import OutcomeClass, PlanPhase, ProbeKind
    from chainbreak.core.models import Observation, ProbeOutcome, ProbeRequestRecord, ProbeTiming

    writer.write_observation(
        Observation(
            observation_id="obs_0000000000000000000000001",
            run_id="01J8XKQ4V7ZP3N2M9YB6TCPART",
            sequence=0,
            phase=PlanPhase.BASELINE,
            probe_matrix_id="pm_01",
            identity_id="principal",
            identity_ref_hash="sha256:" + "c" * 64,
            capability_id="objectstore.read",
            trial=1,
            trial_count=1,
            request=ProbeRequestRecord(
                probe_kind=ProbeKind.READ_MARKER,
                binding_actions=("fake:read",),
                target_ref_hash="sha256:" + "d" * 64,
                target_namespace="cb-01234567",
                parameters_fingerprint="sha256:" + "e" * 64,
            ),
            timing=ProbeTiming(
                monotonic_start_ns=0, monotonic_end_ns=1, wall_start=datetime.now(UTC)
            ),
            outcome=ProbeOutcome(outcome_class=OutcomeClass.ALLOWED),
            preconditions_verified=True,
        )
    )
    # Simulate a crash: no finalize(), just close what the OS already has
    # buffered (write_observation already flushed per record -- F2).
    writer.close()

    run_dir = tmp_path / "01J8XKQ4V7ZP3N2M9YB6TCPART"
    assert not (run_dir / "manifest.json").exists()
    lines = (run_dir / "observations.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    with pytest.raises(EvidenceError):
        # There is nothing to verify without a manifest -- but the raw
        # observation itself is still valid, readable evidence.
        read_manifest(run_dir / "manifest.json")
