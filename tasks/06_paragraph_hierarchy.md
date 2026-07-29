# Task 06 — Paragraph-level hierarchy + additive, multi-level-adjacency summaries

## Goal
Push the summary hierarchy down to the **paragraph** (currently it stops at the
markdown section), glue display **formulas** into adjacent prose, make summaries
**additive** (a child adds to its parents, never repeats them), and give an edit
**prev/next context at every level** — adjacent paragraphs, `###`, `##`, `#`, plus
the whole-doc summary. Extends Task 03.

> Subtasks for a simpler subagent. Orient with `graphify query "<q>"`; the backend
> is coupled, so one agent may do ST-1…ST-4. Depends on Task 03 (`sections.py`,
> `summaries.py`, `context.py`, `app.py`). Do NOT touch `static/`.

## Fixed rules
- **Leaf = paragraph** ("block"): doc → `#` chapter → `##` section → `###`
  subsection → **paragraph**.
- **Formula gluing:** a display-math block (`$$…$$`, may span lines) is never its
  own paragraph. Glue to the **previous** paragraph; **also** glue the **next**
  paragraph when the formula starts a section (no previous paragraph) OR the text
  right after it begins with a **lowercase** letter (sentence continues).
- **Additive summaries:** summaries assume the reader has the parent summaries;
  add only what's new. Generate **top-down** so parents exist first.
- **Adjacency at every level:** context carries prev/next summaries for the current
  paragraph, its `###`, its `##`, its `#`, plus the doc summary.

## Subtasks

### ST-1 — `sections.py`: paragraph blocks + gluing (pure, tested)
- `@dataclass Block { id, section_id, index, start_line, end_line, text }`.
- `parse_blocks(text) -> list[Block]`: walk lines tracking the deepest enclosing
  heading-section; blank-line-separated paragraphs become blocks owned by that
  section (heading lines aren't blocks). A `$$` opening a display block is consumed
  through its closing `$$` as one block (even across blank lines); flag "pure
  formula" blocks; then apply the gluing rule. `id = f"{section_id}::p{index}"`
  (index assigned after gluing).
- `block_at(blocks, offset, text) -> Block | None`;
  `block_adjacent(blocks, target) -> tuple[Block|None, Block|None]` (prev/next in
  document order).
- Tests: splitting; formula→prev; formula continues-lowercase→merge next; formula
  starts-section→merge next; `block_at`/`block_adjacent`.

### ST-2 — `summaries.py`: additive + block-aware
- `summarize(text, parent_summaries, provider) -> str`; system:
  *"Summarize in 1–3 sentences. The reader already has the parent context below; do
  NOT repeat it — add only what is new and specific to this text. Output only the
  summary."*; user: `Parent context:\n{joined}\n\nText:\n{text}`.
- Store holds section AND block summaries (block ids as above; `__doc__` = whole doc).
- `refresh(sections, blocks, whole_text, provider, mode)` — top-down: `__doc__` →
  sections in (level, position) order (parents = ancestor summaries) → blocks
  (parents = doc + ancestor-section summaries). Keep the change-gate for existing
  entries; `all` regenerates everything.
- Extend `estimate`, `status`, `validity` to include blocks.

### ST-3 — `context.py`: paragraph leaf + per-level adjacency
`build_context(*, project_summary, sections, blocks, target_block, selection,
instruction, store)`. Order:
1. Project summary → Document summary.
2. For each ancestor level outer→inner (`#`→`##`→`###`): `[prev-sibling summary]`
   · ancestor summary · `[next-sibling summary]` (via `adjacent(sections, ancestor)`).
3. Leaf: `[prev-paragraph summary]` · **Current paragraph (FULL TEXT)** ·
   `[next-paragraph summary]` (via `block_adjacent`).
4. Selected text → Instruction.
Label items by level+title (e.g. `"## Foo (prev)"`); missing summary → excerpt
fallback; omit absent neighbours. Keep `ContextItem`/`ContextPackage`/`as_prompt`.

### ST-4 — `app.py`: wire blocks
`/api/revise`: `blocks = parse_blocks(text)`, `target = block_at(blocks, sel_start, text)`;
call the new `build_context`. `summaries/refresh|estimate|status` operate on
sections+blocks. Keep `_resolve_endpoint` and the `prompt`/`context` response shape.

### ST-5 — tests + verify
Unit tests for blocks/gluing and additive parent-passing (stub `chat_text`); a
TestClient revise showing Current = the paragraph's full text and neighbours =
adjacent **paragraph** summaries, ancestors = section summaries. `uv run pytest` green.

## Acceptance
- Editing inside a paragraph sends that paragraph's full text + additive summaries
  of its prev/next at every level (paragraph, `###`, `##`, `#`) + doc summary —
  never the whole manuscript, never repeated parent text.
- Display formulas never appear as their own summary unit.
