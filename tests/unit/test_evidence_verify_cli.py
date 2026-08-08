"""``python -m chainbreak.evidence.verify`` -- the milestone's own literal
verification command (M06-evidence-pipeline.md)."""

from __future__ import annotations

from pathlib import Path

import pytest

from chainbreak.evidence import verify as verify_cli

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_RUN_DIR = (
    REPO_ROOT / "tests" / "fixtures" / "bundles" / "golden" / "01J8XKQ4V7ZP3N2M9YB6TCGOLD"
)
TAMPERED_RUN_DIR = (
    REPO_ROOT / "tests" / "fixtures" / "bundles" / "tampered" / "01J8XKQ4V7ZP3N2M9YB6TCGOLD"
)


def test_main_returns_zero_for_a_verified_bundle(capsys: pytest.CaptureFixture[str]) -> None:
    assert verify_cli.main(["verify", str(GOLDEN_RUN_DIR)]) == 0
    assert "OK" in capsys.readouterr().out


def test_main_returns_one_for_a_tampered_bundle(capsys: pytest.CaptureFixture[str]) -> None:
    assert verify_cli.main(["verify", str(TAMPERED_RUN_DIR)]) == 1
    assert "FAILED" in capsys.readouterr().err


def test_main_returns_two_on_bad_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert verify_cli.main(["verify"]) == 2
    assert "usage" in capsys.readouterr().err
