"""Start PR7-PM.

    PR7-PM.exe [FILE.kdbx]        the window (one per user: a second start hands FILE to the running one)
    PR7-PM.exe --register         .kdbx files: Open with PR7-PM, and PR7-PM in Default apps (the installer's task)
    PR7-PM.exe --unregister       take that away again (the uninstaller)
    PR7-PM.exe --version
    PR7-PM.exe --selftest OUT.json   make a database offscreen, add, lock, unlock, edit and copy, and write what
                                     happened (CI checks the installed exe)
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import sys

TIMEOUT_MS = 1500


def server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = "user"
    return "Paragon-PR7-PM-" + hashlib.sha1(user.encode()).hexdigest()[:12]


def hand_over(path: str | None) -> bool:
    from PySide6.QtNetwork import QLocalSocket
    s = QLocalSocket()
    s.connectToServer(server_name())
    if not s.waitForConnected(TIMEOUT_MS):
        return False
    s.write(json.dumps({"open": path}).encode() + b"\n")
    s.flush()
    s.waitForBytesWritten(TIMEOUT_MS)
    if not s.waitForDisconnected(TIMEOUT_MS):
        s.disconnectFromServer()
    return True


def listen(window):
    """Later starts hand over to this window (PR7-R's hand-off, with its Windows fix: data already waiting is read
    when the connection is accepted)."""
    from PySide6.QtNetwork import QLocalServer
    server = QLocalServer(window)
    QLocalServer.removeServer(server_name())
    if not server.listen(server_name()):
        return None

    def connection():
        sock = server.nextPendingConnection()
        if sock is None:
            return
        buf = bytearray()
        done = []

        def read():
            buf.extend(bytes(sock.readAll()))
            if buf.endswith(b"\n") and not done:
                done.append(True)
                try:
                    msg = json.loads(buf.decode())
                except ValueError:
                    return
                window.showNormal()
                window.raise_()
                window.activateWindow()
                if msg.get("open"):
                    if window.vault is not None and os.path.normcase(window.vault.path) != os.path.normcase(
                            msg["open"]):
                        window.lock("open another")
                    if window.vault is None:
                        window.show_unlock(msg["open"])
                sock.disconnectFromServer()
        sock.readyRead.connect(read)
        sock.disconnected.connect(read)
        if sock.bytesAvailable():
            read()
    server.newConnection.connect(connection)
    window.instance_server = server
    return server


def selftest(out: str) -> int:
    import tempfile
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    data = tempfile.mkdtemp()
    os.environ["PR7PM_DATA"] = data
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtWidgets import QApplication
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())
    result = {}
    app = QApplication.instance() or QApplication(sys.argv[:1])
    try:
        from . import __version__, theme, vault
        from .main_window import MainWindow
        theme.load_fonts()
        w = MainWindow()
        w.answers.update({"say": lambda k, t: None, "menu": lambda *a: None, "confirm": lambda t: True})
        path = os.path.join(data, "Selftest.kdbx")
        w.answers["save_db"] = lambda: path
        w.answers["master"] = lambda d: (d.pw.setText("selftest pass phrase"), d.again.setText("selftest pass phrase"),
                                         True)[-1]
        w.new_database()

        def fill(d):
            d.title.setText("Proton Mail"); d.username.setText("me@proton.me"); d.password.setText("v7#Kq2!mWz")
            d.otp.setText("JBSWY3DPEHPK3PXP")
            return True
        w.answers["entry"] = fill
        w.new_entry()
        w.copy_password()
        md = app.clipboard().mimeData()
        marks = sorted(f for f in md.formats() if "Clipboard" in f)
        copied = app.clipboard().text()
        w.lock("selftest")
        cleared = app.clipboard().text() == ""
        w.master.setText("wrong")
        wrong = w.unlock()
        w.master.setText("selftest pass phrase")
        right = w.unlock()
        on_disk = vault.Vault.open(path, "selftest pass phrase").kp.find_entries(title="Proton Mail", first=True)
        result = {"version": __version__, "kdbx": vault.Vault.open(path, "selftest pass phrase").info(),
                  "entry": [on_disk.username, on_disk.password], "otp": len(vault.otp_now(on_disk.otp)[0]),
                  "copied": copied, "marks": marks, "cleared_on_lock": cleared,
                  "wrong_password_refused": not wrong, "unlocked": right,
                  "fonts": "Inter" in QFontDatabase.families()}
        w.close()
    except Exception as e:  # noqa: BLE001 - reported in the output
        result = {"error": f"{type(e).__name__}: {e}"}
    app.clipboard().clear()       # PySide's offscreen clipboard crashes at exit while it holds data (not on Windows)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh)
    return 0 if result.get("unlocked") else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or not argv[0].startswith("--"):
        return _window(argv)
    # a command-line mode (the installer, CI): an unexpected error must end the process with a code; in the windowed
    # exe it would otherwise open an error box that waits for a click nobody gives (PR7-IS met this on CI)
    try:
        return _command(argv)
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 - reported, then a failing exit code
        import traceback
        if sys.stderr is not None:
            sys.stderr.write(traceback.format_exc())
        return 2


def _command(argv: list[str]) -> int:
    if argv[:1] == ["--version"]:
        from . import __version__
        print(__version__)
        return 0
    if argv[:1] == ["--selftest"] and len(argv) == 2:
        return selftest(argv[1])
    if argv[:1] in (["--register"], ["--unregister"]):
        from . import shell
        return shell.run(argv[0])
    print(__doc__)
    return 1


def _window(argv: list[str]) -> int:
    path = os.path.abspath(argv[0]) if argv else None
    from PySide6.QtWidgets import QApplication

    from . import settings, theme
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setOrganizationName("Paragon")
    app.setApplicationName("PR7-PM")
    if hand_over(path):
        return 0
    theme.set_finish(settings.get("finish", "obsidian"))
    theme.load_fonts()
    app.setPalette(theme.palette())
    from PySide6.QtGui import QIcon
    icon = os.path.join(os.path.dirname(__file__), "icons", "app.ico")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    from .main_window import MainWindow
    w = MainWindow()
    listen(w)
    if path:
        w.show_unlock(path)
    w.show()
    from . import update_ui
    update_ui.start(w)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
