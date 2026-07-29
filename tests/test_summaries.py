import dataclasses
import time

import pytest

from mdpad import summaries
from mdpad.provider import ProviderError
from mdpad.sections import parse_blocks, parse_sections

DOC = """# Chapter
intro line

## Alpha
alpha body

## Beta
beta body
"""

PROVIDER = {"base_url": "http://example.test/v1", "api_key": "k", "model": "m"}


@pytest.fixture(autouse=True)
def _clean_store():
    summaries.reset()
    yield
    summaries.reset()


def _stub_chat_text(reply_for_summarize="Stub summary.", reply_for_gate="NO"):
    """Build a stand-in for provider.chat_text that never touches the network,
    distinguishing summarize vs. change-gate calls by their system prompt."""

    def _fn(*, system, user, provider):
        assert provider == PROVIDER
        if system == summaries.SUMMARIZE_SYSTEM:
            return reply_for_summarize
        if system == summaries.CHANGE_GATE_SYSTEM:
            return reply_for_gate
        raise AssertionError(f"unexpected system prompt: {system!r}")

    return _fn


# --- diff_text ---------------------------------------------------------


def test_diff_text_marks_changed_lines():
    diff = summaries.diff_text("a\nb\nc", "a\nx\nc")
    assert "-b" in diff
    assert "+x" in diff


def test_diff_text_empty_for_identical_text():
    assert summaries.diff_text("same\ntext", "same\ntext") == ""


# --- summarize (additive, no LLM stubbed to a fixed reply) ----------------


def test_summarize_prompt_carries_parent_context_additively(monkeypatch):
    captured = {}

    def _fn(*, system, user, provider):
        captured["system"] = system
        captured["user"] = user
        return "New info only."

    monkeypatch.setattr(summaries.prov, "chat_text", _fn)
    result = summaries.summarize("Some text.", ["Parent A.", "Parent B."], PROVIDER)

    assert result == "New info only."
    assert captured["system"] == summaries.SUMMARIZE_SYSTEM
    assert "Parent A." in captured["user"]
    assert "Parent B." in captured["user"]
    assert "Some text." in captured["user"]


def test_summarize_with_no_parents_still_works(monkeypatch):
    monkeypatch.setattr(summaries.prov, "chat_text", _stub_chat_text())
    assert summaries.summarize("Doc text.", [], PROVIDER) == "Stub summary."


# --- estimate (no LLM) ---------------------------------------------------


def test_estimate_all_covers_every_section_block_and_document():
    secs = parse_sections(DOC)
    blocks = parse_blocks(DOC)
    result = summaries.estimate(secs, blocks, "all")
    assert result["count"] == len(secs) + len(blocks) + 1
    assert result["est_tokens"] > 0


def test_estimate_invalidated_only_counts_cached_summaries():
    secs = parse_sections(DOC)
    blocks = parse_blocks(DOC)
    alpha = next(s for s in secs if s.title == "Alpha")
    summaries.put(summaries.Summary(alpha.id, alpha.title, "sum", alpha.text, time.time()))
    result = summaries.estimate(secs, blocks, "invalidated")
    assert result["count"] == 1  # only Alpha is cached; blocks and __doc__ are not


def test_estimate_invalidated_empty_store_is_zero():
    secs = parse_sections(DOC)
    blocks = parse_blocks(DOC)
    assert summaries.estimate(secs, blocks, "invalidated") == {"count": 0, "est_tokens": 0}


# --- refresh(mode="all") --------------------------------------------------


def test_refresh_all_generates_every_section_block_and_document_summary(monkeypatch):
    monkeypatch.setattr(summaries.prov, "chat_text", _stub_chat_text())
    secs = parse_sections(DOC)
    blocks = parse_blocks(DOC)
    result = summaries.refresh(secs, blocks, DOC, PROVIDER, "all")

    assert result["generated"] == len(secs) + len(blocks) + 1
    assert result["checked"] == 0
    assert result["skipped"] == 0
    assert result["error"] is None
    assert result["tokens"] > 0
    for s in secs:
        cached = summaries.get(s.id)
        assert cached is not None
        assert cached.summary == "Stub summary."
        assert cached.source_text == s.text
    for b in blocks:
        cached = summaries.get(b.id)
        assert cached is not None
        assert cached.summary == "Stub summary."
        assert cached.source_text == b.text
    doc_summary = summaries.get(summaries.DOC_ID)
    assert doc_summary is not None
    assert doc_summary.summary == "Stub summary."
    assert doc_summary.source_text == DOC


def test_refresh_all_generates_top_down_with_additive_parents(monkeypatch):
    calls: list[str] = []

    def _fn(*, system, user, provider):
        assert provider == PROVIDER
        if system == summaries.CHANGE_GATE_SYSTEM:
            return "NO"
        assert system == summaries.SUMMARIZE_SYSTEM
        calls.append(user)
        return f"S{len(calls)}"

    monkeypatch.setattr(summaries.prov, "chat_text", _fn)
    secs = parse_sections(DOC)
    blocks = parse_blocks(DOC)
    result = summaries.refresh(secs, blocks, DOC, PROVIDER, "all")
    assert result["generated"] == len(secs) + len(blocks) + 1

    chapter = next(s for s in secs if s.title == "Chapter")
    alpha = next(s for s in secs if s.title == "Alpha")
    beta = next(s for s in secs if s.title == "Beta")

    # __doc__ first, then sections outer -> inner (level, position).
    assert summaries.get(summaries.DOC_ID).summary == "S1"
    assert summaries.get(chapter.id).summary == "S2"
    assert summaries.get(alpha.id).summary == "S3"
    assert summaries.get(beta.id).summary == "S4"

    chapter_block = next(b for b in blocks if b.section_id == chapter.id)
    alpha_block = next(b for b in blocks if b.section_id == alpha.id)
    beta_block = next(b for b in blocks if b.section_id == beta.id)

    # Blocks generated last, each additive on top of the doc + its own
    # ancestor-section chain (Chapter is an ancestor of every section here).
    assert summaries.get(chapter_block.id).summary == "S5"
    assert summaries.get(alpha_block.id).summary == "S6"
    assert summaries.get(beta_block.id).summary == "S7"

    alpha_call = calls[2]  # Alpha section: parents = doc + Chapter
    assert "S1" in alpha_call and "S2" in alpha_call

    alpha_block_call = calls[5]  # Alpha block: parents = doc + Chapter + Alpha
    assert "S1" in alpha_block_call and "S2" in alpha_block_call and "S3" in alpha_block_call
    assert "S4" not in alpha_block_call  # Beta is not Alpha's ancestor

    beta_block_call = calls[6]  # Beta block: parents = doc + Chapter + Beta
    assert "S1" in beta_block_call and "S2" in beta_block_call and "S4" in beta_block_call
    assert "S3" not in beta_block_call  # Alpha is not Beta's ancestor


def test_refresh_without_configured_provider_is_graceful(monkeypatch):
    def _boom(**kwargs):
        raise AssertionError("chat_text must not be called when the provider is unconfigured")

    monkeypatch.setattr(summaries.prov, "chat_text", _boom)
    secs = parse_sections(DOC)
    blocks = parse_blocks(DOC)
    result = summaries.refresh(secs, blocks, DOC, {"base_url": "", "api_key": "", "model": ""}, "all")

    assert result["generated"] == 0
    assert result["error"]
    assert summaries.status(secs, blocks) == {"summarized": 0, "total": len(secs) + len(blocks)}


def test_refresh_unknown_mode_reports_error(monkeypatch):
    monkeypatch.setattr(summaries.prov, "chat_text", _stub_chat_text())
    secs = parse_sections(DOC)
    blocks = parse_blocks(DOC)
    result = summaries.refresh(secs, blocks, DOC, PROVIDER, "bogus")
    assert result["error"] is not None
    assert result["generated"] == 0


# --- refresh(mode="invalidated") -----------------------------------------


def _seed_all(monkeypatch, secs, blocks, text):
    monkeypatch.setattr(summaries.prov, "chat_text", _stub_chat_text())
    summaries.refresh(secs, blocks, text, PROVIDER, "all")
    # Push every cached summary's timestamp into the past so the change-gate's
    # staleness check (age > STALE_AFTER_S) actually engages.
    old = time.time() - summaries.STALE_AFTER_S - 1
    for sid, s in list(summaries._STORE.items()):
        summaries._STORE[sid] = dataclasses.replace(s, generated_at=old)


def test_refresh_invalidated_skips_unchanged_sections(monkeypatch):
    secs = parse_sections(DOC)
    blocks = parse_blocks(DOC)
    _seed_all(monkeypatch, secs, blocks, DOC)

    def _gate_should_not_run(**kwargs):
        raise AssertionError("change-gate should not run for unchanged, stale-timestamp text")

    monkeypatch.setattr(summaries.prov, "chat_text", _gate_should_not_run)
    result = summaries.refresh(secs, blocks, DOC, PROVIDER, "invalidated")
    assert result == {
        "generated": 0,
        "checked": 0,
        "skipped": len(secs) + len(blocks) + 1,
        "tokens": 0,
        "error": None,
    }


def test_refresh_invalidated_no_verdict_refreshes_timestamp_only(monkeypatch):
    secs = parse_sections(DOC)
    blocks = parse_blocks(DOC)
    _seed_all(monkeypatch, secs, blocks, DOC)

    new_doc = DOC.replace("alpha body", "alpha body, now revised")
    new_secs = parse_sections(new_doc)
    new_blocks = parse_blocks(new_doc)

    monkeypatch.setattr(summaries.prov, "chat_text", _stub_chat_text(reply_for_gate="NO"))
    result = summaries.refresh(new_secs, new_blocks, new_doc, PROVIDER, "invalidated")

    assert result["generated"] == 0
    assert result["error"] is None
    assert result["checked"] >= 1  # at least Alpha (text changed, summary judged unaffected)

    alpha = next(s for s in new_secs if s.title == "Alpha")
    cached = summaries.get(alpha.id)
    assert cached.summary == "Stub summary."  # unchanged
    assert cached.source_text == alpha.text  # but source_text caught up


def test_refresh_invalidated_yes_verdict_regenerates_summary(monkeypatch):
    secs = parse_sections(DOC)
    blocks = parse_blocks(DOC)
    _seed_all(monkeypatch, secs, blocks, DOC)

    new_doc = DOC.replace("alpha body", "alpha body, now revised")
    new_secs = parse_sections(new_doc)
    new_blocks = parse_blocks(new_doc)

    monkeypatch.setattr(summaries.prov, "chat_text", _stub_chat_text(reply_for_gate="YES"))
    result = summaries.refresh(new_secs, new_blocks, new_doc, PROVIDER, "invalidated")

    assert result["generated"] >= 1
    alpha = next(s for s in new_secs if s.title == "Alpha")
    cached = summaries.get(alpha.id)
    assert cached.summary == "Stub summary."
    assert cached.source_text == alpha.text


def test_refresh_invalidated_provider_error_is_captured(monkeypatch):
    secs = parse_sections(DOC)
    blocks = parse_blocks(DOC)
    _seed_all(monkeypatch, secs, blocks, DOC)

    new_doc = DOC.replace("alpha body", "alpha body, now revised")
    new_secs = parse_sections(new_doc)
    new_blocks = parse_blocks(new_doc)

    def _raise(**kwargs):
        raise ProviderError("boom")

    monkeypatch.setattr(summaries.prov, "chat_text", _raise)
    result = summaries.refresh(new_secs, new_blocks, new_doc, PROVIDER, "invalidated")
    assert result["error"] == "boom"
