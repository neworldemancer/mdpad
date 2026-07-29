from fastapi.testclient import TestClient

from mdpad.app import app
from mdpad.context import build_context
from mdpad.sections import (
    adjacent,
    ancestors,
    block_adjacent,
    block_at,
    parse_blocks,
    parse_sections,
    section_at,
)
from mdpad.summaries import Summary
from mdpad.summaries import reset as reset_summaries

DOC = """# Chapter
intro line

## Alpha
alpha body

## Beta
beta body
"""

# A three-level document (#/##/###) for ancestors()/adjacent() hierarchy tests.
HDOC = """# Book
book intro

## Alpha
alpha body

### Alpha One
a1 body

### Alpha Two
a2 body

## Beta
beta body
"""

# A display formula with a paragraph before it and one that starts a new
# sentence ("Second...") -- glues to the previous paragraph only.
FORMULA_PREV_ONLY = """## Sec
First paragraph text ends here.

$$
E = mc^2
$$

Second paragraph starts new sentence.
"""

# A display formula whose surrounding text is one continuous sentence -- glues
# to both the previous and the next paragraph.
FORMULA_MERGE_LOWERCASE = """## Sec
We define the energy as

$$
E = mc^2
$$

which is the famous formula.
"""

# A display formula that opens its section (no previous paragraph) -- must
# glue to the next paragraph regardless of case.
FORMULA_STARTS_SECTION = """## Sec
$$
E = mc^2
$$

Some explanation follows.
"""


def test_parses_flat_sections_with_ranges():
    secs = parse_sections(DOC)
    assert [s.title for s in secs] == ["Chapter", "Alpha", "Beta"]
    # Chapter spans the whole document; Alpha stops where Beta begins.
    chapter, alpha, beta = secs
    assert chapter.level == 1 and chapter.end_line == len(DOC.splitlines())
    assert alpha.level == 2 and alpha.end_line == beta.start_line


def test_duplicate_titles_get_unique_ids():
    secs = parse_sections("## X\n\n## X\n")
    assert [s.id for s in secs] == ["x", "x-1"]


def test_section_at_returns_deepest_containing_section():
    secs = parse_sections(DOC)
    offset = DOC.index("alpha body")
    assert section_at(secs, offset, DOC).title == "Alpha"


def test_ancestors_orders_root_to_immediate_parent():
    secs = parse_sections(HDOC)
    by_title = {s.title: s for s in secs}
    anc = ancestors(secs, by_title["Alpha One"])
    assert [a.title for a in anc] == ["Book", "Alpha"]


def test_ancestors_empty_for_top_level_section():
    secs = parse_sections(HDOC)
    assert ancestors(secs, secs[0]) == []


def test_ancestors_single_level_for_second_level_section():
    secs = parse_sections(HDOC)
    by_title = {s.title: s for s in secs}
    anc = ancestors(secs, by_title["Alpha"])
    assert [a.title for a in anc] == ["Book"]


def test_adjacent_siblings_nested_under_same_parent():
    secs = parse_sections(HDOC)
    by_title = {s.title: s for s in secs}

    prev_s, next_s = adjacent(secs, by_title["Alpha One"])
    assert prev_s is None
    assert next_s.title == "Alpha Two"

    prev_s, next_s = adjacent(secs, by_title["Alpha Two"])
    assert prev_s.title == "Alpha One"
    assert next_s is None


def test_adjacent_top_level_siblings_skip_deeper_sections():
    secs = parse_sections(HDOC)
    by_title = {s.title: s for s in secs}
    prev_s, next_s = adjacent(secs, by_title["Alpha"])
    assert prev_s is None
    assert next_s.title == "Beta"


def test_adjacent_only_section_has_no_siblings():
    secs = parse_sections(HDOC)
    prev_s, next_s = adjacent(secs, secs[0])  # "Book", the sole top-level section
    assert prev_s is None and next_s is None


# --- parse_blocks: splitting + formula gluing ------------------------------


def test_parse_blocks_splits_on_blank_lines():
    blocks = parse_blocks(DOC)
    assert [b.text for b in blocks] == ["intro line", "alpha body", "beta body"]
    assert [b.id for b in blocks] == ["chapter::p0", "alpha::p0", "beta::p0"]
    assert [b.index for b in blocks] == [0, 0, 0]


def test_formula_glues_to_previous_paragraph_only():
    blocks = parse_blocks(FORMULA_PREV_ONLY)
    assert len(blocks) == 2
    assert "First paragraph text ends here." in blocks[0].text
    assert "E = mc^2" in blocks[0].text
    assert blocks[1].text == "Second paragraph starts new sentence."


def test_formula_merges_next_when_continuation_is_lowercase():
    blocks = parse_blocks(FORMULA_MERGE_LOWERCASE)
    assert len(blocks) == 1
    assert "We define the energy as" in blocks[0].text
    assert "E = mc^2" in blocks[0].text
    assert "which is the famous formula." in blocks[0].text


def test_formula_merges_next_when_it_starts_the_section():
    blocks = parse_blocks(FORMULA_STARTS_SECTION)
    assert len(blocks) == 1
    assert "E = mc^2" in blocks[0].text
    assert "Some explanation follows." in blocks[0].text


def test_block_at_finds_containing_block():
    blocks = parse_blocks(DOC)
    target = block_at(blocks, DOC.index("alpha body"), DOC)
    assert target is not None
    assert target.text == "alpha body"
    assert target.section_id == "alpha"


def test_block_at_returns_none_for_empty_blocks():
    assert block_at([], 0, DOC) is None


def test_block_adjacent_prev_and_next_in_document_order():
    blocks = parse_blocks(DOC)
    target = block_at(blocks, DOC.index("alpha body"), DOC)
    prev_b, next_b = block_adjacent(blocks, target)
    assert prev_b.text == "intro line"
    assert next_b.text == "beta body"


def test_block_adjacent_none_at_document_edges():
    blocks = parse_blocks(DOC)
    prev_b, next_b = block_adjacent(blocks, blocks[0])
    assert prev_b is None
    assert next_b.text == "alpha body"

    prev_b, next_b = block_adjacent(blocks, blocks[-1])
    assert prev_b.text == "alpha body"
    assert next_b is None


# --- build_context ----------------------------------------------------------


def test_context_package_order_and_totals():
    secs = parse_sections(DOC)
    blocks = parse_blocks(DOC)
    target = block_at(blocks, DOC.index("alpha body"), DOC)
    pkg = build_context(
        project_summary="summary",
        sections=secs,
        blocks=blocks,
        target_block=target,
        selection="alpha body",
        instruction="Rewrite",
        store={},
    )
    # No cached summaries -> every ancestor/neighbour item still appears (via
    # the local excerpt fallback), except "## Alpha (prev)" since Alpha is
    # the first child of Chapter, and "Previous paragraph" for the same
    # reason (Chapter's intro paragraph IS the previous paragraph though, so
    # it does appear -- only the section-level "prev" siblings are absent).
    assert [i.label for i in pkg.items] == [
        "Project summary",
        "Document summary",
        "# Chapter",
        "## Alpha",
        "## Alpha (next)",
        "Previous paragraph",
        "Current paragraph",
        "Next paragraph",
        "Selected text",
        "Instruction",
    ]
    assert pkg.total_tokens == sum(i.tokens for i in pkg.items)


def test_context_uses_cached_summaries_not_full_text_for_neighbors():
    secs = parse_sections(DOC)
    blocks = parse_blocks(DOC)
    target = block_at(blocks, DOC.index("alpha body"), DOC)
    chapter = next(s for s in secs if s.title == "Chapter")
    beta = next(s for s in secs if s.title == "Beta")
    beta_block = next(b for b in blocks if b.section_id == beta.id)
    chapter_block = next(b for b in blocks if b.section_id == chapter.id)
    store = {
        chapter.id: Summary(chapter.id, chapter.title, "Chapter overview.", chapter.text, 0.0),
        beta.id: Summary(beta.id, beta.title, "Beta covers XYZ.", beta.text, 0.0),
        "__doc__": Summary("__doc__", "Document", "Doc-level summary.", DOC, 0.0),
        beta_block.id: Summary(beta_block.id, beta_block.id, "Beta's paragraph, in short.", beta_block.text, 0.0),
        chapter_block.id: Summary(
            chapter_block.id, chapter_block.id, "Chapter's intro, in short.", chapter_block.text, 0.0
        ),
    }
    pkg = build_context(
        project_summary="summary",
        sections=secs,
        blocks=blocks,
        target_block=target,
        selection="alpha body",
        instruction="Rewrite",
        store=store,
    )
    by_label = {i.label: i.text for i in pkg.items}
    assert by_label["Document summary"] == "Doc-level summary."
    assert by_label["# Chapter"] == "Chapter overview."
    assert by_label["## Alpha (next)"] == "Beta covers XYZ."
    assert by_label["Previous paragraph"] == "Chapter's intro, in short."
    assert by_label["Next paragraph"] == "Beta's paragraph, in short."
    assert by_label["Current paragraph"] == "alpha body"
    assert "beta body" not in by_label["## Alpha (next)"]


def test_context_target_none_omits_ancestor_and_paragraph_items():
    secs = parse_sections(DOC)
    blocks = parse_blocks(DOC)
    pkg = build_context(
        project_summary="summary",
        sections=secs,
        blocks=blocks,
        target_block=None,
        selection="",
        instruction="Rewrite",
        store={},
    )
    labels = [i.label for i in pkg.items]
    assert "Current paragraph" not in labels
    assert labels == ["Project summary", "Document summary", "Instruction"]


# --- /api/revise integration (blocks wired end-to-end) ----------------------


def test_revise_endpoint_sends_full_paragraph_and_section_summaries():
    reset_summaries()
    client = TestClient(app)
    offset = DOC.index("alpha body")
    resp = client.post(
        "/api/revise",
        json={
            "text": DOC,
            "sel_start": offset,
            "sel_end": offset + len("alpha body"),
            "instruction": "Rewrite",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["section"] == "Alpha"

    items = {i["label"]: i["text"] for i in data["context"]["items"]}
    assert items["Current paragraph"] == "alpha body"
    assert "# Chapter" in items
    assert "## Alpha" in items
    assert "## Alpha (next)" in items  # Beta is Alpha's next sibling
    assert "Previous paragraph" in items  # Chapter's intro paragraph
    assert "Next paragraph" in items  # Beta's paragraph
    reset_summaries()
