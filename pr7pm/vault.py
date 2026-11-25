"""A password database, the way KeePassXC keeps one: a KDBX 4 file (AES-256, Argon2), read and written by pykeepass.

No Qt here. `Vault` wraps one open file: groups (the tree), entries (title, user name, password, URL, notes, tags,
expiry, one-time codes), the Recycle Bin, search, and saving through a temporary file so a crash mid-save can't
damage the database. The same file opens in KeePassXC, KeePass, KeePassDX and Strongbox."""

from __future__ import annotations

import datetime
import os
import time
from dataclasses import dataclass

from pykeepass import PyKeePass, create_database
from pykeepass.exceptions import CredentialsError

ICONS = {"Email": "mail", "Banking": "bank", "Shopping": "cart", "Social": "people", "Work": "briefcase",
         "Wi-Fi": "wifi", "Recycle Bin": "trash"}
STARTER_GROUPS = ["Email", "Banking", "Shopping", "Social", "Work", "Wi-Fi"]


class WrongKey(Exception):
    """The password or key file doesn't open this database."""


def group_icon(name: str) -> str:
    return ICONS.get(name, "folder")


@dataclass
class Row:
    """One entry as the window shows it (no password: that's read only when it's copied or shown)."""
    uuid: str
    title: str
    username: str
    url: str
    modified: float
    group: str
    expired: bool
    has_otp: bool


def otp_now(uri: str, at: float | None = None) -> tuple[str, int]:
    """(code, seconds left) for an otpauth:// URI (KeePassXC keeps it in the entry's "otp" field): RFC 6238 TOTP,
    written here because pyotp refuses the 80-bit secrets many services (Google among them) still hand out."""
    import base64
    import hashlib
    import hmac
    import struct
    from urllib.parse import parse_qs, urlparse
    q = {k.lower(): v[0] for k, v in parse_qs(urlparse(uri).query).items()}
    secret = q.get("secret", "").replace(" ", "").upper()
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digits = int(q.get("digits", 6))
    period = int(q.get("period", 30)) or 30
    algo = {"SHA1": hashlib.sha1, "SHA256": hashlib.sha256, "SHA512": hashlib.sha512}[q.get("algorithm",
                                                                                            "SHA1").upper()]
    t = time.time() if at is None else at
    mac = hmac.new(key, struct.pack(">Q", int(t // period)), algo).digest()
    o = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** digits
    return str(code).zfill(digits), int(period - t % period)


class Vault:
    def __init__(self, kp: PyKeePass, path: str):
        self.kp = kp
        self.path = path
        self.changed = False

    # ---------------------------------------------------------------- opening
    @classmethod
    def open(cls, path: str, password: str | None, keyfile: str | None = None) -> "Vault":
        try:
            return cls(PyKeePass(path, password=password or None, keyfile=keyfile or None), path)
        except CredentialsError:
            raise WrongKey("The password or key file is wrong.") from None

    @classmethod
    def create(cls, path: str, password: str, keyfile: str | None = None, name: str | None = None) -> "Vault":
        """A new KDBX 4 database (AES-256, Argon2d with 64 MB: what KeePassXC makes too) with the starter groups."""
        kp = create_database(path, password=password or None, keyfile=keyfile or None)
        kp.root_group.name = name or os.path.splitext(os.path.basename(path))[0]
        for g in STARTER_GROUPS:
            kp.add_group(kp.root_group, g)
        v = cls(kp, path)
        v.save()
        return v

    def info(self) -> str:
        kdf = {"argon2": "Argon2d", "argon2id": "Argon2id", "aeskdf": "AES-KDF"}.get(self.kp.kdf_algorithm,
                                                                                    str(self.kp.kdf_algorithm))
        cipher = {"aes256": "AES-256", "chacha20": "ChaCha20", "twofish": "Twofish"}.get(
            self.kp.encryption_algorithm, str(self.kp.encryption_algorithm))
        return f"KDBX {self.kp.version[0]}  ·  {cipher}, {kdf}"

    # ---------------------------------------------------------------- the tree
    @property
    def root(self):
        return self.kp.root_group

    def children(self, group) -> list:
        """A group's subgroups, the Recycle Bin last (as KeePassXC lists them)."""
        bin_ = self.kp.recyclebin_group
        subs = [g for g in group.subgroups if bin_ is None or g.uuid != bin_.uuid]
        subs += [g for g in group.subgroups if bin_ is not None and g.uuid == bin_.uuid]
        return subs

    def group(self, uuid: str):
        if uuid == str(self.root.uuid):
            return self.root
        return self.kp.find_groups(uuid=_uuid(uuid), first=True)

    def entry(self, uuid: str):
        return self.kp.find_entries(uuid=_uuid(uuid), first=True)

    def is_bin(self, group) -> bool:
        b = self.kp.recyclebin_group
        return b is not None and group is not None and group.uuid == b.uuid

    def count(self, group) -> int:
        return len(group.entries)

    def total(self) -> int:
        bin_ = self.kp.recyclebin_group
        return sum(1 for e in self.kp.entries if bin_ is None or not self._in(e, bin_))

    def _in(self, entry, group) -> bool:
        g = entry.group
        while g is not None:
            if g.uuid == group.uuid:
                return True
            g = g.parentgroup
        return False

    # ---------------------------------------------------------------- rows
    def rows(self, group=None, query: str = "") -> list[Row]:
        """The entries of `group` (its own, as KeePassXC shows a group), or with `query` every entry in the database
        outside the Recycle Bin whose title, user name, URL, notes or tags hold every word (any case)."""
        if query.strip():
            words = query.casefold().split()
            bin_ = self.kp.recyclebin_group
            found = [e for e in self.kp.entries if (bin_ is None or not self._in(e, bin_))
                     and all(w in _haystack(e) for w in words)]
        else:
            found = list((group or self.root).entries)
        return [self.row(e) for e in sorted(found, key=lambda e: ((e.title or "").casefold(), str(e.uuid)))]

    def row(self, e) -> Row:
        exp = bool(e.expires and e.expiry_time and e.expiry_time < datetime.datetime.now(datetime.timezone.utc))
        mod = e.mtime.timestamp() if e.mtime else 0.0
        return Row(str(e.uuid), e.title or "", e.username or "", e.url or "", mod,
                   e.group.name if e.group is not None else "", exp, bool(e.otp))

    # ---------------------------------------------------------------- changing
    def add_group(self, parent, name: str):
        g = self.kp.add_group(parent or self.root, name)
        self.changed = True
        return g

    def rename_group(self, group, name: str):
        group.name = name
        self.changed = True

    def add_entry(self, group, title: str, username: str = "", password: str = "", url: str = "", notes: str = "",
                  tags: list[str] | None = None, otp: str = "", expires: datetime.datetime | None = None):
        e = self.kp.add_entry(group or self.root, title, username, password, url=url or None, notes=notes or None,
                              tags=tags or None, force_creation=True)
        if otp:
            e.otp = otp
        if expires is not None:
            e.expires, e.expiry_time = True, expires
        self.changed = True
        return e

    def update_entry(self, e, **fields):
        """Change these fields; the old values go into the entry's history (as KeePassXC keeps it)."""
        e.save_history()
        for k, v in fields.items():
            if k == "expires":
                e.expires = v is not None
                if v is not None:
                    e.expiry_time = v
            elif k == "tags":
                e.tags = v or None
            else:
                setattr(e, k, v or ("" if k in ("password", "username", "title") else None))
        e.touch(modify=True)
        self.changed = True

    def delete_entry(self, e):
        """To the Recycle Bin; from the Recycle Bin, gone (KeePassXC's Delete)."""
        if self.kp.recyclebin_group is not None and self._in(e, self.kp.recyclebin_group):
            self.kp.delete_entry(e)
        else:
            self.kp.trash_entry(e)
        self.changed = True

    def delete_group(self, g):
        if g.uuid == self.root.uuid:
            return
        if self.kp.recyclebin_group is not None and (self.is_bin(g) or self._group_in(g, self.kp.recyclebin_group)):
            self.kp.delete_group(g)
        else:
            self.kp.trash_group(g)
        self.changed = True

    def empty_bin(self):
        b = self.kp.recyclebin_group
        if b is not None:
            self.kp.empty_group(b)
            self.changed = True

    def move_entry(self, e, group):
        self.kp.move_entry(e, group)
        self.changed = True

    def _group_in(self, g, parent) -> bool:
        while g is not None:
            if g.uuid == parent.uuid:
                return True
            g = g.parentgroup
        return False

    def change_key(self, password: str | None, keyfile: str | None = None):
        self.kp.password = password or None
        self.kp.keyfile = keyfile or None
        self.changed = True

    # ---------------------------------------------------------------- saving
    def save(self):
        """Write to <name>.part beside the file, then replace it: the database is never half written."""
        tmp = self.path + ".part"
        self.kp.save(tmp)
        os.replace(tmp, self.path)
        self.kp.filename = self.path
        self.changed = False


def _uuid(text: str):
    import uuid
    return uuid.UUID(text)


def _haystack(e) -> str:
    return " ".join([e.title or "", e.username or "", e.url or "", e.notes or "", " ".join(e.tags or [])]).casefold()


# -------------------------------------------------------------------- importing
_COLUMNS = {   # our field <- the names other programs' CSV exports use (KeePassXC, Bitwarden, browsers, KeePass)
    "group": ("group", "folder", "grouping"),
    "title": ("title", "name", "account", "website name"),
    "username": ("username", "user name", "login_username", "login", "email"),
    "password": ("password", "login_password"),
    "url": ("url", "login_uri", "website", "web site"),
    "notes": ("notes", "comments", "extra"),
    "otp": ("totp", "login_totp", "otp", "otpauth"),
}


def import_csv(v: Vault, path: str, into: str = "Imported") -> int:
    """Entries from a CSV export (KeePassXC, Bitwarden, Chrome / Firefox / Edge, KeePass) into a new group `into`,
    keeping their groups below it. Returns how many were added."""
    import csv
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return 0
    head = [h.strip().casefold() for h in rows[0]]
    col = {}
    for field_, names in _COLUMNS.items():
        for n in names:
            if n in head:
                col[field_] = head.index(n)
                break
    if "password" not in col or ("title" not in col and "url" not in col):
        raise ValueError("This CSV file has no password and title (or URL) columns.")
    top = v.add_group(v.root, into)
    groups = {"": top}
    added = 0
    for r in rows[1:]:
        def get(f):
            i = col.get(f)
            return r[i].strip() if i is not None and i < len(r) else ""
        if not any(x.strip() for x in r):
            continue
        g = top
        path_ = "/".join(p for p in get("group").replace("\\", "/").split("/") if p and p != "Root")
        if path_:
            built = ""
            for part in path_.split("/"):
                key = f"{built}/{part}"
                if key not in groups:
                    groups[key] = v.add_group(groups[built] if built in groups else top, part)
                built = key
            g = groups[built]
        otp = get("otp")
        if otp and not otp.startswith("otpauth://"):
            otp = f"otpauth://totp/{get('title') or 'Imported'}?secret={otp.replace(' ', '')}"
        v.add_entry(g, get("title") or get("url"), get("username"), get("password"), url=get("url"),
                    notes=get("notes"), otp=otp)
        added += 1
    return added
