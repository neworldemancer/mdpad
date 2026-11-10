"""FastAPI application: serves the single-page workspace and its JSON endpoints.

Provider config lives in the browser (localStorage) and travels with each revise
request. The base URL and API key can also be supplied server-side via a
``.env`` file (``MDPAD_BASE_URL`` / ``MDPAD_API_KEY`` — see ``mdpad-configure``)
so the key is never exposed to client code; the browser then only picks a
model. A blank field in a request falls back to the server default.
"""

from __future__ import annotations

import os
import re
import time
import webbrowser
from datetime import datetime
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
# Server-side provider defaults, set via `.env` (see `mdpad-configure`). Never
# sent to the browser; blank means no server default (offline mock unless a
# request supplies its own base URL + key). GPUSTACK_TEST_API_KEY is a legacy
# alias kept for existing `.env` files.
_server_api_key = os.getenv("MDPAD_API_KEY") or os.getenv("GPUSTACK_TEST_API_KEY")
SERVER_API_KEY: str = _server_api_key if _server_api_key else ""
SERVER_BASE_URL = (os.getenv("MDPAD_BASE_URL") or "").rstrip("/")

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

# Projects: each is a folder of flat .md files (+ .summ.json sidecars) plus a
# shared history/ of save snapshots. PROJECTS_ROOT is where "New Project"
# creates one by default; PROJECT_DIR is whichever project is currently open
# (None until one is opened/created -- open/save/history are gated on it).
PROJECTS_ROOT = Path.cwd() / "projects"
PROJECT_DIR: Path | None = None
_NAME_RE = re.compile(r"^[\w.\-]+\.md$")
_PROJECT_NAME_RE = re.compile(r"^[\w.\- ]+$")
HISTORY_RETENTION_DAYS = 30
DEFAULT_PORT = 8670

app = FastAPI(title="mdpad")


def _require_project() -> Path:
    if PROJECT_DIR is None:
        raise HTTPException(400, "No project is open. Create or open a project first.")
    return PROJECT_DIR


def _safe_doc_path(name: str) -> Path:
    """Resolve ``name`` to a .md file directly inside PROJECT_DIR (no traversal)."""
    project_dir = _require_project()
    if not _NAME_RE.match(name):
        raise HTTPException(400, "Invalid filename (use letters, digits, . - _ and a .md extension).")
    path = (project_dir / name).resolve()
    if path.parent != project_dir.resolve():
        raise HTTPException(400, "Filename must not point outside the project folder.")
    return path


def _summ_path(name: str) -> Path:
    """Sidecar file caching a document's summaries: ``<name>.summ.json``."""
    return _require_project() / f"{name}.summ.json"


def _history_dir() -> Path:
    return _require_project() / "history"


def _snapshot_timestamp() -> str:
    now = datetime.now()
    return now.strftime("%y%m%d_%H%M%S") + f".{now.microsecond:06d}"


def _safe_project_path(name: str) -> Path:
    """Resolve ``name`` to a project directory directly inside PROJECTS_ROOT."""
    if not _PROJECT_NAME_RE.match(name):
        raise HTTPException(400, "Invalid project name (use letters, digits, spaces, . - _).")
    path = (PROJECTS_ROOT / name).resolve()
    if path.parent != PROJECTS_ROOT.resolve():
        raise HTTPException(400, "Project name must not point outside the projects folder.")
    return path


def _open_project(project_dir: Path) -> None:
    global PROJECT_DIR, _current_doc, _current_name
    PROJECT_DIR = project_dir
    files = sorted(p.name for p in project_dir.glob("*.md") if p.is_file())
    first = files[0] if files else None
    if first:
        _current_doc = (project_dir / first).read_text(encoding="utf-8")
        _current_name = first
        summ.load(_summ_path(first))
    else:
        _current_doc = ""
        _current_name = None
        summ.reset()


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
    if PROJECT_DIR is None:
        return {"dir": None, "files": [], "current": _current_name}
    files = sorted(p.name for p in PROJECT_DIR.glob("*.md") if p.is_file())
    return {"dir": str(PROJECT_DIR), "files": files, "current": _current_name}


class SaveRequest(BaseModel):
    name: str
    text: str


@app.get("/api/file/{name}")
def read_file(name: str) -> dict:
    global _current_doc, _current_name
    path = _safe_doc_path(name)
    if not path.is_file():
        raise HTTPException(404, f"No such file in {PROJECT_DIR}: {name}")
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
    if summ._STORE:  # persist current summaries alongside the document
        summ.save(_summ_path(req.name))
    history_dir = _history_dir()
    history_dir.mkdir(exist_ok=True)  # defensive: projects predating this feature
    (history_dir / f"{req.name}_{_snapshot_timestamp()}.md").write_text(req.text, encoding="utf-8")
    return {"ok": True, "name": req.name}


class ProjectCreateRequest(BaseModel):
    name: str = ""
    path: str = ""


class ProjectOpenRequest(BaseModel):
    name: str = ""
    path: str = ""


_README_TEMPLATE = "# {name}\n"


@app.get("/api/projects")
def list_projects() -> dict:
    PROJECTS_ROOT.mkdir(exist_ok=True)
    projects = sorted(p.name for p in PROJECTS_ROOT.iterdir() if p.is_dir())
    return {"projects": projects, "current": PROJECT_DIR.name if PROJECT_DIR else None}


@app.post("/api/projects")
def create_project(req: ProjectCreateRequest) -> dict:
    if req.path:
        project_dir = Path(req.path).expanduser().resolve()
        name = project_dir.name
    elif req.name:
        project_dir = _safe_project_path(req.name)
        name = req.name
    else:
        raise HTTPException(400, "A project name or path is required.")
    if project_dir.exists():
        raise HTTPException(400, f"Project already exists: {project_dir}")
    project_dir.mkdir(parents=True)
    (project_dir / "history").mkdir()
    (project_dir / "README.md").write_text(_README_TEMPLATE.format(name=name), encoding="utf-8")
    _open_project(project_dir)
    return list_files()


@app.post("/api/projects/open")
def open_project(req: ProjectOpenRequest) -> dict:
    if req.path:
        project_dir = Path(req.path).expanduser().resolve()
    elif req.name:
        project_dir = _safe_project_path(req.name)
    else:
        raise HTTPException(400, "A project name or path is required.")
    if not project_dir.is_dir():
        raise HTTPException(404, f"No such project folder: {project_dir}")
    _open_project(project_dir)
    return list_files()


@app.get("/api/history/status")
def history_status() -> dict:
    if PROJECT_DIR is None:
        return {"total_bytes": 0}
    history_dir = PROJECT_DIR / "history"
    if not history_dir.is_dir() or (history_dir / "keepforever.md").exists():
        return {"total_bytes": 0}
    cutoff = time.time() - HISTORY_RETENTION_DAYS * 86400
    total = sum(
        f.stat().st_size for f in history_dir.glob("*.md") if f.name != "keepforever.md" and f.stat().st_mtime < cutoff
    )
    return {"total_bytes": total}


class HistoryCleanupRequest(BaseModel):
    action: str  # "delete" | "keep_forever" | "skip"


@app.post("/api/history/cleanup")
def history_cleanup(req: HistoryCleanupRequest) -> dict:
    if PROJECT_DIR is None:
        return {"ok": True}
    history_dir = PROJECT_DIR / "history"
    if req.action == "keep_forever":
        history_dir.mkdir(exist_ok=True)
        (history_dir / "keepforever.md").write_text("", encoding="utf-8")
    elif req.action == "delete":
        if history_dir.is_dir():
            cutoff = time.time() - HISTORY_RETENTION_DAYS * 86400
            for f in history_dir.glob("*.md"):
                if f.name != "keepforever.md" and f.stat().st_mtime < cutoff:
                    f.unlink()
    elif req.action != "skip":
        raise HTTPException(400, f"Unknown action: {req.action!r}")
    return {"ok": True}


@app.post("/api/revise")
def revise(req: ReviseRequest) -> dict:
    selection = req.text[req.sel_start : req.sel_end]
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
    if _current_name and summ._STORE:  # only persist when there's something to save
        summ.save(_summ_path(_current_name))  # so a reopen reuses them
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
        "tree": ctx.build_tree(
            sections=sections,
            blocks=blocks,
            target_block=target,
            store=summ._STORE,
            states=summ.validity(sections, blocks, req.text),
        ),
    }


@app.middleware("http")
async def _revalidate_assets(request, call_next):
    """Always revalidate the app's HTML/CSS/JS so edits show up on a normal reload
    (no hard-refresh needed). Vendored libs (fonts/KaTeX) stay cacheable."""
    resp = await call_next(request)
    p = request.url.path
    if p == "/" or (p.startswith("/static/") and "/vendor/" not in p):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


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
    the bundled example. Its parent directory becomes the open project.
    """
    import sys
    import threading

    import uvicorn

    global PROJECT_DIR, _current_doc, _current_name
    paths = [a for a in sys.argv[1:] if not a.startswith("-")]
    if paths:
        target = Path(paths[0]).resolve()
        if target.is_file():
            PROJECT_DIR = target.parent
            (PROJECT_DIR / "history").mkdir(exist_ok=True)
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
