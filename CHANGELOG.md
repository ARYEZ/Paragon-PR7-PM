# Changelog

## 0.2.2

- The family list (`family.py`) knows the four newest Paragon apps: PR7-HX (hex editor), PR7-DB (SQLite browser),
  PR7-UN (uninstaller) and PR7-LN (launcher), so links between the apps and the PR7-U offer find them.

## 0.2.1

- The family's list knows the newest apps (PR7-HB, PR7-FS, PR7-AR, PR7-WM), so links between apps and Check for Updates find them.

## 0.2.0

- **One finish for the whole family.** Choosing OBSIDIAN or AURORA here switches every Paragon app, open ones included (within a couple of seconds), and every app starts in the family's choice. PR7-PM's menu has a Finish choice now, and its group list and entry details are light in AURORA (they stayed dark).
- In AURORA, group titles and selected rows are dark and readable (they were white on the light finish).

## 0.1.1

- Knows the whole family: PR7-DU, PR7-CB, PR7-IS, PR7-PM and PR7-SM are in its list of family apps (their permanent install IDs), so the family links find them when they're installed.

## 0.1.0

- First release: a password manager that works the way KeePassXC works. Databases are KDBX 4 files (AES-256,
  Argon2) that KeePassXC, KeePass, KeePassDX and Strongbox open too. Groups, entries, the Recycle Bin, search,
  one-time 2FA codes, entry history, KeePassXC's keys, a password and passphrase generator, and CSV import
  (KeePassXC, Bitwarden, browsers). Copies are marked private and emptied after 10 seconds; it locks after 5 idle
  minutes and when Windows locks. It updates itself like the other family apps.
