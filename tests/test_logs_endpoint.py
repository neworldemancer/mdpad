from fastapi.testclient import TestClient

from mdpad import app as mdpad_app
from mdpad import applog

client = TestClient(mdpad_app.app)


def setup_function():
    applog.clear()


def test_get_logs_empty():
    res = client.get("/api/logs")
    assert res.status_code == 200
    assert res.json() == {"logs": []}


def test_get_logs_returns_logged_entries():
    applog.log("error", "revise", "boom")
    res = client.get("/api/logs")
    logs = res.json()["logs"]
    assert len(logs) == 1
    assert logs[0]["message"] == "boom"
    assert logs[0]["level"] == "error"
    assert logs[0]["source"] == "revise"


def test_get_logs_since_filters_out_older_entries():
    applog.log("info", "x", "old")
    cutoff = applog.get_logs()[-1]["id"]
    applog.log("info", "x", "new")
    res = client.get(f"/api/logs?since={cutoff}")
    assert [e["message"] for e in res.json()["logs"]] == ["new"]


def test_clear_logs_endpoint_empties_the_buffer():
    applog.log("info", "x", "y")
    res = client.post("/api/logs/clear")
    assert res.status_code == 200
    assert res.json() == {"ok": True}
    assert client.get("/api/logs").json() == {"logs": []}


def test_models_endpoint_logs_on_error():
    res = client.get("/api/models?base_url=https://api.openai.com/v1&api_key=")
    assert res.status_code == 200
    logs = client.get("/api/logs").json()["logs"]
    assert any(e["source"] == "models" and e["level"] == "error" for e in logs)
