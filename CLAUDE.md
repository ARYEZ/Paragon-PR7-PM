# Paragon PR7-PM: notes for Claude

**Paragon PR7-PM** is the owner's personal password manager: Python (**PySide6** + **pykeepass**) that **works the
way KeePassXC works**, in the Paragon family look (PR7-Z ... PR7-CB, PR7-IS `ARYEZ/Paragon-PR7-IS`). Windows 10/11 x64
is the target; it runs on Linux for tests. The owner writes Python; explain the why.

## How it's built

- `pr7pm/vault.py` (no Qt): `Vault` over pykeepass: KDBX 4 (AES-256, Argon2d 64 MB from pykeepass's
  blank_database.kdbx), `children` (Recycle Bin last), `rows(group, query)` (search: every word in title / user name /
  URL / notes / tags, never the password; the bin isn't searched), `delete_entry` (to the bin, then for good),
  `update_entry` (save_history first), `save` through `<file>.part` + os.replace. `otp_now` is RFC 6238 written here:
  pyotp refuses 80-bit secrets, which many services use. `import_csv` maps KeePassXC / Bitwarden / browser columns.
- `pr7pm/generator.py` (no Qt): `secrets` only; `words.txt` = the EFF large list as KeePassXC ships it (7,772 words).
- `pr7pm/clipboard.py`: `private_data` sets ExcludeClipboardContentFromMonitorProcessing, CanIncludeInClipboardHistory
  = DWORD 0 and Clipboard Viewer Ignore, in Qt's windows-mime form on Windows (`mime_name`): what PR7-CB's
  `clipwatch.private` and Windows' history check. `SecretClipboard` empties it after N s only if it's still ours.
- `pr7pm/main_window.py`: unlock page / database page (QStackedWidget); `EntryModel` (plain list, never
  QStandardItemModel); `EntryTable` and `SearchBox` take their keys themselves (Qt's table answers Ctrl+C with the
  cell's text; window shortcuts need an active window); saves after every change (`changed`); `lock` (idle timer via
  the app-wide `_Activity` filter, WTS session lock in `nativeEvent`, minimise); every dialog through `_ask(kind)` /
  `answers`. Dialogs: `NewDatabaseDialog`, `EntryDialog`, `GeneratorDialog`, `OptionsDialog`.
- `pr7pm/app.py`: one window per user (QLocalSocket hand-off of a .kdbx, PR7-R's Windows fix); command-line modes
  never let an error escape (the windowed exe would wait on an error box: PR7-IS's lesson); `--selftest OUT.json`
  (CI runs it on the installed exe), `--register` / `--unregister` (shell.py: .kdbx Open with + Default apps, HKCU).
- `pr7pm.spec` must `collect_data_files("pykeepass")` (blank_database.kdbx: new databases fail without it) and ship
  words.txt. Installer `installer/pr7pm.iss` (per user, AppId {18BE3275-9FB9-46DF-9C29-060A544E4632} permanent; task
  kdbx (ticked), desktopicon); CI installs it, `tools/verify_install.py installed|uninstalled`.
- Updates: `pr7pm/updates.py` / `update_ui.py` (the family's files, keep them in step; with PR7-U installed,
  update_ui offers it); `family.py`: the family's AppIds (PR7-PM included).

## The look (family rules)

- Theme is PR7-IS's (OBSIDIAN + AURORA). Colours: the family's only; Inter (revealed / generated passwords are the
  one exception: monospaced, so l 1 I and O 0 differ); labels UPPER CASE.
- The PR7-PM mark: PR7 `Logo.cpp` geometry plus P and M (PR7-P's bowl, `widgets.M_SHAPE`); icon "7PM" by
  `tools/make_icon.py`, wizard art by `tools/make_installer_art.py`. Check visuals with
  `QT_SCALE_FACTOR=2 python tools/screenshots.py OUT` (a made-up database).

## Rules

- Behaviour questions: do what KeePassXC does (keys, Delete, copy and clear, lock, generator).
- Tests: `python -m pytest` (offscreen) on real .kdbx files; `keepassxc-cli` (when installed) cross-checks both ways.
  Never the real settings or data folder (conftest), or, outside CI, the registry.
- Never log, print or send a password, a master key or an entry's contents.
- Releases: bump `__version__` in `pr7pm/__init__.py` and add a `## x.y.z` section to CHANGELOG.md, then push: CI
  publishes that version by itself once every check has passed. Run workflow / `v*` tags still work.
