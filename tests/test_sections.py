from mdpad.context import build_context
from mdpad.sections import parse_sections, section_at

DOC = """# Chapter
intro line

## Alpha
alpha body

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


def test_context_package_order_and_totals():
    secs = parse_sections(DOC)
    pkg = build_context(
        project_summary="summary",
        section=section_at(secs, DOC.index("alpha body"), DOC),
        selection="alpha body",
        instruction="Rewrite",
    )
    assert [i.label for i in pkg.items] == [
        "Project summary",
        "Current section",
        "Selected text",
        "Instruction",
    ]
    assert pkg.total_tokens == sum(i.tokens for i in pkg.items)
