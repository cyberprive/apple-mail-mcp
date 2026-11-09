// flag_message — set or clear the flag on a message.
//
// argv[0] = JSON {account, mailbox, id, color}
//   color: integer 0..6 (Apple Mail's flag colors), or -1 to clear the flag.
//     0 red · 1 orange · 2 yellow · 3 green · 4 blue · 5 purple · 6 gray
//
// Output: JSON {id, flag_index}

function run(argv) {
  if (!argv || argv.length < 1) throw new Error("Usage: flag_message <json>");
  const args = JSON.parse(argv[0]);
  if (!args.account || !args.mailbox || !args.id) {
    throw new Error("account, mailbox, id are all required");
  }
  if (args.color === undefined || args.color === null) {
    throw new Error("color is required (0..6 to set, -1 to clear)");
  }
  const colorIdx = Number(args.color);
  if (!Number.isInteger(colorIdx) || colorIdx < -1 || colorIdx > 6) {
    throw new Error("color must be an integer in -1..6");
  }
  const Mail = Application('Mail');
  const accounts = Mail.accounts.whose({ name: args.account })();
  if (accounts.length === 0) throw new Error("Account not found: " + args.account);
  const mbs = accounts[0].mailboxes.whose({ name: args.mailbox })();
  if (mbs.length === 0) throw new Error("Mailbox not found: " + args.mailbox);
  const matches = mbs[0].messages.whose({ id: Number(args.id) })();
  if (matches.length === 0) throw new Error("Message not found: id=" + args.id);
  matches[0].flagIndex = colorIdx;
  return JSON.stringify({ id: args.id, flag_index: colorIdx });
}
