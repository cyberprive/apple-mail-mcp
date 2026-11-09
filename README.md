# apple-mail-mcp

A local [MCP](https://modelcontextprotocol.io) server that lets Claude, or any
MCP client, read, search, draft and file email in **Apple Mail on macOS**.

It drives Mail through AppleScript (JXA), so it works with every account Mail
already has (iCloud, Gmail, Exchange/Microsoft 365, plain IMAP) and never
sees a password or token. It writes drafts but **never sends**: you review and
press Send in Mail.

## Requirements

- macOS with Mail set up
- Python 3.11+
- An MCP client: Claude Code, Claude Desktop, or another

## Install

```sh
git clone https://github.com/cyberprive/apple-mail-mcp.git
cd apple-mail-mcp
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Connect it to your client

**Claude Code**, from the repo folder:

```sh
claude mcp add apple-mail -- "$PWD/.venv/bin/python" -m apple_mail_mcp.server
```

**Claude Desktop**: add this to `~/Library/Application Support/Claude/claude_desktop_config.json`,
using the absolute path to your clone, then restart Claude Desktop:

```json
{
  "mcpServers": {
    "apple-mail": {
      "command": "/absolute/path/to/apple-mail-mcp/.venv/bin/python",
      "args": ["-m", "apple_mail_mcp.server"],
      "env": {}
    }
  }
}
```

Settings from [Configuration](#configuration) go in `env`.

## First run: allow automation

The first tool call that touches Mail makes macOS ask whether the app running
the server (your terminal, or Claude) may control Mail. Click **OK**. Mail
launches if it isn't running.

If you clicked *Don't Allow*, or calls fail with `Not authorized to send Apple
events to Mail` (error -1743): open **System Settings → Privacy & Security →
Automation**, find that app, and turn on **Mail**.

To check it works, ask your client to call `ping`, then `list_accounts`.

## Safety

**Email is untrusted input.** `search_messages` and `get_thread` hand message
text to the model, and anyone who can email you can write instructions into
that text (prompt injection). The server is built to limit what such an
instruction can do:

- **No sending.** `create_draft` saves to Drafts. Nothing leaves your Mac until
  you press Send.
- **Attachments only land in one folder.** `save_attachment` and
  `save_all_attachments` write only inside `APPLE_MAIL_MCP_ATTACHMENTS_DIR`
  (default `~/Downloads/apple-mail-mcp`). Other paths are refused, including
  ones that try to leave the folder with `..`, `~` or a symlink. Filenames chosen
  by the sender are cleaned: no `/`, no leading dots or dashes, no control
  characters.
- **Moving a message or overwriting a file needs `confirm=true`.** Without it,
  the tool does nothing and returns a `CONFIRM_REQUIRED` description of what it
  would do.

`confirm=true` is a checkpoint, not a lock: a model can pass it on its first
call. The real gate is your client's approval prompt, so **keep approval on for
`move_to_mailbox`, `save_attachment` and `save_all_attachments`**. Every tool
carries MCP annotations (`readOnlyHint`, `destructiveHint`) that clients can
use to decide what to ask about.

**Everything stays local.** The server talks to your client over stdio and
opens no network port. It logs tool calls, account and mailbox names, message
ids and errors to `~/Library/Logs/apple-mail-mcp.log`. Message bodies are not
logged; the one exception is a script that returns malformed output, whose
first 200 characters are logged to help debug it.

## Tools

| Tool | Kind | Arguments | Returns |
|---|---|---|---|
| `ping` | read | — | `"OK"` |
| `version` | read | — | `{version}` |
| `list_accounts` | read | — | `[{id, name, user_name, account_type, email_addresses, enabled}]` |
| `list_mailboxes` | read | `account`, `with_counts=false` | `[{name, unread_count?, total_count?}]` |
| `search_messages` | read | `account`, `mailbox?`, `since?`, `before?`, `limit=50`, `unread_only=false`, `query?`, `field="all"` | `[{id, message_id, account, mailbox, subject, sender, date_received, read, snippet}]` |
| `get_thread` | read | `account`, `mailbox`, `id` | `{messages: [{id, message_id, account, mailbox, subject, sender, to, cc, date_received, date_sent, read, body}]}` |
| `list_attachments` | read | `account`, `mailbox`, `id` | `[{index, name, size, mime_type, downloaded}]` |
| `create_draft` | writes | `account`, `body`, `to[]?`, `subject?`, `cc[]?`, `bcc[]?`, `reply_to?`, `reply_all=false`, `visible?` | `{created, mailbox, account, sender, to, cc, bcc, subject, visible, replied_to_id}` |
| `mark_read` / `mark_unread` | writes | `account`, `mailbox`, `id` | `{id, read}` |
| `flag_message` | writes | `account`, `mailbox`, `id`, `color` (`0`–`6`, `-1` clears) | `{id, flag_index}` |
| `move_to_mailbox` | **destructive** | `account`, `mailbox`, `id`, `target_mailbox`, `confirm=false` | `{id, from_mailbox, to_mailbox}` |
| `save_attachment` | **destructive** | `account`, `mailbox`, `id`, `index`, `target_dir?`, `overwrite=false`, `confirm=false` | `{saved_path, name, original_name, size, downloaded}` |
| `save_all_attachments` | **destructive** | `account`, `mailbox`, `id`, `target_dir?`, `overwrite=false`, `confirm=false` | `{saved: [...], skipped: [...]}` |

Typical flow: `list_accounts` → `list_mailboxes(account)` →
`search_messages(account, since=...)` → `get_thread(account, mailbox, id)` →
`create_draft(...)` → `mark_read` or `move_to_mailbox` once handled.

Notes:

- **`account`** is the `name` from `list_accounts`.
- **`search_messages`** looks in the inbox when `mailbox` is omitted, whatever
  language Mail uses for it. `since` defaults to **7 days ago**; pass an older
  date to look further back. `field` is one of `subject`, `sender`, `content`
  (slow: reads every body) or `all` (subject + sender).
- **Message ids are volatile.** Mail can renumber messages after a move, delete
  or reindex. In multi-step flows, search again rather than reusing old ids.
- **`target_dir`** on the save tools is optional. A relative path is a subfolder
  of the attachments folder; an absolute one must already be inside it.

### Mailbox aliases

`move_to_mailbox` accepts aliases for standard folders, so callers don't need
to know the account's language. `search_messages` accepts `@inbox`.

| Alias | Matches (examples) |
|---|---|
| `@inbox` | INBOX, Inbox, Bandeja de entrada, Boîte de réception, Posteingang, … |
| `@archive` | Archive, Archivo, Archives, All Mail, Archiv, Archivio, Arquivo |
| `@drafts` | Drafts, Borradores, Brouillons, Entwürfe, Bozze, Rascunhos |
| `@sent` | Sent, Sent Messages, Enviados, Elementos enviados, Envoyés, Gesendet |
| `@trash` | Trash, Deleted Messages, Papelera, Elementos eliminados, Corbeille, … |
| `@junk` | Junk, Correo no deseado, Courrier indésirable, Werbung, Spam |

The first name that exists in the account wins. The response reports the
literal folder name it used.

### Drafts and replies

- **New message:** pass `account`, `to`, `subject`, `body`.
- **Reply:** pass `account`, `body` and `reply_to={"account", "mailbox", "id"}`
  from `search_messages`. Mail sets the threading headers, the subject becomes
  `Re: …`, the recipient becomes the original sender, and the original is
  quoted below your text. `cc`/`bcc` are added on top. `reply_all=true` replies
  to everyone.

## Responses and errors

Every tool returns the same envelope:

```json
{"ok": true,  "data": "…"}
{"ok": false, "error": {"code": "…", "message": "…", "details": {}}}
```

| Code | Meaning |
|---|---|
| `INVALID_ARGUMENT` | A required argument is missing or malformed, or a path is outside the attachments folder. |
| `CONFIRM_REQUIRED` | The action needs `confirm=true`. `details` says exactly what would happen. |
| `APPLESCRIPT_ERROR` | Mail refused or failed: account/mailbox/message not found, permission missing, etc. |
| `TIMEOUT` | Mail didn't answer in time. Narrow `since`, or raise the timeout. |
| `INTERNAL_ERROR` | A bug. Please open an issue with the log line. |

## Configuration

All optional. Set them in your client's `env` block for the server.

| Variable | Default | What it does |
|---|---|---|
| `APPLE_MAIL_MCP_ATTACHMENTS_DIR` | `~/Downloads/apple-mail-mcp` | The only folder attachments may be saved into. |
| `APPLE_MAIL_MCP_DRAFT_VISIBLE` | `false` | `true` opens the compose window for each draft; `false` saves silently. |
| `APPLE_MAIL_MCP_APPLESCRIPT_TIMEOUT_MS` | `45000` | Per-call timeout for Mail. |
| `APPLE_MAIL_MCP_LOG_PATH` | `~/Library/Logs/apple-mail-mcp.log` | JSON log file (rotates at 2 MB). |
| `APPLE_MAIL_MCP_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. |

[`.env.example`](./.env.example) has the same list with notes.

## Performance

Mail's scripting interface is slow on big mailboxes, so the server pushes date
and unread filters into Mail's own index: query time follows the size of the
result, not the mailbox. On a ~30k-message iCloud inbox, a 24-hour search takes
about 3 s instead of 60+ s.

Always pass a `since` on large mailboxes (the default is 7 days).
`list_mailboxes(with_counts=true)` and `field="content"` are the slow paths.

## Limitations

- Drafts are **plain text**. Mail's scripting interface doesn't reliably set
  HTML bodies.
- `create_draft` doesn't return the draft's id; Mail saves drafts
  asynchronously.
- `get_thread` returns **the requested message only**, not the whole
  conversation.

## Development

```sh
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

The unit tests mock Mail, so they run anywhere; one filename test runs real JXA
and is skipped off macOS. See [CONTRIBUTING.md](./CONTRIBUTING.md) for the
rules a change has to follow.

## License

[MIT](./LICENSE)
