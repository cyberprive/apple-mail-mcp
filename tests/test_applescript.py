import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from apple_mail_mcp.applescript import (
    AppleScriptError,
    SCRIPTS_DIR,
    _detect_language,
    run_script,
    run_script_json,
)


def test_detect_language_js():
    assert _detect_language(Path("foo.js")) == "JavaScript"


def test_detect_language_applescript():
    assert _detect_language(Path("foo.applescript")) == "AppleScript"
    assert _detect_language(Path("foo.scpt")) == "AppleScript"


def test_detect_language_unknown():
    with pytest.raises(ValueError):
        _detect_language(Path("foo.txt"))


def test_run_script_missing_file():
    with pytest.raises(FileNotFoundError):
        run_script("does_not_exist.js")


def _fake_result(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


def test_run_script_success():
    target = SCRIPTS_DIR / "list_accounts.js"
    assert target.is_file()
    with patch("apple_mail_mcp.applescript.subprocess.run") as mock_run:
        mock_run.return_value = _fake_result(stdout='[{"name":"x"}]\n')
        out = run_script("list_accounts.js")
    assert out == '[{"name":"x"}]'
    cmd = mock_run.call_args.args[0]
    assert cmd[0] == "osascript"
    assert "JavaScript" in cmd
    assert str(target) in cmd


def test_run_script_propagates_args():
    with patch("apple_mail_mcp.applescript.subprocess.run") as mock_run:
        mock_run.return_value = _fake_result(stdout="[]")
        run_script("list_mailboxes.js", ["my-account"])
    cmd = mock_run.call_args.args[0]
    assert cmd[-1] == "my-account"


def test_run_script_raises_on_nonzero():
    with patch("apple_mail_mcp.applescript.subprocess.run") as mock_run:
        mock_run.return_value = _fake_result(returncode=1, stderr="boom")
        with pytest.raises(AppleScriptError) as exc:
            run_script("list_accounts.js")
        assert exc.value.returncode == 1
        assert exc.value.stderr == "boom"
        assert exc.value.script == "list_accounts.js"


def test_run_script_json_parses():
    with patch("apple_mail_mcp.applescript.subprocess.run") as mock_run:
        mock_run.return_value = _fake_result(stdout='{"a":1}')
        assert run_script_json("list_accounts.js") == {"a": 1}


def test_run_script_json_raises_on_garbage():
    with patch("apple_mail_mcp.applescript.subprocess.run") as mock_run:
        mock_run.return_value = _fake_result(stdout="not json")
        with pytest.raises(AppleScriptError):
            run_script_json("list_accounts.js")


def test_run_script_json_empty_stdout_returns_none():
    with patch("apple_mail_mcp.applescript.subprocess.run") as mock_run:
        mock_run.return_value = _fake_result(stdout="")
        assert run_script_json("list_accounts.js") is None


def test_run_script_honors_timeout(monkeypatch):
    monkeypatch.setenv("APPLE_MAIL_MCP_APPLESCRIPT_TIMEOUT_MS", "12345")
    # Settings is module-level, so we need to reload. Easier: pass timeout_ms.
    with patch("apple_mail_mcp.applescript.subprocess.run") as mock_run:
        mock_run.return_value = _fake_result(stdout="[]")
        run_script("list_accounts.js", timeout_ms=2000)
    assert mock_run.call_args.kwargs["timeout"] == pytest.approx(2.0)
