import os

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from pr7pm import settings, vault

PW = "correct horse battery staple"


def make(window, tmp_path, name="Personal.kdbx"):
    """A new database through the window, as File > New database does."""
    path = str(tmp_path / name)
    window.answers["save_db"] = lambda: path
    window.answers["master"] = lambda d: (d.pw.setText(PW), d.again.setText(PW), not d.problem())[-1]
    window.new_database()
    return path


def add(window, title, user="", pw="", url="", group=None, otp=""):
    def fill(d):
        d.title.setText(title); d.username.setText(user); d.password.setText(pw); d.url.setText(url)
        d.otp.setText(otp)
        if group:
            d.group.setCurrentIndex(d.group.findText(group, Qt.MatchFlag.MatchContains))
        return not d.problem()
    window.answers["entry"] = fill
    window.new_entry()


def on_disk(path, title):
    return vault.Vault.open(path, PW).kp.find_entries(title=title, first=True)


def select(window, title):
    row = next(i for i, r in enumerate(window.model.rows) if r.title == title)
    window.table.selectRow(row)


def test_a_new_database_and_entries_are_saved_at_once(window, tmp_path):
    path = make(window, tmp_path)
    assert os.path.exists(path) and window.pages.currentIndex() == 1
    assert [window.tree.topLevelItem(0).child(i).text(0) for i in range(6)] == \
        ["Email", "Banking", "Shopping", "Social", "Work", "Wi-Fi"]
    add(window, "Proton Mail", "me@proton.me", "v7#Kq2!mWz@R8pL$e4Tn", "account.proton.me", group="Email")
    e = on_disk(path, "Proton Mail")                                   # saved after the change, nothing else
    assert (e.username, e.password, e.group.name) == ("me@proton.me", "v7#Kq2!mWz@R8pL$e4Tn", "Email")
    assert window.tree.currentItem().text(0) == "Email   1" and [r.title for r in window.model.rows] == ["Proton Mail"]
    assert window.p_title.text() == "PROTON MAIL" and "•" in window.p["password"].text()
    window.toggle_password()
    assert window.p["password"].text() == "v7#Kq2!mWz@R8pL$e4Tn"
    assert settings.get_list("recent") == [path]


def test_edit_keeps_history_and_delete_goes_to_the_bin_then_for_good(window, tmp_path):
    path = make(window, tmp_path)
    add(window, "Router", "admin", "old-pw", group="Wi-Fi")
    window.answers["entry"] = lambda d: (d.password.setText("new-pw"), True)[-1]
    window.edit_entry()
    e = on_disk(path, "Router")
    assert e.password == "new-pw" and [h.password for h in e.history] == ["old-pw"]
    window.answers["confirm"] = lambda text: True
    window.delete_entry()
    assert on_disk(path, "Router").group.name == "Recycle Bin"
    window.tree.setCurrentItem(window.tree.topLevelItem(0).child(window.tree.topLevelItem(0).childCount() - 1))
    assert window.tree.currentItem().text(0) == "Recycle Bin   1"
    select(window, "Router")
    window.delete_entry()
    assert on_disk(path, "Router") is None


def test_search_covers_the_whole_database(window, tmp_path):
    make(window, tmp_path)
    add(window, "Proton Mail", "me@proton.me", "x", group="Email")
    add(window, "Shop", "me@shop.example", "y", group="Shopping")
    QTest.keyClicks(window.search, "me@")
    assert sorted(r.title for r in window.model.rows) == ["Proton Mail", "Shop"]
    assert window.status.text().startswith("Search: 2 found")
    QTest.keyClick(window.search, Qt.Key.Key_Escape)
    assert window.search.text() == ""


def test_copies_are_private_and_cleared(window, tmp_path, qapp):
    make(window, tmp_path)
    add(window, "Proton Mail", "me@proton.me", "v7#Kq2!mWz@R8pL$e4Tn", group="Email")
    settings.set("clear_seconds", 1)
    window.table.setFocus()
    QTest.keyClick(window.table, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    md = qapp.clipboard().mimeData()
    assert qapp.clipboard().text() == "v7#Kq2!mWz@R8pL$e4Tn"
    assert any("ExcludeClipboardContentFromMonitorProcessing" in f for f in md.formats())
    assert bytes(md.data(next(f for f in md.formats() if "CanIncludeInClipboardHistory" in f))) == b"\0\0\0\0"
    assert "PASSWORD COPIED" in window.copied.text() and "KEPT OUT OF CLIPBOARD HISTORY" in window.copied.text()
    QTest.qWait(1500)
    assert qapp.clipboard().text() == "" and window.copied.text() == ""      # emptied after a second
    QTest.keyClick(window.table, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    assert qapp.clipboard().text() == "me@proton.me"
    qapp.clipboard().setText("something the user copied since")
    QTest.qWait(1500)
    assert qapp.clipboard().text() == "something the user copied since"     # not ours any more: left alone
    window.search.setText("prot")
    window.search.selectAll()
    window.search.setFocus()
    QTest.keyClick(window.search, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert qapp.clipboard().text() == "prot"                                  # Ctrl+C in a text field is text


def test_lock_unlock_and_the_idle_lock(window, tmp_path, qapp):
    path = make(window, tmp_path)
    add(window, "Proton Mail", "me@proton.me", "pw", group="Email")
    window.copy("pw", "password")
    window.lock("test")
    assert window.vault is None and window.pages.currentIndex() == 0 and qapp.clipboard().text() == ""
    assert window.model.rows == [] and window.unlock_title.text() == "UNLOCK PERSONAL.KDBX"
    window.master.setText("wrong")
    assert not window.unlock() and window.unlock_error.text() == "Wrong password or key file."
    window.master.setText(PW)
    QTest.keyClick(window.master, Qt.Key.Key_Return)
    assert window.vault is not None and window.vault.path == path and window.vault.total() == 1
    assert window.master.text() == ""                                         # not kept in the field
    settings.set("lock_minutes", 1)
    window.active()
    assert window.idle.isActive() and 59_000 < window.idle.remainingTime() <= 63_000   # coarse timer: up to 5% late
    window.idle.timeout.emit()
    assert window.vault is None


def test_groups_new_rename_delete(window, tmp_path):
    path = make(window, tmp_path)
    window.answers["text"] = lambda payload: "Streaming"
    window.new_group()
    assert window.tree.currentItem().text(0) == "Streaming"
    window.answers["text"] = lambda payload: "Video"
    window.rename_group()
    window.answers["confirm"] = lambda text: True
    window.delete_group()
    v = vault.Vault.open(path, PW)
    assert [g.name for g in v.kp.recyclebin_group.subgroups] == ["Video"]


def test_one_time_codes_show_and_copy(window, tmp_path, qapp):
    make(window, tmp_path)
    add(window, "GitHub", "me", "pw", group="Work", otp="JBSWY3DPEHPK3PXP")
    code, left = vault.otp_now(window.current_entry().otp)
    assert window.p["otp"].text().replace(" ", "").startswith(code)
    window.copy_otp()
    assert qapp.clipboard().text() == vault.otp_now(window.current_entry().otp)[0]


def test_the_generator(window, qapp):
    from pr7pm.main_window import GeneratorDialog
    d = GeneratorDialog(window)
    d.length.setValue(32)
    for c in ("symbols", "digits"):
        d.classes[c].setChecked(False)
    assert len(d.value) == 32 and d.value.isalpha() and "EXCELLENT" in d.quality.text() or "GOOD" in d.quality.text()
    d.tabs.setCurrentIndex(1)
    d.words.setValue(5)
    assert len(d.value.split("-")) == 5 and "BITS" in d.quality.text()
    copied = []
    d.copied = copied.append
    d.copy()
    assert copied == [d.value]
    d.reject()


def test_import_a_csv_file(window, tmp_path):
    path = make(window, tmp_path)
    f = tmp_path / "bitwarden.csv"
    f.write_text("folder,favorite,type,name,notes,fields,reprompt,login_uri,login_username,login_password,login_totp\n"
                 ",,login,Shop,,,0,https://shop.example,me@x,pw-shop,\n", encoding="utf-8")
    window.answers["open_csv"] = lambda: str(f)
    window.import_csv()
    assert on_disk(path, "Shop").password == "pw-shop" and window.said[-1][1].startswith("1 entries imported")


def test_keepassxc_keys_on_the_entry_list(window, tmp_path, qapp):
    make(window, tmp_path)
    add(window, "Shop", "me@shop", "pw-shop", "shop.example", group="Shopping")
    opened = []
    window.answers["open_url"] = opened.append
    window.table.setFocus()
    QTest.keyClick(window.table, Qt.Key.Key_U, Qt.KeyboardModifier.ControlModifier)
    assert qapp.clipboard().text() == "shop.example"                          # Ctrl+U copies the URL
    window.open_url()
    assert opened == ["https://shop.example"]                                  # Ctrl+Shift+U opens it
    window.answers["confirm"] = lambda text: "Recycle Bin" in text
    QTest.keyClick(window.table, Qt.Key.Key_Delete)
    assert window.vault.kp.find_entries(title="Shop", first=True).group.name == "Recycle Bin"


def test_version_and_selftest(tmp_path, capsys):
    import json
    import subprocess
    import sys
    from pr7pm import __version__, app
    assert app.main(["--version"]) == 0 and capsys.readouterr().out.strip() == __version__
    out = tmp_path / "out.json"
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = subprocess.run([sys.executable, "-m", "pr7pm", "--selftest", str(out)], cwd=root, timeout=120).returncode
    got = json.loads(out.read_text())
    assert code == 0, got
    assert got["entry"] == ["me@proton.me", "v7#Kq2!mWz"] and got["copied"] == "v7#Kq2!mWz" and got["otp"] == 6
    assert got["cleared_on_lock"] and got["wrong_password_refused"] and got["unlocked"] and got["fonts"]
    assert len(got["marks"]) == 3 and got["kdbx"].startswith("KDBX 4")
