# Architecture

Reference detail for the mdpad codebase: where things live, and how to run
the environment day to day. See `CLAUDE.md` for the high-level philosophy and
design invariants, and `README.md` for run/use instructions.

## Codebase map

Backend — all logic in Python, `src/mdpad/`:
- `app.py` — FastAPI app + entry point. Serves the SPA and the JSON API:
  `GET /api/document`, file open/save (`/api/files`, `/api/file/{name}`),
  provider (`/api/config`, `/api/models`), `POST /api/revise`, and the summary
  endpoints (`/api/summaries`, `/api/summaries/refresh`, `/api/summaries/estimate`).
  The `.env` key is resolved server-side via `_resolve_endpoint` and never sent to
  the browser; a custom base URL must bring its own key.
- `sections.py` — heading parser (`parse_sections`, `section_at`) plus hierarchy
  helpers (`ancestors`, `adjacent`); authoritative for context building.
- `context.py` — builds the inspectable, **summary-based** context package:
  project summary → document summary → parent summaries → previous-section summary
  → current section (full text) → next-section summary → selection → instruction
  (a missing summary falls back to a local excerpt). Rough `len/4` token estimates.
- `summaries.py` — in-memory summary store keyed by section id (+ a `__doc__` key):
  `summarize`, `diff_text` (difflib), change-gated `refresh` (`all`|`invalidated`),
  `estimate`, `status`. All LLM calls go through `provider.chat_text`.
- `provider.py` — one OpenAI-compatible interface: `revise` (strict-JSON + offline
  **mock**), `chat_text` (plain completions, for summaries), `list_models`.
- `example/book.md` — default manuscript loaded on start.

Frontend — `src/mdpad/static/` (`index.html`, `styles.css`, `app.js`, `vendor/`):
a `<textarea>` editor, markdown-it + KaTeX preview (both **vendored** under
`vendor/`, no CDN), outline, selection actions, model dropdown, open/save,
draggable pane/dock dividers, editor↔preview block sync, 30 s autosave, and a
token-warned "Regenerate summaries" control. The visible context "spectrum" bar
and the read-only full-prompt textarea live in the bottom dock. Provider
model/settings live in `localStorage`; the API key stays server-side (`.env`).

## Environment & commands

Windows / PowerShell. Python is managed by **uv** (project requires Python
>=3.14). src-layout: package lives in `src/mdpad/`.

- Launch the app (starts a local server + opens the browser at
  `http://127.0.0.1:8670`, free-port fallback): `uv run mdpad [FILE.md]`. Works
  offline via the mock; a provider (GPUStack via `.env`, or **Settings**) enables
  real edits and summaries.
- Run tests: `uv run pytest`
- Editable install into a local `.venv` (then `.venv\Scripts\activate` → `mdpad`): run `install.bat`
- Refresh/sync the env: `uv sync`  ·  Add a dependency: `uv add <pkg>`

Entry point: `mdpad = "mdpad:main"` → `main()` in `src/mdpad/app.py`
(re-exported from `__init__.py`) starts uvicorn. Keep stdout ASCII — the Windows
console mangles non-ASCII characters (e.g. em-dash).

## Tooling

`graphifyy` is installed as a global uv tool, providing the `graphify` /
`graphify-mcp` CodeGraph tooling. **Restart Claude Code after installing it** so
the tooling is picked up.
