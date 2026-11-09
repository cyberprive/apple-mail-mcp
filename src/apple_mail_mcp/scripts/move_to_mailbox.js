// move_to_mailbox — move a message from one mailbox to another (same account).
//
// argv[0] = JSON {account, mailbox, id, target_mailbox}
//   `mailbox` and `target_mailbox` accept either an exact name OR a
//   localization-aware alias starting with "@":
//     @inbox    INBOX / Bandeja de entrada / Boîte de réception / Posteingang …
//     @archive  Archive / Archivo / All Mail …
//     @drafts   Drafts / Borradores / Brouillons …
//     @sent     Sent / Sent Messages / Enviados / Elementos enviados …
//     @trash    Trash / Deleted Messages / Papelera / Corbeille …
//     @junk     Junk / Correo no deseado / Courrier indésirable …
//
// Output: JSON {id, from_mailbox, to_mailbox} — `from_mailbox`/`to_mailbox`
//   are the resolved (literal) names so callers can log accurately.

const STANDARD_ALIASES = {
  "@inbox":   ["INBOX", "Inbox", "Bandeja de entrada", "Boîte de réception", "Posteingang", "Caixa de entrada", "Posta in arrivo", "受信", "收件箱"],
  "@archive": ["Archive", "Archives", "Archivo", "Archivos", "All Mail", "Archiv", "Archivio", "Arquivo"],
  "@drafts":  ["Drafts", "Borradores", "Brouillons", "Entwürfe", "Bozze", "Rascunhos"],
  "@sent":    ["Sent", "Sent Messages", "Enviados", "Elementos enviados", "Envoyés", "Gesendet", "Enviadas", "Posta inviata"],
  "@trash":   ["Trash", "Deleted Messages", "Papelera", "Elementos eliminados", "Corbeille", "Papierkorb", "Cestino", "Lixo"],
  "@junk":    ["Junk", "Junk Mail", "Junk E-mail", "Correo no deseado", "Courrier indésirable", "Werbung", "Posta indesiderata", "Lixo eletrônico", "Spam"],
};

function resolveMailbox(acct, name) {
  if (typeof name !== "string" || name.length === 0) {
    throw new Error("mailbox name is required");
  }
  if (name.charAt(0) === "@") {
    const key = name.toLowerCase();
    const aliases = STANDARD_ALIASES[key];
    if (!aliases) throw new Error("Unknown mailbox alias: " + name);
    for (let i = 0; i < aliases.length; i++) {
      const m = acct.mailboxes.whose({ name: aliases[i] })();
      if (m.length > 0) return { ref: m[0], name: aliases[i] };
    }
    throw new Error(
      "No mailbox matching " + name + " in account '" + acct.name() +
      "'. Pass an explicit name from list_mailboxes."
    );
  }
  const m = acct.mailboxes.whose({ name: name })();
  if (m.length === 0) throw new Error("Mailbox not found: " + name);
  return { ref: m[0], name: name };
}

function run(argv) {
  if (!argv || argv.length < 1) throw new Error("Usage: move_to_mailbox <json>");
  const args = JSON.parse(argv[0]);
  if (!args.account || !args.mailbox || !args.id || !args.target_mailbox) {
    throw new Error("account, mailbox, id, target_mailbox are all required");
  }
  const Mail = Application('Mail');
  const accounts = Mail.accounts.whose({ name: args.account })();
  if (accounts.length === 0) throw new Error("Account not found: " + args.account);
  const acct = accounts[0];

  const src = resolveMailbox(acct, args.mailbox);
  const dst = resolveMailbox(acct, args.target_mailbox);

  const matches = src.ref.messages.whose({ id: Number(args.id) })();
  if (matches.length === 0) {
    throw new Error("Message not found: id=" + args.id + " in '" + src.name + "'");
  }

  Mail.move(matches[0], { to: dst.ref });

  return JSON.stringify({
    id: args.id,
    from_mailbox: src.name,
    to_mailbox: dst.name,
  });
}
