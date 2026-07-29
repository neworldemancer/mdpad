"""In-memory cache of section summaries, and the logic to (re)build them.

Summaries let :mod:`mdpad.context` send the model a compact package -- full
text for the section being edited, 1-3 sentence summaries for everything
around it. Summaries are cached server-side (module dict, no persistence yet),
change-gated on refresh (a cheap YES/NO model call decides whether an edited
section's summary is stale before spending tokens regenerating it), and can be
rebuilt in bulk on demand.
"""

from __future__ import annotations

import difflib
import time
from dataclasses import asdict, dataclass

from . import provider as prov
from .sections import Section

DOC_ID = "__doc__"

SUMMARIZE_SYSTEM = (
    "Summarize this manuscript section in 1-3 sentences: its purpose and key "
    "claims. Output only the summary, no preamble."
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


def summarize(text: str, provider: dict) -> str:
    """Ask the model for a 1-3 sentence summary of ``text``."""
    return prov.chat_text(system=SUMMARIZE_SYSTEM, user=text, provider=provider).strip()


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


def refresh(sections: list[Section], whole_text: str, provider: dict, mode: str) -> dict:
    """(Re)build summaries.

    ``mode == "all"``: (re)summarize every section plus the whole document.
    ``mode == "invalidated"``: change-gate every *existing* summary (including
    ``__doc__``) against its current text; never creates missing summaries.
    """
    generated = checked = skipped = tokens = 0
    error: str | None = None
    now = time.time()

    if mode not in ("all", "invalidated"):
        return {"generated": 0, "checked": 0, "skipped": 0, "tokens": 0, "error": f"Unknown mode: {mode!r}"}

    if not _configured(provider):
        pending = len(sections) + 1 if mode == "all" else len(_STORE)
        return {
            "generated": 0,
            "checked": 0,
            "skipped": pending,
            "tokens": 0,
            "error": "Provider not configured; skipped summarization.",
        }

    try:
        if mode == "all":
            for s in sections:
                tokens += _est_tokens(s.text)
                text = summarize(s.text, provider)
                put(Summary(s.id, s.title, text, s.text, now))
                generated += 1
            tokens += _est_tokens(whole_text)
            doc_text = summarize(whole_text, provider)
            put(Summary(DOC_ID, "Document", doc_text, whole_text, now))
            generated += 1
        else:  # "invalidated"
            by_id = {s.id: s for s in sections}
            for sid, summ in list(_STORE.items()):
                current_text = whole_text if sid == DOC_ID else (by_id[sid].text if sid in by_id else None)
                if current_text is None:
                    # Section no longer exists in the document -- nothing to check.
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
                    new_text = summarize(current_text, provider)
                    put(Summary(sid, summ.title, new_text, current_text, now))
                    generated += 1
                else:
                    put(Summary(sid, summ.title, summ.summary, current_text, now))
                    checked += 1
    except prov.ProviderError as e:
        error = str(e)

    return {"generated": generated, "checked": checked, "skipped": skipped, "tokens": tokens, "error": error}


def estimate(sections: list[Section], mode: str) -> dict:
    """Token estimate for a refresh, with no LLM calls."""
    if mode == "all":
        targets = list(sections)
        include_doc = True
    else:
        targets = [s for s in sections if s.id in _STORE]
        include_doc = DOC_ID in _STORE

    count = len(targets) + (1 if include_doc else 0)
    tokens = sum(_est_tokens(s.text) for s in targets)
    if include_doc:
        # No whole-document text is passed in; approximate it as the
        # concatenation of all sections (which is what the document is).
        tokens += sum(_est_tokens(s.text) for s in sections)
    tokens += _OVERHEAD_TOKENS * count
    return {"count": count, "est_tokens": tokens}


def status(sections: list[Section]) -> dict:
    summarized = sum(1 for s in sections if s.id in _STORE)
    return {"summarized": summarized, "total": len(sections)}
