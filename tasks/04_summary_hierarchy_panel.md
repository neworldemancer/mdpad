# Task 04 — Live summary-hierarchy panel (right side)

## Goal
As the caret/selection moves through the document, show — on the **right** — the
**hierarchy of summaries** that would frame an edit at that spot: the document
summary, the parent-section summaries (outer → inner), the current section, and
the previous/next sibling summaries. It updates live as you move, so you always
see the context the model would receive, without running a revise.

This reuses everything Task 03 built (`ancestors`, `adjacent`, the summary store,
the excerpt fallback) — it is a **read-only view of the summary context**, no LLM
calls on selection.

> Written as subtasks for a simple subagent. Orient with `graphify query "<q>"`
> or by reading the named files. Depends on Task 03 (`summaries.py`,
> `sections.ancestors/adjacent`, `context._excerpt`).

## Subtasks

### ST-1 — `src/mdpad/app.py`: context-map endpoint (no LLM)
Add `POST /api/context/map {text, offset}` → for the section at `offset`
(`section_at`), return the summary hierarchy from the in-memory store, using the
same excerpt fallback as `context.build_context` when a summary is missing:
```json
{
  "document": "…doc summary…",
  "ancestors": [{"title": "...", "summary": "...", "level": 1}, …],   // root→parent
  "previous":  {"title": "...", "summary": "..."} | null,
  "current":   {"title": "...", "level": 2},
  "next":      {"title": "...", "summary": "..."} | null
}
```
Add a small helper in `summaries.py` (e.g. `summary_or_excerpt(section, store)`)
so app and `context.py` share the fallback logic. No network. Accept: TestClient
returns the right hierarchy for an offset inside a nested section.

### ST-2 — `index.html` + `styles.css`: the panel
Add a collapsible right-hand `aside#context-map` (after the preview pane) with a
toggle button in the topbar (`#map-toggle`, label "Context"). Structure: a
"Document" summary at top, an indented list of ancestor summaries, the current
section highlighted, and previous/next summary cards. Hidden by default; when
shown, add a `.gutter`-style handle or a fixed ~280px column. Reuse the existing
CSS tokens (`--accent`, `--line`, `--font-*`); keep the visual language.

### ST-3 — `app.js`: live updates
On editor `selectionchange`/`keyup`/`click` (debounced ~250 ms) and when the panel
is visible, `POST /api/context/map {text: editor.value, offset: editor.selectionStart}`
and render the hierarchy (safe DOM: `textContent`/`createElement`). Also refresh
after a revise Accept and after a summaries regeneration. Toggle button shows/hides
the panel (persist the open/closed state in `localStorage`, like the layout).

### ST-4 — polish
Show an "(unsummarized)" tag when a card is an excerpt fallback (so the user knows
to Regenerate). Empty/None neighbours render a muted "— none —".

## Acceptance
- With the panel open, moving the caret between sections updates the right panel to
  show that section's document/parent/prev/current/next summary hierarchy, live,
  with no model calls.
- Sections without a cached summary show their excerpt fallback tagged
  "(unsummarized)".
- `uv run pytest` green (new endpoint test); `node --check app.js` clean.
