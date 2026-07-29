from mdpad.context import build_context
from mdpad.sections import adjacent, ancestors, parse_sections, section_at
from mdpad.summaries import Summary

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


def test_context_package_order_and_totals():
    secs = parse_sections(DOC)
    target = section_at(secs, DOC.index("alpha body"), DOC)
    pkg = build_context(
        project_summary="summary",
        sections=secs,
        target=target,
        selection="alpha body",
        instruction="Rewrite",
        store={},
    )
    # No cached summaries -> "Parent sections"/"Next section" still appear (via
    # the local excerpt fallback); "Previous section" is absent since Alpha is
    # the first child of Chapter.
    assert [i.label for i in pkg.items] == [
        "Project summary",
        "Document summary",
        "Parent sections",
        "Current section",
        "Next section",
        "Selected text",
        "Instruction",
    ]
    assert pkg.total_tokens == sum(i.tokens for i in pkg.items)


def test_context_uses_cached_summaries_not_full_text_for_neighbors():
    secs = parse_sections(DOC)
    target = section_at(secs, DOC.index("alpha body"), DOC)
    chapter = next(s for s in secs if s.title == "Chapter")
    beta = next(s for s in secs if s.title == "Beta")
    store = {
        chapter.id: Summary(chapter.id, chapter.title, "Chapter overview.", chapter.text, 0.0),
        beta.id: Summary(beta.id, beta.title, "Beta covers XYZ.", beta.text, 0.0),
        "__doc__": Summary("__doc__", "Document", "Doc-level summary.", DOC, 0.0),
    }
    pkg = build_context(
        project_summary="summary",
        sections=secs,
        target=target,
        selection="alpha body",
        instruction="Rewrite",
        store=store,
    )
    by_label = {i.label: i.text for i in pkg.items}
    assert by_label["Document summary"] == "Doc-level summary."
    assert by_label["Parent sections"] == "Chapter: Chapter overview."
    assert by_label["Next section"] == "Beta: Beta covers XYZ."
    assert "alpha body" in by_label["Current section"]
    assert "beta body" not in by_label["Next section"]
