// save_attachments — save one attachment (index set) or every attachment
// (index null) on a message into a directory.
//
// argv[0] = JSON {account, mailbox, id, index, target_dir, overwrite}
//   index:      1-based, from list_attachments; null = save all.
//   target_dir: absolute, existing directory. server.py has already resolved
//               it and refused anything outside APPLE_MAIL_MCP_ATTACHMENTS_DIR.
//   overwrite:  bool. When false and a file already exists at the chosen name,
//               append " (2)", " (3)", ... before the extension.
//
// The file NAME comes from whoever sent the email, so it is untrusted.
// safeFilename() removes path separators, control characters and leading
// dots/dashes, so a name like "../../.zshrc" can neither leave target_dir nor
// create a hidden file. tests/test_attachment_paths.py runs this function directly.
//
// Output, index set:  {saved_path, name, original_name, size, downloaded}
// Output, index null: {saved: [{index, saved_path, name, original_name, size}],
//                      skipped: [{index, name, reason}]}

ObjC.import("Foundation");

function safeFilename(raw, fallback) {
  let s = (raw === null || raw === undefined) ? "" : String(raw);
  s = s.replace(/[\/\\]/g, "-");               // no path separators
  s = s.replace(/[\u0000-\u001f\u007f]/g, ""); // no control characters
  s = s.replace(/^[\s.\-]+/, "");             // no hidden files, no "."/"..", no "-flag" names
  s = s.replace(/\s+$/, "");
  if (s.length > 200) {                        // stay under the 255-byte limit
    const dot = s.lastIndexOf(".");
    const ext = (dot > 0 && s.length - dot <= 16) ? s.substring(dot) : "";
    s = s.substring(0, 200 - ext.length) + ext;
  }
  return s || fallback;
}

function fileExists(path) {
  return $.NSFileManager.defaultManager.fileExistsAtPath(path);
}

function isDirectory(path) {
  const isDir = Ref();
  return $.NSFileManager.defaultManager.fileExistsAtPathIsDirectory(path, isDir) && isDir[0];
}

function destination(dir, name, overwrite) {
  if (name.indexOf("/") !== -1 || name === "." || name === "..") {
    throw new Error("refusing unsafe filename: " + JSON.stringify(name));
  }
  const base = dir.replace(/\/+$/, "") + "/";
  if (overwrite || !fileExists(base + name)) return base + name;
  const lastDot = name.lastIndexOf(".");
  const stem = lastDot > 0 ? name.substring(0, lastDot) : name;
  const ext = lastDot > 0 ? name.substring(lastDot) : "";
  for (let n = 2; n < 1000; n++) {
    const candidate = base + stem + " (" + n + ")" + ext;
    if (!fileExists(candidate)) return candidate;
  }
  throw new Error("Could not find a free filename in " + dir);
}

function sizeOf(att) {
  try { return att.fileSize(); } catch (e) { return null; }
}

function run(argv) {
  if (!argv || argv.length < 1) throw new Error("Usage: save_attachments <json>");
  const args = JSON.parse(argv[0]);
  if (!args.account || !args.mailbox || !args.id) {
    throw new Error("account, mailbox, id are all required");
  }
  if (!args.target_dir || args.target_dir.charAt(0) !== "/") {
    throw new Error("target_dir must be an absolute path");
  }
  if (!isDirectory(args.target_dir)) {
    throw new Error("target_dir does not exist: " + args.target_dir);
  }
  const single = args.index !== null && args.index !== undefined;
  if (single && !(Number(args.index) >= 1)) {
    throw new Error("index must be a 1-based integer");
  }

  const Mail = Application('Mail');
  const accounts = Mail.accounts.whose({ name: args.account })();
  if (accounts.length === 0) throw new Error("Account not found: " + args.account);
  const mbs = accounts[0].mailboxes.whose({ name: args.mailbox })();
  if (mbs.length === 0) throw new Error("Mailbox not found: " + args.mailbox);
  const matches = mbs[0].messages.whose({ id: Number(args.id) })();
  if (matches.length === 0) throw new Error("Message not found: id=" + args.id);
  const atts = matches[0].mailAttachments();

  if (single) {
    const idx = Number(args.index) - 1;
    if (idx >= atts.length) {
      throw new Error("Attachment index out of range: " + args.index + " (have " + atts.length + ")");
    }
    const att = atts[idx];
    let downloaded;
    try { downloaded = att.downloaded(); } catch (e) { downloaded = null; }
    if (downloaded === false) {
      throw new Error("Attachment is not downloaded locally; open the message in Mail to fetch it first");
    }
    let original = null;
    try { original = att.name(); } catch (e) {}
    const name = safeFilename(original, "attachment_" + args.index);
    const path = destination(args.target_dir, name, !!args.overwrite);
    Mail.save(att, { in: Path(path) });
    return JSON.stringify({
      saved_path: path,
      name: name,
      original_name: original,
      size: sizeOf(att),
      downloaded: downloaded,
    });
  }

  const saved = [];
  const skipped = [];
  for (let i = 0; i < atts.length; i++) {
    const a = atts[i];
    let original = null;
    try { original = a.name(); } catch (e) {}
    const name = safeFilename(original, "attachment_" + (i + 1));
    let downloaded = null;
    try { downloaded = a.downloaded(); } catch (e) {}
    if (downloaded === false) {
      skipped.push({ index: i + 1, name: name, reason: "not_downloaded" });
      continue;
    }
    try {
      const path = destination(args.target_dir, name, !!args.overwrite);
      Mail.save(a, { in: Path(path) });
      saved.push({ index: i + 1, saved_path: path, name: name, original_name: original, size: sizeOf(a) });
    } catch (e) {
      skipped.push({ index: i + 1, name: name, reason: String(e.message || e) });
    }
  }
  return JSON.stringify({ saved: saved, skipped: skipped });
}
