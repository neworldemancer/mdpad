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
    end_line: int  # 0-based, exclusive
    text: str  # raw section text, heading included

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
        for line_j, lvl_j, _ in heads[n + 1 :]:
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


def ancestors(sections: list[Section], target: Section) -> list[Section]:
    """Return ``target``'s enclosing sections, ordered root -> immediate parent.

    A section ``s`` encloses ``target`` when it has a strictly lower level and
    its line range contains ``target``'s whole range. ``sections`` is in
    document order, so enclosing sections naturally sort outermost-first.
    """
    return [
        s
        for s in sections
        if s.level < target.level and s.start_line <= target.start_line and s.end_line >= target.end_line
    ]


def _parent(sections: list[Section], s: Section) -> Section | None:
    anc = ancestors(sections, s)
    return anc[-1] if anc else None


def adjacent(sections: list[Section], target: Section) -> tuple[Section | None, Section | None]:
    """Return ``target``'s previous and next sibling (nearest sections at the
    same level sharing the same immediate parent), or ``None`` where absent."""
    parent = _parent(sections, target)
    siblings = [s for s in sections if s.level == target.level and _parent(sections, s) == parent]
    if target not in siblings:
        return None, None
    idx = siblings.index(target)
    prev_s = siblings[idx - 1] if idx > 0 else None
    next_s = siblings[idx + 1] if idx < len(siblings) - 1 else None
    return prev_s, next_s


@dataclass
class Block:
    """A paragraph-level unit within a section -- the leaf of the summary
    hierarchy (doc -> ``#`` -> ``##`` -> ``###`` -> paragraph)."""

    id: str
    section_id: str
    index: int  # 0-based position among this section's blocks
    start_line: int  # 0-based, inclusive
    end_line: int  # 0-based, exclusive
    text: str

    def as_dict(self) -> dict:
        return asdict(self)


def _owner_section(sections: list[Section], line_idx: int) -> Section | None:
    """Deepest section whose range contains ``line_idx`` (or ``None``)."""
    best: Section | None = None
    for s in sections:
        if s.start_line <= line_idx < s.end_line and (best is None or s.level > best.level):
            best = s
    return best


def _is_formula_open(line: str) -> bool:
    return line.lstrip().startswith("$$")


def parse_blocks(text: str) -> list[Block]:
    """Parse ``text`` into paragraph-level blocks, owned by their section.

    Blank-line-separated paragraphs become blocks; heading lines are never
    blocks. A ``$$...$$`` display-math block is consumed as a single unit
    -- even across blank lines -- then glued to the previous paragraph
    (and also to the next paragraph when it opens its section, i.e. has no
    previous paragraph, or when the text right after it continues the
    sentence in lowercase). Block ids are ``f"{section_id}::p{index}"``,
    with ``index`` assigned per-section after gluing.
    """
    lines = text.splitlines()
    sections = parse_sections(text)
    n = len(lines)

    # Pass 1: split into ordered (type, section_id, start, end) segments,
    # skipping headings and blank lines. A "$$" opening line is consumed
    # through its closing "$$" (which may be the same line) as one segment.
    segments: list[dict] = []
    i = 0
    while i < n:
        line = lines[i]
        if _HEADING.match(line) or line.strip() == "":
            i += 1
            continue
        owner = _owner_section(sections, i)
        if owner is None:
            # Content before any heading -- no section to own it; skip.
            i += 1
            continue
        sid = owner.id
        if _is_formula_open(line):
            start = i
            stripped = line.strip()
            if len(stripped) > 2 and stripped.count("$$") >= 2:
                i += 1  # opened and closed on the same line
            else:
                j = i + 1
                while j < n and not lines[j].rstrip().endswith("$$"):
                    j += 1
                i = min(j + 1, n)
            segments.append({"type": "formula", "section_id": sid, "start": start, "end": i})
        else:
            start = i
            i += 1
            while i < n and lines[i].strip() != "" and not _HEADING.match(lines[i]) and not _is_formula_open(lines[i]):
                i += 1
            segments.append({"type": "para", "section_id": sid, "start": start, "end": i})

    # Pass 2: glue formula segments to their neighbouring paragraph(s).
    groups: list[list[dict]] = []
    m = len(segments)
    i = 0
    while i < m:
        seg = segments[i]
        if seg["type"] != "formula":
            groups.append([seg])
            i += 1
            continue

        prev_group = groups[-1] if groups else None
        if prev_group is not None and prev_group[-1]["section_id"] == seg["section_id"]:
            prev_group.append(seg)
            i += 1
            nxt = segments[i] if i < m else None
            starts_lower = (
                nxt is not None
                and nxt["type"] == "para"
                and nxt["section_id"] == seg["section_id"]
                and lines[nxt["start"]].lstrip()[:1].islower()
            )
            if starts_lower and nxt is not None:
                prev_group.append(nxt)
                i += 1
        else:
            # No previous paragraph (formula opens its section) -- must glue
            # to the next paragraph, whatever case it starts with.
            group = [seg]
            i += 1
            nxt = segments[i] if i < m else None
            if nxt is not None and nxt["section_id"] == seg["section_id"]:
                group.append(nxt)
                i += 1
            groups.append(group)

    # Pass 3: build Block objects; indexing restarts per section.
    counters: dict[str, int] = {}
    blocks: list[Block] = []
    for g in groups:
        sid = g[0]["section_id"]
        idx = counters.get(sid, 0)
        counters[sid] = idx + 1
        start_line = g[0]["start"]
        end_line = g[-1]["end"]
        block_text = "\n".join(lines[start_line:end_line])
        blocks.append(Block(f"{sid}::p{idx}", sid, idx, start_line, end_line, block_text))
    return blocks


def block_at(blocks: list[Block], offset: int, text: str) -> Block | None:
    """Return the block whose line range contains character ``offset``."""
    if not blocks:
        return None
    line = text.count("\n", 0, max(offset, 0))
    for b in blocks:
        if b.start_line <= line < b.end_line:
            return b
    return None


def block_adjacent(blocks: list[Block], target: Block) -> tuple[Block | None, Block | None]:
    """Return ``target``'s previous and next block in document order."""
    try:
        idx = blocks.index(target)
    except ValueError:
        return None, None
    prev_b = blocks[idx - 1] if idx > 0 else None
    next_b = blocks[idx + 1] if idx < len(blocks) - 1 else None
    return prev_b, next_b
