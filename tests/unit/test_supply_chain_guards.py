"""Negative controls for release and CI supply-chain guards."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "scripts" / "check_github_action_pins.py"


def test_all_repository_actions_are_sha_pinned() -> None:
    result = subprocess.run(
        [sys.executable, str(GUARD), str(REPO_ROOT / ".github" / "workflows")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_action_pin_guard_rejects_unpinned_actions(tmp_path: Path) -> None:
    workflow = tmp_path / "bad.yml"
    workflow.write_text(
        "jobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(GUARD), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "actions/checkout@v4" in result.stderr


def test_action_pin_guard_does_not_exempt_hashicorp_or_actions(tmp_path: Path) -> None:
    workflow = tmp_path / "bad.yml"
    workflow.write_text(
        "jobs:\n  test:\n    steps:\n"
        "      - uses: actions/checkout@main\n"
        "      - uses: hashicorp/setup-terraform@v3\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(GUARD), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "actions/checkout@main" in result.stderr
    assert "hashicorp/setup-terraform@v3" in result.stderr
