"""Mock-up pictures of PR7-PM, drawn offscreen with real Qt widgets: QT_SCALE_FACTOR=2 python tools/mockup.py OUT
Every name, user name and password here is made up."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSize, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QPainter  # noqa: E402
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QFrame, QGridLayout, QHBoxLayout,  # noqa
                               QHeaderView, QLabel, QLineEdit, QProgressBar, QPushButton, QSlider, QTableWidget,
                               QTableWidgetItem, QTabBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from pr7pm import theme, widgets  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/mockup")
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
theme.load_fonts()
MONO = QFont("Consolas"); MONO.setStyleHint(QFont.StyleHint.Monospace); MONO.setPixelSize(15)

GROUPS = [("Personal", "safe", 0, 42), ("Email", "mail", 1, 6), ("Banking", "bank", 1, 5), ("Shopping", "cart", 1, 9),
          ("Social", "people", 1, 7), ("Work", "briefcase", 1, 11), ("Wi-Fi", "wifi", 1, 4), ("Recycle Bin", "trash", 1, 2)]
ENTRIES = [
    ("Proton Mail", "me@proton.me", "https://account.proton.me", "2026-11-24", "mail"),
    ("Gmail (old)", "paragon.prod@gmail.com", "https://accounts.google.com", "2026-09-02", "mail"),
    ("Fastmail", "me@fastmail.com", "https://app.fastmail.com", "2026-06-18", "mail"),
    ("Outlook", "paragon.music@outlook.com", "https://login.live.com", "2026-03-11", "mail"),
    ("Tuta", "elseworld@tuta.io", "https://app.tuta.com", "2025-12-30", "mail"),
    ("Domain mail (Zoho)", "studio@paragon-productions.example", "https://mail.zoho.com", "2025-10-07", "mail"),
]


def base(w: QWidget, finish: str, extra=""):
    theme.set_finish(finish)
    extra = extra() if callable(extra) else extra          # colours read after the finish is set
    app.setPalette(theme.palette())
    w.setPalette(theme.palette()); w.setAutoFillBackground(True)
    w.setStyleSheet(theme.stylesheet() + f"""
QTableWidget::item:selected, QTreeWidget::item:selected {{ background: {theme.ACCENT_DIM}; color: #FFFFFF; }}
QTableWidget {{ alternate-background-color: {theme.ALT_ROW}; }}
QLabel#key {{ color: {theme.TEXT_DIM}; font-size: 11px; font-weight: 600; letter-spacing: 1px; }}
QLabel#value {{ font-size: 14px; }}
QPushButton[kind="primary"] {{ background: {theme.qss_gradient()}; color: #FFFFFF; border: none; border-radius: 4px;
    padding: 10px 26px; font-weight: 600; }}
QLabel#note {{ color: {theme.TEXT_DIM}; }}
""" + extra)


def key(icon, tip):
    return widgets.SmallKey(icon, tip)


# ---------------------------------------------------------------- 1. unlock
def unlock():
    w = QWidget(); w.resize(1180, 720)
    base(w, "obsidian", "QLineEdit#pw { font-size: 16px; padding: 9px 12px; }")
    v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)
    v.addWidget(widgets.Header("PASSWORDS"))
    body = QHBoxLayout(); body.setContentsMargins(0, 0, 0, 0); v.addLayout(body, 1)
    recent = QVBoxLayout(); recent.setContentsMargins(24, 24, 24, 24); recent.setSpacing(10)
    side = QFrame(); side.setObjectName("side"); side.setLayout(recent); side.setFixedWidth(300)
    side.setStyleSheet(f"QFrame#side {{ background: {theme.PANEL}; border-right: 1px solid {theme.PANEL_EDGE}; }}")
    t = QLabel("RECENT DATABASES"); t.setObjectName("key"); recent.addWidget(t)
    for name, where, on in (("Personal.kdbx", "D:\\Sync\\Vault", True), ("Studio.kdbx", "D:\\Sync\\Vault", False),
                            ("Family.kdbx", "C:\\Users\\me\\Documents", False)):
        row = QLabel(f"<b>{name}</b><br><span style='color:{theme.TEXT_DIM}'>{where}</span>")
        row.setStyleSheet(f"padding: 8px 10px; border-radius: 4px; background: {theme.ACCENT_DIM if on else 'transparent'};")
        recent.addWidget(row)
    recent.addStretch(1)
    for label in ("NEW DATABASE", "OPEN DATABASE", "IMPORT"):
        b = QPushButton(label); recent.addWidget(b)
    body.addWidget(side)
    centre = QVBoxLayout(); centre.setContentsMargins(90, 70, 90, 40); centre.setSpacing(12)
    lock = QLabel(); pm = widgets.file_pixmap("lock", 54) if False else None
    icon = QLabel(); icon.setFixedSize(56, 56)
    pix = __import__("PySide6.QtGui", fromlist=["QPixmap"]).QPixmap(112, 112); pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    from PySide6.QtCore import QRectF
    widgets.draw_icon(p, "lock", QRectF(0, 0, 112, 112), QColor(theme.ACCENT), 1.6); p.end()
    pix.setDevicePixelRatio(2); icon.setPixmap(pix)
    centre.addWidget(icon)
    h = QLabel("UNLOCK PERSONAL.KDBX"); h.setStyleSheet("font-size: 22px; font-weight: 600;"); centre.addWidget(h)
    sub = QLabel("D:\\Sync\\Vault\\Personal.kdbx  ·  KDBX 4  ·  AES-256, Argon2id"); sub.setObjectName("note")
    centre.addWidget(sub); centre.addSpacing(18)
    k = QLabel("PASSWORD"); k.setObjectName("key"); centre.addWidget(k)
    row = QHBoxLayout()
    pw = QLineEdit("correct horse battery staple"); pw.setObjectName("pw"); pw.setEchoMode(QLineEdit.EchoMode.Password)
    row.addWidget(pw, 1); row.addWidget(key("eye", "Show the password")); centre.addLayout(row)
    k = QLabel("KEY FILE  (OPTIONAL)"); k.setObjectName("key"); centre.addSpacing(6); centre.addWidget(k)
    row = QHBoxLayout(); kf = QLineEdit(); kf.setPlaceholderText("None"); row.addWidget(kf, 1)
    row.addWidget(QPushButton("BROWSE")); centre.addLayout(row)
    centre.addSpacing(14)
    row = QHBoxLayout(); go = QPushButton("UNLOCK"); go.setProperty("kind", "primary"); row.addWidget(go)
    caps = QLabel("Caps Lock is on"); caps.setStyleSheet(f"color: {theme.LED_ORANGE};"); row.addSpacing(14)
    row.addWidget(caps); row.addStretch(1); centre.addLayout(row)
    centre.addStretch(1)
    n = QLabel("Your passwords stay in this file, encrypted on your computer. PR7-PM sends nothing anywhere.\n"
               "The same file opens in KeePassXC, KeePass and KeePassDX / Strongbox on your phone.")
    n.setObjectName("note"); centre.addWidget(n)
    body.addLayout(centre, 1)
    return w


# ---------------------------------------------------------------- 2. the database
def database():
    w = QWidget(); w.resize(1180, 720)
    base(w, "obsidian", "QLineEdit#search { padding: 7px 12px; }")
    v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)
    v.addWidget(widgets.Header("PASSWORDS"))
    bar = QHBoxLayout(); bar.setContentsMargins(14, 10, 14, 10); bar.setSpacing(4)
    for icon, tip in (("add", "New entry (Ctrl+N)"), ("edit", "Edit entry (Ctrl+E)"), ("trash", "Delete entry (Del)"),
                      (None, None), ("user", "Copy user name (Ctrl+B)"), ("key", "Copy password (Ctrl+C)"),
                      ("link", "Open the URL (Ctrl+Shift+U)"), (None, None), ("dice", "Password generator (Ctrl+G)"),
                      ("lock", "Lock the database (Ctrl+L)")):
        if icon is None:
            bar.addSpacing(14)
        else:
            bar.addWidget(key(icon, tip))
    bar.addStretch(1)
    s = QLineEdit(); s.setObjectName("search"); s.setPlaceholderText("Search (Ctrl+F)"); s.setFixedWidth(340)
    bar.addWidget(s)
    v.addLayout(bar)
    split = QHBoxLayout(); split.setContentsMargins(0, 0, 0, 0); split.setSpacing(0); v.addLayout(split, 1)
    tree = QTreeWidget(); tree.setHeaderHidden(True); tree.setFixedWidth(230); tree.setIndentation(16)
    tree.setIconSize(QSize(18, 18)); tree.setFrameShape(QFrame.Shape.NoFrame)
    tree.setStyleSheet(f"QTreeWidget {{ background: {theme.PANEL}; border-right: 1px solid {theme.PANEL_EDGE}; padding: 6px; }}"
                       " QTreeWidget::item { padding: 5px 2px; }")
    root = None
    for name, icon, depth, n in GROUPS:
        it = QTreeWidgetItem([f"{name}   {n}" if depth else name])
        it.setIcon(0, widgets.line_icon(icon, theme.ACCENT if icon in ("safe", "trash") else theme.LED_ORANGE))
        if depth == 0:
            tree.addTopLevelItem(it); root = it
        else:
            root.addChild(it)
            if name == "Email":
                tree.setCurrentItem(it)
    tree.expandAll()
    split.addWidget(tree)
    right = QVBoxLayout(); right.setSpacing(0); split.addLayout(right, 1)
    t = QTableWidget(len(ENTRIES), 4); t.setHorizontalHeaderLabels(["TITLE", "USER NAME", "URL", "MODIFIED"])
    t.verticalHeader().hide(); t.setShowGrid(False); t.setAlternatingRowColors(True); t.setFrameShape(QFrame.Shape.NoFrame)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); t.verticalHeader().setDefaultSectionSize(30)
    t.setIconSize(QSize(18, 18))
    for r, (title, user, url, mod, icon) in enumerate(ENTRIES):
        it = QTableWidgetItem(title); it.setIcon(widgets.line_icon("key", theme.TEXT_DIM)); t.setItem(r, 0, it)
        t.setItem(r, 1, QTableWidgetItem(user)); t.setItem(r, 2, QTableWidgetItem(url)); t.setItem(r, 3, QTableWidgetItem(mod))
    h = t.horizontalHeader()
    for c, cw in ((0, 210), (1, 270), (3, 110)):
        h.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed); t.setColumnWidth(c, cw)
    h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
    t.selectRow(0)
    right.addWidget(t, 1)
    pre = QFrame(); pre.setStyleSheet(f"QFrame#pre {{ background: {theme.PANEL}; border-top: 1px solid {theme.PANEL_EDGE}; }}")
    pre.setObjectName("pre")
    g = QGridLayout(pre); g.setContentsMargins(22, 16, 22, 16); g.setHorizontalSpacing(18); g.setVerticalSpacing(9)
    title = QLabel("PROTON MAIL"); title.setStyleSheet("font-size: 17px; font-weight: 600;")
    g.addWidget(title, 0, 0, 1, 4)

    def field(r, c, k, val, mono=False, keys=()):
        kl = QLabel(k); kl.setObjectName("key"); g.addWidget(kl, r, c)
        row = QHBoxLayout(); row.setSpacing(4)
        vl = QLabel(val); vl.setObjectName("value")
        if mono:
            vl.setFont(MONO)
        row.addWidget(vl); row.addStretch(1)
        for icon, tip in keys:
            row.addWidget(key(icon, tip))
        g.addLayout(row, r, c + 1)
    field(1, 0, "USER NAME", "me@proton.me", keys=(("copy", "Copy"),))
    field(2, 0, "PASSWORD", "••••••••••••••••••••", keys=(("eye", "Show"), ("copy", "Copy")))
    field(3, 0, "URL", "https://account.proton.me", keys=(("link", "Open"),))
    field(1, 2, "ONE-TIME CODE", "481 927   ·  19 s", mono=True, keys=(("copy", "Copy"),))
    field(2, 2, "EXPIRES", "Never")
    field(3, 2, "TAGS", "email · 2fa")
    nl = QLabel("NOTES"); nl.setObjectName("key"); g.addWidget(nl, 4, 0)
    nv = QLabel("Recovery phrase is in the paper envelope. Backup codes attached (backup-codes.txt)."); g.addWidget(nv, 4, 1, 1, 3)
    g.setColumnStretch(1, 1); g.setColumnStretch(3, 1)
    right.addWidget(pre)
    status = QHBoxLayout(); status.setContentsMargins(14, 7, 14, 7)
    s1 = QLabel("Email  ·  6 entries  ·  42 in the database"); s1.setObjectName("note"); status.addWidget(s1)
    status.addStretch(1)
    s2 = QLabel("PASSWORD COPIED  ·  CLEARED IN 9 S  ·  KEPT OUT OF CLIPBOARD HISTORY")
    s2.setStyleSheet(f"color: {theme.LED_ORANGE}; font-size: 11px; font-weight: 600; letter-spacing: 1px;")
    status.addWidget(s2)
    v.addLayout(status)
    return w


# ---------------------------------------------------------------- 3. the generator (AURORA)
def generator():
    w = QWidget(); w.resize(640, 600)
    base(w, "aurora", lambda: f"QLabel#pw {{ font-size: 22px; padding: 14px; background: {theme.WIDGET}; "
                              f"border: 1px solid {theme.PANEL_EDGE}; border-radius: 4px; color: {theme.TEXT}; }}")
    v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)
    v.addWidget(widgets.Header("GENERATOR"))
    b = QVBoxLayout(); b.setContentsMargins(26, 18, 26, 22); b.setSpacing(12); v.addLayout(b, 1)
    tabs = QTabBar(); tabs.addTab("PASSWORD"); tabs.addTab("PASSPHRASE"); tabs.setExpanding(False); b.addWidget(tabs)
    row = QHBoxLayout()
    pw = QLabel("v7#Kq2!mWz@R8pL$e4Tn"); pw.setObjectName("pw"); pw.setFont(MONO)
    f = pw.font(); f.setPixelSize(22); pw.setFont(f)
    row.addWidget(pw, 1); row.addWidget(key("dice", "Another (Space)")); row.addWidget(key("copy", "Copy (Ctrl+C)"))
    b.addLayout(row)
    meter = QProgressBar(); meter.setRange(0, 100); meter.setValue(92); meter.setTextVisible(False); meter.setFixedHeight(6)
    meter.setStyleSheet(f"QProgressBar {{ background: {theme.PANEL_EDGE}; border: none; border-radius: 3px; }}"
                        f"QProgressBar::chunk {{ background: {theme.qss_gradient()}; border-radius: 3px; }}")
    b.addWidget(meter)
    q = QLabel("EXCELLENT  ·  129 BITS"); q.setObjectName("key"); b.addWidget(q)
    b.addSpacing(6)
    row = QHBoxLayout(); k = QLabel("LENGTH"); k.setObjectName("key"); k.setFixedWidth(80); row.addWidget(k)
    sl = QSlider(Qt.Orientation.Horizontal); sl.setRange(8, 64); sl.setValue(20); row.addWidget(sl, 1)
    n = QLabel("20"); n.setFixedWidth(30); row.addWidget(n); b.addLayout(row)
    k = QLabel("CHARACTERS"); k.setObjectName("key"); b.addWidget(k)
    grid = QGridLayout(); grid.setHorizontalSpacing(24)
    for i, (t, on) in enumerate((("A-Z  upper case", True), ("a-z  lower case", True), ("0-9  numbers", True),
                                 ("!@#$%  symbols", True), ("Extended ASCII", False), ("Spaces", False))):
        c = QCheckBox(t); c.setChecked(on); grid.addWidget(c, i // 3, i % 3)
    b.addLayout(grid)
    c = QCheckBox("Leave out look-alike characters  (l 1 I | O 0)"); c.setChecked(True); b.addWidget(c)
    c = QCheckBox("Use every kind ticked at least once"); c.setChecked(True); b.addWidget(c)
    row = QHBoxLayout(); k = QLabel("ALSO LEAVE OUT"); k.setObjectName("key"); k.setFixedWidth(120); row.addWidget(k)
    row.addWidget(QLineEdit("`~\"'"), 1); b.addLayout(row)
    b.addStretch(1)
    row = QHBoxLayout(); row.addStretch(1)
    use = QPushButton("USE THIS PASSWORD"); use.setProperty("kind", "primary"); row.addWidget(use)
    row.addWidget(QPushButton("CLOSE")); b.addLayout(row)
    return w


for name, make in (("1_unlock.png", unlock), ("2_database.png", database), ("3_generator_aurora.png", generator)):
    win = make()
    win.show(); app.processEvents()
    win.grab().save(str(out / name))
    print(out / name)
