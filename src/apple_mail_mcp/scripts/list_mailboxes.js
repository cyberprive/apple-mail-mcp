// list_mailboxes — list mailboxes (folders) in a given account.
//
// argv[0] = account name (as returned by list_accounts).
// argv[1] = "true" to include unread_count + total_count, "false" to skip.
//          Counts trigger Mail to enumerate each folder, which is slow on
//          large iCloud accounts (88 folders × multiple 30k+ folders can
//          easily hit 30+ seconds). Default: skip counts.
//
// Output: JSON array of {name, unread_count?, total_count?}.

function run(argv) {
  if (!argv || argv.length < 1) throw new Error("Usage: list_mailboxes <account_name> [with_counts]");
  const accountName = argv[0];
  const withCounts = argv[1] === "true";
  const Mail = Application('Mail');
  const matches = Mail.accounts.whose({ name: accountName })();
  if (matches.length === 0) throw new Error("Account not found: " + accountName);
  const acct = matches[0];
  const mailboxes = acct.mailboxes();
  const out = [];
  for (let i = 0; i < mailboxes.length; i++) {
    const mb = mailboxes[i];
    const entry = { name: mb.name() };
    if (withCounts) {
      try { entry.unread_count = mb.unreadCount(); } catch (e) { entry.unread_count = null; }
      try { entry.total_count = mb.messages.length; } catch (e) { entry.total_count = null; }
    }
    out.push(entry);
  }
  return JSON.stringify(out);
}
