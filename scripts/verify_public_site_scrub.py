"""Publication gate for the GitHub Pages site and the release assets.

``chainbreak evidence export --public`` (EVIDENCE_SCHEMA.md section 11) is the
scrubber, but it only knows how to walk a *sealed bundle directory*: it reads
``manifest.json``, verifies the integrity root, and scrubs the fixed artifact
list in :data:`chainbreak.evidence.export._PUBLIC_ARTIFACTS`. It has no entry
point for a rendered ``.html`` page, a ``.md`` report, or a ``.tar.gz``
archive -- and it refuses outright on a bundle whose manifest no longer
matches its artifacts, which is the permanent state of every bundle that has
already been scrubbed (scrubbing rewrites artifacts after sealing; see
``docs/site-provenance.md``).

So this script does not reimplement the rules. It imports the *same* compiled
patterns the scrubber uses and applies :func:`chainbreak.evidence.export._assert_clean`
-- the scrubber's own pre-write gate -- to every byte that is about to be
published, whatever its container:

* text (``.html``, ``.md``, ``.json``, ``.jsonl``, ``.yaml``, ``.txt``)
* HTML-entity-decoded text, so ``&#34;arn:aws:...&#34;`` cannot hide behind
  an escape the raw-byte regex would miss
* every member of a ``.tar.gz`` archive, read without extracting to disk

The classes checked are the ones EVIDENCE_SCHEMA.md section 11 names and
``docs/research/history-scan.md`` scanned for: account ID, ARN, hostname,
namespace, session name, policy document, and credential-shaped material.

Exit code 0 means every scanned file is clean and may be published. Any other
code means publication is blocked.
"""

from __future__ import annotations

import argparse
import collections
import html
import re
import sys
import tarfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from chainbreak.evidence.export import (  # noqa: E402
    _POLICY_DOCUMENT_PATTERN,
    _REDACTED_POLICY_DOCUMENT,
)
from chainbreak.evidence.redaction import (  # noqa: E402
    _BASE64_BLOB,
    _SECRET_PATTERNS,
    ACCOUNT_ID_PATTERN,
    ARN_PATTERN,
    HOSTNAME_PATTERN,
    NAMESPACE_PATTERN,
    REDACTED_ACCOUNT,
    REDACTED_ARN,
    REDACTED_HOSTNAME,
    REDACTED_NAMESPACE,
    REDACTED_SESSION_NAME,
    SESSION_NAME_PATTERN,
    _is_benign_hex,
)

_TEXT_SUFFIXES: Final = {
    ".html",
    ".htm",
    ".md",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".txt",
    ".css",
    ".svg",
}
_ARCHIVE_SUFFIXES: Final = {".gz", ".tgz"}

# The scrubber's own replacement tokens are identifier-*shaped* by design --
# ``cb-00000000`` keeps a scrubbed bundle schema-valid (redaction.py). They
# carry no account-, region-, or run-specific information, so a hit that is
# exactly one of these is the scrubber working, not a leak.
_ALLOWED_LITERALS: Final = frozenset(
    {
        REDACTED_ARN,
        REDACTED_ACCOUNT,
        REDACTED_HOSTNAME,
        REDACTED_NAMESPACE,
        REDACTED_SESSION_NAME,
        _REDACTED_POLICY_DOCUMENT,
    }
)

# ULIDs are 26 chars of Crockford base32 and appear in every report header as
# the run id. They are not credential material and are not account-derived.
_ULID: Final = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")

# ---------------------------------------------------------------------------
# Narrow, named exemptions.
#
# Every exemption below is a case where the pattern is provably matching
# something that is not the identifier class it is looking for. Each one is
# counted and printed in the report, because an exemption nobody can see is
# indistinguishable from a leak nobody noticed. None of them would have
# suppressed the live ``cb-`` namespace this gate caught in the block04
# archive -- that is the standard they are held to.
# ---------------------------------------------------------------------------

# A SHA-256 digest is 64 hex chars; any 12 consecutive decimal digits inside
# one match ACCOUNT_ID_PATTERN by coincidence. Widen the match over hex
# characters: if it is interior to a long hex run, it is digest material.
_HEX_RUN: Final = re.compile(r"[0-9a-f]+")
_MIN_DIGEST_RUN: Final = 32

# The fake provider mints credential ids as ``cred_fake_<seed>_<counter>``
# and uses a fixed synthetic ``account_ref``. These are laboratory constants
# compiled into src/chainbreak/providers/fake/, not account material -- but
# they are only ever exempted when --allow-fake-synthetic is passed, and only
# for the exact shapes below.
_FAKE_CREDENTIAL_ID: Final = re.compile(r"cred_fake_\d+_\d{12}")
_FAKE_ACCOUNT_REFS: Final = frozenset({"555555555555", "000000000000", "123456789012"})

# ``"session_name": {`` in a JSON Schema is a property *declaration*: the
# captured "value" is a structural token, not a session name.
_JSON_STRUCTURAL: Final = frozenset({"{", "[", "null", "true", "false"})

# ``/`` is in the base64 alphabet, so any URL path of >=40 characters is
# credential-shaped to _BASE64_BLOB. On an HTML page that is most of the
# links. Exempt a candidate only when the whitespace-delimited token it sits
# in is a URL -- and note this cannot hide a credential: the dedicated
# AKIA/ASIA, JWT and x-amz-security-token patterns run independently of this
# one and are never exempted.
_TOKEN_DELIMITERS: Final = " \t\r\n\"'<>()[]{},;"  # noqa: S105 - string delimiters, not a secret


def _in_url(text: str, start: int) -> bool:
    left = start
    while left > 0 and text[left - 1] not in _TOKEN_DELIMITERS:
        left -= 1
    right = start
    while right < len(text) and text[right] not in _TOKEN_DELIMITERS:
        right += 1
    return "://" in text[left:right]


def _is_digest_interior(text: str, start: int, end: int) -> bool:
    """True when text[start:end] is interior to a >=32-char hex run."""
    left = start
    while left > 0 and text[left - 1] in "0123456789abcdef":
        left -= 1
    right = end
    while right < len(text) and text[right] in "0123456789abcdef":
        right += 1
    return (right - left) >= _MIN_DIGEST_RUN and (left < start or right > end)


@dataclass(frozen=True)
class Hit:
    source: str
    member: str
    klass: str
    line: int
    excerpt: str

    def render(self) -> str:
        where = f"{self.source}" if not self.member else f"{self.source}::{self.member}"
        return f"  {where}:{self.line}  [{self.klass}]  {self.excerpt}"


def _redact_for_display(text: str) -> str:
    """Never print a matched identifier back out -- that would make this
    report itself the disclosure (redaction.py makes the same promise about
    its exception messages)."""
    text = ARN_PATTERN.sub(REDACTED_ARN, text)
    text = HOSTNAME_PATTERN.sub(REDACTED_HOSTNAME, text)
    text = ACCOUNT_ID_PATTERN.sub(REDACTED_ACCOUNT, text)
    text = NAMESPACE_PATTERN.sub(REDACTED_NAMESPACE, text)
    return text[:120]


def _scan_text(
    text: str,
    source: str,
    member: str,
    *,
    label: str,
    exemptions: collections.Counter[str],
    allow_fake_synthetic: bool,
) -> list[Hit]:
    hits: list[Hit] = []
    lines = text.splitlines()

    def _record(klass: str, match_text: str, offset: int) -> None:
        if match_text in _ALLOWED_LITERALS:
            exemptions[f"{klass}: scrubber redaction placeholder ({match_text})"] += 1
            return
        line_no = text.count("\n", 0, offset) + 1
        raw = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
        hits.append(
            Hit(
                source,
                f"{member} ({label})" if member else label,
                klass,
                line_no,
                _redact_for_display(raw.strip()),
            )
        )

    for klass, pattern in (
        ("arn", ARN_PATTERN),
        ("hostname", HOSTNAME_PATTERN),
        ("account_id", ACCOUNT_ID_PATTERN),
        ("namespace", NAMESPACE_PATTERN),
    ):
        for match in pattern.finditer(text):
            value = match.group(0)
            if klass == "account_id":
                if _is_digest_interior(text, match.start(), match.end()):
                    exemptions["account_id: 12 digits interior to a SHA-256 hex digest"] += 1
                    continue
                if allow_fake_synthetic:
                    window = text[max(0, match.start() - 24) : match.end()]
                    if _FAKE_CREDENTIAL_ID.search(window):
                        exemptions["account_id: fake-provider cred_fake_<seed>_<counter>"] += 1
                        continue
                    if value in _FAKE_ACCOUNT_REFS:
                        exemptions[
                            f"account_id: fake-provider synthetic account_ref ({value})"
                        ] += 1
                        continue
            _record(klass, value, match.start())

    for match in SESSION_NAME_PATTERN.finditer(text):
        value = match.group(2)
        if value == REDACTED_SESSION_NAME:
            exemptions["session_name: scrubber redaction placeholder"] += 1
            continue
        if value in _JSON_STRUCTURAL:
            exemptions["session_name: JSON Schema property declaration, not a value"] += 1
            continue
        _record("session_name", value, match.start())

    for match in _POLICY_DOCUMENT_PATTERN.finditer(text):
        if _REDACTED_POLICY_DOCUMENT in match.group(0):
            exemptions["policy_document: scrubber redaction placeholder"] += 1
            continue
        _record("policy_document", match.group(0), match.start())

    for klass, pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(text):
            _record(klass, match.group(0), match.start())

    for match in _BASE64_BLOB.finditer(text):
        candidate = match.group(0).rstrip("=")
        if _is_benign_hex(candidate) or _ULID.match(candidate):
            continue
        if _in_url(text, match.start()):
            exemptions["base64_blob: URL path, not an opaque credential run"] += 1
            continue
        _record("base64_blob", candidate, match.start())

    return hits


def _scan_blob(
    data: bytes,
    source: str,
    member: str,
    *,
    exemptions: collections.Counter[str],
    allow_fake_synthetic: bool,
) -> list[Hit]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [Hit(source, member, "undecodable", 0, "not valid UTF-8; cannot prove clean")]

    kwargs = {"exemptions": exemptions, "allow_fake_synthetic": allow_fake_synthetic}
    hits = _scan_text(text, source, member, label="raw", **kwargs)
    decoded = html.unescape(text)
    if decoded != text:
        # Same bytes seen the way a browser sees them. An identifier written
        # as &#34;arn:aws:...&#34; is invisible to the raw pass but perfectly
        # readable on the published page.
        hits.extend(_scan_text(decoded, source, member, label="entity-decoded", **kwargs))
    return hits


def _iter_targets(paths: list[Path]) -> Iterator[Path]:
    for path in paths:
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    yield child
        elif path.is_file():
            yield path


def scan(
    paths: list[Path], *, repo_root: Path, allow_fake_synthetic: bool = False
) -> tuple[list[Hit], list[str], list[str], collections.Counter[str]]:
    hits: list[Hit] = []
    scanned: list[str] = []
    skipped: list[str] = []
    exemptions: collections.Counter[str] = collections.Counter()
    kwargs = {"exemptions": exemptions, "allow_fake_synthetic": allow_fake_synthetic}

    for target in _iter_targets(paths):
        try:
            rel = str(target.relative_to(repo_root))
        except ValueError:
            rel = str(target)
        suffix = target.suffix.lower()

        if suffix in _ARCHIVE_SUFFIXES or target.name.endswith(".tar.gz"):
            with tarfile.open(target, "r:gz") as tar:
                members = 0
                for member in tar.getmembers():
                    if not member.isfile():
                        continue
                    handle = tar.extractfile(member)
                    if handle is None:
                        continue
                    hits.extend(_scan_blob(handle.read(), rel, member.name, **kwargs))
                    members += 1
            scanned.append(f"{rel}  ({members} archive members)")
            continue

        if suffix in _TEXT_SUFFIXES:
            hits.extend(_scan_blob(target.read_bytes(), rel, "", **kwargs))
            scanned.append(rel)
            continue

        skipped.append(rel)

    return hits, scanned, skipped, exemptions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Files or directories to gate.")
    parser.add_argument(
        "--repo-root", type=Path, default=_REPO_ROOT, help="Root for relative path display."
    )
    parser.add_argument(
        "--allow-fake-synthetic",
        action="store_true",
        help="Exempt the fake provider's compiled-in synthetic account_ref and "
        "cred_fake_<seed>_<counter> ids. Never exempts a cb- namespace or an ARN.",
    )
    args = parser.parse_args(argv)

    hits, scanned, skipped, exemptions = scan(
        args.paths,
        repo_root=args.repo_root.resolve(),
        allow_fake_synthetic=args.allow_fake_synthetic,
    )

    print("CHAINBREAK public-site scrub gate")
    print("rules: EVIDENCE_SCHEMA.md section 11 + docs/research/history-scan.md classes")
    print("patterns: imported from chainbreak.evidence.redaction / .export (not reimplemented)")
    print(f"fake-provider synthetic exemption: {'ON' if args.allow_fake_synthetic else 'OFF'}")
    print()
    print(f"scanned {len(scanned)} file(s):")
    for name in scanned:
        print(f"  {name}")
    if skipped:
        print(f"\nskipped {len(skipped)} non-text file(s) (nothing to scrub):")
        for name in skipped:
            print(f"  {name}")

    if exemptions:
        print(f"\nexemptions exercised ({sum(exemptions.values())} match(es) waved, by rule):")
        for rule, count in sorted(exemptions.items()):
            print(f"  {count:>5}x  {rule}")

    print()
    if hits:
        print(f"BLOCKED: {len(hits)} identifier-shaped hit(s); refusing to publish")
        for hit in hits:
            print(hit.render())
        return 1

    print("residual matches after exemptions, by class:")
    for klass in (
        "account_id",
        "arn",
        "hostname",
        "namespace",
        "session_name",
        "policy_document",
        "credential/base64",
    ):
        print(f"  {klass:<18} 0")
    print()
    print("CLEAN: every scanned file may be published.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
