"""Convenience entry point: ``python -m chainbreak.evidence.verify <run_dir>``.

Recomputes the integrity root and compares it against the sealed manifest.
Thin wrapper around :func:`chainbreak.evidence.manifest.verify`; not one of
M6's required modules, just the literal command M06-evidence-pipeline.md's
own verification section names.
"""

from __future__ import annotations

import sys
from pathlib import Path

from chainbreak.evidence.manifest import verify as verify_manifest
from chainbreak.evidence.reader import read_manifest


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m chainbreak.evidence.verify <run_dir>", file=sys.stderr)
        return 2
    run_dir = Path(argv[1])
    manifest = read_manifest(run_dir / "manifest.json")
    ok = verify_manifest(run_dir, manifest)
    if ok:
        print(f"OK: {manifest.run_id} root verified ({manifest.integrity.root})")
        return 0
    print(f"FAILED: {manifest.run_id} integrity root mismatch", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
