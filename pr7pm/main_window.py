"""PR7-PM's window, the way KeePassXC's works: an unlock page, then the database (groups, entries, the selected entry)
with KeePassXC's keys. Every change is saved at once (KeePassXC's default). It locks after a few idle minutes and when
Windows locks; locking forgets the open database and empties the clipboard of anything PR7-PM put there.

Every question goes through `_ask(kind, ...)`: tests answer them with `window.answers[kind]`."""

from __future__ import annotations

import datetime
import os
import sys
import time

from PySide6.QtCore import QAbstractTableModel, QDateTime, QEvent, QModelIndex, QObject, QRectF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDateTimeEdit, QDialog,
                               QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSlider,
                               QSpinBox, QStackedWidget, QTableView, QTabBar, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from . import __version__, generator, settings, shell, theme, vault, widgets
from .clipboard import SecretClipboard

DEFAULTS = {"lock_minutes": 5, "lock_on_session": True, "lock_on_minimize": False, "clear_seconds": 10,
            "open_last": True}
COLUMNS = ["TITLE", "USER NAME", "URL", "MODIFIED"]


def option(key: str):
    d = DEFAULTS[key]
    if isinstance(d, bool):
        return settings.get_bool(key, d)
    return settings.get_int(key, d)


def mono(px: int = 15) -> QFont:
    """Revealed and generated passwords: monospaced, so l / 1 / I and O / 0 can be told apart (KeePassXC does this)."""
    f = QFont("Consolas")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setFamilies(["Consolas", "Cascadia Mono", "DejaVu Sans Mono", "monospace"])
    f.setPixelSize(px)
    return f


def stylesheet() -> str:
    return theme.stylesheet() + f"""
QTableView::item:selected, QTreeWidget::item:selected {{ background: {theme.ACCENT_DIM}; color: #FFFFFF; }}
QTableView {{ alternate-background-color: {theme.ALT_ROW}; }}
QLabel#key {{ color: {theme.TEXT_DIM}; font-size: 11px; font-weight: 600; letter-spacing: 1px; }}
QLabel#value {{ font-size: 14px; }}
QLabel#note {{ color: {theme.TEXT_DIM}; }}
QLabel#heading {{ font-size: 22px; font-weight: 600; }}
QLabel#title {{ font-size: 17px; font-weight: 600; }}
QLabel#copied {{ color: {theme.LED_ORANGE}; font-size: 11px; font-weight: 600; letter-spacing: 1px; }}
QLabel#caps {{ color: {theme.LED_ORANGE}; }}
QLabel#error {{ color: {theme.ACCENT}; }}
QLineEdit#pw {{ font-size: 16px; padding: 9px 12px; }}
QLineEdit#search {{ padding: 7px 12px; }}
QLabel#generated {{ font-size: 22px; padding: 14px; background: {theme.WIDGET}; border: 1px solid {theme.PANEL_EDGE};
    border-radius: 4px; color: {theme.TEXT}; }}
QPushButton[kind="primary"] {{ background: {theme.qss_gradient()}; color: #FFFFFF; border: none; border-radius: 4px;
    padding: 10px 26px; font-weight: 600; }}
QFrame#side {{ background: {theme.PANEL}; border-right: 1px solid {theme.PANEL_EDGE}; }}
QFrame#preview {{ background: {theme.PANEL}; border-top: 1px solid {theme.PANEL_EDGE}; }}
QTreeWidget#groups {{ background: {theme.PANEL}; border: none; border-right: 1px solid {theme.PANEL_EDGE}; padding: 6px; }}
QTreeWidget#groups::item {{ padding: 5px 2px; }}
QProgressBar#meter {{ background: {theme.PANEL_EDGE}; border: none; border-radius: 3px; }}
QProgressBar#meter::chunk {{ background: {theme.qss_gradient()}; border-radius: 3px; }}
"""


def icon_label(name: str, size: int = 56, colour: str | None = None) -> QLabel:
    lab = QLabel()
    lab.setFixedSize(size, size)
    pix = QPixmap(size * 2, size * 2)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    widgets.draw_icon(p, name, QRectF(0, 0, size * 2, size * 2), QColor(colour or theme.ACCENT), 1.6)
    p.end()
    pix.setDevicePixelRatio(2)
    lab.setPixmap(pix)
    return lab


def caps_lock_on() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetKeyState(0x14) & 1)
    except Exception:  # noqa: BLE001
        return False


def key(icon: str, tip: str, slot=None) -> widgets.SmallKey:
    k = widgets.SmallKey(icon, tip)
    if slot is not None:
        k.clicked.connect(slot)
    return k


def keyed(label: str) -> QLabel:
    lab = QLabel(label)
    lab.setObjectName("key")
    return lab


# ======================================================================== models
class EntryModel(QAbstractTableModel):
    """The entries shown: a plain Python list (never QStandardItemModel: its item ownership crashed PySide in PR7-Z)."""

    def __init__(self):
        super().__init__()
        self.rows: list[vault.Row] = []
        self._icon = None

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r = self.rows[index.row()]
        c = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return [r.title, r.username, r.url,
                    time.strftime("%Y-%m-%d", time.localtime(r.modified)) if r.modified else ""][c]
        if role == Qt.ItemDataRole.DecorationRole and c == 0:
            if self._icon is None:
                self._icon = widgets.line_icon("key", theme.TEXT_DIM)
            return self._icon
        if role == Qt.ItemDataRole.FontRole and r.expired:
            f = QFont()
            f.setStrikeOut(True)                       # KeePassXC strikes expired entries through
            return f
        if role == Qt.ItemDataRole.ToolTipRole and r.expired:
            return "Expired"
        return None


# ======================================================================== dialogs
class NewDatabaseDialog(QDialog):
    """The master key for a new database (or a changed one): the password twice, a key file if wanted."""

    def __init__(self, parent=None, title: str = "NEW DATABASE"):
        super().__init__(parent)
        self.setWindowTitle("Paragon PR7-PM")
        self.resize(560, 360)
        v = QVBoxLayout(self)
        v.setContentsMargins(26, 22, 26, 22)
        v.setSpacing(10)
        h = QLabel(title)
        h.setObjectName("title")
        v.addWidget(h)
        v.addWidget(keyed("PASSWORD"))
        row = QHBoxLayout()
        self.pw = QLineEdit()
        self.pw.setObjectName("pw")
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        row.addWidget(self.pw, 1)
        row.addWidget(key("dice", "Generate a passphrase", self._generate))
        row.addWidget(key("eye", "Show", self._toggle))
        v.addLayout(row)
        v.addWidget(keyed("AGAIN"))
        self.again = QLineEdit()
        self.again.setObjectName("pw")
        self.again.setEchoMode(QLineEdit.EchoMode.Password)
        v.addWidget(self.again)
        self.meter = QProgressBar()
        self.meter.setObjectName("meter")
        self.meter.setRange(0, 128)
        self.meter.setTextVisible(False)
        self.meter.setFixedHeight(6)
        v.addWidget(self.meter)
        self.quality = keyed("")
        v.addWidget(self.quality)
        v.addWidget(keyed("KEY FILE  (OPTIONAL)"))
        row = QHBoxLayout()
        self.keyfile = QLineEdit()
        self.keyfile.setPlaceholderText("None")
        row.addWidget(self.keyfile, 1)
        b = QPushButton("BROWSE")
        b.clicked.connect(self._browse)
        row.addWidget(b)
        v.addLayout(row)
        self.error = QLabel("")
        self.error.setObjectName("error")
        v.addWidget(self.error)
        v.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("OK")
        ok.setProperty("kind", "primary")
        ok.clicked.connect(self._ok)
        cancel = QPushButton("CANCEL")
        cancel.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        v.addLayout(row)
        self.pw.textChanged.connect(self._strength)
        self._strength()

    def _toggle(self):
        mode = QLineEdit.EchoMode.Normal if self.pw.echoMode() == QLineEdit.EchoMode.Password else \
            QLineEdit.EchoMode.Password
        self.pw.setEchoMode(mode)
        self.again.setEchoMode(mode)

    def _generate(self):
        p = generator.passphrase(generator.PhraseOptions(words=6))
        self.pw.setText(p)
        self.again.setText(p)
        self.pw.setEchoMode(QLineEdit.EchoMode.Normal)
        self.again.setEchoMode(QLineEdit.EchoMode.Normal)

    def _browse(self):
        f, _ = QFileDialog.getOpenFileName(self, "Key file", "", "All files (*)")
        if f:
            self.keyfile.setText(f)

    def _strength(self):
        b = generator.estimate(self.pw.text())
        self.meter.setValue(int(min(128, b)))
        self.quality.setText(f"{generator.quality(b).upper()}  ·  {int(b)} BITS" if self.pw.text() else "")

    def problem(self) -> str:
        if self.pw.text() != self.again.text():
            return "The two passwords aren't the same."
        if not self.pw.text() and not self.keyfile.text():
            return "Give a password, a key file, or both."
        if self.keyfile.text() and not os.path.isfile(self.keyfile.text()):
            return "That key file doesn't exist."
        return ""

    def _ok(self):
        p = self.problem()
        self.error.setText(p)
        if not p:
            self.accept()


class GeneratorDialog(QDialog):
    """KeePassXC's password generator: a password or a passphrase, how strong it is, Use this password."""

    def __init__(self, parent=None, use: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Paragon PR7-PM")
        self.resize(640, 600)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.header = widgets.Header("GENERATOR")
        v.addWidget(self.header)
        b = QVBoxLayout()
        b.setContentsMargins(26, 18, 26, 22)
        b.setSpacing(12)
        v.addLayout(b, 1)
        self.tabs = QTabBar()
        self.tabs.addTab("PASSWORD")
        self.tabs.addTab("PASSPHRASE")
        self.tabs.setExpanding(False)
        self.tabs.setCurrentIndex(settings.get_int("gen_tab", 0))
        b.addWidget(self.tabs)
        row = QHBoxLayout()
        self.out = QLabel()
        self.out.setObjectName("generated")
        self.out.setFont(mono(22))
        self.out.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.out, 1)
        row.addWidget(key("dice", "Another (Space)", self.regenerate))
        row.addWidget(key("copy", "Copy (Ctrl+C)", self.copy))
        b.addLayout(row)
        self.meter = QProgressBar()
        self.meter.setObjectName("meter")
        self.meter.setRange(0, 128)
        self.meter.setTextVisible(False)
        self.meter.setFixedHeight(6)
        b.addWidget(self.meter)
        self.quality = keyed("")
        b.addWidget(self.quality)
        b.addSpacing(6)
        self.pages = QStackedWidget()
        b.addWidget(self.pages)
        # the password page
        pw = QWidget()
        pv = QVBoxLayout(pw)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(10)
        row = QHBoxLayout()
        k = keyed("LENGTH")
        k.setFixedWidth(90)
        row.addWidget(k)
        self.length = QSlider(Qt.Orientation.Horizontal)
        self.length.setRange(8, 64)
        self.length.setValue(settings.get_int("gen_length", 20))
        row.addWidget(self.length, 1)
        self.length_n = QLabel()
        self.length_n.setFixedWidth(30)
        row.addWidget(self.length_n)
        pv.addLayout(row)
        pv.addWidget(keyed("CHARACTERS"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        chosen = settings.get_list("gen_classes") or ["upper", "lower", "digits", "symbols"]
        self.classes = {}
        for i, (c, t) in enumerate((("upper", "A-Z  upper case"), ("lower", "a-z  lower case"),
                                    ("digits", "0-9  numbers"), ("symbols", "!@#$%  symbols"),
                                    ("extended", "Extended ASCII"), ("space", "Spaces"))):
            box = QCheckBox(t)
            box.setChecked(c in chosen)
            self.classes[c] = box
            grid.addWidget(box, i // 3, i % 3)
        pv.addLayout(grid)
        self.no_look = QCheckBox("Leave out look-alike characters  (l 1 I | O 0)")
        self.no_look.setChecked(settings.get_bool("gen_no_look", True))
        pv.addWidget(self.no_look)
        self.every = QCheckBox("Use every kind ticked at least once")
        self.every.setChecked(settings.get_bool("gen_every", True))
        pv.addWidget(self.every)
        row = QHBoxLayout()
        k = keyed("ALSO LEAVE OUT")
        k.setFixedWidth(130)
        row.addWidget(k)
        self.exclude = QLineEdit(settings.get("gen_exclude", ""))
        row.addWidget(self.exclude, 1)
        pv.addLayout(row)
        pv.addStretch(1)
        self.pages.addWidget(pw)
        # the passphrase page
        ph = QWidget()
        hv = QVBoxLayout(ph)
        hv.setContentsMargins(0, 0, 0, 0)
        hv.setSpacing(10)
        row = QHBoxLayout()
        k = keyed("WORDS")
        k.setFixedWidth(90)
        row.addWidget(k)
        self.words = QSlider(Qt.Orientation.Horizontal)
        self.words.setRange(3, 12)
        self.words.setValue(settings.get_int("gen_words", 6))
        row.addWidget(self.words, 1)
        self.words_n = QLabel()
        self.words_n.setFixedWidth(30)
        row.addWidget(self.words_n)
        hv.addLayout(row)
        row = QHBoxLayout()
        k = keyed("BETWEEN WORDS")
        k.setFixedWidth(130)
        row.addWidget(k)
        self.sep = QLineEdit(settings.get("gen_sep", "-"))
        self.sep.setFixedWidth(60)
        row.addWidget(self.sep)
        row.addStretch(1)
        hv.addLayout(row)
        self.caps = QCheckBox("Capital first letters")
        self.caps.setChecked(settings.get_bool("gen_caps", True))
        hv.addWidget(self.caps)
        note = QLabel("Words from the EFF's long list (7,772 words): each adds about 12.9 bits.")
        note.setObjectName("note")
        hv.addWidget(note)
        hv.addStretch(1)
        self.pages.addWidget(ph)
        row = QHBoxLayout()
        row.addStretch(1)
        self.use = QPushButton("USE THIS PASSWORD")
        self.use.setProperty("kind", "primary")
        self.use.clicked.connect(self.accept)
        self.use.setVisible(use)
        row.addWidget(self.use)
        close = QPushButton("CLOSE")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        b.addLayout(row)
        for w in (self.length, self.words):
            w.valueChanged.connect(self.regenerate)
        for w in list(self.classes.values()) + [self.no_look, self.every, self.caps]:
            w.toggled.connect(self.regenerate)
        for w in (self.exclude, self.sep):
            w.textChanged.connect(self.regenerate)
        self.tabs.currentChanged.connect(self.regenerate)
        self.copied = None
        self.value = ""
        self.regenerate()

    def options(self) -> generator.Options:
        return generator.Options(self.length.value(), tuple(c for c, b in self.classes.items() if b.isChecked()),
                                 self.no_look.isChecked(), self.every.isChecked(), self.exclude.text())

    def phrase_options(self) -> generator.PhraseOptions:
        return generator.PhraseOptions(self.words.value(), self.sep.text(), self.caps.isChecked())

    def regenerate(self, *_):
        self.pages.setCurrentIndex(self.tabs.currentIndex())
        self.length_n.setText(str(self.length.value()))
        self.words_n.setText(str(self.words.value()))
        try:
            if self.tabs.currentIndex() == 0:
                self.value = generator.password(self.options())
                b = generator.bits(self.value, self.options())
            else:
                self.value = generator.passphrase(self.phrase_options())
                b = generator.phrase_bits(self.phrase_options())
        except ValueError as e:
            self.value, b = "", 0.0
            self.out.setText(str(e))
            self.use.setEnabled(False)
        else:
            self.out.setText(self.value)
            self.use.setEnabled(True)
        self.meter.setValue(int(min(128, b)))
        self.quality.setText(f"{generator.quality(b).upper()}  ·  {int(b)} BITS" if self.value else "")

    def copy(self):
        if self.value and self.copied is not None:
            self.copied(self.value)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Space:
            self.regenerate()
        elif e.matches(QKeySequence.StandardKey.Copy):
            self.copy()
        else:
            super().keyPressEvent(e)

    def done(self, r):
        settings.set("gen_tab", self.tabs.currentIndex())
        settings.set("gen_length", self.length.value())
        settings.set("gen_classes", [c for c, b in self.classes.items() if b.isChecked()])
        settings.set("gen_no_look", self.no_look.isChecked())
        settings.set("gen_every", self.every.isChecked())
        settings.set("gen_exclude", self.exclude.text())
        settings.set("gen_words", self.words.value())
        settings.set("gen_sep", self.sep.text())
        settings.set("gen_caps", self.caps.isChecked())
        super().done(r)


class EntryDialog(QDialog):
    """Add or edit an entry: KeePassXC's Entry page (title, user name, password, URL, tags, expiry, one-time code,
    notes) and its group."""

    def __init__(self, parent, v: vault.Vault, entry=None, group=None):
        super().__init__(parent)
        self.setWindowTitle("Paragon PR7-PM")
        self.resize(640, 640)
        self.vault = v
        g = QGridLayout(self)
        g.setContentsMargins(26, 22, 26, 22)
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(10)
        t = QLabel("EDIT ENTRY" if entry is not None else "NEW ENTRY")
        t.setObjectName("title")
        g.addWidget(t, 0, 0, 1, 2)
        self.title = QLineEdit(entry.title if entry is not None else "")
        self.username = QLineEdit(entry.username or "" if entry is not None else "")
        self.password = QLineEdit(entry.password or "" if entry is not None else "")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setFont(mono(14))
        self.url = QLineEdit(entry.url or "" if entry is not None else "")
        self.tags = QLineEdit(", ".join(entry.tags or []) if entry is not None else "")
        self.otp = QLineEdit(entry.otp or "" if entry is not None else "")
        self.otp.setPlaceholderText("otpauth://totp/...  or the secret key")
        self.notes = QPlainTextEdit(entry.notes or "" if entry is not None else "")
        self.group = QComboBox()
        self._groups = []

        def walk(gr, depth):
            if v.is_bin(gr):
                return
            self._groups.append(gr)
            self.group.addItem(("    " * depth) + gr.name, str(gr.uuid))
            for sub in v.children(gr):
                walk(sub, depth + 1)
        walk(v.root, 0)
        current = entry.group if entry is not None else (group or v.root)
        at = self.group.findData(str(current.uuid))
        self.group.setCurrentIndex(max(0, at))
        self.expires = QCheckBox("Expires")
        self.expiry = QDateTimeEdit()
        self.expiry.setCalendarPopup(True)
        self.expiry.setDisplayFormat("yyyy-MM-dd HH:mm")
        when = entry.expiry_time if entry is not None and entry.expires and entry.expiry_time else None
        self.expires.setChecked(when is not None)
        self.expiry.setDateTime(QDateTime.fromSecsSinceEpoch(int(when.timestamp())) if when is not None
                                else QDateTime.currentDateTime().addYears(1))
        self.expiry.setEnabled(when is not None)
        self.expires.toggled.connect(self.expiry.setEnabled)
        r = 1
        for label, w in (("TITLE", self.title), ("USER NAME", self.username)):
            g.addWidget(keyed(label), r, 0)
            g.addWidget(w, r, 1)
            r += 1
        g.addWidget(keyed("PASSWORD"), r, 0)
        row = QHBoxLayout()
        row.addWidget(self.password, 1)
        row.addWidget(key("eye", "Show", self._toggle))
        row.addWidget(key("dice", "Password generator (Ctrl+G)", self._generate))
        g.addLayout(row, r, 1)
        r += 1
        self.meter = QProgressBar()
        self.meter.setObjectName("meter")
        self.meter.setRange(0, 128)
        self.meter.setTextVisible(False)
        self.meter.setFixedHeight(5)
        g.addWidget(self.meter, r, 1)
        r += 1
        for label, w in (("URL", self.url), ("TAGS", self.tags), ("ONE-TIME CODE", self.otp), ("GROUP", self.group)):
            g.addWidget(keyed(label), r, 0)
            g.addWidget(w, r, 1)
            r += 1
        row = QHBoxLayout()
        row.addWidget(self.expires)
        row.addWidget(self.expiry, 1)
        g.addWidget(keyed("EXPIRY"), r, 0)
        g.addLayout(row, r, 1)
        r += 1
        g.addWidget(keyed("NOTES"), r, 0, Qt.AlignmentFlag.AlignTop)
        g.addWidget(self.notes, r, 1)
        g.setRowStretch(r, 1)
        r += 1
        self.error = QLabel("")
        self.error.setObjectName("error")
        g.addWidget(self.error, r, 1)
        r += 1
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("OK")
        ok.setProperty("kind", "primary")
        ok.clicked.connect(self._ok)
        cancel = QPushButton("CANCEL")
        cancel.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        g.addLayout(row, r, 0, 1, 2)
        self.password.textChanged.connect(lambda t: self.meter.setValue(int(min(128, generator.estimate(t)))))
        self.meter.setValue(int(min(128, generator.estimate(self.password.text()))))
        self.generate = None                       # tests: a function returning a generated password
        act = QAction(self)
        act.setShortcut(QKeySequence("Ctrl+G"))
        act.triggered.connect(self._generate)
        self.addAction(act)

    def _toggle(self):
        self.password.setEchoMode(QLineEdit.EchoMode.Normal if self.password.echoMode() == QLineEdit.EchoMode.Password
                                  else QLineEdit.EchoMode.Password)

    def _generate(self):
        if self.generate is not None:
            pw = self.generate()
        else:
            d = GeneratorDialog(self)
            d.setStyleSheet(stylesheet())
            pw = d.value if d.exec() == QDialog.DialogCode.Accepted else None
        if pw:
            self.password.setText(pw)

    def otp_uri(self) -> str:
        t = self.otp.text().strip()
        if t and not t.startswith("otpauth://"):
            t = f"otpauth://totp/{self.title.text().strip() or 'PR7-PM'}?secret={t.replace(' ', '').upper()}"
        return t

    def problem(self) -> str:
        if not self.title.text().strip():
            return "Give the entry a title."
        if self.otp_uri():
            try:
                vault.otp_now(self.otp_uri())
            except Exception:  # noqa: BLE001 - shown to the user
                return "The one-time code key isn't valid."
        return ""

    def _ok(self):
        p = self.problem()
        self.error.setText(p)
        if not p:
            self.accept()

    def fields(self) -> dict:
        exp = None
        if self.expires.isChecked():
            exp = datetime.datetime.fromtimestamp(self.expiry.dateTime().toSecsSinceEpoch(), datetime.timezone.utc)
        return {"title": self.title.text().strip(), "username": self.username.text(),
                "password": self.password.text(), "url": self.url.text().strip(),
                "notes": self.notes.toPlainText(), "otp": self.otp_uri(),
                "tags": [t.strip() for t in self.tags.text().replace(";", ",").split(",") if t.strip()],
                "expires": exp}

    def chosen_group(self):
        return self._groups[self.group.currentIndex()]


class OptionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paragon PR7-PM")
        self.resize(600, 520)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.header = widgets.Header("PASSWORDS")
        v.addWidget(self.header)
        b = QVBoxLayout()
        b.setContentsMargins(26, 18, 26, 22)
        b.setSpacing(12)
        v.addLayout(b, 1)
        b.addWidget(keyed("LOCK"))
        row = QHBoxLayout()
        self.lock_idle = QCheckBox("Lock after")
        self.lock_idle.setChecked(option("lock_minutes") > 0)
        self.minutes = QSpinBox()
        self.minutes.setRange(1, 240)
        self.minutes.setValue(option("lock_minutes") or 5)
        self.minutes.setSuffix(" minutes without use")
        row.addWidget(self.lock_idle)
        row.addWidget(self.minutes)
        row.addStretch(1)
        b.addLayout(row)
        self.lock_session = QCheckBox("Lock when Windows locks")
        self.lock_session.setChecked(option("lock_on_session"))
        b.addWidget(self.lock_session)
        self.lock_min = QCheckBox("Lock when the window is minimised")
        self.lock_min.setChecked(option("lock_on_minimize"))
        b.addWidget(self.lock_min)
        b.addWidget(keyed("CLIPBOARD"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Empty it"))
        self.clear = QSpinBox()
        self.clear.setRange(0, 300)
        self.clear.setValue(option("clear_seconds"))
        self.clear.setSuffix(" seconds after a copy  (0 = never)")
        row.addWidget(self.clear)
        row.addStretch(1)
        b.addLayout(row)
        n = QLabel("Copies are always marked private: PR7-CB, Ditto and Windows' clipboard history (Win+V) skip them.")
        n.setObjectName("note")
        n.setWordWrap(True)
        b.addWidget(n)
        b.addWidget(keyed("STARTING"))
        self.open_last = QCheckBox("Open the last database when PR7-PM starts")
        self.open_last.setChecked(option("open_last"))
        b.addWidget(self.open_last)
        self.updates = QCheckBox("Check for updates automatically")
        from . import update_ui
        self.updates.setChecked(update_ui.auto_enabled())
        b.addWidget(self.updates)
        row = QHBoxLayout()
        self.register = QPushButton("OPEN .KDBX FILES WITH PR7-PM")
        self.register.setEnabled(shell.available())
        self.register.clicked.connect(lambda: (shell.register(), shell.open_default_apps()))
        row.addWidget(self.register)
        row.addStretch(1)
        b.addLayout(row)
        b.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("OK")
        ok.setProperty("kind", "primary")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("CANCEL")
        cancel.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        b.addLayout(row)

    def save(self):
        settings.set("lock_minutes", self.minutes.value() if self.lock_idle.isChecked() else 0)
        settings.set("lock_on_session", self.lock_session.isChecked())
        settings.set("lock_on_minimize", self.lock_min.isChecked())
        settings.set("clear_seconds", self.clear.value())
        settings.set("open_last", self.open_last.isChecked())
        from . import update_ui
        update_ui.set_auto(self.updates.isChecked())


# ======================================================================== the window
class SearchBox(QLineEdit):
    """KeePassXC's search field: Escape clears it, Down / Enter go to the entries."""

    def __init__(self, window):
        super().__init__()
        self.window = window

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.window._escape()
        elif e.key() in (Qt.Key.Key_Down, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.window.table.setFocus()
            if self.window.model.rows and not self.window.current_entry_uuid():
                self.window.table.selectRow(0)
        else:
            super().keyPressEvent(e)


class EntryTable(QTableView):
    """The entry list takes KeePassXC's entry keys itself: Qt's table view would otherwise answer Ctrl+C by copying
    the cell's text (the title), before any shortcut sees the key."""

    def __init__(self, window):
        super().__init__()
        self.window = window

    def keyPressEvent(self, e):
        w = self.window
        mods = e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        ctrl = Qt.KeyboardModifier.ControlModifier
        acts = {(Qt.Key.Key_C, ctrl): w.copy_password, (Qt.Key.Key_B, ctrl): w.copy_username,
                (Qt.Key.Key_T, ctrl): w.copy_otp, (Qt.Key.Key_U, ctrl): w.copy_url,
                (Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier): w.delete_entry,
                (Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier): w.edit_entry,
                (Qt.Key.Key_Enter, Qt.KeyboardModifier.NoModifier): w.edit_entry}
        act = acts.get((e.key(), mods))
        if act is not None:
            act()
        else:
            super().keyPressEvent(e)


class _Activity(QObject):
    """Any key or mouse use anywhere in PR7-PM counts as activity for the idle lock."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def eventFilter(self, obj, e):
        if e.type() in (QEvent.Type.KeyPress, QEvent.Type.MouseButtonPress, QEvent.Type.Wheel):
            self.window.active()
        return False


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Paragon PR7-PM")
        self.resize(1180, 720)
        self.answers: dict = {}
        self.said: list = []
        self.vault: vault.Vault | None = None
        self.path = ""
        self.group_uuid = ""
        self.clip = SecretClipboard(option("clear_seconds"), self)
        self.clip.left.connect(self._copied_left)
        self.clip.cleared.connect(lambda: self.copied.setText(""))
        body = QWidget()
        self.setCentralWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.header = widgets.Header("PASSWORDS")
        v.addWidget(self.header)
        self.pages = QStackedWidget()
        v.addWidget(self.pages, 1)
        self.pages.addWidget(self._unlock_page())
        self.pages.addWidget(self._database_page())
        self.idle = QTimer(self)
        self.idle.setSingleShot(True)
        self.idle.timeout.connect(lambda: self.lock("idle"))
        self.otp_timer = QTimer(self)
        self.otp_timer.setInterval(1000)
        self.otp_timer.timeout.connect(self._otp_tick)
        QApplication.instance().installEventFilter(_Activity(self))
        self._session_note = False
        self.restyle()
        self._fill_recent()
        recent = settings.get_list("recent")
        if recent and option("open_last") and os.path.exists(recent[0]):
            self.show_unlock(recent[0])

    def restyle(self):
        QApplication.instance().setPalette(theme.palette())
        self.setStyleSheet(stylesheet())
        self.header.update()

    # ---------------------------------------------------------------- the unlock page
    def _unlock_page(self) -> QWidget:
        page = QWidget()
        body = QHBoxLayout(page)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        side = QFrame()
        side.setObjectName("side")
        side.setFixedWidth(300)
        s = QVBoxLayout(side)
        s.setContentsMargins(24, 24, 24, 24)
        s.setSpacing(10)
        s.addWidget(keyed("RECENT DATABASES"))
        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(4)
        s.addLayout(self.recent_box)
        s.addStretch(1)
        for label, slot in (("NEW DATABASE", self.new_database), ("OPEN DATABASE", self.open_database),
                            ("IMPORT", self.import_csv)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            s.addWidget(b)
        body.addWidget(side)
        centre = QVBoxLayout()
        centre.setContentsMargins(90, 70, 90, 40)
        centre.setSpacing(12)
        centre.addWidget(icon_label("lock"))
        self.unlock_title = QLabel("OPEN A DATABASE")
        self.unlock_title.setObjectName("heading")
        centre.addWidget(self.unlock_title)
        self.unlock_sub = QLabel("Choose one on the left, or make a new one.")
        self.unlock_sub.setObjectName("note")
        centre.addWidget(self.unlock_sub)
        centre.addSpacing(18)
        self.unlock_form = QWidget()
        f = QVBoxLayout(self.unlock_form)
        f.setContentsMargins(0, 0, 0, 0)
        f.setSpacing(12)
        f.addWidget(keyed("PASSWORD"))
        row = QHBoxLayout()
        self.master = QLineEdit()
        self.master.setObjectName("pw")
        self.master.setEchoMode(QLineEdit.EchoMode.Password)
        self.master.returnPressed.connect(self.unlock)
        self.master.textEdited.connect(lambda _: self._caps())
        row.addWidget(self.master, 1)
        row.addWidget(key("eye", "Show the password", lambda: self.master.setEchoMode(
            QLineEdit.EchoMode.Normal if self.master.echoMode() == QLineEdit.EchoMode.Password
            else QLineEdit.EchoMode.Password)))
        f.addLayout(row)
        f.addWidget(keyed("KEY FILE  (OPTIONAL)"))
        row = QHBoxLayout()
        self.keyfile = QLineEdit()
        self.keyfile.setPlaceholderText("None")
        row.addWidget(self.keyfile, 1)
        b = QPushButton("BROWSE")
        b.clicked.connect(self._browse_key)
        row.addWidget(b)
        f.addLayout(row)
        f.addSpacing(14)
        row = QHBoxLayout()
        self.unlock_button = QPushButton("UNLOCK")
        self.unlock_button.setProperty("kind", "primary")
        self.unlock_button.clicked.connect(self.unlock)
        row.addWidget(self.unlock_button)
        row.addSpacing(14)
        self.caps = QLabel("")
        self.caps.setObjectName("caps")
        row.addWidget(self.caps)
        self.unlock_error = QLabel("")
        self.unlock_error.setObjectName("error")
        row.addWidget(self.unlock_error)
        row.addStretch(1)
        f.addLayout(row)
        self.unlock_form.setVisible(False)
        centre.addWidget(self.unlock_form)
        centre.addStretch(1)
        n = QLabel("Your passwords stay in this file, encrypted on your computer. PR7-PM sends nothing anywhere.\n"
                   "The same file opens in KeePassXC, KeePass and KeePassDX / Strongbox on your phone.")
        n.setObjectName("note")
        centre.addWidget(n)
        body.addLayout(centre, 1)
        return page

    def _fill_recent(self):
        while self.recent_box.count():
            w = self.recent_box.takeAt(0).widget()
            if w is not None:
                w.hide()                               # gone now; deleteLater only frees it on the next loop
                w.setParent(None)
                w.deleteLater()
        for path in settings.get_list("recent")[:8]:
            b = QPushButton()
            b.setFlat(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            on = os.path.normcase(path) == os.path.normcase(self.path)
            b.setStyleSheet(f"QPushButton {{ text-align: left; padding: 8px 10px; border: none; border-radius: 4px;"
                            f" background: {theme.ACCENT_DIM if on else 'transparent'}; }}"
                            f"QPushButton:hover {{ background: {theme.ACCENT_DIM}; }}")
            lab = QLabel(f"<b>{os.path.basename(path)}</b><br><span style='color:{theme.TEXT_DIM}'>"
                         f"{os.path.dirname(path)}</span>")
            lab.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            inner = QVBoxLayout(b)
            inner.setContentsMargins(10, 6, 10, 6)
            inner.addWidget(lab)
            b.setMinimumHeight(56)
            b.clicked.connect(lambda _=False, p=path: self.show_unlock(p))
            self.recent_box.addWidget(b)

    def _remember(self, path: str):
        recent = [p for p in settings.get_list("recent") if os.path.normcase(p) != os.path.normcase(path)]
        settings.set("recent", [path] + recent[:7])
        self._fill_recent()

    def _caps(self):
        self.caps.setText("Caps Lock is on" if caps_lock_on() else "")

    def _browse_key(self):
        f = self._ask("open_key")
        if f:
            self.keyfile.setText(f)

    def show_unlock(self, path: str):
        """The unlock form for `path` (a recent database, an opened file, or the locked one)."""
        self.path = path
        self.unlock_title.setText(f"UNLOCK {os.path.basename(path).upper()}")
        self.unlock_sub.setText(path)
        self.unlock_form.setVisible(True)
        self.unlock_error.setText("")
        self.master.clear()
        self.master.setEchoMode(QLineEdit.EchoMode.Password)
        self.pages.setCurrentIndex(0)
        self._fill_recent()
        self.master.setFocus()
        self._caps()

    def unlock(self) -> bool:
        if not self.path:
            return False
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            v = vault.Vault.open(self.path, self.master.text(), self.keyfile.text().strip() or None)
        except vault.WrongKey:
            self.unlock_error.setText("Wrong password or key file.")
            self.master.selectAll()
            return False
        except Exception as e:  # noqa: BLE001 - a damaged or unreadable file: say so
            self.unlock_error.setText(f"Can't open it: {e}")
            return False
        finally:
            QApplication.restoreOverrideCursor()
        self.master.clear()
        self.unlock_sub.setText(f"{self.path}  ·  {v.info()}")
        self.opened(v)
        return True

    def opened(self, v: vault.Vault):
        self.vault = v
        self.path = v.path
        self._remember(v.path)
        self.group_uuid = str(v.root.uuid)
        self.search.clear()
        self.fill_groups()
        self.refresh()
        self.pages.setCurrentIndex(1)
        self.table.setFocus()
        self.active()

    # ---------------------------------------------------------------- the database page
    def _database_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(14, 10, 14, 10)
        bar.setSpacing(4)
        for item in (("add", "New entry (Ctrl+N)", self.new_entry),
                     ("edit", "Edit entry (Ctrl+E)", self.edit_entry),
                     ("trash", "Delete entry (Del)", self.delete_entry), None,
                     ("user", "Copy user name (Ctrl+B)", self.copy_username),
                     ("key", "Copy password (Ctrl+C)", self.copy_password),
                     ("link", "Open the URL (Ctrl+Shift+U)", self.open_url), None,
                     ("dice", "Password generator (Ctrl+G)", self.show_generator),
                     ("lock", "Lock the database (Ctrl+L)", lambda: self.lock("button"))):
            if item is None:
                bar.addSpacing(14)
            else:
                bar.addWidget(key(*item))
        bar.addStretch(1)
        self.search = SearchBox(self)
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Search (Ctrl+F)")
        self.search.setFixedWidth(340)
        self.search.textChanged.connect(lambda _: self.refresh())
        bar.addWidget(self.search)
        bar.addWidget(key("more", "Menu", self.show_menu))
        v.addLayout(bar)
        split = QHBoxLayout()
        split.setContentsMargins(0, 0, 0, 0)
        split.setSpacing(0)
        v.addLayout(split, 1)
        self.tree = QTreeWidget()
        self.tree.setObjectName("groups")
        self.tree.setHeaderHidden(True)
        self.tree.setFixedWidth(240)
        self.tree.setIndentation(16)
        self.tree.setIconSize(QSize(18, 18))
        self.tree.itemSelectionChanged.connect(self._group_chosen)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(lambda p: self.group_menu(self.tree.viewport().mapToGlobal(p)))
        split.addWidget(self.tree)
        right = QVBoxLayout()
        right.setSpacing(0)
        split.addLayout(right, 1)
        self.model = EntryModel()
        self.table = EntryTable(self)
        self.table.setModel(self.model)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.setIconSize(QSize(18, 18))
        h = self.table.horizontalHeader()
        for c, w in ((0, 210), (1, 270), (3, 110)):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(c, w)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda _: self.edit_entry())
        self.table.selectionModel().selectionChanged.connect(lambda *_: self.show_entry())
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(lambda p: self.entry_menu(self.table.viewport().mapToGlobal(p)))
        right.addWidget(self.table, 1)
        right.addWidget(self._preview())
        status = QHBoxLayout()
        status.setContentsMargins(14, 7, 14, 7)
        self.status = QLabel("")
        self.status.setObjectName("note")
        status.addWidget(self.status)
        status.addStretch(1)
        self.copied = QLabel("")
        self.copied.setObjectName("copied")
        status.addWidget(self.copied)
        v.addLayout(status)
        # KeePassXC's keys. The copy keys belong to the entry list, so Ctrl+C in a text field still copies text.
        # (Ctrl+C, Ctrl+B, Ctrl+T, Ctrl+U, Delete and Enter are EntryTable's own.)
        for keys, slot, widget in (("Ctrl+N", self.new_entry, page), ("Ctrl+E", self.edit_entry, page),
                                   ("Ctrl+Shift+U", self.open_url, page),
                                   ("Ctrl+G", self.show_generator, page), ("Ctrl+L", lambda: self.lock("key"), page),
                                   ("Ctrl+F", self.search.setFocus, page), ("Escape", self._escape, page),
                                   ("Ctrl+S", self.save, page)):
            a = QAction(widget)
            a.setShortcut(QKeySequence(keys))
            a.setShortcutContext(Qt.ShortcutContext.WidgetShortcut if widget is self.table
                                 else Qt.ShortcutContext.WidgetWithChildrenShortcut)
            a.triggered.connect(slot)
            widget.addAction(a)
        return page

    def _preview(self) -> QFrame:
        pre = QFrame()
        pre.setObjectName("preview")
        g = QGridLayout(pre)
        g.setContentsMargins(22, 16, 22, 16)
        g.setHorizontalSpacing(18)
        g.setVerticalSpacing(9)
        self.p_title = QLabel("")
        self.p_title.setObjectName("title")
        g.addWidget(self.p_title, 0, 0, 1, 4)
        self.p = {}

        def field(r, c, name, label, keys=()):
            g.addWidget(keyed(label), r, c)
            row = QHBoxLayout()
            row.setSpacing(4)
            val = QLabel("")
            val.setObjectName("value")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(val)
            row.addStretch(1)
            for icon, tip, slot in keys:
                row.addWidget(key(icon, tip, slot))
            g.addLayout(row, r, c + 1)
            self.p[name] = val
        field(1, 0, "username", "USER NAME", (("copy", "Copy (Ctrl+B)", self.copy_username),))
        field(2, 0, "password", "PASSWORD", (("eye", "Show", self.toggle_password),
                                             ("copy", "Copy (Ctrl+C)", self.copy_password)))
        field(3, 0, "url", "URL", (("copy", "Copy (Ctrl+U)", self.copy_url), ("link", "Open (Ctrl+Shift+U)", self.open_url)))
        field(1, 2, "otp", "ONE-TIME CODE", (("copy", "Copy (Ctrl+T)", self.copy_otp),))
        field(2, 2, "expires", "EXPIRES")
        field(3, 2, "tags", "TAGS")
        g.addWidget(keyed("NOTES"), 4, 0)
        self.p_notes = QLabel("")
        self.p_notes.setWordWrap(True)
        self.p_notes.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        g.addWidget(self.p_notes, 4, 1, 1, 3)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)
        self.p["otp"].setFont(mono(15))
        self.shown_password = False
        return pre

    # ---------------------------------------------------------------- groups
    def fill_groups(self):
        v = self.vault
        self.tree.blockSignals(True)
        self.tree.clear()                              # no item is kept anywhere else (see EntryModel's note)

        def add(group, parent):
            name = group.name or "Database"
            n = v.count(group)
            it = QTreeWidgetItem([f"{name}   {n}" if parent is not None and n else name])
            icon = "safe" if parent is None else vault.group_icon(name)
            red = parent is None or v.is_bin(group)
            it.setIcon(0, widgets.line_icon(icon, theme.ACCENT if red else theme.LED_ORANGE))
            it.setData(0, Qt.ItemDataRole.UserRole, str(group.uuid))
            if parent is None:
                self.tree.addTopLevelItem(it)
            else:
                parent.addChild(it)
            for sub in v.children(group):
                add(sub, it)
            if str(group.uuid) == self.group_uuid:
                self.tree.setCurrentItem(it)
        add(v.root, None)
        self.tree.expandAll()
        self.tree.blockSignals(False)

    def _group_chosen(self):
        it = self.tree.currentItem()
        if it is None:
            return
        self.group_uuid = it.data(0, Qt.ItemDataRole.UserRole)
        if self.search.text():
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
        self.refresh()

    def current_group(self):
        return self.vault.group(self.group_uuid) if self.vault is not None else None

    # ---------------------------------------------------------------- entries
    def refresh(self, keep: str = ""):
        if self.vault is None:
            return
        keep = keep or (self.current_entry_uuid() or "")
        q = self.search.text()
        g = self.current_group() or self.vault.root
        self.model.set_rows(self.vault.rows(g, q))
        row = next((i for i, r in enumerate(self.model.rows) if r.uuid == keep), 0 if self.model.rows else -1)
        if row >= 0:
            self.table.selectRow(row)
        self.show_entry()
        where = f"Search: {len(self.model.rows)} found" if q else \
            f"{g.name or 'Database'}  ·  {len(self.model.rows)} entries"
        self.status.setText(f"{where}  ·  {self.vault.total()} in the database")

    def current_entry_uuid(self) -> str | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows or rows[0].row() >= len(self.model.rows):
            return None
        return self.model.rows[rows[0].row()].uuid

    def current_entry(self):
        u = self.current_entry_uuid()
        return self.vault.entry(u) if u and self.vault is not None else None

    def show_entry(self):
        e = self.current_entry()
        self.shown_password = False
        if e is None:
            self.p_title.setText("")
            for w in self.p.values():
                w.setText("")
            self.p_notes.setText("")
            self.otp_timer.stop()
            return
        self.p_title.setText((e.title or "").upper())
        self.p["username"].setText(e.username or "")
        self._password_text(e)
        self.p["url"].setText(e.url or "")
        self.p["expires"].setText(e.expiry_time.astimezone().strftime("%Y-%m-%d %H:%M")
                                  if e.expires and e.expiry_time else "Never")
        self.p["tags"].setText("  ·  ".join(e.tags or []))
        self.p_notes.setText(e.notes or "")
        self._otp_tick()
        if e.otp:
            self.otp_timer.start()
        else:
            self.otp_timer.stop()

    def _password_text(self, e):
        w = self.p["password"]
        if self.shown_password:
            w.setFont(mono(15))
            w.setText(e.password or "")
        else:
            w.setFont(QFont())
            w.setText("•" * min(20, max(8, len(e.password or ""))) if e.password else "")

    def toggle_password(self):
        e = self.current_entry()
        if e is not None:
            self.shown_password = not self.shown_password
            self._password_text(e)

    def _otp_tick(self):
        e = self.current_entry()
        if e is None or not e.otp:
            self.p["otp"].setText("")
            return
        try:
            code, left = vault.otp_now(e.otp)
            self.p["otp"].setText(f"{code[:len(code) // 2]} {code[len(code) // 2:]}   ·  {left} s")
        except Exception:  # noqa: BLE001 - a broken key: say so instead of a code
            self.p["otp"].setText("not a valid key")

    # ---------------------------------------------------------------- actions
    def changed(self, keep: str = ""):
        """After every change: save at once (KeePassXC's default), then show it."""
        try:
            self.vault.save()
        except OSError as e:
            self._say("warning", f"Couldn't save {self.vault.path}: {e}")
        self.fill_groups()
        self.refresh(keep)

    def new_entry(self):
        if self.vault is None:
            return
        g = self.current_group() or self.vault.root
        if self.vault.is_bin(g):
            g = self.vault.root
        d = EntryDialog(self, self.vault, group=g)
        if not self._ask("entry", d):
            return
        f = d.fields()
        e = self.vault.add_entry(d.chosen_group(), f["title"], f["username"], f["password"], f["url"], f["notes"],
                                 f["tags"], f["otp"], f["expires"])
        self.group_uuid = str(d.chosen_group().uuid)
        self.search.clear()
        self.changed(str(e.uuid))

    def edit_entry(self):
        e = self.current_entry()
        if e is None:
            return
        d = EntryDialog(self, self.vault, entry=e)
        if not self._ask("entry", d):
            return
        f = d.fields()
        changed = {k: v for k, v in f.items() if (getattr(e, k) if k != "expires" else
                                                  (e.expiry_time if e.expires else None)) != v
                   and not (k == "tags" and (e.tags or []) == v) and not (not getattr(e, k, None) and not v)}
        if changed:
            self.vault.update_entry(e, **changed)
        if d.chosen_group().uuid != e.group.uuid:
            self.vault.move_entry(e, d.chosen_group())
        if changed or self.vault.changed:
            self.changed(str(e.uuid))

    def delete_entry(self):
        e = self.current_entry()
        if e is None:
            return
        in_bin = self.vault.kp.recyclebin_group is not None and e.group.uuid == self.vault.kp.recyclebin_group.uuid
        ask = (f"Delete “{e.title}” for good?" if in_bin else
               f"Move “{e.title}” to the Recycle Bin?")
        if not self._ask("confirm", ask):
            return
        self.vault.delete_entry(e)
        self.changed()

    def copy_username(self):
        e = self.current_entry()
        if e is not None and e.username:
            self.copy(e.username, "user name")

    def copy_password(self):
        e = self.current_entry()
        if e is not None and e.password:
            self.copy(e.password, "password")

    def copy_url(self):
        e = self.current_entry()
        if e is not None and e.url:
            self.copy(e.url, "URL")

    def copy_otp(self):
        e = self.current_entry()
        if e is not None and e.otp:
            try:
                self.copy(vault.otp_now(e.otp)[0], "code")
            except Exception:  # noqa: BLE001
                self._say("warning", "This entry's one-time code key isn't valid.")

    def copy(self, text: str, what: str):
        self.clip.seconds = option("clear_seconds")
        self.clip.copy(text, what)

    def _copied_left(self, n: int):
        what = self.clip.what.upper()
        if self.clip.seconds:
            self.copied.setText(f"{what} COPIED  ·  CLEARED IN {n} S  ·  KEPT OUT OF CLIPBOARD HISTORY")
        else:
            self.copied.setText(f"{what} COPIED  ·  KEPT OUT OF CLIPBOARD HISTORY")

    def open_url(self):
        e = self.current_entry()
        if e is None or not e.url:
            return
        url = e.url if "://" in e.url else "https://" + e.url
        if "open_url" in self.answers:
            self.answers["open_url"](url)
        else:
            QDesktopServices.openUrl(QUrl(url))

    def show_generator(self):
        d = GeneratorDialog(self, use=False)
        d.copied = lambda text: self.copy(text, "password")
        self._ask("generator", d)

    def _escape(self):
        if self.search.text():
            self.search.clear()
            self.table.setFocus()

    def save(self):
        if self.vault is not None:
            self.vault.save()

    # ---------------------------------------------------------------- groups: add, rename, delete
    def group_menu(self, at=None):
        if self.vault is None:
            return None
        g = self.current_group() or self.vault.root
        m = QMenu(self)
        m.addAction("New group", self.new_group)
        if g.uuid != self.vault.root.uuid and not self.vault.is_bin(g):
            m.addAction("Rename group", self.rename_group)
            m.addAction("Delete group", self.delete_group)
        if self.vault.is_bin(g):
            m.addAction("Empty the Recycle Bin", self.empty_bin)
        if at is not None and "menu" not in self.answers:
            m.exec(at)
        return m

    def new_group(self):
        parent = self.current_group() or self.vault.root
        if self.vault.is_bin(parent):
            parent = self.vault.root
        name = self._ask("text", ("New group", ""))
        if name:
            g = self.vault.add_group(parent, name)
            self.group_uuid = str(g.uuid)
            self.changed()

    def rename_group(self):
        g = self.current_group()
        name = self._ask("text", ("Rename group", g.name))
        if name and name != g.name:
            self.vault.rename_group(g, name)
            self.changed()

    def delete_group(self):
        g = self.current_group()
        if g is None or g.uuid == self.vault.root.uuid:
            return
        if self._ask("confirm", f"Move the group “{g.name}” and its entries to the Recycle Bin?"):
            self.group_uuid = str(g.parentgroup.uuid)
            self.vault.delete_group(g)
            self.changed()

    def empty_bin(self):
        if self._ask("confirm", "Delete everything in the Recycle Bin for good?"):
            self.vault.empty_bin()
            self.changed()

    def entry_menu(self, at=None):
        e = self.current_entry()
        m = QMenu(self)
        if e is None:
            m.addAction("New entry", self.new_entry)
        else:
            for text, slot, enabled in (("Copy user name", self.copy_username, bool(e.username)),
                                        ("Copy password", self.copy_password, bool(e.password)),
                                        ("Copy URL", self.copy_url, bool(e.url)),
                                        ("Copy one-time code", self.copy_otp, bool(e.otp)),
                                        ("Open the URL", self.open_url, bool(e.url))):
                m.addAction(text, slot).setEnabled(enabled)
            m.addSeparator()
            m.addAction("Edit entry", self.edit_entry)
            m.addAction("Delete entry", self.delete_entry)
            move = m.addMenu("Move to group")

            def walk(g, depth):
                if self.vault.is_bin(g):
                    return
                a = move.addAction(("    " * depth) + (g.name or "Database"))
                a.triggered.connect(lambda _=False, target=g: self._move(e, target))
                a.setEnabled(g.uuid != e.group.uuid)
                for sub in self.vault.children(g):
                    walk(sub, depth + 1)
            walk(self.vault.root, 0)
        if at is not None and "menu" not in self.answers:
            m.exec(at)
        return m

    def _move(self, e, g):
        self.vault.move_entry(e, g)
        self.changed()

    # ---------------------------------------------------------------- the menu key
    def show_menu(self):
        m = self.main_menu()
        if "menu" not in self.answers:
            m.exec(self.cursor().pos())

    def main_menu(self) -> QMenu:
        m = QMenu(self)
        m.addAction("New database", self.new_database)
        m.addAction("Open database", self.open_database)
        m.addAction("Save", self.save).setEnabled(self.vault is not None)
        m.addAction("Change the master key", self.change_key).setEnabled(self.vault is not None)
        m.addAction("Import a CSV file", self.import_csv)
        m.addSeparator()
        m.addAction("New group", self.new_group).setEnabled(self.vault is not None)
        m.addSeparator()
        m.addAction("Options", self.options)
        m.addAction("Check for updates", self.check_updates)
        m.addAction(f"About PR7-PM {__version__}", lambda: self._say(
            "info", f"Paragon PR7-PM {__version__}: a password manager that works the way KeePassXC works.\n"
                    "Databases are KDBX 4 (pykeepass); nothing is sent anywhere."))
        m.addSeparator()
        m.addAction("Lock the database", lambda: self.lock("menu")).setEnabled(self.vault is not None)
        return m

    def check_updates(self):
        from . import update_ui
        update_ui.check(self, manual=True)

    # ---------------------------------------------------------------- databases
    def new_database(self):
        path = self._ask("save_db")
        if not path:
            return
        if not path.lower().endswith(".kdbx"):
            path += ".kdbx"
        d = NewDatabaseDialog(self)
        if not self._ask("master", d):
            return
        v = vault.Vault.create(path, d.pw.text(), d.keyfile.text().strip() or None)
        self.opened(v)

    def open_database(self):
        path = self._ask("open_db")
        if path:
            if self.vault is not None:
                self.lock("open another")
            self.show_unlock(path)

    def change_key(self):
        d = NewDatabaseDialog(self, "CHANGE THE MASTER KEY")
        if self.vault is not None and self._ask("master", d):
            self.vault.change_key(d.pw.text(), d.keyfile.text().strip() or None)
            self.changed()
            self._say("info", "The master key is changed. Open the database with the new one from now on.")

    def import_csv(self):
        if self.vault is None:
            self._say("info", "Open or make a database first: the CSV file's entries go into it.")
            return
        path = self._ask("open_csv")
        if not path:
            return
        try:
            n = vault.import_csv(self.vault, path)
        except (OSError, ValueError, UnicodeDecodeError) as e:
            self._say("warning", f"Couldn't import {os.path.basename(path)}: {e}")
            return
        self.changed()
        self._say("info", f"{n} entries imported into the group “Imported”.")

    # ---------------------------------------------------------------- locking
    def active(self):
        """Any use: the idle lock starts counting again."""
        minutes = option("lock_minutes")
        if self.vault is not None and minutes > 0:
            self.idle.start(minutes * 60_000)

    def lock(self, why: str = "") -> bool:
        """Forget the open database (it was saved after every change) and empty our copies off the clipboard."""
        if self.vault is None:
            return False
        if self.vault.changed:
            try:
                self.vault.save()
            except OSError:
                pass
        path = self.vault.path
        self.vault = None
        self.idle.stop()
        self.otp_timer.stop()
        self.clip.clear_now()
        self.model.set_rows([])
        self.tree.clear()
        self.search.clear()
        self.show_unlock(path)
        return True

    def changeEvent(self, e):
        if e.type() == QEvent.Type.WindowStateChange and self.isMinimized() and option("lock_on_minimize"):
            self.lock("minimised")
        super().changeEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        if sys.platform == "win32" and not self._session_note:
            try:                                       # WM_WTSSESSION_CHANGE when Windows locks
                import ctypes
                ctypes.windll.wtsapi32.WTSRegisterSessionNotification(int(self.winId()), 0)
                self._session_note = True
            except Exception:  # noqa: BLE001
                pass

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32" and event_type == b"windows_generic_MSG":
            try:
                import ctypes.wintypes
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == 0x02B1 and msg.wParam == 7 and option("lock_on_session"):   # WTS_SESSION_LOCK
                    self.lock("windows locked")
            except Exception:  # noqa: BLE001
                pass
        return super().nativeEvent(event_type, message)

    def closeEvent(self, e):
        self.lock("closing")
        self.clip.clear_now()
        super().closeEvent(e)

    # ---------------------------------------------------------------- questions
    def options(self):
        d = OptionsDialog(self)
        if self._ask("options", d):
            d.save()
            self.clip.seconds = option("clear_seconds")
            self.active()

    def _ask(self, kind: str, payload=None):
        if kind in self.answers:
            return self.answers[kind](payload) if payload is not None else self.answers[kind]()
        if isinstance(payload, QDialog):
            payload.setStyleSheet(stylesheet())
            return payload.exec() == QDialog.DialogCode.Accepted
        if kind == "confirm":
            return QMessageBox.question(self, "Paragon PR7-PM", payload) == QMessageBox.StandardButton.Yes
        if kind == "text":
            from PySide6.QtWidgets import QInputDialog
            title, value = payload
            text, ok = QInputDialog.getText(self, "Paragon PR7-PM", title, text=value)
            return text.strip() if ok else ""
        if kind in ("open_db", "open_key", "open_csv"):
            filt = {"open_db": "KeePass databases (*.kdbx)", "open_key": "All files (*)",
                    "open_csv": "CSV files (*.csv)"}[kind]
            f, _ = QFileDialog.getOpenFileName(self, "Paragon PR7-PM", "", filt)
            return f
        if kind == "save_db":
            f, _ = QFileDialog.getSaveFileName(self, "New database", "Passwords.kdbx", "KeePass databases (*.kdbx)")
            return f
        return None

    def _say(self, kind: str, text: str):
        self.said.append((kind, text))
        if "say" in self.answers:
            self.answers["say"](kind, text)
            return
        (QMessageBox.warning if kind == "warning" else QMessageBox.information)(self, "Paragon PR7-PM", text)
