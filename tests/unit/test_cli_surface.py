"""S1 (SI-5): no command in the ``chainbreak`` CLI may carry a flag that
bypasses the SafetyGate -- ``--skip-preflight``, ``--no-safety``, ``--force``,
or an equivalent. This is the test that keeps a future contributor from
adding one for convenience (M04-cli-config-safety.md).

Introspection uses ``param_type_name``/``.commands`` duck typing rather than
``isinstance(..., click.Group)``: this environment's installed Typer vendors
its own internal fork (``typer._click``), distinct from the top-level
``click`` package also installed, so ``isinstance`` against the wrong
module silently matches nothing -- duck typing is robust to that either way.

The negative control (milestone's own instruction: add a bypass flag on a
scratch branch and confirm this test catches it) is reproduced here as a
real, always-run assertion against a scratch Typer app built the same way,
rather than a one-off manual experiment that could bit-rot.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import typer

pytestmark = pytest.mark.unit

#: Keyword families a bypass flag would plausibly use. Matched against each
#: option's every spelling (e.g. ``--skip-preflight`` and ``--skip_preflight``
#: alike), case-insensitively, against the flag name only -- not its help
#: text, so this cannot be defeated by wording the flag innocuously while
#: describing the bypass in --help.
_BYPASS_KEYWORDS = re.compile(r"(?i)skip|bypass|override|unsafe|force|ignore|no-safety|disable")


def _all_option_names(command: Any, prefix: str = "") -> list[tuple[str, str]]:
    """Recursively walk a Typer/Click command tree, returning
    ``(command_path, option_flag)`` for every registered *option* (not
    positional argument) anywhere in the tree."""
    results: list[tuple[str, str]] = []
    for param in getattr(command, "params", []):
        if getattr(param, "param_type_name", None) == "option":
            for opt in getattr(param, "opts", []) + getattr(param, "secondary_opts", []):
                results.append((prefix or "<root>", opt))
    for name, sub in getattr(command, "commands", {}).items():
        results.extend(_all_option_names(sub, f"{prefix}{name} "))
    return results


def _bypass_options(command: Any) -> list[tuple[str, str]]:
    return [(path, opt) for path, opt in _all_option_names(command) if _BYPASS_KEYWORDS.search(opt)]


class TestRealCliHasNoBypassFlag:
    def test_no_option_anywhere_in_the_tree_matches_a_bypass_keyword(self):
        from chainbreak.cli.main import app

        root = typer.main.get_group(app)
        offenders = _bypass_options(root)
        assert offenders == [], (
            f"found option(s) that look like a SafetyGate bypass: {offenders}. "
            "SI-5 forbids --skip-preflight, --no-safety, --force, or equivalents "
            "anywhere in the CLI."
        )

    def test_infra_auto_approve_is_not_flagged(self):
        # --auto-approve (infra apply/destroy) is a documented exception:
        # it mirrors `terraform apply -auto-approve`'s non-interactive
        # confirmation convention, distinct from disabling the SafetyGate --
        # infra is not wired to the gate at all yet (stub until M9), and the
        # flag's name does not match any bypass keyword.
        from chainbreak.cli.main import app

        root = typer.main.get_group(app)
        names = {opt for _, opt in _all_option_names(root)}
        assert "--auto-approve" in names
        assert not _BYPASS_KEYWORDS.search("--auto-approve")

    def test_every_command_is_reachable(self):
        # Sanity check on the walker itself: if this count ever drops to 0,
        # the test above would trivially pass for the wrong reason.
        from chainbreak.cli.main import app

        root = typer.main.get_group(app)
        assert len(_all_option_names(root)) >= 5


class TestNegativeControlDetectorCatchesAPlantedBypassFlag:
    """Milestone instruction: add --skip-safety on a scratch branch, confirm
    the test fails. Reproduced as a real fixture rather than a manual,
    undocumented one-off: this class must always find its own planted flag,
    which is proof the detector used above is not vacuously passing."""

    def _scratch_app_with_bypass_flag(self) -> typer.Typer:
        app = typer.Typer()

        @app.command()
        def run(
            skip_safety: bool = typer.Option(False, "--skip-safety"),
        ) -> None:
            raise SystemExit(0)

        return app

    def test_detector_flags_the_planted_option(self):
        scratch = self._scratch_app_with_bypass_flag()
        root = typer.main.get_group(scratch)
        offenders = _bypass_options(root)
        assert offenders != []
        assert any(opt == "--skip-safety" for _, opt in offenders)

    def test_detector_is_silent_on_a_clean_scratch_app(self):
        app = typer.Typer()

        @app.command()
        def run(verbose: bool = typer.Option(False, "--verbose")) -> None:
            raise SystemExit(0)

        root = typer.main.get_group(app)
        assert _bypass_options(root) == []
