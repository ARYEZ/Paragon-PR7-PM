"""Lock with the screen on Linux: Plasma's screen locker (and GNOME's, and others following freedesktop.org) says so
on the session bus with org.freedesktop.ScreenSaver's ActiveChanged(true), on /ScreenSaver and
/org/freedesktop/ScreenSaver. Windows' equivalent (WM_WTSSESSION_CHANGE) is in main_window.nativeEvent.

`ScreenLockWatcher(bus=None)` emits `locked` when the screen locks; `bus` is a QDBusConnection (the session bus by
default; tests pass their own). Without D-Bus (Windows, no session bus) it does nothing and `watching` is False.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QObject, Signal, Slot

INTERFACE = "org.freedesktop.ScreenSaver"
PATHS = ("/ScreenSaver", "/org/freedesktop/ScreenSaver")


class ScreenLockWatcher(QObject):
    locked = Signal()

    def __init__(self, bus=None, parent=None):
        super().__init__(parent)
        self.watching = False
        if sys.platform == "win32":
            return
        try:
            from PySide6.QtCore import SLOT
            from PySide6.QtDBus import QDBusConnection
        except ImportError:
            return
        self.bus = bus if bus is not None else QDBusConnection.sessionBus()
        if not self.bus.isConnected():
            return
        for path in PATHS:                       # any sender: the locker's bus name differs between desktops
            if self.bus.connect("", path, INTERFACE, "ActiveChanged", self, SLOT("_active_changed(bool)")):
                self.watching = True

    @Slot(bool)
    def _active_changed(self, active: bool):
        if active:
            self.locked.emit()
