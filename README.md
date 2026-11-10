# mdpad

A local-first, AI-assisted environment for writing and revising long
technical/scientific documents (Markdown + LaTeX math). Its defining idea: the
model is sent a compact, **inspectable context package** for the selected text —
never the whole manuscript — and it never replaces your text silently (every
edit is a diff you Accept or Reject).

This is a **proof of concept** (see `tasks/01_poc.md`), not production software.

## Run

Requires [uv](https://docs.astral.sh/uv/) and Python ≥ 3.14 (uv fetches it).

```powershell
uv run mdpad
```

This starts a local server and opens `http://127.0.0.1:8000`. It works
immediately with an **offline mock** (no API key needed) so you can try the full
select → context → diff → accept flow. For real edits, open **Settings** and
enter an OpenAI-compatible endpoint (OpenAI, OpenRouter, LM Studio, Ollama, …):
base URL, API key, and model. Settings are stored in your browser only.

To set a server-side default instead (so the key never has to be typed into
the browser, or lives in source/git), write it to a local `.env`:

```powershell
uv run mdpad-configure --base-url https://host/v1 --api-key sk-...
# or run with no flags to be prompted instead
```

> Note: the preview libraries (markdown-it, KaTeX) currently load from a CDN, so
> the preview needs internet access. Vendoring them for fully-offline use is a
> planned hardening step.

## Use

1. Edit Markdown on the left; the rendered preview (with math) updates on the right.
2. Select a passage, then choose **Rewrite / Expand / Shorten / Custom…**.
3. Inspect exactly what was sent (the context "spectrum" panel) and the proposed diff.
4. **Accept** to apply, or **Reject** to discard. Nothing changes until you accept.

## Develop

```powershell
uv run pytest        # tests (section parsing + context package)
install.bat          # editable install into the active/local venv
```

Layout: Python backend in `src/mdpad/` (`app.py`, `sections.py`, `context.py`,
`provider.py`); zero-build frontend in `src/mdpad/static/` — vanilla HTML/CSS/JS,
no React/TypeScript/bundler, a deliberate choice to keep everything in Python
except the thin UI layer. See `docs/architecture.md` for the codebase map.
