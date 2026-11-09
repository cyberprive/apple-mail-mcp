// create_draft — create a draft message in Apple Mail's Drafts folder.
//
// Two modes:
//   1. New message (default): pass account + to + subject + body
//   2. Reply: pass account + body + reply_to {account, mailbox, id}
//      - subject auto-set to "Re: <orig>"
//      - recipient auto-set to original sender (cc/bcc additive)
//      - body becomes <your body> + "\n\n" + manually-quoted original
//      - threading headers (In-Reply-To/References) set by Mail.reply()
//
// argv[0] = JSON object with:
//   account     (string, required) — sender's account name
//   body        (string, required) — your reply text (plain text in v1)
//   to          (array<string>, required UNLESS reply_to is set)
//   subject     (string, required UNLESS reply_to is set)
//   cc          (array<string>, optional)
//   bcc         (array<string>, optional)
//   visible     (bool, optional; default false → silent draft)
//   reply_to    (object, optional) — {account, mailbox, id} of original message
//   reply_all   (bool, optional; default false; only relevant with reply_to)
//
// Output: JSON {created, mailbox, account, sender, to, cc, bcc, subject,
//               visible, replied_to_id?}.
// Note: persisted Drafts id is NOT returned (Mail commits async).

function buildQuote(orig) {
  let dateStr = "";
  try { dateStr = orig.dateReceived().toLocaleString(); } catch (e) {}
  let sender = "";
  try { sender = orig.sender() || ""; } catch (e) {}
  let body = "";
  try { body = orig.content() || ""; } catch (e) {}
  const quotedBody = body.split("\n").map(function(l) { return "> " + l; }).join("\n");
  return "On " + dateStr + ", " + sender + " wrote:\n" + quotedBody;
}

function pushAddrs(Mail, draft, list, kind) {
  if (!Array.isArray(list)) return;
  for (let i = 0; i < list.length; i++) {
    const addr = list[i];
    if (!addr) continue;
    if (kind === "to") draft.toRecipients.push(Mail.ToRecipient({ address: addr }));
    else if (kind === "cc") draft.ccRecipients.push(Mail.CcRecipient({ address: addr }));
    else if (kind === "bcc") draft.bccRecipients.push(Mail.BccRecipient({ address: addr }));
  }
}

function run(argv) {
  if (!argv || argv.length < 1) throw new Error("Usage: create_draft <json>");
  const args = JSON.parse(argv[0]);
  if (!args.account) throw new Error("Missing required arg: account");
  if (typeof args.body !== "string") throw new Error("`body` must be a string");

  const Mail = Application('Mail');

  // Resolve sender's account.
  const accounts = Mail.accounts.whose({ name: args.account })();
  if (accounts.length === 0) throw new Error("Account not found: " + args.account);
  const acct = accounts[0];
  const emails = acct.emailAddresses();
  if (!emails || emails.length === 0) {
    throw new Error("Account has no email addresses: " + args.account);
  }
  const senderAddress = emails[0];
  let senderName = "";
  try { senderName = acct.fullName() || ""; } catch (e) {}
  const sender = senderName ? (senderName + " <" + senderAddress + ">") : senderAddress;

  const visible = !!args.visible;
  const replyTo = args.reply_to;
  let draft;
  let resolvedSubject;
  let resolvedTo = args.to || [];
  let repliedToId = null;

  if (replyTo) {
    if (!replyTo.account || !replyTo.mailbox || !replyTo.id) {
      throw new Error("reply_to requires {account, mailbox, id}");
    }
    const origAccts = Mail.accounts.whose({ name: replyTo.account })();
    if (origAccts.length === 0) throw new Error("reply_to account not found: " + replyTo.account);
    const origMbs = origAccts[0].mailboxes.whose({ name: replyTo.mailbox })();
    if (origMbs.length === 0) throw new Error("reply_to mailbox not found: " + replyTo.mailbox);
    const origMatches = origMbs[0].messages.whose({ id: Number(replyTo.id) })();
    if (origMatches.length === 0) throw new Error("reply_to message not found: id=" + replyTo.id);
    const orig = origMatches[0];

    const quote = buildQuote(orig);
    repliedToId = String(replyTo.id);

    draft = Mail.reply(orig, {
      openingWindow: visible,
      replyToAll: !!args.reply_all,
    });
    // Mail.reply() does not populate draft.content synchronously; the OM is empty.
    // Set our body + quote directly. Threading headers are already set by reply().
    draft.content = args.body + "\n\n" + quote;
    // Subject is auto-set by reply() to "Re: <orig>"; honor an explicit override if given.
    if (args.subject) draft.subject = args.subject;
    resolvedSubject = draft.subject();
    try {
      resolvedTo = draft.toRecipients().map(function(r) { return r.address(); });
    } catch (e) {}
    // cc/bcc passed by caller are ADDITIVE on a reply.
    pushAddrs(Mail, draft, args.cc, "cc");
    pushAddrs(Mail, draft, args.bcc, "bcc");
  } else {
    if (!Array.isArray(args.to) || args.to.length === 0) {
      throw new Error("`to` must be a non-empty array (or pass reply_to)");
    }
    if (typeof args.subject !== "string") {
      throw new Error("`subject` must be a string (or pass reply_to)");
    }
    resolvedSubject = args.subject;

    draft = Mail.OutgoingMessage({
      subject: args.subject,
      content: args.body,
      sender: sender,
      visible: visible,
    });
    Mail.outgoingMessages.push(draft);
    pushAddrs(Mail, draft, args.to, "to");
    pushAddrs(Mail, draft, args.cc, "cc");
    pushAddrs(Mail, draft, args.bcc, "bcc");
  }

  draft.save();

  return JSON.stringify({
    created: true,
    mailbox: "Drafts",
    account: args.account,
    sender: sender,
    to: resolvedTo,
    cc: args.cc || [],
    bcc: args.bcc || [],
    subject: resolvedSubject,
    visible: visible,
    replied_to_id: repliedToId,
  });
}
