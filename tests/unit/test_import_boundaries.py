"""Structural enforcement of ARCH-1, the layer dependency rule (ARCHITECTURE.md section 2).

Deliberately independent of the ``import-linter`` configuration in ``pyproject.toml``
(exercised separately by ``lint-imports`` in CI's ``boundaries`` job): this file walks
the AST directly so the invariant is provable even if the import-linter contracts
themselves are misconfigured.
"""

from __future__ import annotations

import ast
import os
import re
import warnings
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "chainbreak"

_PLANTED_VIOLATION_NAME = "_zz_planted_violation.py"


def _safe_unlink(path: Path) -> None:
    """Best-effort removal of a planted-violation fixture file.

    A denied unlink (e.g. a filesystem where unlink is refused) must not fail a test
    whose assertion already ran -- that would fail the test for the wrong reason. A
    file that survives is instead caught loudly by ``_warn_on_leftover_planted_violations``
    rather than being left to silently pollute a later ``_iter_source_files`` scan.
    """
    try:
        path.unlink()
    except OSError as exc:
        warnings.warn(
            f"Failed to remove planted-violation fixture {path}: {exc}. It was not "
            "deleted and will be flagged as leftover debris the next time this module "
            "is collected.",
            stacklevel=2,
        )


def _leftover_planted_violation_files() -> list[Path]:
    return sorted(SRC_ROOT.rglob(_PLANTED_VIOLATION_NAME))


def _warn_on_leftover_planted_violations() -> None:
    """Loudly flag planted-violation fixtures a prior failed teardown left behind.

    Without this check, a leftover file under ``src/`` is picked up silently by
    ``_iter_source_files`` and misreported by the checks above as a genuine boundary
    violation, rather than being diagnosed as stale test debris from an earlier run.
    """
    leftover = _leftover_planted_violation_files()
    if leftover:
        warnings.warn(
            "Leftover import-boundary planted-violation file(s) from a previous test "
            f"session's failed teardown were found and were NOT removed: "
            f"{[str(p) for p in leftover]}. Delete them manually -- until then, the "
            "checks in this module may report violations that do not exist in the "
            "real source tree.",
            stacklevel=2,
        )


# Run at collection time (session start for this module) rather than only from within
# a test, so a leftover file is surfaced before the ordinary boundary checks above run
# and potentially misattribute it.
_warn_on_leftover_planted_violations()

# Source files allowed to name AWS service/action strings literally. Scoped to the
# implementation tree only -- design docs (ARCHITECTURE.md, THREAT_MODEL.md, ...) and
# the test corpus that exercises the detector are expected to discuss AWS by name and
# are not part of this check. ``scenarios/safety.py`` is the provider-agnostic literal-
# infrastructure detector (SI-11): it must recognise the ARN shape to reject it, which
# is a different thing from the rest of the engine depending on AWS semantics.
# ``evidence/redaction.py`` and ``evidence/export.py`` are the same category of
# exception for SI-1/T-13 (M6): redacting or scrubbing an ARN-shaped identifier
# that a provider response put into evidence requires recognising that shape,
# regardless of which provider produced it.
_AWS_STRING_ALLOWED_PATHS: tuple[str, ...] = (
    "src/chainbreak/providers/",
    "src/chainbreak/scenarios/safety.py",
    "src/chainbreak/evidence/redaction.py",
    "src/chainbreak/evidence/export.py",
    "AWS_PROVIDER_SPEC.md",
)

_AWS_SERVICE_STRING_RE = re.compile(r"(s3:|arn:aws|dynamodb:|sts:)")


def _module_name(path: Path) -> str:
    rel = path.relative_to(SRC_ROOT.parent).with_suffix("")
    return ".".join(rel.parts)


def _iter_source_files(*, under: Path | None = None) -> list[Path]:
    root = under or SRC_ROOT
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _top_level_imports(path: Path) -> set[str]:
    """Every dotted module named in an ``import`` or ``from ... import`` statement."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


class TestCoreImportsNothingFromChainbreak:
    """`core/` is the foundation layer: it must not import any other chainbreak package."""

    def test_core_modules_have_no_internal_chainbreak_imports(self) -> None:
        offenders: dict[str, set[str]] = {}
        for path in _iter_source_files(under=SRC_ROOT / "core"):
            chainbreak_imports = {
                name
                for name in _top_level_imports(path)
                if name == "chainbreak" or name.startswith("chainbreak.")
            }
            non_core = {
                name
                for name in chainbreak_imports
                if not (name == "chainbreak.core" or name.startswith("chainbreak.core."))
            }
            if non_core:
                offenders[str(path.relative_to(REPO_ROOT))] = non_core

        assert not offenders, f"core/ must not import outside chainbreak.core: {offenders}"


class TestGraphImportsOnlyCore:
    """`graph/` may depend on `chainbreak.core` and nothing else in chainbreak."""

    def test_graph_modules_only_import_core(self) -> None:
        graph_dir = SRC_ROOT / "graph"
        if not graph_dir.exists() or not _iter_source_files(under=graph_dir):
            pytest.skip("graph/ has no modules yet")

        offenders: dict[str, set[str]] = {}
        for path in _iter_source_files(under=graph_dir):
            chainbreak_imports = {
                name
                for name in _top_level_imports(path)
                if name == "chainbreak" or name.startswith("chainbreak.")
            }
            disallowed = {
                name
                for name in chainbreak_imports
                if not (
                    name == "chainbreak.core"
                    or name.startswith("chainbreak.core.")
                    or name == "chainbreak.graph"
                    or name.startswith("chainbreak.graph.")
                )
            }
            if disallowed:
                offenders[str(path.relative_to(REPO_ROOT))] = disallowed

        assert not offenders, f"graph/ may only import chainbreak.core: {offenders}"


class TestBoto3ConfinedToAwsProvider:
    """Nothing outside `providers/aws/` may import boto3 or botocore."""

    def test_no_boto3_outside_providers_aws(self) -> None:
        aws_provider_dir = SRC_ROOT / "providers" / "aws"
        offenders: dict[str, set[str]] = {}

        for path in _iter_source_files():
            if aws_provider_dir in path.parents or path == aws_provider_dir:
                continue
            boto_imports = {
                name
                for name in _top_level_imports(path)
                if name == "boto3"
                or name.startswith("boto3.")
                or name == "botocore"
                or name.startswith("botocore.")
            }
            if boto_imports:
                offenders[str(path.relative_to(REPO_ROOT))] = boto_imports

        assert not offenders, f"boto3/botocore is confined to providers/aws/: {offenders}"


class TestNoLiteralAwsServiceStringsOutsideProviders:
    """No AWS action-string prefix outside `providers/` in the implementation tree.

    Scoped to ``src/chainbreak/**`` -- see the rationale on ``_AWS_STRING_ALLOWED_PATHS``
    for why docs and tests are out of scope for this particular check.
    """

    def test_no_aws_service_strings_outside_allowed_paths(self) -> None:
        offenders: dict[str, list[str]] = {}

        for path in _iter_source_files():
            rel = path.relative_to(REPO_ROOT).as_posix()
            is_allowed = any(
                rel.startswith(allowed) or rel == allowed for allowed in _AWS_STRING_ALLOWED_PATHS
            )
            if is_allowed:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            hits = _AWS_SERVICE_STRING_RE.findall(text)
            if hits:
                offenders[rel] = sorted(set(hits))

        assert not offenders, (
            f"AWS service strings must live only in providers/ or AWS_PROVIDER_SPEC.md: {offenders}"
        )


class TestPlantedViolationsAreDetected:
    """Negative control: the checks above must actually be able to fail."""

    def test_core_check_fails_on_a_planted_cross_import(self, tmp_path: Path) -> None:
        planted = SRC_ROOT / "core" / "_zz_planted_violation.py"
        planted.write_text("from chainbreak.graph import something\n", encoding="utf-8")
        try:
            chainbreak_imports = {
                name
                for name in _top_level_imports(planted)
                if name == "chainbreak" or name.startswith("chainbreak.")
            }
            non_core = {
                name
                for name in chainbreak_imports
                if not (name == "chainbreak.core" or name.startswith("chainbreak.core."))
            }
            assert non_core, "planted violation should have been detected"
        finally:
            _safe_unlink(planted)

    def test_boto3_check_fails_on_a_planted_import(self, tmp_path: Path) -> None:
        planted = SRC_ROOT / "graph" / "_zz_planted_violation.py"
        planted.write_text("import boto3\n", encoding="utf-8")
        try:
            boto_imports = {
                name
                for name in _top_level_imports(planted)
                if name == "boto3" or name.startswith("boto3.")
            }
            assert boto_imports, "planted boto3 import should have been detected"
        finally:
            _safe_unlink(planted)

    def test_denied_unlink_warns_instead_of_failing_and_leftover_is_reported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A filesystem that refuses unlink must not fail a test whose assertion already
        passed, and the file it leaves behind must be surfaced as a loud warning rather
        than silently absorbed into a later boundary scan."""
        planted = SRC_ROOT / "core" / "_zz_planted_violation.py"
        planted.write_text("from chainbreak.graph import something\n", encoding="utf-8")

        def _deny_unlink(path: object, *args: object, **kwargs: object) -> None:
            raise PermissionError("simulated: unlink denied")

        monkeypatch.setattr(os, "unlink", _deny_unlink)

        try:
            chainbreak_imports = {
                name
                for name in _top_level_imports(planted)
                if name == "chainbreak" or name.startswith("chainbreak.")
            }
            non_core = {
                name
                for name in chainbreak_imports
                if not (name == "chainbreak.core" or name.startswith("chainbreak.core."))
            }

            with pytest.warns(UserWarning, match="Failed to remove planted-violation fixture"):
                _safe_unlink(planted)

            assert non_core, "the detection assertion must still pass despite the denied unlink"
            assert planted.exists(), "a denied unlink must leave the file in place, not raise"

            with pytest.warns(UserWarning, match="Leftover import-boundary planted-violation"):
                _warn_on_leftover_planted_violations()
        finally:
            monkeypatch.undo()
            if planted.exists():
                planted.unlink()
