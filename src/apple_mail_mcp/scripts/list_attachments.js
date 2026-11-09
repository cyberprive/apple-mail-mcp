// list_attachments — list attachments on a message.
//
// argv[0] = JSON {account, mailbox, id}
// Output: JSON array of {index, name, size, mime_type, downloaded}
//   `index` is the 1-based AppleScript position; pass to save_attachment.
//   `downloaded` indicates whether the attachment body is on disk locally.

function run(argv) {
  if (!argv || argv.length < 1) throw new Error("Usage: list_attachments <json>");
  const args = JSON.parse(argv[0]);
  if (!args.account || !args.mailbox || !args.id) {
    throw new Error("account, mailbox, id are all required");
  }
  const Mail = Application('Mail');
  const accounts = Mail.accounts.whose({ name: args.account })();
  if (accounts.length === 0) throw new Error("Account not found: " + args.account);
  const mbs = accounts[0].mailboxes.whose({ name: args.mailbox })();
  if (mbs.length === 0) throw new Error("Mailbox not found: " + args.mailbox);
  const matches = mbs[0].messages.whose({ id: Number(args.id) })();
  if (matches.length === 0) throw new Error("Message not found: id=" + args.id);
  const m = matches[0];

  const atts = m.mailAttachments();
  const out = [];
  for (let i = 0; i < atts.length; i++) {
    const a = atts[i];
    out.push({
      index: i + 1, // 1-based for AppleScript compatibility
      name: (function() { try { return a.name(); } catch (e) { return null; } })(),
      size: (function() { try { return a.fileSize(); } catch (e) { return null; } })(),
      mime_type: (function() { try { return a.mimeType(); } catch (e) { return null; } })(),
      downloaded: (function() { try { return a.downloaded(); } catch (e) { return null; } })(),
    });
  }
  return JSON.stringify(out);
}
