"""Verify relative links and `#fragment` anchors across the documentation set.

Scope is the root markdown files (``*.md`` directly under the repository root) plus
everything under ``docs/``. Every relative link found in that scope must resolve to an
existing file (or directory), and every ``#fragment`` -- same-file or cross-file --
must match a heading that actually exists in its target file, using GitHub's own
heading-slug algorithm (lowercase; strip everything but letters/digits/spaces/hyphens/
underscores; spaces become hyphens; the Nth repeat of a slug within one file gets a
``-N`` suffix). Absolute URLs (``http(s)://``, ``mailto:``, ...) are out of scope --
this is a relative-link and anchor checker, not a network reachability check, matching
this repository's no-cloud-credentials CI invariant.

A link's *target file* need not itself be a root markdown file or under docs/: the repo
cross-links out to things like ``schemas/scenario.v1alpha1.schema.json`` or
``infra/terraform/README.md``, and those targets are resolved and anchor-checked like
any other.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+#+\s*)?$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_LINK_RE = re.compile(r"!?\[([^\]]*)\]\(\s*([^)\s]*)(?:\s+\"[^\"]*\")?\s*\)")
_INLINE_CODE_RE = re.compile(r"`([^`]*)`")
_MD_LINK_TEXT_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_EMPHASIS_RE = re.compile(r"(\*\*\*|\*\*|\*|___|__|_|~~)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_DISALLOWED_RE = re.compile(r"[^\w\- ]", re.UNICODE)
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


def github_slug(heading_text: str, seen: dict[str, int]) -> str:
    text = _INLINE_CODE_RE.sub(r"\1", heading_text)
    text = _MD_LINK_TEXT_RE.sub(r"\1", text)
    text = _HTML_TAG_RE.sub("", text)
    text = _EMPHASIS_RE.sub("", text)
    text = text.lower()
    text = _DISALLOWED_RE.sub("", text)
    slug = text.replace(" ", "-")
    count = seen.get(slug, 0)
    seen[slug] = count + 1
    return slug if count == 0 else f"{slug}-{count}"


def extract_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    in_fence = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING_RE.match(line)
        if match:
            anchors.add(github_slug(match.group(2), seen))
    return anchors


def _blank_inline_code(line: str) -> str:
    # Masks code-span *content* (not the surrounding link syntax) so a code span
    # showing literal link syntax as documentation text isn't mistaken for a real
    # link, while a real link whose *text* happens to contain a code span (e.g.
    # "[`credentials.jsonl`](EVIDENCE_SCHEMA.md#...)") still matches correctly.
    return _INLINE_CODE_RE.sub(lambda m: "`" + " " * len(m.group(1)) + "`", line)


def extract_links(path: Path) -> list[tuple[int, str]]:
    links: list[tuple[int, str]] = []
    in_fence = False
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
    ):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in _LINK_RE.finditer(_blank_inline_code(line)):
            target = match.group(2).strip()
            if target:
                links.append((line_number, target))
    return links


def check_docs(repo_root: Path) -> list[str]:
    docs_dir = repo_root / "docs"
    root_docs = sorted(repo_root.glob("*.md"))
    nested_docs = sorted(docs_dir.rglob("*.md")) if docs_dir.is_dir() else []
    scope = root_docs + nested_docs

    anchor_cache: dict[Path, set[str]] = {}

    def anchors_for(target_file: Path) -> set[str]:
        resolved = target_file.resolve()
        if resolved not in anchor_cache:
            anchor_cache[resolved] = extract_anchors(target_file)
        return anchor_cache[resolved]

    failures: list[str] = []
    for doc in scope:
        rel_doc = doc.relative_to(repo_root)
        for line_number, raw_target in extract_links(doc):
            if _SCHEME_RE.match(raw_target) or raw_target.startswith("//"):
                continue  # absolute URL / protocol-relative -- out of scope

            path_part, _, fragment = raw_target.partition("#")
            path_part = unquote(path_part)
            fragment = unquote(fragment)

            if path_part:
                target_file = (doc.parent / path_part).resolve()
                if not target_file.exists():
                    failures.append(
                        f"{rel_doc}:{line_number}: broken link -> {raw_target} "
                        f"(no such file: {path_part})"
                    )
                    continue
            else:
                target_file = doc  # same-file fragment

            if (
                fragment
                and target_file.is_file()
                and target_file.suffix == ".md"
                and fragment not in anchors_for(target_file)
            ):
                target_desc = path_part if path_part else "this file"
                failures.append(
                    f"{rel_doc}:{line_number}: broken anchor -> {raw_target} "
                    f"(no heading slugs to '#{fragment}' in {target_desc})"
                )

    return failures


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]) if args else Path()
    failures = check_docs(repo_root)
    if failures:
        print("Documentation link check: FAIL")
        print("\n".join(sorted(failures)))
        return 1
    print("Documentation link check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
