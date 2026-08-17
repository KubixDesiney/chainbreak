#!/usr/bin/env python3
"""Fail unless every workflow action reference is pinned to a full commit SHA."""

from __future__ import annotations

import re
import sys
from pathlib import Path

_USES = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)")
_SHA = re.compile(r"@[0-9a-f]{40}$")


def unpinned_actions(workflows: Path) -> list[str]:
    failures: list[str] = []
    for path in sorted((*workflows.glob("*.yml"), *workflows.glob("*.yaml"))):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = _USES.match(line)
            if match and not _SHA.search(match.group(1)):
                failures.append(f"{path}:{line_number}: {match.group(1)}")
    return failures


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    workflows = Path(args[0]) if args else Path(".github/workflows")
    failures = unpinned_actions(workflows)
    if failures:
        print("unpinned GitHub Actions:", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"all workflow actions are SHA-pinned under {workflows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
