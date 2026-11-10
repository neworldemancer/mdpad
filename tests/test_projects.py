import os
import time

import pytest
from fastapi.testclient import TestClient

from mdpad import app as mdpad_app
from mdpad import summaries as summ

client = TestClient(mdpad_app.app)


@pytest.fixture(autouse=True)
def _isolated_projects_root(tmp_path, monkeypatch):
    """Point PROJECTS_ROOT at a throwaway dir and reset the open-project state
    so tests never touch the real repo's ./projects, and don't leak between
    tests."""
    monkeypatch.setattr(mdpad_app, "PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(mdpad_app, "PROJECT_DIR", None)
    monkeypatch.setattr(mdpad_app, "_current_doc", "")
    monkeypatch.setattr(mdpad_app, "_current_name", None)
    summ.reset()
    yield
    summ.reset()


# --- project creation / opening --------------------------------------------


def test_create_project_scaffolds_readme_and_history():
    resp = client.post("/api/projects", json={"name": "demo"})
    assert resp.status_code == 200
    project_dir = mdpad_app.PROJECTS_ROOT / "demo"
    assert (project_dir / "README.md").is_file()
    assert (project_dir / "README.md").read_text(encoding="utf-8").startswith("# demo")
    assert (project_dir / "history").is_dir()
    assert mdpad_app.PROJECT_DIR == project_dir


def test_create_project_opens_it_and_loads_readme():
    resp = client.post("/api/projects", json={"name": "demo"})
    data = resp.json()
    assert data["files"] == ["README.md"]
    assert mdpad_app._current_name == "README.md"


def test_create_duplicate_project_fails():
    client.post("/api/projects", json={"name": "demo"})
    resp = client.post("/api/projects", json={"name": "demo"})
    assert resp.status_code == 400


def test_list_projects_reports_current():
    client.post("/api/projects", json={"name": "demo"})
    resp = client.get("/api/projects")
    data = resp.json()
    assert "demo" in data["projects"]
    assert data["current"] == "demo"


def test_open_existing_project_switches_current_doc():
    client.post("/api/projects", json={"name": "alpha"})
    client.post("/api/file", json={"name": "zz-notes.md", "text": "alpha notes"})
    client.post("/api/projects", json={"name": "beta"})

    resp = client.post("/api/projects/open", json={"name": "alpha"})
    assert resp.status_code == 200
    assert "zz-notes.md" in resp.json()["files"]
    # _open_project loads the alphabetically-first file (README.md here).
    assert mdpad_app._current_name == "README.md"
    assert mdpad_app._current_doc.startswith("# alpha")


def test_open_nonexistent_project_404s():
    resp = client.post("/api/projects/open", json={"name": "nope"})
    assert resp.status_code == 404


def test_file_ops_require_an_open_project():
    resp = client.post("/api/file", json={"name": "x.md", "text": "hi"})
    assert resp.status_code == 400


# --- save snapshots into history/ ------------------------------------------


def test_save_writes_a_history_snapshot():
    client.post("/api/projects", json={"name": "demo"})
    client.post("/api/file", json={"name": "doc.md", "text": "v1"})
    history_dir = mdpad_app.PROJECT_DIR / "history"
    snapshots = [f for f in history_dir.glob("doc.md_*.md")]
    assert len(snapshots) == 1
    assert snapshots[0].read_text(encoding="utf-8") == "v1"


def test_multiple_saves_produce_distinct_snapshots():
    client.post("/api/projects", json={"name": "demo"})
    client.post("/api/file", json={"name": "doc.md", "text": "v1"})
    client.post("/api/file", json={"name": "doc.md", "text": "v2"})
    history_dir = mdpad_app.PROJECT_DIR / "history"
    snapshots = sorted(f.name for f in history_dir.glob("doc.md_*.md"))
    assert len(snapshots) == 2
    assert snapshots[0] != snapshots[1]


# --- 30-day retention status/cleanup ---------------------------------------


def _age_all_snapshots(history_dir, days):
    cutoff = time.time() - days * 86400
    for f in history_dir.glob("*.md"):
        if f.name != "keepforever.md":
            os.utime(f, (cutoff, cutoff))


def test_history_status_ignores_recent_snapshots():
    client.post("/api/projects", json={"name": "demo"})
    client.post("/api/file", json={"name": "doc.md", "text": "v1"})
    resp = client.get("/api/history/status")
    assert resp.json()["total_bytes"] == 0


def test_history_status_reports_stale_snapshots():
    client.post("/api/projects", json={"name": "demo"})
    client.post("/api/file", json={"name": "doc.md", "text": "v1"})
    _age_all_snapshots(mdpad_app.PROJECT_DIR / "history", days=31)
    resp = client.get("/api/history/status")
    assert resp.json()["total_bytes"] > 0


def test_cleanup_delete_removes_only_stale_snapshots():
    client.post("/api/projects", json={"name": "demo"})
    client.post("/api/file", json={"name": "doc.md", "text": "v1"})
    history_dir = mdpad_app.PROJECT_DIR / "history"
    _age_all_snapshots(history_dir, days=31)
    client.post("/api/file", json={"name": "doc.md", "text": "v2"})  # fresh snapshot

    resp = client.post("/api/history/cleanup", json={"action": "delete"})
    assert resp.status_code == 200
    remaining = list(history_dir.glob("doc.md_*.md"))
    assert len(remaining) == 1
    assert remaining[0].read_text(encoding="utf-8") == "v2"


def test_cleanup_keep_forever_suppresses_future_status():
    client.post("/api/projects", json={"name": "demo"})
    client.post("/api/file", json={"name": "doc.md", "text": "v1"})
    _age_all_snapshots(mdpad_app.PROJECT_DIR / "history", days=31)

    client.post("/api/history/cleanup", json={"action": "keep_forever"})
    assert (mdpad_app.PROJECT_DIR / "history" / "keepforever.md").is_file()

    resp = client.get("/api/history/status")
    assert resp.json()["total_bytes"] == 0


def test_cleanup_skip_is_a_noop():
    client.post("/api/projects", json={"name": "demo"})
    client.post("/api/file", json={"name": "doc.md", "text": "v1"})
    history_dir = mdpad_app.PROJECT_DIR / "history"
    _age_all_snapshots(history_dir, days=31)

    client.post("/api/history/cleanup", json={"action": "skip"})
    assert list(history_dir.glob("doc.md_*.md"))
    assert client.get("/api/history/status").json()["total_bytes"] > 0
