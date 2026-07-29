"""In-memory cache of section AND paragraph-block summaries, and the logic to
(re)build them.

Summaries let :mod:`mdpad.context` send the model a compact package -- full
text for the paragraph being edited, 1-3 sentence summaries for everything
around it, at every level (paragraph, ``###``, ``##``, ``#``, whole doc).
Summaries are **additive**: each one assumes the reader already has its
parents' summaries, so it adds only what's new rather than repeating them --
this requires generating top-down (``__doc__`` first, then sections
outer-to-inner, then paragraph blocks last) so a summary's parents always
exist by the time it is generated.

Summaries are cached server-side (module dict, no persistence yet),
change-gated on refresh (a cheap YES/NO model call decides whether an edited
section/block's summary is stale before spending tokens regenerating it), and
can be rebuilt in bulk on demand.
"""

from __future__ import annotations

import difflib
import time
from dataclasses import asdict, dataclass

from . import provider as prov
from .sections import Block, Section, ancestors

DOC_ID = "__doc__"

SUMMARIZE_SYSTEM = (
    "Summarize in 1-3 sentences. The reader already has the parent context "
    "below; do NOT repeat it -- add only what is new and specific to this "
    "text. Output only the summary."
)
CHANGE_GATE_SYSTEM = (
    "You get a section's current summary and a unified diff of edits. Answer "
    "with one word: YES if the summary should change, otherwise NO."
)

# How stale (seconds) an existing summary must be before the change-gate even
# considers re-checking it. Mirrors the frontend's 10-minute refresh tick.
STALE_AFTER_S = 600.0
# Rough per-item overhead (system prompt + instructions) added to `estimate`.
_OVERHEAD_TOKENS = 40


@dataclass
class Summary:
    """A cached summary. Reused for both sections and paragraph blocks --
    ``section_id`` holds a :class:`~mdpad.sections.Section` id or a
    :class:`~mdpad.sections.Block` id (``f"{section_id}::p{index}"``); the
    id ``__doc__`` is the whole-document summary."""

    section_id: str
    title: str
    summary: str
    source_text: str
    generated_at: float

    def as_dict(self) -> dict:
        return asdict(self)


_STORE: dict[str, Summary] = {}


def get(section_id: str) -> Summary | None:
    return _STORE.get(section_id)


def put(summary: Summary) -> None:
    _STORE[summary.section_id] = summary


def reset() -> None:
    _STORE.clear()


def _est_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text else 0


def summarize(text: str, parent_summaries: list[str], provider: dict) -> str:
    """Ask the model for a 1-3 sentence summary of ``text``, additive on top
    of ``parent_summaries`` (the reader already has those; add only what's
    new)."""
    joined = "\n".join(parent_summaries)
    user = f"Parent context:\n{joined}\n\nText:\n{text}"
    return prov.chat_text(system=SUMMARIZE_SYSTEM, user=user, provider=provider).strip()


def _section_by_id(sections: list[Section], section_id: str) -> Section | None:
    return next((s for s in sections if s.id == section_id), None)


def _parents_for_section(sections: list[Section], section: Section) -> list[str]:
    """Doc summary + ancestor-section summaries (root -> immediate parent),
    whichever are currently cached."""
    parents = []
    doc = get(DOC_ID)
    if doc is not None:
        parents.append(doc.summary)
    for anc in ancestors(sections, section):
        cached = get(anc.id)
        if cached is not None:
            parents.append(cached.summary)
    return parents


def _parents_for_block(sections: list[Section], block: Block) -> list[str]:
    """Doc summary + ancestor-section summaries, including the block's own
    immediate containing section (its innermost "ancestor")."""
    parents = []
    doc = get(DOC_ID)
    if doc is not None:
        parents.append(doc.summary)
    owner = _section_by_id(sections, block.section_id)
    if owner is None:
        return parents
    for anc in ancestors(sections, owner) + [owner]:
        cached = get(anc.id)
        if cached is not None:
            parents.append(cached.summary)
    return parents


def diff_text(old: str, new: str) -> str:
    """Unified diff between ``old`` and ``new``, as a single string."""
    lines = difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="")
    return "\n".join(lines)


def summary_changed(old_summary: str, diff: str, provider: dict) -> bool:
    """Ask the model whether ``diff`` invalidates ``old_summary``."""
    user = f"Current summary:\n{old_summary}\n\nDiff:\n{diff}"
    resp = prov.chat_text(system=CHANGE_GATE_SYSTEM, user=user, provider=provider)
    return resp.strip().upper().startswith("Y")


def _configured(provider: dict) -> bool:
    return bool(
        (provider.get("base_url") or "").strip()
        and (provider.get("api_key") or "").strip()
        and (provider.get("model") or "").strip()
    )


def refresh(sections: list[Section], blocks: list[Block], whole_text: str, provider: dict, mode: str) -> dict:
    """(Re)build summaries, top-down so additive parents always exist first.

    ``mode == "all"``: (re)summarize the whole document, then every section
    (outer -> inner, i.e. sorted by ``(level, position)``), then every
    paragraph block. Each summary is generated additively on top of its
    already-generated parents (doc, then ancestor sections).
    ``mode == "invalidated"``: change-gate every *existing* summary (sections,
    blocks, and ``__doc__``) against its current text; never creates missing
    summaries.
    """
    generated = checked = skipped = tokens = 0
    error: str | None = None
    now = time.time()

    if mode not in ("all", "invalidated"):
        return {"generated": 0, "checked": 0, "skipped": 0, "tokens": 0, "error": f"Unknown mode: {mode!r}"}

    if not _configured(provider):
        pending = len(sections) + len(blocks) + 1 if mode == "all" else len(_STORE)
        return {
            "generated": 0,
            "checked": 0,
            "skipped": pending,
            "tokens": 0,
            "error": "Provider not configured; skipped summarization.",
        }

    try:
        if mode == "all":
            tokens += _est_tokens(whole_text)
            doc_text = summarize(whole_text, [], provider)
            put(Summary(DOC_ID, "Document", doc_text, whole_text, now))
            generated += 1

            for s in sorted(sections, key=lambda s: (s.level, s.start_line)):
                parents = _parents_for_section(sections, s)
                tokens += _est_tokens(s.text)
                text = summarize(s.text, parents, provider)
                put(Summary(s.id, s.title, text, s.text, now))
                generated += 1

            for b in blocks:
                parents = _parents_for_block(sections, b)
                tokens += _est_tokens(b.text)
                text = summarize(b.text, parents, provider)
                put(Summary(b.id, b.id, text, b.text, now))
                generated += 1
        else:  # "invalidated"
            by_sec = {s.id: s for s in sections}
            by_block = {b.id: b for b in blocks}
            for sid, summ in list(_STORE.items()):
                if sid == DOC_ID:
                    current_text: str | None = whole_text
                elif sid in by_sec:
                    current_text = by_sec[sid].text
                elif sid in by_block:
                    current_text = by_block[sid].text
                else:
                    current_text = None
                if current_text is None:
                    # No longer exists in the document -- nothing to check.
                    skipped += 1
                    continue
                stale = current_text != summ.source_text and (now - summ.generated_at) > STALE_AFTER_S
                if not stale:
                    skipped += 1
                    continue
                diff = diff_text(summ.source_text, current_text)
                tokens += _est_tokens(summ.summary) + _est_tokens(diff)
                if summary_changed(summ.summary, diff, provider):
                    tokens += _est_tokens(current_text)
                    if sid == DOC_ID:
                        parents: list[str] = []
                    elif sid in by_sec:
                        parents = _parents_for_section(sections, by_sec[sid])
                    else:
                        parents = _parents_for_block(sections, by_block[sid])
                    new_text = summarize(current_text, parents, provider)
                    put(Summary(sid, summ.title, new_text, current_text, now))
                    generated += 1
                else:
                    put(Summary(sid, summ.title, summ.summary, current_text, now))
                    checked += 1
    except prov.ProviderError as e:
        error = str(e)

    return {"generated": generated, "checked": checked, "skipped": skipped, "tokens": tokens, "error": error}


def estimate(sections: list[Section], blocks: list[Block], mode: str) -> dict:
    """Token estimate for a refresh, with no LLM calls."""
    if mode == "all":
        sec_targets = list(sections)
        block_targets = list(blocks)
        include_doc = True
    else:
        sec_targets = [s for s in sections if s.id in _STORE]
        block_targets = [b for b in blocks if b.id in _STORE]
        include_doc = DOC_ID in _STORE

    count = len(sec_targets) + len(block_targets) + (1 if include_doc else 0)
    tokens = sum(_est_tokens(s.text) for s in sec_targets) + sum(_est_tokens(b.text) for b in block_targets)
    if include_doc:
        # No whole-document text is passed in; approximate it as the
        # concatenation of all sections (which is what the document is).
        tokens += sum(_est_tokens(s.text) for s in sections)
    tokens += _OVERHEAD_TOKENS * count
    return {"count": count, "est_tokens": tokens}


def status(sections: list[Section], blocks: list[Block]) -> dict:
    summarized = sum(1 for s in sections if s.id in _STORE) + sum(1 for b in blocks if b.id in _STORE)
    return {"summarized": summarized, "total": len(sections) + len(blocks)}
