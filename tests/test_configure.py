from mdpad.configure import _read_env, _write_env


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
