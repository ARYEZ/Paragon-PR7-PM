"""Screenshots of the real PR7-PM window on a made-up database (every entry is invented):
QT_SCALE_FACTOR=2 python tools/screenshots.py OUT_DIR"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
data = tempfile.mkdtemp()
os.environ["PR7PM_DATA"] = data
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())

from pr7pm import settings, theme, vault  # noqa: E402
from pr7pm.main_window import GeneratorDialog, MainWindow  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots")
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
theme.load_fonts()

folder = Path(data) / "Vault"
folder.mkdir()
path = str(folder / "Personal.kdbx")
v = vault.Vault.create(path, "correct horse battery staple")
groups = {g.name: g for g in v.children(v.root)}
ENTRIES = {
    "Email": [("Proton Mail", "me@proton.me", "https://account.proton.me", ["email", "2fa"],
               "Recovery phrase is in the paper envelope. Backup codes attached (backup-codes.txt).",
               "otpauth://totp/Proton:me?secret=JBSWY3DPEHPK3PXP"),
              ("Gmail (old)", "paragon.prod@gmail.com", "https://accounts.google.com", [], "", ""),
              ("Fastmail", "me@fastmail.com", "https://app.fastmail.com", [], "", ""),
              ("Outlook", "paragon.music@outlook.com", "https://login.live.com", [], "", ""),
              ("Tuta", "elseworld@tuta.io", "https://app.tuta.com", [], "", ""),
              ("Domain mail (Zoho)", "studio@paragon-productions.example", "https://mail.zoho.com", [], "", "")],
    "Banking": [("Bank", "me", "https://bank.example", [], "", "")] * 5,
    "Shopping": [("Shop", "me", "https://shop.example", [], "", "")] * 9,
    "Social": [("Social", "me", "https://social.example", [], "", "")] * 7,
    "Work": [("Work", "me", "https://work.example", [], "", "")] * 11,
    "Wi-Fi": [("Wi-Fi", "", "", [], "", "")] * 4,
}
for g, entries in ENTRIES.items():
    for n, (title, user, url, tags, notes, otp) in enumerate(entries):
        v.add_entry(groups[g], title if len(entries) < 5 or g == "Email" else f"{title} {n + 1}", user,
                    "v7#Kq2!mWz@R8pL$e4Tn", url=url, notes=notes, tags=tags, otp=otp)
for title in ("Old router", "Old forum"):
    v.delete_entry(v.add_entry(groups["Wi-Fi"], title, "x", "x"))
v.save()
settings.set("recent", [path, str(folder / "Studio.kdbx"), str(Path(data) / "Documents" / "Family.kdbx")])
settings.set("open_last", True)

w = MainWindow()
w.answers.update({"say": lambda k, t: None, "menu": lambda *a: None})
w.resize(1180, 720)
w.show()
app.processEvents()


def shot(widget, name):
    app.processEvents()
    widget.grab().save(str(out / name))
    print(out / name)


w.master.setText("correct horse battery staple")
shot(w, "unlock.png")
w.unlock()
w.tree.setCurrentItem(w.tree.topLevelItem(0).child(0))       # Email
w.table.selectRow(next(i for i, r in enumerate(w.model.rows) if r.title == "Proton Mail"))
w.copy_password()
w.clip.timer.stop()
w._copied_left(9)
shot(w, "database.png")
theme.set_finish("aurora")
d = GeneratorDialog(w)
d.restyle = None
from pr7pm.main_window import stylesheet  # noqa: E402
app.setPalette(theme.palette())
d.setStyleSheet(stylesheet())
d.show()
shot(d, "generator_aurora.png")
d.reject()
theme.set_finish("obsidian")
app.clipboard().clear()          # PySide's offscreen clipboard crashes at exit while it holds data
w.close()
