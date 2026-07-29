import dataclasses
import time

import pytest

from mdpad import summaries
from mdpad.provider import ProviderError
from mdpad.sections import parse_sections

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


# --- estimate (no LLM) ---------------------------------------------------


def test_estimate_all_covers_every_section_plus_document():
    secs = parse_sections(DOC)
    result = summaries.estimate(secs, "all")
    assert result["count"] == len(secs) + 1
    assert result["est_tokens"] > 0


def test_estimate_invalidated_only_counts_cached_summaries():
    secs = parse_sections(DOC)
    alpha = next(s for s in secs if s.title == "Alpha")
    summaries.put(summaries.Summary(alpha.id, alpha.title, "sum", alpha.text, time.time()))
    result = summaries.estimate(secs, "invalidated")
    assert result["count"] == 1  # only Alpha is cached; __doc__ is not


def test_estimate_invalidated_empty_store_is_zero():
    secs = parse_sections(DOC)
    assert summaries.estimate(secs, "invalidated") == {"count": 0, "est_tokens": 0}


# --- refresh(mode="all") --------------------------------------------------


def test_refresh_all_generates_every_section_and_document_summary(monkeypatch):
    monkeypatch.setattr(summaries.prov, "chat_text", _stub_chat_text())
    secs = parse_sections(DOC)
    result = summaries.refresh(secs, DOC, PROVIDER, "all")

    assert result["generated"] == len(secs) + 1
    assert result["checked"] == 0
    assert result["skipped"] == 0
    assert result["error"] is None
    assert result["tokens"] > 0
    for s in secs:
        cached = summaries.get(s.id)
        assert cached is not None
        assert cached.summary == "Stub summary."
        assert cached.source_text == s.text
    doc_summary = summaries.get(summaries.DOC_ID)
    assert doc_summary is not None
    assert doc_summary.summary == "Stub summary."
    assert doc_summary.source_text == DOC


def test_refresh_without_configured_provider_is_graceful(monkeypatch):
    def _boom(**kwargs):
        raise AssertionError("chat_text must not be called when the provider is unconfigured")

    monkeypatch.setattr(summaries.prov, "chat_text", _boom)
    secs = parse_sections(DOC)
    result = summaries.refresh(secs, DOC, {"base_url": "", "api_key": "", "model": ""}, "all")

    assert result["generated"] == 0
    assert result["error"]
    assert summaries.status(secs) == {"summarized": 0, "total": len(secs)}


def test_refresh_unknown_mode_reports_error(monkeypatch):
    monkeypatch.setattr(summaries.prov, "chat_text", _stub_chat_text())
    secs = parse_sections(DOC)
    result = summaries.refresh(secs, DOC, PROVIDER, "bogus")
    assert result["error"] is not None
    assert result["generated"] == 0


# --- refresh(mode="invalidated") -----------------------------------------


def _seed_all(monkeypatch, secs, text):
    monkeypatch.setattr(summaries.prov, "chat_text", _stub_chat_text())
    summaries.refresh(secs, text, PROVIDER, "all")
    # Push every cached summary's timestamp into the past so the change-gate's
    # staleness check (age > STALE_AFTER_S) actually engages.
    old = time.time() - summaries.STALE_AFTER_S - 1
    for sid, s in list(summaries._STORE.items()):
        summaries._STORE[sid] = dataclasses.replace(s, generated_at=old)


def test_refresh_invalidated_skips_unchanged_sections(monkeypatch):
    secs = parse_sections(DOC)
    _seed_all(monkeypatch, secs, DOC)

    def _gate_should_not_run(**kwargs):
        raise AssertionError("change-gate should not run for unchanged, stale-timestamp text")

    monkeypatch.setattr(summaries.prov, "chat_text", _gate_should_not_run)
    result = summaries.refresh(secs, DOC, PROVIDER, "invalidated")
    assert result == {"generated": 0, "checked": 0, "skipped": len(secs) + 1, "tokens": 0, "error": None}


def test_refresh_invalidated_no_verdict_refreshes_timestamp_only(monkeypatch):
    secs = parse_sections(DOC)
    _seed_all(monkeypatch, secs, DOC)

    new_doc = DOC.replace("alpha body", "alpha body, now revised")
    new_secs = parse_sections(new_doc)

    monkeypatch.setattr(summaries.prov, "chat_text", _stub_chat_text(reply_for_gate="NO"))
    result = summaries.refresh(new_secs, new_doc, PROVIDER, "invalidated")

    assert result["generated"] == 0
    assert result["error"] is None
    assert result["checked"] >= 1  # at least Alpha (text changed, summary judged unaffected)

    alpha = next(s for s in new_secs if s.title == "Alpha")
    cached = summaries.get(alpha.id)
    assert cached.summary == "Stub summary."  # unchanged
    assert cached.source_text == alpha.text  # but source_text caught up


def test_refresh_invalidated_yes_verdict_regenerates_summary(monkeypatch):
    secs = parse_sections(DOC)
    _seed_all(monkeypatch, secs, DOC)

    new_doc = DOC.replace("alpha body", "alpha body, now revised")
    new_secs = parse_sections(new_doc)

    monkeypatch.setattr(summaries.prov, "chat_text", _stub_chat_text(reply_for_gate="YES"))
    result = summaries.refresh(new_secs, new_doc, PROVIDER, "invalidated")

    assert result["generated"] >= 1
    alpha = next(s for s in new_secs if s.title == "Alpha")
    cached = summaries.get(alpha.id)
    assert cached.summary == "Stub summary."
    assert cached.source_text == alpha.text


def test_refresh_invalidated_provider_error_is_captured(monkeypatch):
    secs = parse_sections(DOC)
    _seed_all(monkeypatch, secs, DOC)

    new_doc = DOC.replace("alpha body", "alpha body, now revised")
    new_secs = parse_sections(new_doc)

    def _raise(**kwargs):
        raise ProviderError("boom")

    monkeypatch.setattr(summaries.prov, "chat_text", _raise)
    result = summaries.refresh(new_secs, new_doc, PROVIDER, "invalidated")
    assert result["error"] == "boom"
