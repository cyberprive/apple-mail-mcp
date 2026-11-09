"""The server as a client sees it: spawned as a subprocess, spoken to over stdio.

Invariant: a real MCP client over stdio sees exactly these 14 tools, with
these annotations under their camelCase wire names, and an attachment path
outside the attachments folder is refused before any script runs.

Why it matters: test_server.py calls the Python functions directly, so it
cannot see what the SDK puts on the wire. mcp 2.x renamed every model field to
snake_case (`read_only_hint`) and kept camelCase only as the JSON alias. Other
clients read `readOnlyHint`; if the wire ever said `read_only_hint` they would
see no hints at all, and every test that reads the Python model would still pass.

The server runs with an empty PATH, so `osascript` cannot be found: nothing
here can reach Mail, even if a refusal regressed.
"""
import asyncio
import json
import queue
import subprocess
import sys
import threading

import pytest

from apple_mail_mcp import __version__

READ_ONLY = {"readOnlyHint": True}
SETS_STATE = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True}
CREATES = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}
DESTRUCTIVE = {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False}

EXPECTED_ANNOTATIONS = {
    "ping": READ_ONLY,
    "version": READ_ONLY,
    "list_accounts": READ_ONLY,
    "list_mailboxes": READ_ONLY,
    "search_messages": READ_ONLY,
    "get_thread": READ_ONLY,
    "list_attachments": READ_ONLY,
    "create_draft": CREATES,
    "mark_read": SETS_STATE,
    "mark_unread": SETS_STATE,
    "flag_message": SETS_STATE,
    "move_to_mailbox": DESTRUCTIVE,
    "save_attachment": DESTRUCTIVE,
    "save_all_attachments": DESTRUCTIVE,
}

TIMEOUT_S = 30
SERVER_ARGS = ["-m", "apple_mail_mcp.server"]


@pytest.fixture
def server_env(tmp_path):
    no_bin = tmp_path / "empty-bin"
    no_bin.mkdir()
    return {
        "PATH": str(no_bin),
        "APPLE_MAIL_MCP_LOG_PATH": str(tmp_path / "server.log"),
        "APPLE_MAIL_MCP_ATTACHMENTS_DIR": str(tmp_path / "attachments"),
    }


def test_raw_wire_carries_camelcase_annotations(server_env, tmp_path):
    """Read tools/list as raw JSON, with no SDK models in between to re-alias it."""
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    replies = _raw_exchange(server_env, tmp_path, messages, want_ids={1, 2})

    assert replies[1]["result"]["serverInfo"] == {"name": "apple-mail-mcp", "version": __version__}
    tools = replies[2]["result"]["tools"]
    assert {t["name"]: t.get("annotations") for t in tools} == EXPECTED_ANNOTATIONS


def test_stdio_client_lists_tools_and_annotations(server_env, tmp_path):
    async def check(session):
        init = await session.initialize()
        assert init.server_info.name == "apple-mail-mcp"
        assert init.server_info.version == __version__
        listed = await session.list_tools()
        assert listed.next_cursor is None, "all tools must fit in one page"
        return {
            t.name: t.annotations.model_dump(by_alias=True, exclude_none=True)
            for t in listed.tools
        }

    assert _with_session(server_env, tmp_path, check) == EXPECTED_ANNOTATIONS


def test_stdio_client_gets_envelopes_and_refusals(server_env, tmp_path):
    outside = tmp_path / "outside"

    async def check(session):
        await session.initialize()
        ping = await session.call_tool("ping", {})
        refused = await session.call_tool("save_attachment", {
            "account": "a", "mailbox": "INBOX", "id": "1", "index": 1,
            "target_dir": str(outside), "overwrite": True, "confirm": True,
        })
        unconfirmed = await session.call_tool("move_to_mailbox", {
            "account": "a", "mailbox": "INBOX", "id": "1", "target_mailbox": "@trash",
        })
        return ping, refused, unconfirmed

    ping, refused, unconfirmed = _with_session(server_env, tmp_path, check)

    assert not ping.is_error
    assert _envelope(ping) == {"ok": True, "data": "OK"}

    assert _envelope(refused)["error"]["code"] == "INVALID_ARGUMENT"
    assert not outside.exists(), "a refused path must not be created"

    assert _envelope(unconfirmed)["error"]["code"] == "CONFIRM_REQUIRED"


# --- helpers -------------------------------------------------------------------

def _envelope(result):
    [block] = result.content
    return json.loads(block.text)


def _with_session(env, tmp_path, check):
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(command=sys.executable, args=SERVER_ARGS, env=env)

    async def run():
        with open(tmp_path / "server.stderr", "w") as errlog:
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    return await check(session)

    return asyncio.run(asyncio.wait_for(run(), TIMEOUT_S))


def _raw_exchange(env, tmp_path, messages, want_ids):
    """Send JSON-RPC lines, collect replies by id, then close stdin."""
    errlog = open(tmp_path / "server.stderr", "w")
    proc = subprocess.Popen(
        [sys.executable, *SERVER_ARGS],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errlog,
        env=env, text=True,
    )
    lines: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: [lines.put(l) for l in proc.stdout], daemon=True).start()
    try:
        proc.stdin.write("".join(json.dumps(m) + "\n" for m in messages))
        proc.stdin.flush()
        replies = {}
        while not want_ids <= replies.keys():
            try:
                line = lines.get(timeout=TIMEOUT_S)
            except queue.Empty:
                pytest.fail(f"no reply for ids {want_ids - replies.keys()}")
            msg = json.loads(line)  # anything but JSON-RPC on stdout is a bug
            if msg.get("id") in want_ids:
                replies[msg["id"]] = msg
        return replies
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
        proc.stdout.close()
        errlog.close()
