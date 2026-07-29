# Task 03 — Hierarchical summaries for context construction

## Goal
Stop sending the whole manuscript to the model. For an edit, send: the **full text
of the current section only**, plus **1–3 sentence summaries** of its parent
hierarchy, its previous/next sibling, and the whole document. Summaries are cached,
change-gated on regeneration, refreshed on a timer, and manually regenerable with a
token warning. Add 30 s autosave.

> This brief is written as discrete subtasks (ST-1…ST-8). Each is self-contained —
> a subagent can implement one at a time. Orient with `graphify query "<question>"`
> or by reading the named file.

## Design decisions (fixed)
- **Cache:** in-memory server-side dict keyed by section id, plus a `__doc__` key for
  the whole-document summary. Disk persistence is future work.
- **Model:** reuse the caller's configured provider/model (server `.env` key) for
  both summarizing and change-detection; all LLM calls stay server-side.
- **Timers (frontend):** autosave every 30 s if dirty & a file is open; summary
  refresh (invalidated-only) every 10 min.
- **Token policy:** the 10-min tick only re-checks *existing* summaries. **Missing**
  summaries are generated only via the user's "Regenerate summaries" (mode `all`,
  shown a token estimate first).
- **Fallback:** a section with no cached summary contributes a local excerpt (first
  ~2 sentences, no LLM), labelled "(unsummarized)", so revise always works.
- **Change-gate:** `Summary` stores `source_text`. On refresh, if
  `section.text != source_text` AND age > 10 min → build a local `difflib` diff →
  ask the model (old summary + diff **only**) "does this change the summary? YES/NO"
  → regenerate only on YES; on NO just refresh `source_text` + timestamp.
- **Future:** build a section's summary from its child summaries; for now summarize
  the section's whole text.

## Subtasks

### ST-1 — `src/mdpad/sections.py`: hierarchy helpers (pure)
- `ancestors(sections, target) -> list[Section]`: enclosing sections (level < target
  and line range contains target), ordered root → immediate parent.
- `adjacent(sections, target) -> tuple[Section | None, Section | None]`: previous and
  next **sibling** (nearest section with the same level and same parent as target).
- Tests in `tests/test_sections.py` on a `#`/`##`/`###` document.

### ST-2 — `src/mdpad/provider.py`: plain-text completion
- `chat_text(*, system: str, user: str, provider: dict) -> str`: same httpx call +
  HTTP-error-body handling as `revise`, but returns the raw message content (no JSON
  parse). Blank base_url/api_key/model → raise `ProviderError` (callers decide).

### ST-3 — `src/mdpad/summaries.py` (new): store + logic
- `@dataclass Summary { section_id, title, summary, source_text, generated_at: float }`.
- Module `_STORE: dict[str, Summary]`; `get(id)`, `put(summary)`, `reset()`.
- `summarize(text, provider) -> str` — `chat_text` with system: *"Summarize this
  manuscript section in 1–3 sentences: its purpose and key claims. Output only the
  summary, no preamble."*
- `diff_text(old, new) -> str` — `difflib.unified_diff` joined to a string.
- `summary_changed(old_summary, diff, provider) -> bool` — `chat_text` with system:
  *"You get a section's current summary and a unified diff of edits. Answer with one
  word: YES if the summary should change, otherwise NO."* → `resp.strip().upper().startswith("Y")`.
- `refresh(sections, whole_text, provider, mode) -> dict`:
  - `mode == "all"`: (re)summarize every section and `__doc__` (from `whole_text`).
  - `mode == "invalidated"`: for each existing summary, apply the change-gate; also
    re-check `__doc__` vs `whole_text`. Do **not** create missing summaries.
  - Returns `{ "generated": int, "checked": int, "skipped": int, "tokens": int, "error": str|None }`.
- `estimate(sections, mode) -> dict` → `{ "count": int, "est_tokens": int }` (no LLM;
  `est_tokens ≈ Σ len(section.text)//4 + overhead`).
- `status(sections) -> dict` → `{ "summarized": int, "total": int }`.
- Tests (`tests/test_summaries.py`) for `diff_text`, `estimate`, and `refresh` with a
  stub `provider` (monkeypatch `chat_text`).

### ST-4 — `src/mdpad/context.py`: summary-based package
Rewrite `build_context` to:
`build_context(*, project_summary, sections, target, selection, instruction, store)`.
Item order: **Project summary → Document summary (`__doc__`) → Parent sections
(ancestor summaries, each `title: summary`) → Previous section (summary) → Current
section (full text) → Next section (summary) → Selected text → Instruction.**
Missing summary → `_excerpt(text)` (first ~2 sentences) with a "(unsummarized)" note.
Keep `ContextItem` / `ContextPackage` / `as_prompt` / `as_dict`.

### ST-5 — `src/mdpad/app.py`: wire store + endpoints
- `/api/revise`: build context via `context.build_context(..., sections=parse_sections(text),
  target=section_at(...), store=summaries._STORE)`.
- `POST /api/summaries/refresh {text, mode, provider}` → resolve endpoint via
  `_resolve_endpoint`, call `summaries.refresh(parse_sections(text), text, provider, mode)`.
- `POST /api/summaries/estimate {text, mode}` → `summaries.estimate(...)` (no LLM).
- `GET /api/summaries {text}` or query → `summaries.status(...)`.
- Accept (TestClient): `refresh {mode:"all"}` with a real model fills `_STORE`;
  `/api/revise` `prompt.user` then contains neighbor **summaries**, not neighbor full text.

### ST-6 — `src/mdpad/static/app.js`: autosave
`setInterval(30_000)`: if `dirty && currentName` → `await saveFile()` (silent; toast
"Autosaved <name>").

### ST-7 — `src/mdpad/static/app.js`: summary tick
`setInterval(600_000)`: `POST /api/summaries/refresh { text: editor.value,
mode: "invalidated", provider: readSettings() }`; toast a one-line result.

### ST-8 — `app.js` + `index.html`: manual regenerate + status
Sidebar button "Regenerate summaries": `POST /api/summaries/estimate {text, mode:"all"}`
→ `confirm("~N tokens. Regenerate all summaries?")` → `POST refresh {mode:"all"}` →
toast counts. Small status label (e.g. "12/15 summarized"), refreshed via `GET /api/summaries`.

## Acceptance (whole task)
- `uv run pytest` green.
- With summaries generated, the revise prompt shows neighbor/parent **summaries** +
  current-section full text — never the whole manuscript.
- Editing a section then waiting the tick regenerates its summary only if the model
  says the diff changed it (change-gate), and only after 10 min.
- Autosave persists edits within 30 s; manual regenerate warns tokens first.
