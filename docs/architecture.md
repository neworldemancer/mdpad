# Architecture

Reference detail for the mdpad codebase: where things live, and how to run
the environment day to day. See `CLAUDE.md` for the high-level philosophy and
design invariants, and `README.md` for run/use instructions.

## Codebase map

Backend — all logic in Python, `src/mdpad/`:
- `app.py` — FastAPI app: serves `static/index.html`, `GET /api/document`,
  `POST /api/revise` (build context → call provider → return package + proposal).
- `sections.py` — heading parser (`parse_sections`, `section_at`); authoritative
  for context building.
- `context.py` — builds the inspectable context package + rough `len/4` token estimates.
- `provider.py` — OpenAI-compatible `chat/completions` call, strict-JSON
  validation, and a deterministic offline **mock** used when no provider is configured.
- `example/book.md` — default manuscript loaded on start.

Frontend — `src/mdpad/static/` (`index.html`, `styles.css`, `app.js`): a
`<textarea>` editor, markdown-it + KaTeX preview, outline, selection actions,
and the diff. Provider settings live in `localStorage` and travel with each
request (no server-side secrets). Signature UI element: the context "spectrum"
bar. CDN assets → needs internet until vendored (known TODO; SRI also TODO).

## Environment & commands

Windows / PowerShell. Python is managed by **uv** (project requires Python
>=3.14). src-layout: package lives in `src/mdpad/`.

- Launch the app (starts a local server + opens the browser at
  `http://127.0.0.1:8000`): `uv run mdpad`. Works offline via the mock;
  configure a provider in **Settings** for real edits.
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
