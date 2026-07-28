"""FastAPI application: serves the single-page workspace and two JSON endpoints.

Provider settings live in the browser (localStorage) and travel with each revise
request, so no secrets are stored server-side -- a deliberate PoC simplification.
"""

from __future__ import annotations

import webbrowser
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import context as ctx
from . import provider as prov
from .sections import parse_sections, section_at

_HERE = Path(__file__).parent
_STATIC = _HERE / "static"
_DEFAULT_DOC = (_HERE / "example" / "book.md").read_text(encoding="utf-8")
_PROJECT_SUMMARY = (
    "A vision/review manuscript on representation dynamics and the physics of "
    "information processing. Audience: researchers in representation learning. "
    "Tone: precise, hypothesis-aware, mathematically careful."
)

app = FastAPI(title="mdpad")


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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


@app.get("/api/document")
def document() -> dict:
    return {"text": _DEFAULT_DOC, "project_summary": _PROJECT_SUMMARY}


@app.post("/api/revise")
def revise(req: ReviseRequest) -> dict:
    selection = req.text[req.sel_start:req.sel_end]
    sections = parse_sections(req.text)
    section = section_at(sections, req.sel_start, req.text)
    package = ctx.build_context(
        project_summary=_PROJECT_SUMMARY,
        section=section,
        selection=selection,
        instruction=req.instruction,
    )
    proposal = None
    error = None
    try:
        proposal = prov.revise(
            package_text=package.as_prompt(),
            selection=selection,
            instruction=req.instruction,
            provider=req.provider.model_dump(),
        )
    except prov.ProviderError as e:
        error = str(e)
    return {
        "section": section.title if section else None,
        "context": package.as_dict(),
        "proposal": proposal.as_dict() if proposal else None,
        "error": error,
    }


app.mount("/static", StaticFiles(directory=_STATIC), name="static")


def main() -> None:
    """Launch the local server and open the workspace in a browser."""
    import uvicorn

    host, port = "127.0.0.1", 8000
    try:
        webbrowser.open(f"http://{host}:{port}")
    except Exception:
        pass
    uvicorn.run(app, host=host, port=port, log_level="info")
