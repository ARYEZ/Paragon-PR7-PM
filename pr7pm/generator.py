"""KeePassXC's password generator: passwords from character classes, passphrases from a word list, and how strong
they are. No Qt. Every random choice comes from `secrets` (the operating system's cryptographic source)."""

from __future__ import annotations

import math
import secrets
import string
from dataclasses import dataclass, field
from pathlib import Path

LOOK_ALIKE = set("l1I|O0")
CLASSES = {
    "upper": string.ascii_uppercase,
    "lower": string.ascii_lowercase,
    "digits": string.digits,
    "symbols": "!@#$%^&*()-_=+[]{};:,.<>/?~`'\"\\|",
    "extended": "".join(chr(c) for c in range(0xA1, 0x100) if chr(c).isprintable() and c != 0xAD),
    "space": " ",
}
WORDS_FILE = Path(__file__).parent / "words.txt"


@dataclass
class Options:
    length: int = 20
    classes: tuple[str, ...] = ("upper", "lower", "digits", "symbols")
    no_look_alike: bool = True
    every_class: bool = True          # at least one of each ticked class
    exclude: str = ""


@dataclass
class PhraseOptions:
    words: int = 6
    separator: str = "-"
    capitalize: bool = True
    word_list: list[str] = field(default_factory=list)


def pools(o: Options) -> list[str]:
    out = []
    for c in o.classes:
        chars = "".join(ch for ch in CLASSES[c] if not (o.no_look_alike and ch in LOOK_ALIKE)
                        and ch not in o.exclude)
        if chars:
            out.append(chars)
    return out


def password(o: Options) -> str:
    ps = pools(o)
    if not ps:
        raise ValueError("Tick at least one kind of character.")
    every = "".join(ps)
    n = max(o.length, len(ps) if o.every_class else 1)
    while True:
        pw = [secrets.choice(every) for _ in range(n)]
        if not o.every_class or all(any(ch in p for ch in pw) for p in ps):
            return "".join(pw)


def words() -> list[str]:
    try:
        return [w for w in WORDS_FILE.read_text(encoding="utf-8").split() if w.isalpha()]
    except OSError:
        return []


def passphrase(o: PhraseOptions) -> str:
    lst = o.word_list or words()
    if len(lst) < 2:
        raise ValueError("No word list.")
    picked = [secrets.choice(lst) for _ in range(o.words)]
    if o.capitalize:
        picked = [w.capitalize() for w in picked]
    return o.separator.join(picked)


def bits(pw: str, o: Options | None = None) -> float:
    """Entropy of a generated password: length x log2(how many characters it could have used)."""
    if o is not None:
        return len(pw) * math.log2(max(2, len("".join(pools(o)))))
    return estimate(pw)


def phrase_bits(o: PhraseOptions) -> float:
    return o.words * math.log2(max(2, len(o.word_list or words())))


def estimate(pw: str) -> float:
    """A rough strength for a password someone typed: the character kinds it uses, less for repeats."""
    if not pw:
        return 0.0
    size = 0
    for chars in (string.ascii_lowercase, string.ascii_uppercase, string.digits):
        if any(c in chars for c in pw):
            size += len(chars)
    if any(not c.isalnum() for c in pw):
        size += 33
    unique = len(set(pw))
    return unique * math.log2(max(2, size)) + (len(pw) - unique) * 1.0


def quality(b: float) -> str:
    """KeePassXC's words for a strength."""
    if b < 40:
        return "Poor"
    if b < 65:
        return "Weak"
    if b < 100:
        return "Good"
    return "Excellent"
