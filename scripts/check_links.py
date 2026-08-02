#!/usr/bin/env python3
"""Check relative links, heading anchors, and orphaned files across the skill.

Runs offline: it only validates links that point inside the repository.
External URLs are checked separately by the scheduled lychee job in CI.

Usage: python scripts/check_links.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".claude", "node_modules"}

# [text](target) and ![alt](target), ignoring reference-style and autolinks.
LINK_RE = re.compile(r"!?\[[^\]]*\]\(\s*([^)\s]+)")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$", re.MULTILINE)
FENCE_RE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)


def markdown_files() -> list[Path]:
    return sorted(
        p
        for p in ROOT.rglob("*.md")
        if not SKIP_DIRS.intersection(p.relative_to(ROOT).parts)
    )


def strip_code(text: str) -> str:
    """Drop fenced blocks so example code isn't parsed for links."""
    return FENCE_RE.sub("", text)


def slugify(heading: str) -> str:
    """Approximate GitHub's heading-anchor algorithm."""
    text = re.sub(r"`([^`]*)`", r"\1", heading)  # unwrap inline code
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # unwrap links
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)  # drop punctuation, keep unicode word chars
    return re.sub(r"\s+", "-", text.strip())


def anchors(text: str) -> set[str]:
    """Heading slugs for a document, including GitHub's -1/-2 duplicate suffixes."""
    seen: dict[str, int] = {}
    found: set[str] = set()
    for heading in HEADING_RE.findall(strip_code(text)):
        slug = slugify(heading)
        count = seen.get(slug, 0)
        found.add(slug if count == 0 else f"{slug}-{count}")
        seen[slug] = count + 1
    return found


def main() -> int:
    files = markdown_files()
    if not files:
        print("no markdown files found", file=sys.stderr)
        return 1

    cache: dict[Path, str] = {p: p.read_text(encoding="utf-8") for p in files}
    anchor_cache: dict[Path, set[str]] = {}
    errors: list[str] = []
    linked: set[Path] = set()

    for path in files:
        rel = path.relative_to(ROOT)
        body = strip_code(cache[path])

        for target in LINK_RE.findall(body):
            target = target.strip("<>")
            if re.match(r"^(https?|mailto):", target):
                continue

            file_part, _, fragment = target.partition("#")

            if file_part:
                dest = (path.parent / file_part).resolve()
                if not dest.exists():
                    errors.append(f"{rel}: broken link -> {target}")
                    continue
                if dest.suffix == ".md":
                    linked.add(dest)
            else:
                dest = path  # same-document anchor

            if fragment and dest.suffix == ".md":
                if dest not in anchor_cache:
                    anchor_cache[dest] = anchors(
                        cache.get(dest) or dest.read_text(encoding="utf-8")
                    )
                if fragment not in anchor_cache[dest]:
                    errors.append(f"{rel}: missing anchor -> {target}")

    # A reference nobody links to will never be read by an agent.
    for path in files:
        rel = path.relative_to(ROOT)
        if rel.parts[0] == "references" and path not in linked:
            errors.append(f"{rel}: orphaned — not linked from any other document")

    if errors:
        print(f"{len(errors)} problem(s) found:\n", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    print(f"checked {len(files)} files — all internal links and anchors resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
