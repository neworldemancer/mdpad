"""Build the compact, inspectable context package sent to the model.

Order: project summary -> document summary -> parent-section summaries ->
previous-sibling summary -> current section (full text) -> next-sibling
summary -> selected text -> user instruction. The current section is the only
thing sent in full; everything else around it is a cached 1-3 sentence
summary (or, if none is cached yet, a local first-two-sentences excerpt --
never the whole manuscript). Token counts are rough ``len/4`` estimates -- a
deliberate PoC stand-in for a real tokenizer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .sections import Section, adjacent, ancestors

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


def _summary_for(section: Section, store: dict) -> str:
    """Cached summary for ``section``, or a local excerpt fallback."""
    cached = store.get(section.id)
    if cached is not None:
        return cached.summary
    excerpt = _excerpt(section.text)
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
    target: Section | None,
    selection: str,
    instruction: str,
    store: dict,
) -> ContextPackage:
    parents_text = ""
    prev_text = ""
    next_text = ""
    current_text = ""

    if target is not None:
        parent_secs = ancestors(sections, target)
        parents_text = "\n".join(f"{p.title}: {_summary_for(p, store)}" for p in parent_secs)

        prev_sec, next_sec = adjacent(sections, target)
        if prev_sec is not None:
            prev_text = f"{prev_sec.title}: {_summary_for(prev_sec, store)}"
        if next_sec is not None:
            next_text = f"{next_sec.title}: {_summary_for(next_sec, store)}"

        current_text = f"{target.title}\n\n{target.text}"

    raw = [
        ("Project summary", project_summary.strip()),
        ("Document summary", _doc_summary(sections, store)),
        ("Parent sections", parents_text),
        ("Previous section", prev_text),
        ("Current section", current_text),
        ("Next section", next_text),
        ("Selected text", selection.strip()),
        ("Instruction", instruction.strip()),
    ]
    items = [ContextItem(label, txt, est_tokens(txt)) for label, txt in raw if txt]
    return ContextPackage(items, sum(i.tokens for i in items))
