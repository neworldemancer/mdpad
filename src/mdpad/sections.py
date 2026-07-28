"""Heading-based section parsing for Markdown manuscripts.

A section spans from one ATX heading (``#``, ``##``, ``###`` ...) up to the next
heading of the same or higher level. Sections carry a slug id, title, level, the
half-open line range ``[start_line, end_line)`` and the raw text (heading
included). This is the authoritative parse used for context construction; the
frontend does its own lightweight scan only for outline navigation.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*$")


@dataclass
class Section:
    id: str
    title: str
    level: int
    start_line: int  # 0-based, inclusive
    end_line: int    # 0-based, exclusive
    text: str        # raw section text, heading included

    def as_dict(self) -> dict:
        return asdict(self)


def _slug(title: str) -> str:
    s = re.sub(r"[^\w\s-]", "", title.lower()).strip()
    return re.sub(r"[\s_]+", "-", s) or "section"


def parse_sections(text: str) -> list[Section]:
    """Parse ``text`` into a flat, ordered list of sections."""
    lines = text.splitlines()
    heads: list[tuple[int, int, str]] = []  # (line_index, level, title)
    for i, line in enumerate(lines):
        m = _HEADING.match(line)
        if m:
            heads.append((i, len(m.group(1)), m.group(2).strip()))

    sections: list[Section] = []
    seen: dict[str, int] = {}
    for n, (line_i, level, title) in enumerate(heads):
        end = len(lines)
        for line_j, lvl_j, _ in heads[n + 1:]:
            if lvl_j <= level:
                end = line_j
                break
        base = _slug(title)
        seen[base] = seen.get(base, -1) + 1
        sid = base if seen[base] == 0 else f"{base}-{seen[base]}"
        body = "\n".join(lines[line_i:end])
        sections.append(Section(sid, title, level, line_i, end, body))
    return sections


def section_at(sections: list[Section], offset: int, text: str) -> Section | None:
    """Return the deepest section whose line range contains character ``offset``."""
    if not sections:
        return None
    line = text.count("\n", 0, max(offset, 0))
    best: Section | None = None
    for s in sections:
        if s.start_line <= line < s.end_line and (best is None or s.level >= best.level):
            best = s
    return best
