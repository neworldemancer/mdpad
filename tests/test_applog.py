from mdpad import applog


def setup_function():
    applog.clear()


def test_log_and_get_logs_returns_in_order():
    applog.log("info", "test", "first")
    applog.log("error", "test", "second")
    entries = applog.get_logs()
    assert [e["message"] for e in entries] == ["first", "second"]
    assert entries[0]["level"] == "info"
    assert entries[1]["level"] == "error"
    assert entries[0]["id"] < entries[1]["id"]


def test_get_logs_since_only_returns_newer_entries():
    applog.log("info", "test", "first")
    cutoff = applog.get_logs()[-1]["id"]
    applog.log("info", "test", "second")
    entries = applog.get_logs(cutoff)
    assert [e["message"] for e in entries] == ["second"]


def test_clear_empties_the_buffer():
    applog.log("info", "test", "x")
    applog.clear()
    assert applog.get_logs() == []


def test_ring_buffer_caps_at_max_logs():
    for i in range(applog._MAX_LOGS + 10):
        applog.log("info", "test", str(i))
    entries = applog.get_logs()
    assert len(entries) == applog._MAX_LOGS
    assert entries[0]["message"] == "10"  # the oldest 10 fell off
    assert entries[-1]["message"] == str(applog._MAX_LOGS + 9)
