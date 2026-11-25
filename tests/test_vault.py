import datetime
import math

import pytest

from pr7pm import generator, vault


@pytest.fixture
def db(tmp_path):
    v = vault.Vault.create(str(tmp_path / "Personal.kdbx"), "correct horse battery staple")
    email = next(g for g in v.children(v.root) if g.name == "Email")
    v.add_entry(email, "Proton Mail", "me@proton.me", "v7#Kq2!mWz@R8pL$e4Tn", url="https://account.proton.me",
                notes="Recovery phrase is in the envelope.", tags=["email", "2fa"],
                otp="otpauth://totp/Proton:me?secret=JBSWY3DPEHPK3PXP&issuer=Proton")
    v.add_entry(email, "Fastmail", "me@fastmail.com", "s3cret-pw", url="https://app.fastmail.com")
    v.save()
    return v


def test_a_new_database_is_kdbx4_with_the_starter_groups(db, tmp_path):
    again = vault.Vault.open(db.path, "correct horse battery staple")
    assert again.info() == "KDBX 4  ·  AES-256, Argon2d"
    assert [g.name for g in again.children(again.root)][:6] == vault.STARTER_GROUPS
    e = again.kp.find_entries(title="Proton Mail", first=True)
    assert (e.username, e.password, e.url, e.tags) == ("me@proton.me", "v7#Kq2!mWz@R8pL$e4Tn",
                                                      "https://account.proton.me", ["email", "2fa"])
    assert not (tmp_path / "Personal.kdbx.part").exists()                  # saved through a temporary file


def test_the_wrong_password_or_key_file(db, tmp_path):
    with pytest.raises(vault.WrongKey):
        vault.Vault.open(db.path, "Correct horse battery staple")
    key = tmp_path / "key.keyx"
    key.write_bytes(b"0123456789abcdef" * 4)
    db.change_key("pw2", str(key))
    db.save()
    with pytest.raises(vault.WrongKey):
        vault.Vault.open(db.path, "pw2")                                     # the key file is needed too
    assert vault.Vault.open(db.path, "pw2", str(key)).total() == 2


def test_search_finds_every_word_in_any_field_but_never_the_password(db):
    assert [r.title for r in db.rows(query="proton")] == ["Proton Mail"]
    assert [r.title for r in db.rows(query="ENVELOPE recovery")] == ["Proton Mail"]
    assert [r.title for r in db.rows(query="2fa")] == ["Proton Mail"]               # tags
    assert db.rows(query="s3cret") == []                                          # passwords aren't searched
    assert [r.title for r in db.rows(query="me@")] == ["Fastmail", "Proton Mail"]


def test_delete_goes_to_the_recycle_bin_then_for_good(db):
    e = db.kp.find_entries(title="Fastmail", first=True)
    db.delete_entry(e)
    bin_ = db.kp.recyclebin_group
    assert [x.title for x in bin_.entries] == ["Fastmail"] and db.total() == 1
    assert db.rows(query="fastmail") == []                                        # the bin isn't searched
    assert db.children(db.root)[-1].name == "Recycle Bin"                          # listed last
    db.delete_entry(bin_.entries[0])
    assert bin_.entries == [] and db.kp.find_entries(title="Fastmail", first=True) is None


def test_editing_keeps_history_and_survives_saving(db):
    e = db.kp.find_entries(title="Proton Mail", first=True)
    when = datetime.datetime(2027, 1, 1, tzinfo=datetime.timezone.utc)
    db.update_entry(e, password="new-password-1", expires=when)
    assert db.changed
    db.save()
    again = vault.Vault.open(db.path, "correct horse battery staple")
    e2 = again.kp.find_entries(title="Proton Mail", first=True)
    assert e2.password == "new-password-1" and e2.expires and e2.expiry_time == when
    assert [h.password for h in e2.history] == ["v7#Kq2!mWz@R8pL$e4Tn"]          # the old one kept, as KeePassXC


def test_one_time_codes_match_rfc_6238():
    # RFC 6238's test key (SHA-1, "12345678901234567890" as base32), 8 digits, at its test times
    uri = "otpauth://totp/t?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&digits=8&period=30"
    assert vault.otp_now(uri, 59) == ("94287082", 1)
    assert vault.otp_now(uri, 1111111109)[0] == "07081804"
    assert vault.otp_now(uri, 1234567890)[0] == "89005924"


def test_generated_passwords_follow_the_options():
    o = generator.Options(length=32, no_look_alike=True, exclude="%")
    for _ in range(200):
        pw = generator.password(o)
        assert len(pw) == 32 and not set(pw) & (generator.LOOK_ALIKE | {"%"})
        assert any(c.isupper() for c in pw) and any(c.islower() for c in pw) and any(c.isdigit() for c in pw)
        assert any(not c.isalnum() for c in pw)                                  # every ticked kind at least once
    digits = generator.Options(length=12, classes=("digits",))
    assert set(generator.password(digits)) <= set("23456789")                   # 0 and 1 are look-alikes
    assert generator.bits("x" * 20, generator.Options()) == pytest.approx(20 * math.log2(len("".join(
        generator.pools(generator.Options())))))
    assert generator.quality(129) == "Excellent" and generator.quality(30) == "Poor"
    with pytest.raises(ValueError):
        generator.password(generator.Options(classes=()))


def test_passphrases_come_from_the_eff_list():
    words = generator.words()
    assert len(words) == 7772 and words[0] == "abacus"
    p = generator.passphrase(generator.PhraseOptions(words=6, separator="-", capitalize=False))
    assert len(p.split("-")) == 6 and all(w in words for w in p.split("-"))
    assert generator.phrase_bits(generator.PhraseOptions(words=6)) == pytest.approx(6 * math.log2(7772))


@pytest.mark.skipif(not __import__("shutil").which("keepassxc-cli"), reason="needs KeePassXC's keepassxc-cli")
def test_keepassxc_itself_opens_what_pr7pm_writes_and_the_other_way(db, tmp_path):
    import subprocess

    def cli(*args, pw="correct horse battery staple"):
        return subprocess.run(["keepassxc-cli", *args], input=pw + "\n", capture_output=True, text=True, timeout=60)
    r = cli("show", "-s", db.path, "Email/Proton Mail")                       # -s: show the password too
    assert r.returncode == 0, r.stderr
    assert "UserName: me@proton.me" in r.stdout and "Password: v7#Kq2!mWz@R8pL$e4Tn" in r.stdout
    made = tmp_path / "made-by-keepassxc.kdbx"
    r = subprocess.run(["keepassxc-cli", "db-create", "-p", str(made)], input="pw-from-kx\npw-from-kx\n",
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    r = cli("add", "-u", "kx-user", "--url", "https://example.org", "-p", str(made), "From KeePassXC",
            pw="pw-from-kx\nentry-password-9")
    assert r.returncode == 0, r.stderr
    v = vault.Vault.open(str(made), "pw-from-kx")
    e = v.kp.find_entries(title="From KeePassXC", first=True)
    assert (e.username, e.password, e.url) == ("kx-user", "entry-password-9", "https://example.org")
