"""FastAPI application: serves the single-page workspace and its JSON endpoints.

Provider config lives in the browser (localStorage) and travels with each revise
request. The API key can also be supplied server-side via a ``.env`` file
(``GPUSTACK_TEST_API_KEY``) so it is never exposed to client code; the browser
then only picks a model. A blank field in a request falls back to the server
default (base URL + key).
"""

from __future__ import annotations

import os
import re
import webbrowser
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import context as ctx
from . import provider as prov
from . import summaries as summ
from .sections import block_at, parse_blocks, parse_sections

load_dotenv()
# Server-side provider defaults. The key is read from .env and never sent to the
# browser; base URL defaults to the GPUStack endpoint but is overridable per-request.
SERVER_API_KEY = os.getenv("GPUSTACK_TEST_API_KEY", "")
SERVER_BASE_URL = (os.getenv("MDPAD_BASE_URL") or "https://api.openai.com/v1").rstrip("/")

_HERE = Path(__file__).parent
_STATIC = _HERE / "static"
_DEFAULT_DOC = (_HERE / "example" / "book.md").read_text(encoding="utf-8")
_PROJECT_SUMMARY = (
    "A vision/review manuscript on representation dynamics and the physics of "
    "information processing. Audience: researchers in representation learning. "
    "Tone: precise, hypothesis-aware, mathematically careful."
)

# The manuscript served to the browser. Defaults to the bundled example; a file
# path passed to `mdpad` (e.g. `uv run mdpad test.md`) replaces it at startup.
_current_doc = _DEFAULT_DOC
_current_name: str | None = None

# Open/Save operate on Markdown files in the folder mdpad was launched from.
DOCS_DIR = Path.cwd()
_NAME_RE = re.compile(r"^[\w.\-]+\.md$")
DEFAULT_PORT = 8670

app = FastAPI(title="mdpad")


def _safe_doc_path(name: str) -> Path:
    """Resolve ``name`` to a .md file directly inside DOCS_DIR (no traversal)."""
    if not _NAME_RE.match(name):
        raise HTTPException(400, "Invalid filename (use letters, digits, . - _ and a .md extension).")
    path = (DOCS_DIR / name).resolve()
    if path.parent != DOCS_DIR.resolve():
        raise HTTPException(400, "Filename must not point outside the documents folder.")
    return path


def _summ_path(name: str) -> Path:
    """Sidecar file caching a document's summaries: ``<name>.summ.json``."""
    return DOCS_DIR / f"{name}.summ.json"


class ProviderSettings(BaseModel):
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.3
    max_tokens: int = 1024


class ReviseRequest(BaseModel):
    text: str
    sel_start: int
    sel_end: int
    instruction: str
    provider: ProviderSettings = Field(default_factory=ProviderSettings)


class SummariesRefreshRequest(BaseModel):
    text: str
    mode: str = "invalidated"
    provider: ProviderSettings = Field(default_factory=ProviderSettings)


class SummariesEstimateRequest(BaseModel):
    text: str
    mode: str = "all"


class SummariesStatusRequest(BaseModel):
    text: str = ""


class ContextMapRequest(BaseModel):
    text: str
    offset: int = 0


def _resolve_endpoint(base_url: str, api_key: str) -> tuple[str, str]:
    """Resolve (base_url, api_key) without ever leaking the server key.

    The server-side .env key is only ever paired with the server's own base URL.
    A caller-supplied custom base URL must bring its own key -- otherwise a
    forged request (e.g. ?base_url=http://attacker/) could exfiltrate the key.
    """
    bu = (base_url or SERVER_BASE_URL).rstrip("/")
    if bu == SERVER_BASE_URL:
        return bu, (api_key or SERVER_API_KEY)
    if not api_key:
        raise ValueError("A custom base URL requires its own API key.")
    return bu, api_key


# Model ids whose names indicate a non-chat model (won't work with /chat/completions).
_NON_CHAT_HINTS = ("whisper", "embedding", "rerank", "-tts", "-stt")


def _chat_models(ids: list[str]) -> list[str]:
    return [m for m in ids if not any(h in m.lower() for h in _NON_CHAT_HINTS)]


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


@app.get("/api/document")
def document() -> dict:
    return {"text": _current_doc, "project_summary": _PROJECT_SUMMARY, "name": _current_name}


@app.get("/api/config")
def provider_config() -> dict:
    """Non-secret provider defaults for the UI (never returns the key itself)."""
    return {"base_url": SERVER_BASE_URL, "has_key": bool(SERVER_API_KEY)}


@app.get("/api/usage")
def usage() -> dict:
    """Cumulative token usage for this server session."""
    return prov.usage_totals()


@app.get("/api/models")
def list_models_endpoint(base_url: str = "", api_key: str = "") -> dict:
    """Fetch the OpenAI-compatible model list. Blank args use the server defaults."""
    bu = (base_url or SERVER_BASE_URL).rstrip("/")
    try:
        _, ak = _resolve_endpoint(base_url, api_key)
        models = _chat_models(prov.list_models(base_url=bu, api_key=ak))
        return {"models": models, "base_url": bu, "has_key": bool(ak), "error": None}
    except (ValueError, prov.ProviderError) as e:
        return {"models": [], "base_url": bu, "has_key": bool(api_key), "error": str(e)}


@app.get("/api/files")
def list_files() -> dict:
    files = sorted(p.name for p in DOCS_DIR.glob("*.md") if p.is_file())
    return {"dir": str(DOCS_DIR), "files": files, "current": _current_name}


class SaveRequest(BaseModel):
    name: str
    text: str


@app.get("/api/file/{name}")
def read_file(name: str) -> dict:
    global _current_doc, _current_name
    path = _safe_doc_path(name)
    if not path.is_file():
        raise HTTPException(404, f"No such file in {DOCS_DIR}: {name}")
    _current_doc = path.read_text(encoding="utf-8")
    _current_name = name
    summ.load(_summ_path(name))  # reuse this doc's cached summaries if present
    return {"name": name, "text": _current_doc}


@app.post("/api/file")
def save_file(req: SaveRequest) -> dict:
    global _current_doc, _current_name
    path = _safe_doc_path(req.name)
    path.write_text(req.text, encoding="utf-8")
    _current_doc = req.text
    _current_name = req.name
    return {"ok": True, "name": req.name}


@app.post("/api/revise")
def revise(req: ReviseRequest) -> dict:
    selection = req.text[req.sel_start:req.sel_end]
    sections = parse_sections(req.text)
    blocks = parse_blocks(req.text)
    target_block = block_at(blocks, req.sel_start, req.text)
    owner_section = None
    if target_block is not None:
        owner_section = next((s for s in sections if s.id == target_block.section_id), None)
    package = ctx.build_context(
        project_summary=_PROJECT_SUMMARY,
        sections=sections,
        blocks=blocks,
        target_block=target_block,
        selection=selection,
        instruction=req.instruction,
        store=summ._STORE,
    )
    proposal = None
    error = None
    try:
        d = req.provider.model_dump()
        d["base_url"], d["api_key"] = _resolve_endpoint(d.get("base_url", ""), d.get("api_key", ""))
        proposal = prov.revise(
            package_text=package.as_prompt(),
            selection=selection,
            instruction=req.instruction,
            provider=d,
        )
    except (ValueError, prov.ProviderError) as e:
        error = str(e)
    return {
        "section": owner_section.title if owner_section else None,
        "context": package.as_dict(),
        "prompt": {"system": prov.SYSTEM_PROMPT, "user": package.as_prompt()},
        "proposal": proposal.as_dict() if proposal else None,
        "error": error,
        "usage": prov.usage_totals(),
    }


@app.post("/api/summaries/refresh")
def summaries_refresh(req: SummariesRefreshRequest) -> dict:
    sections = parse_sections(req.text)
    blocks = parse_blocks(req.text)
    d = req.provider.model_dump()
    try:
        d["base_url"], d["api_key"] = _resolve_endpoint(d.get("base_url", ""), d.get("api_key", ""))
    except ValueError as e:
        return {"generated": 0, "checked": 0, "skipped": 0, "tokens": 0, "error": str(e)}
    result = summ.refresh(sections, blocks, req.text, d, req.mode)
    if _current_name:
        summ.save(_summ_path(_current_name))  # persist so a reopen reuses them
    result["usage"] = prov.usage_totals()
    return result


@app.post("/api/summaries/estimate")
def summaries_estimate(req: SummariesEstimateRequest) -> dict:
    sections = parse_sections(req.text)
    blocks = parse_blocks(req.text)
    return summ.estimate(sections, blocks, req.mode)


@app.post("/api/summaries")
def summaries_status(req: SummariesStatusRequest) -> dict:
    text = req.text or _current_doc
    sections = parse_sections(text)
    blocks = parse_blocks(text)
    return summ.status(sections, blocks, text)


@app.post("/api/context/map")
def context_map(req: ContextMapRequest) -> dict:
    """The summary hierarchy for the paragraph at ``offset`` (no LLM): the same
    items build_context assembles, plus per-unit validity and counts."""
    sections = parse_sections(req.text)
    blocks = parse_blocks(req.text)
    target = block_at(blocks, req.offset, req.text)
    package = ctx.build_context(
        project_summary=_PROJECT_SUMMARY,
        sections=sections,
        blocks=blocks,
        target_block=target,
        selection="",
        instruction="",
        store=summ._STORE,
    )
    return {
        "items": package.as_dict()["items"],
        "counts": summ.status(sections, blocks, req.text),
        "current": target.id if target else None,
    }


app.mount("/static", StaticFiles(directory=_STATIC), name="static")


def _free_port(preferred: int) -> int:
    """Return ``preferred`` if bindable, else an OS-assigned free port."""
    import socket

    for candidate in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", candidate))
                return s.getsockname()[1]
            except OSError:
                continue
    return preferred


def _open_when_ready(url: str) -> None:
    """Open the browser only once the server answers (avoids ERR_EMPTY_RESPONSE)."""
    import time
    import urllib.request

    for _ in range(60):
        try:
            urllib.request.urlopen(url, timeout=0.5)
            break
        except Exception:
            time.sleep(0.2)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main() -> None:
    """Launch the local server and open the workspace in a browser.

    Usage: ``mdpad [FILE.md]`` -- an optional Markdown file to open instead of
    the bundled example.
    """
    import sys
    import threading

    import uvicorn

    global _current_doc, _current_name
    paths = [a for a in sys.argv[1:] if not a.startswith("-")]
    if paths:
        target = Path(paths[0])
        if target.is_file():
            _current_doc = target.read_text(encoding="utf-8")
            _current_name = target.name
            n = summ.load(_summ_path(target.name))
            print(f"mdpad: loaded {target}" + (f" (+{n} cached summaries)" if n else ""))
        else:
            print(f"mdpad: file not found, using the bundled example: {target}")

    host = "127.0.0.1"
    port = _free_port(DEFAULT_PORT)
    url = f"http://{host}:{port}"
    if port != DEFAULT_PORT:
        print(f"mdpad: port {DEFAULT_PORT} busy, using {port}")
    print(f"mdpad: serving on {url}")
    threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="info")
