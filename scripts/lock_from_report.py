#!/usr/bin/env python3
"""Convert a `pip install --report` JSON document into requirements.lock (T-14).

Not pip-tools/pip-compile: pip-tools 7.6.0 is incompatible with the pip
version this repo currently develops against (`ImportError` on
`pip._internal.utils.compat.stdlib_pkgs`, a pip-internal API pip-tools
depends on that has since moved). `pip install --report` is pip's own,
already-stable JSON report of exactly what it resolved and would install,
including each artifact's sha256 -- this script just reshapes that into the
`name==version --hash=sha256:...` format `pip install --require-hashes`
expects.

`chainbreak` itself is excluded from the output: it is the local package
under test (installed separately, with `pip install --no-deps -e .`), not a
pinned third-party download, and has no hash to pin regardless (it is
installed from the working directory, not a distributed artifact).

Usage:
    docker run --rm -v "$PWD:/repo:ro" -w /repo \\
      python:3.12-slim@sha256:dd29372629eeba2dd003fd9e9d35a5b8236c44727875a0364254b5127af88e65 \\
      bash -c \\
      "pip install --no-cache-dir '.[dev,aws,report,analysis]' \\
       --report /tmp/report.json && cat /tmp/report.json" > report.json
    python scripts/lock_from_report.py report.json requirements.lock

Run inside a Linux container (not directly on a development machine) so the
resolved wheels -- and therefore their hashes -- match what CI's
ubuntu-latest runners actually install, rather than whatever platform this
script happens to run on.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HEADER = """\
# Hash-locked dependency closure for `pip install .[dev,aws,report,analysis]` (T-14).
#
# Generated inside a Linux python:3.12-slim container (matching CI's
# ubuntu-latest / cp312 target) via `pip install --report`, then
# scripts/lock_from_report.py. See that script's docstring for the exact
# regeneration command. Do not hand-edit -- regenerate instead.
#
# chainbreak itself is intentionally excluded -- it is the local package
# under test, installed separately with `pip install --no-deps -e .`, not a
# pinned third-party download.
#
# `pip install --require-hashes -r requirements.lock` in CI (security job,
# ci.yml) is what proves every hash below still resolves.

"""


def build_lockfile(report: dict) -> str:
    entries: list[tuple[str, str, str]] = []
    for item in report["install"]:
        name = item["metadata"]["name"]
        if name.lower() == "chainbreak":
            continue
        version = item["metadata"]["version"]
        hashes = item.get("download_info", {}).get("archive_info", {}).get("hashes", {})
        sha256 = hashes.get("sha256")
        if not sha256:
            raise SystemExit(
                f"no sha256 hash recorded for {name}=={version}; refusing to write a lockfile "
                "with an unpinned entry"
            )
        entries.append((name.lower(), version, sha256))

    entries.sort(key=lambda entry: entry[0])
    body = "\n".join(
        f"{name}=={version} \\\n    --hash=sha256:{sha256}" for name, version, sha256 in entries
    )
    return _HEADER + body + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="pip install --report JSON document")
    parser.add_argument("output", type=Path, help="destination lockfile path")
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    lockfile_text = build_lockfile(report)
    args.output.write_text(lockfile_text, encoding="utf-8", newline="\n")
    package_count = lockfile_text.count("--hash=")
    print(f"wrote {package_count} pinned packages to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
