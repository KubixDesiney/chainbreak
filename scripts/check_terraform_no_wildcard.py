"""Fail-closed Terraform IAM wildcard-resource check.

The sandbox permits ``Resource = "*"`` only for a statement whose complete
action set is exactly ``sts:GetCallerIdentity``.  This deliberately conservative
scanner rejects ambiguous HCL instead of trying to infer policy safety from
Terraform expressions.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_WILDCARD_RE = re.compile(r"(?:\bResource\b|[\"']Resource[\"'])\s*(?:=|:)\s*[\"']\*[\"']")
_ACTION_RE = re.compile(r"\bAction\b\s*=\s*(?:\[(.*?)\]|\"([^\"]+)\")", re.DOTALL)
_STRING_RE = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')
_ALLOWED_ACTIONS = frozenset({"sts:GetCallerIdentity"})


def _brace_depths(lines: list[str]) -> tuple[list[int], list[int]]:
    before: list[int] = []
    after: list[int] = []
    depth = 0
    for line in lines:
        before.append(depth)
        in_string = False
        escaped = False
        in_comment = False
        index = 0
        while index < len(line):
            char = line[index]
            if in_comment:
                break
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "#" or (char == "/" and index + 1 < len(line) and line[index + 1] == "/"):
                in_comment = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            index += 1
        after.append(depth)
    return before, after


def _object_text(lines: list[str], before: list[int], after: list[int], index: int) -> str:
    target = before[index]
    start = index
    for candidate in range(index, -1, -1):
        if before[candidate] < target and "{" in lines[candidate]:
            start = candidate
            break
    end = index
    for candidate in range(index, len(lines)):
        if candidate > index and after[candidate] < target:
            end = candidate
            break
    return "\n".join(lines[start : end + 1])


def _actions_in(object_text: str) -> frozenset[str] | None:
    matches = list(_ACTION_RE.finditer(object_text))
    if len(matches) != 1:
        return None
    match = matches[0]
    if match.group(1) is not None:
        return frozenset(_STRING_RE.findall(match.group(1)))
    return frozenset({match.group(2)})


def check_file(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    before, after = _brace_depths(lines)
    findings: list[str] = []
    for index, line in enumerate(lines):
        code = line.split("#", 1)[0].split("//", 1)[0]
        if not _WILDCARD_RE.search(code):
            continue
        actions = _actions_in(_object_text(lines, before, after, index))
        if actions != _ALLOWED_ACTIONS:
            findings.append(
                f"{path}:{index + 1}: wildcard Resource is not exclusively sts:GetCallerIdentity"
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args(argv)
    files = sorted(args.root.rglob("*.tf"))
    findings = [finding for path in files for finding in check_file(path)]
    if findings:
        print("Terraform wildcard-resource check: FAIL")
        print("\n".join(findings))
        return 1
    print(f"Terraform wildcard-resource check: PASS ({len(files)} Terraform files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
