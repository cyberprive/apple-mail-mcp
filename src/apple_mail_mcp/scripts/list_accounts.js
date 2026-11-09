// list_accounts — return every account configured in Apple Mail.
// No arguments. Output: JSON array of {id, name, user_name, account_type,
// email_addresses, enabled}.

function run() {
  const Mail = Application('Mail');
  const accounts = Mail.accounts();
  const out = [];
  for (let i = 0; i < accounts.length; i++) {
    const a = accounts[i];
    out.push({
      id: String(a.id()),
      name: a.name(),
      user_name: a.userName(),
      account_type: String(a.accountType()),
      email_addresses: a.emailAddresses(),
      enabled: a.enabled(),
    });
  }
  return JSON.stringify(out);
}
