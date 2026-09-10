#!/usr/bin/env python3
"""Fail unless the built wheel and sdist carry exactly what a release must carry.

Two distinct regressions this guards against, both observed on v0.1.0:

1. The sdist shipped 744 untracked files from `.claude/worktrees/` -- 4.83 MB,
   48% of the unpacked tarball. Hatchling's default sdist selection is "every
   file under the project root that .gitignore does not match", which includes
   untracked ones, so the published artifact was a function of the builder's
   working directory rather than of the tagged commit. pyproject.toml now
   declares an explicit allowlist; this script is what keeps it honest.

2. Nothing verified the sdist at all. CI built `--wheel` only, so a corpus or
   schema missing from the sdist -- and therefore from any wheel built from it
   downstream -- would not have been caught before upload. PyPI versions are
   immutable, so "caught after upload" is not a recovery path.

Stdlib only, by design: this runs before any publishing tool is installed.

Usage:
    python scripts/check_dist_contents.py dist
"""

from __future__ import annotations

import sys
import tarfile
import zipfile
from collections.abc import Iterable
from pathlib import Path

# Every top-level entry pyproject.toml's [tool.hatch.build.targets.sdist]
# allowlist is expected to produce. A new repository-root directory must be
# added to both places deliberately, or the sdist silently stops carrying it.
_SDIST_TOP_LEVEL = {
    ".dockerignore",
    ".gitattributes",
    # Hatchling always ships the VCS ignore file with an sdist, allowlist or not.
    ".gitignore",
    ".github",
    ".pre-commit-config.yaml",
    "AGENTS.md",
    "ARCHITECTURE.md",
    "AUTHORIZATION_MODEL.md",
    "AWS_PROVIDER_SPEC.md",
    "CAPABILITY_MODEL.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "Dockerfile",
    "EVIDENCE_SCHEMA.md",
    "EXPERIMENT_PROTOCOL.md",
    "LICENSE",
    "Makefile",
    "NOTICE",
    "PKG-INFO",
    "PROJECT_STATUS.md",
    "README.md",
    "REPRODUCIBILITY.md",
    "RESEARCH_METHODOLOGY.md",
    "ROADMAP.md",
    "SCENARIO_SPECIFICATION.md",
    "SCORING_MODEL.md",
    "SECURITY.md",
    "SECURITY_MODEL.md",
    "TESTING.md",
    "THREAT_MODEL.md",
    "chainbreak.example.toml",
    "docs",
    "examples",
    "infra",
    "pyproject.toml",
    "requirements-build.lock",
    "requirements-runtime.lock",
    "requirements.lock",
    "scenarios",
    "schemas",
    "scripts",
    "src",
    "tests",
}

# The corpus and runtime data every distribution must be able to reach.
_SCENARIO_COUNT = 24
_SCHEMA_COUNT = 12  # 11 JSON Schemas + run-index.sql


def _fail(failures: list[str], message: str) -> None:
    failures.append(message)


def _check_sdist(path: Path, failures: list[str]) -> None:
    with tarfile.open(path) as tar:
        names = [m.name for m in tar.getmembers() if m.isfile()]
    if not names:
        _fail(failures, f"{path.name}: contains no files")
        return

    root = names[0].split("/")[0]
    top_level = {n[len(root) + 1 :].split("/")[0] for n in names if n.startswith(f"{root}/")}

    unexpected = sorted(top_level - _SDIST_TOP_LEVEL)
    if unexpected:
        _fail(
            failures,
            f"{path.name}: unexpected top-level entries {unexpected} -- "
            "add them to the sdist allowlist in pyproject.toml and to "
            "_SDIST_TOP_LEVEL here, or exclude them",
        )

    scenarios = [n for n in names if n.startswith(f"{root}/scenarios/") and n.endswith(".yaml")]
    if len(scenarios) != _SCENARIO_COUNT:
        _fail(failures, f"{path.name}: {len(scenarios)} scenarios, expected {_SCENARIO_COUNT}")

    schemas = [n for n in names if n.startswith(f"{root}/schemas/")]
    if len(schemas) != _SCHEMA_COUNT:
        _fail(failures, f"{path.name}: {len(schemas)} schema files, expected {_SCHEMA_COUNT}")

    for required in (
        f"{root}/src/chainbreak/capabilities/catalog.yaml",
        f"{root}/src/chainbreak/py.typed",
        f"{root}/pyproject.toml",
    ):
        if required not in names:
            _fail(failures, f"{path.name}: missing {required}")


def _check_wheel(path: Path, failures: list[str]) -> None:
    with zipfile.ZipFile(path) as whl:
        names = whl.namelist()

    scenarios = [
        n
        for n in names
        if n.startswith("chainbreak/_packaged_data/scenarios/") and n.endswith(".yaml")
    ]
    if len(scenarios) != _SCENARIO_COUNT:
        _fail(failures, f"{path.name}: {len(scenarios)} scenarios, expected {_SCENARIO_COUNT}")

    schemas = [n for n in names if n.startswith("chainbreak/_packaged_data/schemas/")]
    if len(schemas) != _SCHEMA_COUNT:
        _fail(failures, f"{path.name}: {len(schemas)} schema files, expected {_SCHEMA_COUNT}")

    for required in ("chainbreak/capabilities/catalog.yaml", "chainbreak/py.typed"):
        if required not in names:
            _fail(failures, f"{path.name}: missing {required}")

    # A wheel is an install target, not a source archive: the test suite and any
    # editor/agent scratch directory belong nowhere near it.
    unwanted = ("tests/", ".claude/", "scenarios/", "schemas/")
    strays = sorted(n for n in names if n.startswith(unwanted))
    if strays:
        _fail(failures, f"{path.name}: unexpected top-level payload {strays[:5]}")


def _dists(dist_dir: Path) -> tuple[list[Path], list[Path]]:
    return sorted(dist_dir.glob("*.tar.gz")), sorted(dist_dir.glob("*.whl"))


def main(argv: Iterable[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    dist_dir = Path(args[0]) if args else Path("dist")

    sdists, wheels = _dists(dist_dir)
    failures: list[str] = []

    if not sdists:
        _fail(failures, f"{dist_dir}: no sdist (*.tar.gz) found")
    if not wheels:
        _fail(failures, f"{dist_dir}: no wheel (*.whl) found")

    for sdist in sdists:
        _check_sdist(sdist, failures)
    for wheel in wheels:
        _check_wheel(wheel, failures)

    if failures:
        print("distribution contents check failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    checked = ", ".join(p.name for p in (*sdists, *wheels))
    print(f"distribution contents OK: {checked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
