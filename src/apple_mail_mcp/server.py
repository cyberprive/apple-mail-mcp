"""apple-mail-mcp — MCP server.

This module is the transport layer. No business logic lives here — tools
validate args, delegate to applescript.run_script_json, and wrap the result in
the standard envelope.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import __version__
from .applescript import AppleScriptError, run_script_json
from .config import SETTINGS
from .envelope import err, ok
from .logging_setup import setup_logging
from .paths import resolve_target_dir

setup_logging()
logger = logging.getLogger("apple_mail_mcp.server")

# Without `version`, mcp 2.x reports an empty serverInfo.version.
mcp = MCPServer("apple-mail-mcp", version=__version__)

# MCP tool annotations. Clients can use these to decide what to ask the user
# about. They are hints, not enforcement: see "Safety" in the README.
# mcp 2.x spells the fields in snake_case; they still go out as readOnlyHint etc.
READ_ONLY = ToolAnnotations(read_only_hint=True)
SETS_STATE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True)
CREATES = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False)


def _safe_call(tool: str, script: str, args: list[str] | None = None) -> dict:
    """Run a script through the standard error envelope."""
    try:
        data = run_script_json(script, args or [])
        return ok(data)
    except AppleScriptError as exc:
        logger.error(
            "applescript_error",
            extra={"tool": tool, "script": exc.script, "stderr": exc.stderr},
        )
        return err("APPLESCRIPT_ERROR", exc.stderr or str(exc), script=exc.script)
    except subprocess.TimeoutExpired as exc:
        logger.error("applescript_timeout", extra={"tool": tool, "timeout_s": exc.timeout})
        return err(
            "TIMEOUT",
            f"Mail did not answer within {exc.timeout:g}s. Large or slow (iCloud) "
            "mailboxes may need a narrower `since`, or a higher "
            "APPLE_MAIL_MCP_APPLESCRIPT_TIMEOUT_MS.",
            script=script,
            timeout_s=exc.timeout,
        )
    except Exception as exc:  # noqa: BLE001 — last-line catch: every error reaches the caller
        logger.exception("tool_error", extra={"tool": tool})
        return err("INTERNAL_ERROR", str(exc))


@mcp.tool(annotations=READ_ONLY)
def ping() -> dict:
    """Health check. Returns {ok: true, data: "OK"} if the MCP is reachable."""
    return ok("OK")


@mcp.tool(annotations=READ_ONLY)
def version() -> dict:
    """Return the MCP server version."""
    return ok({"version": __version__})


@mcp.tool(annotations=READ_ONLY)
def list_accounts() -> dict:
    """List every account configured in Apple Mail.

    Returns a list of {id, name, user_name, account_type, email_addresses, enabled}.
    The `name` field is the canonical handle to pass to other tools as `account`.
    """
    return _safe_call("list_accounts", "list_accounts.js")


@mcp.tool(annotations=READ_ONLY)
def list_mailboxes(account: str, with_counts: bool = False) -> dict:
    """List mailboxes (folders) inside an account.

    Args:
        account: Account name as returned by list_accounts.
        with_counts: If true, include `unread_count` and `total_count` per
            mailbox. **Slow on large accounts** — Mail enumerates each folder
            to count messages. On a 30k-message iCloud account with 80+
            folders this can take 30+ seconds. Default false.

    Returns a list of {name, unread_count?, total_count?}.
    """
    if not account:
        return err("INVALID_ARGUMENT", "account is required")
    return _safe_call(
        "list_mailboxes",
        "list_mailboxes.js",
        [account, "true" if with_counts else "false"],
    )


@mcp.tool(annotations=READ_ONLY)
def search_messages(
    account: str,
    mailbox: Optional[str] = None,
    since: Optional[str] = None,
    before: Optional[str] = None,
    limit: int = 50,
    unread_only: bool = False,
    query: Optional[str] = None,
    field: str = "all",
) -> dict:
    """Search messages in a mailbox. Returns lightweight summaries.

    Args:
        account: Account name (from list_accounts).
        mailbox: Mailbox name (from list_mailboxes). When omitted (or set to
            "@inbox"), the server auto-detects the account's inbox by trying
            the common localizations (INBOX, Bandeja de entrada, Posteingang,
            Boîte de réception, Caixa de entrada, etc.).
        since: ISO 8601 timestamp; only messages received at or after are returned.
            **Defaults to 7 days ago** if not provided — without a date floor,
            the script must materialize the entire mailbox, which is ruinous
            on large iCloud inboxes. Pass an explicit older date if you need
            to look further back.
        before: ISO 8601 timestamp; only messages received strictly before are returned.
        limit: Max results, capped at 500. Default 50.
        unread_only: If true, only return unread messages.
        query: Case-insensitive substring filter. Scope set by `field`.
        field: Where `query` is matched. One of:
            "subject"  — subject line only
            "sender"   — sender name + address
            "content"  — full body text (slower; iterates message content)
            "all"      — subject + sender (default; content excluded for perf)

    Returns a list of {id, message_id, account, mailbox, subject, sender,
    date_received, read, snippet}. Use `id` with get_thread to fetch the full body.
    """
    if not account:
        return err("INVALID_ARGUMENT", "account is required")
    if field not in {"subject", "sender", "content", "all"}:
        return err("INVALID_ARGUMENT", "field must be one of: subject, sender, content, all")
    # Default since to 7 days ago when caller doesn't specify one. Without a
    # since floor, the script materializes the full mailbox before iterating —
    # ruinous on a 30k+ inbox. 7 days is a safe default for triage; callers who
    # need older messages MUST pass an explicit `since`.
    if not since:
        from datetime import datetime, timedelta, timezone
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat().replace("+00:00", "Z")
    payload = {
        "account": account,
        "mailbox": mailbox,
        "since": since,
        "before": before,
        "limit": limit,
        "unread_only": unread_only,
        "query": query,
        "field": field,
    }
    return _safe_call("search_messages", "search_messages.js", [json.dumps(payload)])


@mcp.tool(annotations=READ_ONLY)
def get_thread(account: str, mailbox: str, id: str) -> dict:  # noqa: A002 — MCP arg
    """Fetch the full content for a single message.

    v1 returns one message (no thread reconstruction). For triage this is
    sufficient; full threading lands in v1.5.

    Args:
        account: Account name.
        mailbox: Mailbox name (from search_messages output).
        id: Mail.app numeric message id (from search_messages output).

    Returns {messages: [{id, message_id, account, mailbox, subject, sender,
    to, cc, date_received, date_sent, read, body}]}.
    """
    if not (account and mailbox and id):
        return err("INVALID_ARGUMENT", "account, mailbox, id are all required")
    payload = {"account": account, "mailbox": mailbox, "id": id}
    return _safe_call("get_thread", "get_thread.js", [json.dumps(payload)])


@mcp.tool(annotations=CREATES)
def create_draft(
    account: str,
    body: str,
    to: Optional[list[str]] = None,
    subject: Optional[str] = None,
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
    reply_to: Optional[dict] = None,
    reply_all: bool = False,
    visible: Optional[bool] = None,
) -> dict:
    """Create a plain-text draft in Apple Mail's Drafts folder.

    Two modes:

    1. **New message** — pass `to` and `subject`. `body` is the message text.

    2. **Reply** — pass `reply_to={"account":..., "mailbox":..., "id":...}` (use
       the values returned by `search_messages`). `subject` and `to` become
       optional and are auto-set from the original. `body` is your reply text;
       the original message is automatically quoted below it. Threading headers
       (In-Reply-To/References) are set so the recipient's mail client groups
       this with the original conversation. `cc` / `bcc` are additive.

    Args:
        account: Sender account name (from list_accounts).
        body: Plain-text reply/message text. May be empty.
        to: Recipient addresses. Required for new messages, optional for replies.
        subject: Subject line. Required for new messages, optional for replies
            (defaults to "Re: <original>"). Pass an explicit value to override.
        cc, bcc: Optional CC/BCC addresses.
        reply_to: If set, creates a reply. {account, mailbox, id} of the original
            message. `account` here is the account where the original was
            received, which may differ from the sending account.
        reply_all: If true and replying, replies to all recipients. Default false.
        visible: If true, Mail brings the compose window forward; if false the
            draft is saved silently. Defaults to APPLE_MAIL_MCP_DRAFT_VISIBLE.

    Returns metadata about the created draft. Does NOT return a persisted
    Drafts-mailbox id — Mail commits drafts asynchronously. Drafts are reviewed
    in Mail.app.

    HTML body rendering is v1.5.
    """
    if not account:
        return err("INVALID_ARGUMENT", "account is required")
    if reply_to is None:
        if not to:
            return err("INVALID_ARGUMENT", "to is required when reply_to is not set")
        if subject is None:
            return err("INVALID_ARGUMENT", "subject is required when reply_to is not set")
    payload = {
        "account": account,
        "to": to or [],
        "subject": subject if subject is not None else "",
        "body": body if body is not None else "",
        "cc": cc or [],
        "bcc": bcc or [],
        "visible": SETTINGS.draft_visible if visible is None else bool(visible),
        "reply_to": reply_to,
        "reply_all": bool(reply_all),
    }
    return _safe_call("create_draft", "create_draft.js", [json.dumps(payload)])


@mcp.tool(annotations=SETS_STATE)
def mark_read(account: str, mailbox: str, id: str) -> dict:  # noqa: A002
    """Mark a single message as read.

    Args:
        account, mailbox, id: As returned by search_messages.
    """
    if not (account and mailbox and id):
        return err("INVALID_ARGUMENT", "account, mailbox, id are all required")
    payload = {"account": account, "mailbox": mailbox, "id": id}
    return _safe_call("mark_read", "mark_read.js", [json.dumps(payload)])


@mcp.tool(annotations=SETS_STATE)
def mark_unread(account: str, mailbox: str, id: str) -> dict:  # noqa: A002
    """Mark a single message as unread.

    Args:
        account, mailbox, id: As returned by search_messages.
    """
    if not (account and mailbox and id):
        return err("INVALID_ARGUMENT", "account, mailbox, id are all required")
    payload = {"account": account, "mailbox": mailbox, "id": id}
    return _safe_call("mark_unread", "mark_unread.js", [json.dumps(payload)])


def _confirm_required(action: str, summary: str, **details) -> dict:
    """Standard refusal envelope for destructive ops missing `confirm=true`.

    Agents calling these tools MUST surface the action to the user and pass
    confirm=true on a follow-up call after explicit human approval.
    """
    return err(
        "CONFIRM_REQUIRED",
        f"{summary} Re-call with confirm=true to proceed.",
        action=action,
        **details,
    )


@mcp.tool(annotations=DESTRUCTIVE)
def move_to_mailbox(
    account: str,
    mailbox: str,
    id: str,  # noqa: A002
    target_mailbox: str,
    confirm: bool = False,
) -> dict:
    """[DESTRUCTIVE] Move a message from one mailbox to another within the same account.

    **This tool refuses without `confirm=true`.** Always surface the planned
    move to the user and get explicit approval before passing confirm=true —
    moving a message changes user-visible state (especially when the target
    is Trash, Junk, or Archive). Reversible by moving back, but disruptive.

    Both `mailbox` and `target_mailbox` accept either an exact mailbox name
    OR a localization-aware alias starting with "@":
        @inbox, @archive, @drafts, @sent, @trash, @junk
    The MCP resolves the alias against the account's actual folder names
    (e.g. @archive → "Archivo" on a Spanish-localized M365 account, "Archive"
    on iCloud English). The returned `to_mailbox` field is the resolved
    literal name so callers can log accurately.

    Args:
        account, mailbox, id: As returned by search_messages.
        target_mailbox: Destination — exact name or `@alias`.
        confirm: Must be true to actually perform the move. False (default)
            returns a CONFIRM_REQUIRED envelope describing the action.
    """
    if not (account and mailbox and id and target_mailbox):
        return err(
            "INVALID_ARGUMENT",
            "account, mailbox, id, target_mailbox are all required",
        )
    if not confirm:
        return _confirm_required(
            "move_to_mailbox",
            f"Will move message {id} from '{mailbox}' to '{target_mailbox}' in account '{account}'.",
            account=account,
            from_mailbox=mailbox,
            to_mailbox=target_mailbox,
            message_id=id,
        )
    payload = {"account": account, "mailbox": mailbox, "id": id, "target_mailbox": target_mailbox}
    logger.info(
        "destructive_action_confirmed",
        extra={"action": "move_to_mailbox", "account": account, "from": mailbox, "to": target_mailbox, "id": id},
    )
    return _safe_call("move_to_mailbox", "move_to_mailbox.js", [json.dumps(payload)])


@mcp.tool(annotations=SETS_STATE)
def flag_message(account: str, mailbox: str, id: str, color: int) -> dict:  # noqa: A002
    """Set or clear the flag color on a message.

    Args:
        account, mailbox, id: As returned by search_messages.
        color: 0..6 sets a color; -1 clears the flag.
            0 red · 1 orange · 2 yellow · 3 green · 4 blue · 5 purple · 6 gray
    """
    if not (account and mailbox and id):
        return err("INVALID_ARGUMENT", "account, mailbox, id are all required")
    if not isinstance(color, int) or color < -1 or color > 6:
        return err("INVALID_ARGUMENT", "color must be an integer in -1..6")
    payload = {"account": account, "mailbox": mailbox, "id": id, "color": color}
    return _safe_call("flag_message", "flag_message.js", [json.dumps(payload)])


@mcp.tool(annotations=READ_ONLY)
def list_attachments(account: str, mailbox: str, id: str) -> dict:  # noqa: A002
    """List attachments on a message.

    Args:
        account, mailbox, id: As returned by search_messages.

    Returns a list of {index, name, size, mime_type, downloaded}. Pass `index`
    to save_attachment. `downloaded=false` means the attachment body isn't
    on disk yet — open the message in Mail.app to fetch it before saving.
    """
    if not (account and mailbox and id):
        return err("INVALID_ARGUMENT", "account, mailbox, id are all required")
    payload = {"account": account, "mailbox": mailbox, "id": id}
    return _safe_call("list_attachments", "list_attachments.js", [json.dumps(payload)])


def _save_attachments(
    tool: str,
    account: str,
    mailbox: str,
    id: str,  # noqa: A002
    index: Optional[int],
    target_dir: Optional[str],
    overwrite: bool,
    confirm: bool,
) -> dict:
    """Shared body of save_attachment / save_all_attachments.

    Order matters: the path is checked before anything else happens, so a
    refused path never creates a directory and never reaches Mail.
    """
    if not (account and mailbox and id):
        return err("INVALID_ARGUMENT", "account, mailbox, id are all required")
    try:
        directory: Path = resolve_target_dir(target_dir, SETTINGS.attachments_dir, create=False)
    except ValueError as exc:
        return err("INVALID_ARGUMENT", str(exc))
    if overwrite and not confirm:
        return _confirm_required(
            tool,
            f"Will overwrite any existing file with the same name in '{directory}'.",
            account=account,
            mailbox=mailbox,
            message_id=id,
            index=index,
            target_dir=str(directory),
        )
    try:
        directory = resolve_target_dir(target_dir, SETTINGS.attachments_dir, create=True)
    except OSError as exc:
        return err("INTERNAL_ERROR", f"could not create '{directory}': {exc}")
    payload = {
        "account": account,
        "mailbox": mailbox,
        "id": id,
        "index": index,
        "target_dir": str(directory),
        "overwrite": bool(overwrite),
    }
    return _safe_call(tool, "save_attachments.js", [json.dumps(payload)])


@mcp.tool(annotations=DESTRUCTIVE)
def save_attachment(
    account: str,
    mailbox: str,
    id: str,  # noqa: A002
    index: int,
    target_dir: Optional[str] = None,
    overwrite: bool = False,
    confirm: bool = False,
) -> dict:
    """Save one attachment to disk, inside the attachments folder.

    Files can only be written inside the attachments folder
    (APPLE_MAIL_MCP_ATTACHMENTS_DIR, default ~/Downloads/apple-mail-mcp).
    Paths outside it are refused. The attachment's filename comes from the
    sender and is cleaned (no path separators, no leading dots); the result
    reports both `name` (as saved) and `original_name`.

    Args:
        account, mailbox, id: As returned by search_messages.
        index: 1-based index from list_attachments.
        target_dir: Optional subfolder. Relative paths are taken relative to the
            attachments folder; absolute paths must be inside it. Default: the
            folder itself. Created if missing.
        overwrite: If false (default), append " (2)", " (3)" etc. when the name
            is taken. True replaces existing files and requires confirm=true.
        confirm: Required with overwrite=true. Get the user's approval first.

    Returns {saved_path, name, original_name, size, downloaded}.
    """
    if not isinstance(index, int) or isinstance(index, bool) or index < 1:
        return err("INVALID_ARGUMENT", "index must be a 1-based integer")
    return _save_attachments(
        "save_attachment", account, mailbox, id, index, target_dir, overwrite, confirm
    )


@mcp.tool(annotations=DESTRUCTIVE)
def save_all_attachments(
    account: str,
    mailbox: str,
    id: str,  # noqa: A002
    target_dir: Optional[str] = None,
    overwrite: bool = False,
    confirm: bool = False,
) -> dict:
    """Save every attachment on a message, inside the attachments folder.

    Same rules as save_attachment: writes only inside
    APPLE_MAIL_MCP_ATTACHMENTS_DIR, filenames cleaned, overwrite needs confirm.

    Args:
        account, mailbox, id: As returned by search_messages.
        target_dir: Optional subfolder (relative, or absolute inside the folder).
        overwrite: If false (default), taken names get a " (2)", " (3)" suffix.
            True replaces existing files and requires confirm=true.
        confirm: Required with overwrite=true. Get the user's approval first.

    Returns {saved: [{index, saved_path, name, original_name, size}],
    skipped: [{index, name, reason}]}. `reason` is typically "not_downloaded" —
    open the message in Mail.app to fetch it.
    """
    return _save_attachments(
        "save_all_attachments", account, mailbox, id, None, target_dir, overwrite, confirm
    )


def main() -> None:
    logger.info("server_start", extra={"version": __version__})
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
