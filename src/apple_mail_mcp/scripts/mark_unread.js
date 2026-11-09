// mark_unread — flip readStatus to false on a single message.
//
// argv[0] = JSON {account, mailbox, id}
// Output: JSON {id, read: false}

function run(argv) {
  if (!argv || argv.length < 1) throw new Error("Usage: mark_unread <json>");
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
  matches[0].readStatus = false;
  return JSON.stringify({ id: args.id, read: false });
}
