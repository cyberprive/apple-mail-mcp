"""osascript subprocess wrapper.

Single boundary between Python and macOS scripting. Owns timeouts, error
surfacing, and language detection (.applescript = AppleScript, .js = JXA).

No business logic here: run the script, parse stdout, raise on non-zero.
Callers handle interpretation. Arguments always travel as argv strings —
never spliced into script text.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Sequence

from .config import SETTINGS

logger = logging.getLogger("apple_mail_mcp.applescript")

SCRIPTS_DIR = Path(__file__).parent / "scripts"


class AppleScriptError(RuntimeError):
    """osascript exited non-zero. `stderr` is the raw error from osascript."""

    def __init__(self, *, returncode: int, stderr: str, script: str) -> None:
        super().__init__(f"osascript({script}) exit={returncode}: {stderr}")
        self.returncode = returncode
        self.stderr = stderr
        self.script = script


def _detect_language(script_path: Path) -> str:
    suffix = script_path.suffix.lower()
    if suffix == ".js":
        return "JavaScript"
    if suffix in {".applescript", ".scpt"}:
        return "AppleScript"
    raise ValueError(f"Cannot detect osascript language from path: {script_path}")


def run_script(
    script_name: str,
    args: Sequence[str] | None = None,
    *,
    language: str | None = None,
    timeout_ms: int | None = None,
) -> str:
    """Run a script from `scripts/` and return stdout (stripped).

    Args:
        script_name: Filename inside `scripts/`, e.g. "list_accounts.js".
        args: Positional string args passed to the script.
        language: Override for `osascript -l`. Auto-detected from extension.
        timeout_ms: Per-call timeout. Defaults to SETTINGS.applescript_timeout_ms.

    Raises:
        AppleScriptError: Non-zero exit from osascript.
        subprocess.TimeoutExpired: Script exceeded timeout.
    """
    script_path = SCRIPTS_DIR / script_name
    if not script_path.is_file():
        raise FileNotFoundError(f"Script not found: {script_path}")

    lang = language or _detect_language(script_path)
    timeout_s = (timeout_ms or SETTINGS.applescript_timeout_ms) / 1000.0
    cmd: list[str] = ["osascript", "-l", lang, str(script_path), *(args or [])]

    logger.debug("osascript invoke", extra={"script": script_name, "args_count": len(args or [])})
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)

    if result.returncode != 0:
        raise AppleScriptError(
            returncode=result.returncode,
            stderr=result.stderr.strip(),
            script=script_name,
        )
    return result.stdout.strip()


def run_script_json(
    script_name: str,
    args: Sequence[str] | None = None,
    **kwargs: Any,
) -> Any:
    """Run a script and JSON-parse stdout. Use for read-tool scripts."""
    raw = run_script(script_name, args, **kwargs)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppleScriptError(
            returncode=0,
            stderr=f"script returned non-JSON output: {raw[:200]!r}",
            script=script_name,
        ) from exc
