# Contributing

Issues and pull requests are welcome. A few rules keep this server safe to run
against a real mailbox.

## Ground rules

- **Never send mail.** The server creates drafts; a person presses Send. A PR
  that adds sending will not be merged.
- **Never put caller input into script text.** Python passes every argument to
  the JXA scripts as a single JSON string in `argv`; scripts `JSON.parse` it.
  No string-building of AppleScript, no `eval`, no `do shell script`.
- **Treat email content as hostile.** Message bodies, subjects and attachment
  names come from whoever sent the email, and the model reading them may be
  following their instructions. Anything that writes (files, folders, flags)
  must be safe even when every argument was chosen by an attacker. See
  `paths.py` and `scripts/save_attachments.js` for the pattern.
- **Destructive tools need `confirm=true`** and the `DESTRUCTIVE` annotation.
  Without `confirm`, return the `CONFIRM_REQUIRED` envelope describing exactly
  what would happen, and do nothing.
- **No personal data in the repo.** No real addresses, account names or home
  paths in code, docs, tests or commit messages. `tests/test_repo_hygiene.py`
  checks the files; commit messages are on you.

## Layout

| Path | What lives there |
|---|---|
| `server.py` | Tool definitions only: validate arguments, call a script, wrap the result. |
| `applescript.py` | The one place that runs `osascript`: timeouts, errors, JSON parsing. |
| `paths.py` | Where attachments may be written. |
| `config.py` | Settings from `APPLE_MAIL_MCP_*` environment variables. |
| `envelope.py` | The `{ok, data}` / `{ok, error}` response shape every tool returns. |
| `scripts/*.js` | One JXA script per Mail operation. |

## Tests

```sh
pip install -e ".[dev]"
pytest
```

Unit tests mock `osascript`, so they don't touch Mail. The filename test in
`tests/test_attachment_paths.py` runs real JXA and needs macOS.

When you add a tool: document it in the README's tool table, give it
annotations, and add a test for its argument validation. If it writes
anything, add a test that tries to make it write somewhere it shouldn't.
