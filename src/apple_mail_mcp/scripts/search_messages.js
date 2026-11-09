// search_messages — list recent messages from a mailbox in an account.
// argv[0] = JSON object with:
//   account      (string, required)
//   mailbox      (string, optional; default "INBOX")
//   since        (ISO 8601 string, optional) — `date_received >= since`
//   before       (ISO 8601 string, optional) — `date_received < before`
//   limit        (int, optional; default 50; max 500)
//   unread_only  (bool, optional; default false)
//   query        (string, optional) — case-insensitive substring filter
//   field        (string, optional; default "all")
//                  "subject"  — match query against subject only
//                  "sender"   — match against sender (name + address)
//                  "content"  — match against body text (slower; iterates content)
//                  "all"      — subject OR sender (NOT content; for that ask explicitly)
// Output: JSON array of message summaries.

function run(argv) {
  if (!argv || argv.length < 1) throw new Error("Usage: search_messages <json>");
  const args = JSON.parse(argv[0]);
  if (!args.account) throw new Error("Missing required arg: account");

  const Mail = Application('Mail');
  const accounts = Mail.accounts.whose({ name: args.account })();
  if (accounts.length === 0) throw new Error("Account not found: " + args.account);
  const acct = accounts[0];

  // Resolve the mailbox. Empty/null/"@inbox" → search known inbox localizations.
  // Apple Mail accounts don't expose a language-agnostic inbox reference, so we
  // try the canonical names. Add new languages here as we encounter them.
  const INBOX_ALIASES = [
    "INBOX",                  // iCloud, IMAP default, English
    "Inbox",                  // English variant
    "Bandeja de entrada",     // Spanish (M365 ES, iCloud ES)
    "Boîte de réception",     // French
    "Posteingang",            // German
    "Caixa de entrada",       // Portuguese
    "Posta in arrivo",        // Italian
    "受信",                    // Japanese
    "收件箱",                  // Chinese (Simplified)
  ];

  let mb = null;
  let mailboxName;
  const requested = args.mailbox;
  if (!requested || requested === "@inbox") {
    for (let i = 0; i < INBOX_ALIASES.length; i++) {
      const cand = acct.mailboxes.whose({ name: INBOX_ALIASES[i] })();
      if (cand.length > 0) {
        mb = cand[0];
        mailboxName = INBOX_ALIASES[i];
        break;
      }
    }
    if (!mb) {
      throw new Error(
        "Could not auto-detect inbox in account '" + args.account +
        "'. Pass an explicit mailbox name from list_mailboxes."
      );
    }
  } else {
    const mbMatches = acct.mailboxes.whose({ name: requested })();
    if (mbMatches.length === 0) {
      throw new Error("Mailbox not found: " + requested + " in " + args.account);
    }
    mb = mbMatches[0];
    mailboxName = requested;
  }

  const sinceDate = args.since ? new Date(args.since) : null;
  const beforeDate = args.before ? new Date(args.before) : null;
  const limit = Math.min(args.limit || 50, 500);
  const unreadOnly = !!args.unread_only;
  const query = args.query ? String(args.query).toLowerCase() : null;
  const field = (args.field || "all").toLowerCase();
  if (["subject", "sender", "content", "all"].indexOf(field) === -1) {
    throw new Error("field must be one of: subject, sender, content, all");
  }

  // Push date and unread filters into Mail's `whose` clause so Mail's index
  // does the heavy lifting. On a 30k+ message inbox, this is the difference
  // between a 2-3 second query and a 60+ second one. Note: JXA exposes
  // `_greaterThan` and `_lessThan` (no `_greaterEqualTo`); the off-by-one
  // millisecond on a `since` boundary is irrelevant for triage windows.
  const conditions = [];
  if (sinceDate) conditions.push({ dateReceived: { _greaterThan: sinceDate } });
  if (beforeDate) conditions.push({ dateReceived: { _lessThan: beforeDate } });
  if (unreadOnly) conditions.push({ readStatus: false });

  let messages;
  if (conditions.length === 0) {
    // No prefilters — fall back to iterating. Mail returns newest-first,
    // so we still bound work by `limit`.
    messages = mb.messages();
  } else if (conditions.length === 1) {
    messages = mb.messages.whose(conditions[0])();
  } else {
    messages = mb.messages.whose({ _and: conditions })();
  }
  const out = [];
  for (let i = 0; i < messages.length && out.length < limit; i++) {
    const m = messages[i];
    let date;
    try { date = m.dateReceived(); } catch (e) { continue; }
    // When `whose` was used, date+read are already filtered. Keep these
    // checks as a safety net for the no-prefilter path.
    if (conditions.length === 0) {
      if (sinceDate && date < sinceDate) break;
      if (beforeDate && date >= beforeDate) continue;
    }

    let read;
    try { read = m.readStatus(); } catch (e) { read = null; }
    if (conditions.length === 0 && unreadOnly && read) continue;

    let subject = "";
    try { subject = m.subject() || ""; } catch (e) {}
    let sender = "";
    try { sender = m.sender() || ""; } catch (e) {}

    if (query) {
      let hay;
      if (field === "subject") {
        hay = subject;
      } else if (field === "sender") {
        hay = sender;
      } else if (field === "content") {
        try { hay = m.content() || ""; } catch (e) { hay = ""; }
      } else { // "all" — subject + sender (content excluded for perf)
        hay = subject + " " + sender;
      }
      if (hay.toLowerCase().indexOf(query) === -1) continue;
    }

    let snippet = "";
    try {
      const content = m.content() || "";
      snippet = content.substring(0, 240).replace(/\s+/g, " ").trim();
    } catch (e) {}

    out.push({
      id: String(m.id()),
      message_id: (function() { try { return m.messageId(); } catch (e) { return null; } })(),
      account: args.account,
      mailbox: mailboxName,
      subject: subject,
      sender: sender,
      date_received: date.toISOString(),
      read: read,
      snippet: snippet,
    });
  }
  return JSON.stringify(out);
}
