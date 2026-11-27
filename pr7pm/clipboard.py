"""Copying secrets the way KeePassXC does: marked private, and cleared after a few seconds.

Every copy carries Windows' three "don't keep this" marks: ExcludeClipboardContentFromMonitorProcessing,
CanIncludeInClipboardHistory = 0 (Windows' own clipboard history, Win+V) and the older Clipboard Viewer Ignore.
PR7-CB, Ditto and Windows' history leave such copies alone. On Linux it carries KDE's mark instead,
x-kde-passwordManagerHint = "secret" (KeePassXC's too), so Plasma's clipboard history (Klipper) neither lists nor saves
it. After `seconds` the clipboard is emptied, but only if it
still holds what PR7-PM put there (something copied since is left alone)."""

from __future__ import annotations

import sys

from PySide6.QtCore import QMimeData, QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication

MARKS = {"ExcludeClipboardContentFromMonitorProcessing": b"\0",
         "CanIncludeInClipboardHistory": b"\0\0\0\0",          # a DWORD 0
         "Clipboard Viewer Ignore": b"\0"}


KDE_MARK = ("x-kde-passwordManagerHint", b"secret")      # Klipper skips and never saves such copies


def mime_name(name: str) -> str:
    """Qt registers a Windows clipboard format by this exact name only in its windows-mime form."""
    return f'application/x-qt-windows-mime;value="{name}"' if sys.platform == "win32" else name


def private_data(text: str) -> QMimeData:
    md = QMimeData()
    md.setText(text)
    for name, value in MARKS.items():
        md.setData(mime_name(name), value)
    if sys.platform != "win32":
        md.setData(*KDE_MARK)
    return md


class SecretClipboard(QObject):
    """copy(text, what) puts a private copy on the clipboard; `left` counts down; `cleared` when it's emptied."""
    left = Signal(int)
    cleared = Signal()

    def __init__(self, seconds: int = 10, parent=None):
        super().__init__(parent)
        self.seconds = seconds
        self.text = None
        self.what = ""
        self.remaining = 0
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)

    def copy(self, text: str, what: str = "password"):
        QGuiApplication.clipboard().setMimeData(private_data(text))
        self.text, self.what = text, what
        self.remaining = self.seconds
        if self.seconds > 0:
            self.timer.start()
        self.left.emit(self.remaining)

    def _tick(self):
        self.remaining -= 1
        if self.remaining <= 0:
            self.clear_now()
        else:
            self.left.emit(self.remaining)

    def clear_now(self):
        """Empty the clipboard if it still holds our copy (also called on lock and exit)."""
        self.timer.stop()
        if self.text is not None and QGuiApplication.clipboard().text() == self.text:
            QGuiApplication.clipboard().clear()
        self.text = None
        self.remaining = 0
        self.cleared.emit()
