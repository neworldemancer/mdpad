# mdpad

[![CI](https://github.com/neworldemancer/mdpad/actions/workflows/ci.yml/badge.svg)](https://github.com/neworldemancer/mdpad/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mdpad.svg)](https://pypi.org/project/mdpad/)
[![Python](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache--2.0-informational.svg)](LICENSE)

A local-first, AI-assisted environment for writing and revising long
technical/scientific documents (Markdown + LaTeX math). Its defining idea: the
model is sent a compact, **inspectable context package** for the selected text —
never the whole manuscript — and it never replaces your text silently (every
edit is a diff you Accept or Reject).

This is a **proof of concept** (see `tasks/done/01_poc.md`), not production software.

## Run

Requires [uv](https://docs.astral.sh/uv/) and Python ≥ 3.14 (uv fetches it).

```powershell
uv run mdpad
```

Or double-click `mdpad.bat` (Windows) / run `./mdpad.sh` (macOS/Linux).

Don't want to clone the repo at all? `uvx mdpad` runs it straight from PyPI,
no install step:

```powershell
uvx mdpad
```

This starts a local server and opens `http://127.0.0.1:8000`. It works
immediately with an **offline mock** (no API key needed) so you can try the full
select → context → diff → accept flow. For real edits, open **Settings** and
enter an OpenAI-compatible endpoint (OpenAI, OpenRouter, LM Studio, Ollama, …):
base URL, API key, and model. Settings are stored in your browser only.

To set a server-side default instead (so the key never has to be typed into
the browser, or lives in source/git), write it to a local `.env` — the same
`mdpad` command handles this with `--configure`, so no second tool/invocation
is needed even with `uvx`:

```powershell
uvx mdpad --configure --base-url https://host/v1 --api-key sk-...
# or with no flags, to be prompted instead
```

Then every regular run picks that `.env` up — with a cloned repo, `uv run mdpad`
already does (python-dotenv finds it in the working directory); running via
`uvx` instead, hand it to uv explicitly so it's loaded regardless of the
current directory's own project state:

```powershell
uv run --env-file .env --no-project --with mdpad mdpad
```

The preview libraries (markdown-it, KaTeX, Mermaid) are vendored locally, so
the editor/preview works fully offline once the page has loaded.

## Use

1. Edit Markdown on the left; the rendered preview (with math) updates on the right.
2. Select a passage, then choose **Rewrite / Expand / Shorten / Custom…**.
3. Inspect exactly what was sent (the context "spectrum" panel) and the proposed diff.
4. **Accept** to apply, or **Reject** to discard. Nothing changes until you accept.

## Develop

```powershell
uv sync --group dev    # install dev tools (pytest, ruff, mypy)
uv run pytest           # tests (section parsing + context package)
uv run ruff check .     # lint
uv run ruff format .    # format
uv run mypy src/mdpad   # type check
install.bat             # editable install into the active/local venv
```

CI (`.github/workflows/ci.yml`) runs all of the above on every push/PR.
Pushing a tag matching `vX.Y[.Z]` publishes to PyPI (`.github/workflows/publish.yml`).

Layout: Python backend in `src/mdpad/` (`app.py`, `sections.py`, `context.py`,
`provider.py`); zero-build frontend in `src/mdpad/static/` — vanilla HTML/CSS/JS,
no React/TypeScript/bundler, a deliberate choice to keep everything in Python
except the thin UI layer. See `docs/architecture.md` for the codebase map.
