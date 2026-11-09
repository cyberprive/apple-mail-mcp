"""Tool-surface tests. We invoke the underlying functions, not the MCP transport."""
from unittest.mock import patch

from apple_mail_mcp import server
from apple_mail_mcp.applescript import AppleScriptError


def _fn(tool):
    """FastMCP wraps tools; the original callable is on .fn."""
    return tool.fn if hasattr(tool, "fn") else tool


def test_ping():
    assert _fn(server.ping)() == {"ok": True, "data": "OK"}


def test_version():
    out = _fn(server.version)()
    assert out["ok"] is True
    assert "version" in out["data"]


def test_list_mailboxes_requires_account():
    out = _fn(server.list_mailboxes)("")
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_ARGUMENT"


def test_get_thread_requires_all_args():
    out = _fn(server.get_thread)("acct", "", "123")
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_ARGUMENT"


def test_list_accounts_wraps_applescript_error():
    with patch("apple_mail_mcp.server.run_script_json") as mock:
        mock.side_effect = AppleScriptError(
            returncode=1, stderr="Mail not running", script="list_accounts.js"
        )
        out = _fn(server.list_accounts)()
    assert out["ok"] is False
    assert out["error"]["code"] == "APPLESCRIPT_ERROR"
    assert "Mail not running" in out["error"]["message"]


def test_create_draft_requires_account():
    out = _fn(server.create_draft)(account="", body="y", to=["someone@example.com"], subject="x")
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_ARGUMENT"


def test_create_draft_new_message_requires_to():
    out = _fn(server.create_draft)(account="me", body="y", to=None, subject="x")
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_ARGUMENT"
    assert "to" in out["error"]["message"]


def test_create_draft_new_message_requires_subject():
    out = _fn(server.create_draft)(account="me", body="y", to=["someone@example.com"], subject=None)
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_ARGUMENT"
    assert "subject" in out["error"]["message"]


def test_create_draft_reply_skips_to_subject_validation():
    with patch("apple_mail_mcp.server.run_script_json") as mock:
        mock.return_value = {"created": True}
        out = _fn(server.create_draft)(
            account="me",
            body="thanks",
            reply_to={"account": "me", "mailbox": "INBOX", "id": "42"},
        )
    assert out["ok"] is True
    import json as _json
    payload = _json.loads(mock.call_args.args[1][0])
    assert payload["reply_to"] == {"account": "me", "mailbox": "INBOX", "id": "42"}
    assert payload["reply_all"] is False
    assert payload["to"] == []
    assert payload["subject"] == ""


def test_create_draft_uses_settings_default_visibility():
    with patch("apple_mail_mcp.server.run_script_json") as mock:
        mock.return_value = {"created": True}
        _fn(server.create_draft)(account="me", body="b", to=["someone@example.com"], subject="s")
    import json as _json
    payload = _json.loads(mock.call_args.args[1][0])
    assert payload["visible"] is False
    assert payload["cc"] == []
    assert payload["bcc"] == []


def test_create_draft_explicit_visible_overrides_settings():
    with patch("apple_mail_mcp.server.run_script_json") as mock:
        mock.return_value = {"created": True}
        _fn(server.create_draft)(
            account="me", body="b", to=["someone@example.com"], subject="s", visible=True
        )
    import json as _json
    payload = _json.loads(mock.call_args.args[1][0])
    assert payload["visible"] is True


def test_mark_read_validates():
    assert _fn(server.mark_read)("", "INBOX", "1")["error"]["code"] == "INVALID_ARGUMENT"
    assert _fn(server.mark_read)("a", "", "1")["error"]["code"] == "INVALID_ARGUMENT"
    assert _fn(server.mark_read)("a", "INBOX", "")["error"]["code"] == "INVALID_ARGUMENT"


def test_mark_unread_validates():
    assert _fn(server.mark_unread)("", "INBOX", "1")["error"]["code"] == "INVALID_ARGUMENT"


def test_move_to_mailbox_requires_all_args():
    assert _fn(server.move_to_mailbox)("a", "INBOX", "1", "")["error"]["code"] == "INVALID_ARGUMENT"
    assert _fn(server.move_to_mailbox)("a", "INBOX", "", "Archive")["error"]["code"] == "INVALID_ARGUMENT"


def test_move_to_mailbox_refuses_without_confirm():
    """Destructive ops require explicit confirm=true; refusal envelope describes the action."""
    with patch("apple_mail_mcp.server.run_script_json") as mock:
        out = _fn(server.move_to_mailbox)("acct", "INBOX", "42", "Archive")
    assert out["ok"] is False
    assert out["error"]["code"] == "CONFIRM_REQUIRED"
    assert "INBOX" in out["error"]["message"]
    assert "Archive" in out["error"]["message"]
    assert out["error"]["details"]["action"] == "move_to_mailbox"
    mock.assert_not_called()  # script must NOT run without confirm


def test_move_to_mailbox_proceeds_with_confirm():
    with patch("apple_mail_mcp.server.run_script_json") as mock:
        mock.return_value = {"id": "1", "from_mailbox": "INBOX", "to_mailbox": "Archive"}
        out = _fn(server.move_to_mailbox)("acct", "INBOX", "42", "Archive", confirm=True)
    assert out["ok"] is True
    import json as _json
    payload = _json.loads(mock.call_args.args[1][0])
    assert payload == {"account": "acct", "mailbox": "INBOX", "id": "42", "target_mailbox": "Archive"}


def test_search_messages_rejects_invalid_field():
    out = _fn(server.search_messages)(account="a", field="garbage")
    assert out["ok"] is False
    assert out["error"]["code"] == "INVALID_ARGUMENT"


def test_search_messages_default_mailbox_is_none():
    """No mailbox arg means 'auto-detect' — script handles localization."""
    with patch("apple_mail_mcp.server.run_script_json") as mock:
        mock.return_value = []
        _fn(server.search_messages)(account="me")
    import json as _json
    payload = _json.loads(mock.call_args.args[1][0])
    assert payload["mailbox"] is None


def test_search_messages_passes_field_and_before():
    with patch("apple_mail_mcp.server.run_script_json") as mock:
        mock.return_value = []
        _fn(server.search_messages)(
            account="a", field="sender", before="2026-01-01T00:00:00Z", since="2025-12-01T00:00:00Z"
        )
    import json as _json
    payload = _json.loads(mock.call_args.args[1][0])
    assert payload["field"] == "sender"
    assert payload["before"] == "2026-01-01T00:00:00Z"
    assert payload["since"] == "2025-12-01T00:00:00Z"


def test_flag_message_validates_color_range():
    assert _fn(server.flag_message)("a", "INBOX", "1", color=7)["error"]["code"] == "INVALID_ARGUMENT"
    assert _fn(server.flag_message)("a", "INBOX", "1", color=-2)["error"]["code"] == "INVALID_ARGUMENT"


def test_flag_message_accepts_minus_one_to_clear():
    with patch("apple_mail_mcp.server.run_script_json") as mock:
        mock.return_value = {"id": "1", "flag_index": -1}
        out = _fn(server.flag_message)("a", "INBOX", "1", color=-1)
    assert out["ok"] is True
    import json as _json
    payload = _json.loads(mock.call_args.args[1][0])
    assert payload["color"] == -1


def test_flag_message_requires_all_id_args():
    assert _fn(server.flag_message)("", "INBOX", "1", color=2)["error"]["code"] == "INVALID_ARGUMENT"


def test_list_attachments_validates():
    assert _fn(server.list_attachments)("", "INBOX", "1")["error"]["code"] == "INVALID_ARGUMENT"


def test_save_attachment_validates_index():
    out = _fn(server.save_attachment)("a", "INBOX", "1", index=0, target_dir="/tmp/x")
    assert out["error"]["code"] == "INVALID_ARGUMENT"


def test_save_all_attachments_requires_message_args():
    with patch("apple_mail_mcp.server.run_script_json") as mock:
        out = _fn(server.save_all_attachments)("a", "", "1")
    assert out["error"]["code"] == "INVALID_ARGUMENT"
    mock.assert_not_called()


def test_search_messages_passes_payload_as_json():
    with patch("apple_mail_mcp.server.run_script_json") as mock:
        mock.return_value = []
        out = _fn(server.search_messages)(
            account="me", mailbox="INBOX", limit=10, unread_only=True
        )
    assert out["ok"] is True
    args = mock.call_args.args
    assert args[0] == "search_messages.js"
    import json as _json
    payload = _json.loads(args[1][0])
    assert payload["account"] == "me"
    assert payload["mailbox"] == "INBOX"
    assert payload["limit"] == 10
    assert payload["unread_only"] is True


def test_timeout_is_reported_as_timeout_not_internal_error():
    import subprocess
    with patch("apple_mail_mcp.server.run_script_json") as mock:
        mock.side_effect = subprocess.TimeoutExpired(cmd=["osascript"], timeout=45)
        out = _fn(server.list_accounts)()
    assert out["ok"] is False
    assert out["error"]["code"] == "TIMEOUT"
    assert "APPLE_MAIL_MCP_APPLESCRIPT_TIMEOUT_MS" in out["error"]["message"]


def _tools():
    import asyncio
    return {t.name: t for t in asyncio.run(server.mcp.list_tools())}


def test_every_tool_declares_annotations():
    for name, tool in _tools().items():
        assert tool.annotations is not None, name
        assert tool.annotations.readOnlyHint is not None, name


def test_only_reads_are_marked_read_only():
    read_only = {n for n, t in _tools().items() if t.annotations.readOnlyHint}
    assert read_only == {
        "ping", "version", "list_accounts", "list_mailboxes",
        "search_messages", "get_thread", "list_attachments",
    }


def test_destructive_tools_are_marked_destructive():
    destructive = {n for n, t in _tools().items() if t.annotations.destructiveHint}
    assert destructive == {"move_to_mailbox", "save_attachment", "save_all_attachments"}
