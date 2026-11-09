// get_thread — fetch full content for a message.
// v1: returns the single message identified by (account, mailbox, id).
// True threading (gather all messages by Message-ID/References) is v1.5;
// for triage purposes a single-message fetch is sufficient.
//
// argv[0] = JSON object with:
//   account     (string, required)
//   mailbox     (string, required)
//   id          (string, required) — Mail.app's numeric message id from search_messages
// Output: JSON object {messages: [{...}]}

function run(argv) {
  if (!argv || argv.length < 1) throw new Error("Usage: get_thread <json>");
  const args = JSON.parse(argv[0]);
  if (!args.account) throw new Error("Missing required arg: account");
  if (!args.mailbox) throw new Error("Missing required arg: mailbox");
  if (!args.id) throw new Error("Missing required arg: id");

  const Mail = Application('Mail');
  const accounts = Mail.accounts.whose({ name: args.account })();
  if (accounts.length === 0) throw new Error("Account not found: " + args.account);
  const acct = accounts[0];

  const mbMatches = acct.mailboxes.whose({ name: args.mailbox })();
  if (mbMatches.length === 0) throw new Error("Mailbox not found: " + args.mailbox);
  const mb = mbMatches[0];

  const idNum = Number(args.id);
  const matches = mb.messages.whose({ id: idNum })();
  if (matches.length === 0) throw new Error("Message not found: id=" + args.id);
  const m = matches[0];

  let recipients = [];
  try {
    const rs = m.toRecipients();
    for (let i = 0; i < rs.length; i++) {
      recipients.push({ name: rs[i].name(), address: rs[i].address() });
    }
  } catch (e) { /* skip */ }

  let ccs = [];
  try {
    const rs = m.ccRecipients();
    for (let i = 0; i < rs.length; i++) {
      ccs.push({ name: rs[i].name(), address: rs[i].address() });
    }
  } catch (e) { /* skip */ }

  const message = {
    id: String(m.id()),
    message_id: (function() { try { return m.messageId(); } catch (e) { return null; } })(),
    account: args.account,
    mailbox: args.mailbox,
    subject: (function() { try { return m.subject() || ""; } catch (e) { return ""; } })(),
    sender: (function() { try { return m.sender() || ""; } catch (e) { return ""; } })(),
    to: recipients,
    cc: ccs,
    date_received: (function() { try { return m.dateReceived().toISOString(); } catch (e) { return null; } })(),
    date_sent: (function() { try { return m.dateSent().toISOString(); } catch (e) { return null; } })(),
    read: (function() { try { return m.readStatus(); } catch (e) { return null; } })(),
    body: (function() { try { return m.content() || ""; } catch (e) { return ""; } })(),
  };

  return JSON.stringify({ messages: [message] });
}
