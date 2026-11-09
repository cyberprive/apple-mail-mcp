"""Runtime settings, read from APPLE_MAIL_MCP_* environment variables.

All user-tunable behavior lives here. No personal data, no account names,
no schedules — those belong to whoever calls the tools.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return Path(raw).expanduser()


@dataclass(frozen=True)
class Settings:
    log_path: Path
    log_level: str
    draft_visible: bool
    applescript_timeout_ms: int
    attachments_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            log_path=_path(
                "APPLE_MAIL_MCP_LOG_PATH",
                Path.home() / "Library" / "Logs" / "apple-mail-mcp.log",
            ),
            log_level=os.environ.get("APPLE_MAIL_MCP_LOG_LEVEL", "INFO").upper(),
            draft_visible=_bool("APPLE_MAIL_MCP_DRAFT_VISIBLE", False),
            applescript_timeout_ms=_int("APPLE_MAIL_MCP_APPLESCRIPT_TIMEOUT_MS", 45000),
            attachments_dir=_path(
                "APPLE_MAIL_MCP_ATTACHMENTS_DIR",
                Path.home() / "Downloads" / "apple-mail-mcp",
            ),
        )


SETTINGS = Settings.from_env()
