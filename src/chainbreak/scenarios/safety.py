"""Scenario safety validation -- stage 5 of the validation pipeline (SI-11).

Runs even in offline mode and cannot be skipped. This is what makes an
untrusted scenario file a *parsing* problem rather than a *security* problem.

Two concerns:

1. The YAML loader must not be able to construct arbitrary Python objects, and
   must not be susceptible to alias-expansion amplification.
2. A scenario document must contain no literal ARN, account ID, or region.
   Scenarios reference infrastructure indirectly through Terraform output names
   (SCENARIO_SPECIFICATION.md section 3), which is what makes them safe to
   publish (threat T-13).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

import yaml

from chainbreak.core.errors import ScenarioSafetyError, ScenarioSyntaxError

MAX_DOCUMENT_BYTES: Final = 1 << 20  # 1 MiB
MAX_NODE_COUNT: Final = 20_000
MAX_NESTING_DEPTH: Final = 32

_ARN_RE: Final = re.compile(r"\barn:aws[a-z-]*:", re.IGNORECASE)
_ACCOUNT_ID_RE: Final = re.compile(r"(?<!\d)\d{12}(?!\d)")
_REGION_RE: Final = re.compile(
    r"\b(?:us|eu|ap|sa|ca|me|af|il|mx)-(?:north|south|east|west|central|northeast|"
    r"northwest|southeast|southwest)-[1-9]\b",
    re.IGNORECASE,
)
_URL_RE: Final = re.compile(r"\bhttps?://(?!(?:example|localhost)\b)", re.IGNORECASE)


class StrictScenarioLoader(yaml.SafeLoader):
    """SafeLoader that rejects every non-standard tag outright.

    ``SafeLoader`` already refuses ``!!python/object``, but it raises a
    ConstructorError that some callers swallow. Rejecting explicitly gives a
    clear, attributable error and closes custom-tag surface added by plugins.
    """


def _reject_tag(loader: StrictScenarioLoader, suffix: str, node: yaml.Node) -> Any:
    raise ScenarioSafetyError(
        f"unsupported YAML tag '!{suffix}': scenarios are data, not code",
        tag=suffix,
    )


StrictScenarioLoader.add_multi_constructor("!", _reject_tag)  # type: ignore[no-untyped-call]
StrictScenarioLoader.add_multi_constructor("tag:", _reject_tag)  # type: ignore[no-untyped-call]


def load_scenario_yaml(path: Path) -> dict[str, Any]:
    """Load a scenario document with every structural guard applied."""
    raw = path.read_bytes()
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ScenarioSafetyError(
            f"scenario exceeds {MAX_DOCUMENT_BYTES} bytes", size=len(raw), path=str(path)
        )

    text = raw.decode("utf-8")
    assert_no_literal_infrastructure(text, source=str(path))

    try:
        document = yaml.load(text, Loader=StrictScenarioLoader)  # noqa: S506 # nosec B506
    except yaml.YAMLError as exc:
        raise ScenarioSyntaxError(f"invalid YAML in {path}: {exc}") from exc

    if not isinstance(document, dict):
        raise ScenarioSyntaxError(f"{path}: scenario document must be a mapping")

    _assert_bounded(document, path=str(path))
    return document


def assert_no_literal_infrastructure(text: str, *, source: str) -> None:
    """Reject literal ARNs, account IDs, regions and external URLs.

    A scenario that names real infrastructure both leaks the operator's
    environment when shared and bypasses the Terraform-output indirection that
    the namespace guarantees depend on.
    """
    findings: list[str] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.split("#", 1)[0]
        if _ARN_RE.search(stripped):
            findings.append(f"line {line_number}: literal ARN")
        if _ACCOUNT_ID_RE.search(stripped):
            findings.append(f"line {line_number}: 12-digit account id")
        if _REGION_RE.search(stripped):
            findings.append(f"line {line_number}: literal region name")
        if _URL_RE.search(stripped):
            findings.append(f"line {line_number}: external URL")

    if findings:
        raise ScenarioSafetyError(
            f"{source}: scenarios must not name real infrastructure "
            f"({len(findings)} occurrence(s))",
            source=source,
            findings=findings[:20],
        )


def _assert_bounded(node: Any, *, path: str) -> None:
    """Guard against amplification and pathological nesting."""
    count = 0
    stack: list[tuple[Any, int]] = [(node, 0)]

    while stack:
        current, depth = stack.pop()
        count += 1
        if count > MAX_NODE_COUNT:
            raise ScenarioSafetyError(
                f"{path}: document exceeds {MAX_NODE_COUNT} nodes (possible alias amplification)",
                source=path,
            )
        if depth > MAX_NESTING_DEPTH:
            raise ScenarioSafetyError(
                f"{path}: nesting deeper than {MAX_NESTING_DEPTH}", source=path
            )
        if isinstance(current, dict):
            stack.extend((value, depth + 1) for value in current.values())
        elif isinstance(current, list):
            stack.extend((value, depth + 1) for value in current)
