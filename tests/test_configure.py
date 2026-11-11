import mdpad.configure as configure_module
from mdpad import app as mdpad_app
from mdpad.configure import _read_env, _write_env
from mdpad.configure import main as configure_main


def test_write_then_read_round_trip(tmp_path):
    path = tmp_path / ".env"
    _write_env(path, {"MDPAD_BASE_URL": "https://host/v1", "MDPAD_API_KEY": "sk-test"})
    assert _read_env(path) == {"MDPAD_BASE_URL": "https://host/v1", "MDPAD_API_KEY": "sk-test"}


def test_read_env_ignores_blank_lines_and_comments(tmp_path):
    path = tmp_path / ".env"
    path.write_text("# comment\n\nMDPAD_BASE_URL=https://host/v1\n", encoding="utf-8")
    assert _read_env(path) == {"MDPAD_BASE_URL": "https://host/v1"}


def test_read_env_missing_file_returns_empty(tmp_path):
    assert _read_env(tmp_path / "nope.env") == {}


def test_main_accepts_an_explicit_argv(tmp_path):
    env_file = tmp_path / ".env"
    configure_main(["--base-url", "http://localhost:11434/v1", "--api-key", "", "--env-file", str(env_file)])
    assert _read_env(env_file) == {"MDPAD_BASE_URL": "http://localhost:11434/v1", "MDPAD_API_KEY": ""}


def test_mdpad_main_dashdash_configure_delegates_without_starting_the_server(monkeypatch):
    """Regression test: `mdpad --configure ...` (e.g. via `uvx mdpad --configure`)
    must write .env and return, never touch PROJECT_DIR or start uvicorn/tray."""
    calls = []
    monkeypatch.setattr(configure_module, "main", lambda argv: calls.append(argv))
    monkeypatch.setattr("sys.argv", ["mdpad", "--configure", "--base-url", "http://x", "--api-key", "k"])
    mdpad_app.main()
    assert calls == [["--base-url", "http://x", "--api-key", "k"]]
