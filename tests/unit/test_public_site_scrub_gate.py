"""The publication gate in ``scripts/verify_public_site_scrub.py`` must fail
on the things it exists to catch, not merely pass on the things that are
already clean.

The regression that motivated this gate is reproduced verbatim below: the
committed ``aws-m17-block04-excluded-scrubbed-sample.tar.gz`` carried a live
``cb-`` benchmark namespace in ``environment.json`` and ``observations.jsonl``
because the archive was built one day before ``NAMESPACE_PATTERN`` was added
to the exporter's ``_scrub_text``. A gate that would not have caught that is
not a gate, so every exemption it grants is tested against it here.
"""

from __future__ import annotations

import importlib.util
import sys
import tarfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_public_site_scrub.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("verify_public_site_scrub", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate()

_LIVE_NAMESPACE = "cb-3daed833"
_LIVE_ARN = "arn:aws:iam::314159265358:role/cb-live-agent"
_LIVE_HOSTNAME = "sts.eu-west-3.amazonaws.com"


def _scan(tmp_path: Path, name: str, body: str, **kwargs):
    target = tmp_path / name
    target.write_text(body, encoding="utf-8")
    hits, _scanned, _skipped, _exempt = gate.scan([target], repo_root=tmp_path, **kwargs)
    return hits


@pytest.mark.parametrize(
    ("name", "body", "klass"),
    [
        ("evidence.json", f'{{"namespace":"{_LIVE_NAMESPACE}"}}', "namespace"),
        ("report.html", f"<p>role {_LIVE_ARN}</p>", "arn"),
        ("report.html", f"<p>endpoint {_LIVE_HOSTNAME}</p>", "hostname"),
        ("evidence.json", '{"account_ref":"314159265358"}', "account_id"),
        ("evidence.json", '{"session_name":"cb-3daed833-session-abc"}', "session_name"),
        ("evidence.json", '{"policy_document":"{\\"Effect\\":\\"Allow\\"}"}', "policy_document"),
        ("creds.jsonl", '{"key":"AKIAIOSFODNN7EXAMPLE"}', "aws_access_key_id"),
    ],
)
def test_gate_blocks_each_identifier_class(
    tmp_path: Path, name: str, body: str, klass: str
) -> None:
    hits = _scan(tmp_path, name, body)
    assert hits, f"{klass} was not caught"
    assert any(hit.klass == klass for hit in hits), [hit.klass for hit in hits]


def test_gate_blocks_the_exact_block04_regression(tmp_path: Path) -> None:
    """The real shape: a live namespace inside a .tar.gz member, which the
    scrubber's own entry point cannot even open because the bundle's manifest
    no longer verifies."""
    bundle = tmp_path / "sample.tar.gz"
    payload = (
        b'{"account_ref":"<REDACTED_ACCOUNT>","namespace":"' + _LIVE_NAMESPACE.encode() + b'",'
        b'"provider":"aws","region":"eu-west-3"}'
    )
    with tarfile.open(bundle, "w:gz") as tar:
        info = tarfile.TarInfo("01ABC/bundle/environment.json")
        info.size = len(payload)
        import io

        tar.addfile(info, io.BytesIO(payload))

    hits, _s, _k, _e = gate.scan([bundle], repo_root=tmp_path)
    assert [hit.klass for hit in hits] == ["namespace"]
    assert "environment.json" in hits[0].member


def test_entity_encoded_identifier_cannot_hide(tmp_path: Path) -> None:
    """An ARN written with HTML entities renders perfectly in a browser but is
    invisible to a raw-byte regex."""
    encoded = _LIVE_ARN.replace(":", "&#58;")
    hits = _scan(tmp_path, "report.html", f"<p>{encoded}</p>")
    assert any(hit.klass == "arn" for hit in hits)
    assert any("entity-decoded" in hit.member for hit in hits)


def test_redaction_placeholders_are_not_leaks(tmp_path: Path) -> None:
    body = '{"namespace":"cb-00000000","account_ref":"<REDACTED_ACCOUNT>"}'
    assert _scan(tmp_path, "evidence.json", body) == []


def test_digest_interior_digits_are_not_an_account_id(tmp_path: Path) -> None:
    body = (
        '{"fingerprint":"sha256:c420b269517eb743075d384a0c876865107812f6e1e0894d8a996ba4ccde4360"}'
    )
    assert _scan(tmp_path, "evidence.json", body) == []


def test_url_paths_are_not_credentials(tmp_path: Path) -> None:
    body = '<a href="https://github.com/KubixDesiney/chainbreak/blob/main/EVIDENCE_SCHEMA.md">x</a>'
    assert _scan(tmp_path, "index.html", body) == []


def test_fake_synthetic_exemption_never_covers_a_namespace(tmp_path: Path) -> None:
    """--allow-fake-synthetic relaxes account_id only. A live namespace must
    still block, or the flag would have hidden the block04 regression."""
    body = f'{{"namespace":"{_LIVE_NAMESPACE}","credential_id":"cred_fake_1729_000000000001"}}'
    hits = _scan(tmp_path, "evidence.json", body, allow_fake_synthetic=True)
    assert [hit.klass for hit in hits] == ["namespace"]


def test_committed_examples_stay_clean() -> None:
    """Regression guard on the repository itself: the archives and reports in
    examples/reports must remain publishable."""
    repo = _SCRIPT.parents[1]
    hits, scanned, _skipped, _exempt = gate.scan(
        [repo / "examples" / "reports"], repo_root=repo, allow_fake_synthetic=True
    )
    assert scanned, "nothing was scanned; the examples directory moved"
    assert hits == [], [hit.render() for hit in hits]
