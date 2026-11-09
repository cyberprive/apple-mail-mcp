from apple_mail_mcp.envelope import err, ok


def test_ok_wraps_data():
    assert ok({"a": 1}) == {"ok": True, "data": {"a": 1}}


def test_ok_with_list():
    assert ok([1, 2]) == {"ok": True, "data": [1, 2]}


def test_err_basic():
    assert err("FOO", "bar") == {"ok": False, "error": {"code": "FOO", "message": "bar"}}


def test_err_with_details():
    out = err("FOO", "bar", script="x.js", stderr="boom")
    assert out["ok"] is False
    assert out["error"]["code"] == "FOO"
    assert out["error"]["details"] == {"script": "x.js", "stderr": "boom"}
