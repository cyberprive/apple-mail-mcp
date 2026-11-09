from pathlib import Path

from apple_mail_mcp.config import Settings


def test_defaults(monkeypatch):
    for var in [
        "APPLE_MAIL_MCP_LOG_PATH",
        "APPLE_MAIL_MCP_LOG_LEVEL",
        "APPLE_MAIL_MCP_DRAFT_VISIBLE",
        "APPLE_MAIL_MCP_APPLESCRIPT_TIMEOUT_MS",
        "APPLE_MAIL_MCP_ATTACHMENTS_DIR",
    ]:
        monkeypatch.delenv(var, raising=False)
    s = Settings.from_env()
    assert s.log_level == "INFO"
    assert s.draft_visible is False
    assert s.applescript_timeout_ms == 45000
    assert s.attachments_dir == Path.home() / "Downloads" / "apple-mail-mcp"
    assert s.log_path.name == "apple-mail-mcp.log"


def test_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("APPLE_MAIL_MCP_LOG_PATH", str(tmp_path / "x.log"))
    monkeypatch.setenv("APPLE_MAIL_MCP_LOG_LEVEL", "debug")
    monkeypatch.setenv("APPLE_MAIL_MCP_DRAFT_VISIBLE", "true")
    monkeypatch.setenv("APPLE_MAIL_MCP_APPLESCRIPT_TIMEOUT_MS", "10000")
    monkeypatch.setenv("APPLE_MAIL_MCP_ATTACHMENTS_DIR", str(tmp_path / "att"))
    s = Settings.from_env()
    assert s.log_path == Path(tmp_path / "x.log")
    assert s.log_level == "DEBUG"
    assert s.draft_visible is True
    assert s.applescript_timeout_ms == 10000
    assert s.attachments_dir == tmp_path / "att"


def test_bool_parsing(monkeypatch):
    for value, expected in [("1", True), ("0", False), ("yes", True), ("no", False),
                             ("TRUE", True), ("false", False), ("", False)]:
        monkeypatch.setenv("APPLE_MAIL_MCP_DRAFT_VISIBLE", value)
        assert Settings.from_env().draft_visible is expected, value
