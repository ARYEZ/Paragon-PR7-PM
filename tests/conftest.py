import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["PR7PM_DATA"] = tempfile.mkdtemp()                    # never the real data folder


@pytest.fixture(scope="session")
def qapp(tmp_path_factory):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)           # never the real settings
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path_factory.mktemp("settings")))
    app = QApplication.instance() or QApplication([])
    from pr7pm import theme
    theme.load_fonts()
    yield app
    app.clipboard().clear()                  # PySide's offscreen clipboard crashes at exit while it holds data


@pytest.fixture
def window(qapp, tmp_path):
    from pr7pm import main_window, settings
    for k in ("recent", "lock_minutes", "clear_seconds", "open_last", "lock_on_minimize"):
        settings.set(k, main_window.DEFAULTS.get(k, []) if k != "recent" else [])
    w = main_window.MainWindow()
    w.answers["say"] = lambda kind, text: None
    w.answers["menu"] = lambda *a: None
    w.show()
    yield w
    w.answers["say"] = lambda kind, text: None
    w.close()
    qapp.clipboard().clear()
