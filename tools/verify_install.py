"""Check a real install of PR7-PM-Setup.exe (CI, Windows): verify_install.py installed|uninstalled

`installed`: the files, the Start menu entry, the uninstall entry, .kdbx Open with (the ticked task), and the installed
exe's --selftest (a real KDBX 4 database made, locked, unlocked, copied from). `uninstalled`: all of it gone."""
import json
import os
import subprocess
import sys
import tempfile
import time
import winreg
from pathlib import Path

HKCU = winreg.HKEY_CURRENT_USER
APP = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "PR7-PM"
SHORTCUT = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Paragon PR7-PM.lnk"
UNINSTALL = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{18BE3275-9FB9-46DF-9C29-060A544E4632}_is1"
PROGID = "Paragon.PR7PM.KDBX"


def value(path, name=""):
    try:
        with winreg.OpenKey(HKCU, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def has_value(path, name) -> bool:
    """Whether the value exists: Open with's entries are empty REG_NONE values, which winreg reads back as None."""
    try:
        with winreg.OpenKey(HKCU, path) as k:
            winreg.QueryValueEx(k, name)
            return True
    except OSError:
        return False


def check(ok, what, p):
    print(("ok    " if ok else "FAIL  ") + what)
    if not ok:
        p.append(what)


def installed():
    p = []
    exe = APP / "PR7-PM.exe"
    for f in (exe, APP / "unins000.exe", APP / "_internal" / "pr7pm" / "fonts" / "Inter-Regular.ttf",
              APP / "_internal" / "pr7pm" / "words.txt"):
        check(f.is_file(), f"file {f}", p)
    check(SHORTCUT.is_file(), "Start menu shortcut", p)
    check(value(UNINSTALL, "DisplayName") == "Paragon PR7-PM", "Installed apps entry", p)
    cmd = value(rf"Software\Classes\{PROGID}\shell\open\command") or ""
    check(str(exe).lower() in cmd.lower() and cmd.endswith('"%1"'), f".kdbx opens with PR7-PM: {cmd}", p)
    check(has_value(r"Software\Classes\.kdbx\OpenWithProgids", PROGID), ".kdbx Open with lists PR7-PM", p)
    check(value(r"Software\RegisteredApplications", "Paragon PR7-PM") is not None, "PR7-PM in Default apps", p)
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out.json"
        try:
            subprocess.run([str(exe), "--selftest", str(out)], timeout=180, check=False)
        except subprocess.TimeoutExpired:
            pass
        got = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        check(got.get("kdbx", "").startswith("KDBX 4") and got.get("entry") == ["me@proton.me", "v7#Kq2!mWz"]
              and got.get("otp") == 6 and got.get("fonts") is True, f"the installed exe makes a real database ({got})", p)
        check(len(got.get("marks", [])) == 3 and got.get("copied") == "v7#Kq2!mWz",
              "copies carry the three private marks", p)
        check(got.get("cleared_on_lock") is True and got.get("wrong_password_refused") is True
              and got.get("unlocked") is True, "locking empties the clipboard; a wrong password is refused", p)
    return p


def uninstalled():
    deadline = time.time() + 60
    while True:
        p = []
        check(not (APP / "PR7-PM.exe").exists(), "program files removed", p)
        check(not SHORTCUT.exists(), "Start menu shortcut removed", p)
        check(value(UNINSTALL, "DisplayName") is None, "Installed apps entry removed", p)
        check(value(rf"Software\Classes\{PROGID}") is None and
              value(r"Software\RegisteredApplications", "Paragon PR7-PM") is None, ".kdbx registration removed", p)
        if not p or time.time() > deadline:
            return p
        print("... waiting for the uninstaller to finish")
        time.sleep(3)


if __name__ == "__main__":
    problems = {"installed": installed, "uninstalled": uninstalled}[sys.argv[1]]()
    print("\nALL OK" if not problems else f"\n{len(problems)} problem(s)")
    sys.exit(1 if problems else 0)
