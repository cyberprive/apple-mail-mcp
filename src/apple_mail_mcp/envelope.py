"""Standard response envelope. Every MCP tool returns this shape.

    {"ok": true,  "data": <payload>}
    {"ok": false, "error": {"code": "ERR_CODE", "message": "..."}}

One shape for every tool, so callers handle success and failure the same
way everywhere.
"""
from __future__ import annotations

from typing import Any


def ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def err(code: str, message: str, **extra: Any) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if extra:
        error["details"] = extra
    return {"ok": False, "error": error}
