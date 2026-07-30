"""Build the compact, inspectable context package sent to the model.

Order: project summary -> document summary -> for each ancestor level
outer-to-inner (``#`` -> ``##`` -> ``###``): previous-sibling summary ->
ancestor summary -> next-sibling summary -> previous-paragraph summary ->
current paragraph (full text) -> next-paragraph summary -> selected text ->
user instruction. The current paragraph is the only thing sent in full;
everything else around it is a cached 1-3 sentence (additive) summary or, if
none is cached yet, a local first-two-sentences excerpt -- never the whole
manuscript. Token counts are rough ``len/4`` estimates -- a deliberate PoC
stand-in for a real tokenizer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .sections import Block, Section, adjacent, ancestors, block_adjacent

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def est_tokens(text: str) -> int:
    return max(1, round(len(text) / 4)) if text else 0


def _excerpt(text: str, n: int = 2) -> str:
    """First ~``n`` sentences of ``text``, skipping a leading heading line."""
    lines = text.strip().splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        lines = lines[1:]
    body = " ".join(lines).strip()
    sentences = [s for s in _SENTENCE_SPLIT.split(body) if s]
    return " ".join(sentences[:n]).strip()


def _summary_for(entity: Section | Block, store: dict) -> str:
    """Cached summary for a section or block, or a local excerpt fallback."""
    cached = store.get(entity.id)
    if cached is not None:
        return cached.summary
    excerpt = _excerpt(entity.text)
    return f"{excerpt} (unsummarized)" if excerpt else "(unsummarized)"


def _doc_summary(sections: list[Section], store: dict) -> str:
    cached = store.get("__doc__")
    if cached is not None:
        return cached.summary
    whole = "\n\n".join(s.text for s in sections)
    excerpt = _excerpt(whole)
    return f"{excerpt} (unsummarized)" if excerpt else ""


@dataclass
class ContextItem:
    label: str
    text: str
    tokens: int


@dataclass
class ContextPackage:
    items: list[ContextItem]
    total_tokens: int

    def as_dict(self) -> dict:
        return {
            "items": [item.__dict__ for item in self.items],
            "total_tokens": self.total_tokens,
        }

    def as_prompt(self) -> str:
        """Flatten the package into the exact text handed to the model."""
        return "\n\n".join(f"## {item.label}\n{item.text}" for item in self.items)


def build_context(
    *,
    project_summary: str,
    sections: list[Section],
    blocks: list[Block],
    target_block: Block | None,
    selection: str,
    instruction: str,
    store: dict,
) -> ContextPackage:
    raw: list[tuple[str, str]] = [
        ("Project summary", project_summary.strip()),
        ("Document summary", _doc_summary(sections, store)),
    ]

    if target_block is not None:
        owner = next((s for s in sections if s.id == target_block.section_id), None)
        chain = (ancestors(sections, owner) + [owner]) if owner is not None else []
        for anc in chain:
            prev_s, next_s = adjacent(sections, anc)
            # Each entry is labelled by its OWN title + role, so a neighbour reads
            # "(next) Mode Occupation", not the current section's title.
            if prev_s is not None:
                raw.append((f"(previous) {prev_s.title}", _summary_for(prev_s, store)))
            raw.append((f"(current) {anc.title}", _summary_for(anc, store)))
            if next_s is not None:
                raw.append((f"(next) {next_s.title}", _summary_for(next_s, store)))

        prev_b, next_b = block_adjacent(blocks, target_block)
        if prev_b is not None:
            raw.append(("(previous) paragraph", _summary_for(prev_b, store)))
        raw.append(("(current) paragraph", target_block.text))
        if next_b is not None:
            raw.append(("(next) paragraph", _summary_for(next_b, store)))

    raw.append(("Selected text", selection.strip()))
    raw.append(("Instruction", instruction.strip()))

    items = [ContextItem(label, txt, est_tokens(txt)) for label, txt in raw if txt]
    return ContextPackage(items, sum(i.tokens for i in items))
