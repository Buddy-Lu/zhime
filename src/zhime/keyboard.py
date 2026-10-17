"""Daqian (大千) Zhuyin layout on a US keyboard, and the typo cost model.

All costs are in log10 units so they add directly to the lexicon's log10
probabilities: a cost of 2.0 means "this edit happens about 1 in 100 times".
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Standard Daqian layout. Space is tone 1 (unmarked in readings).
KEY_TO_BPMF = {
    "1": "ㄅ", "q": "ㄆ", "a": "ㄇ", "z": "ㄈ",
    "2": "ㄉ", "w": "ㄊ", "s": "ㄋ", "x": "ㄌ",
    "e": "ㄍ", "d": "ㄎ", "c": "ㄏ",
    "r": "ㄐ", "f": "ㄑ", "v": "ㄒ",
    "5": "ㄓ", "t": "ㄔ", "g": "ㄕ", "b": "ㄖ",
    "y": "ㄗ", "h": "ㄘ", "n": "ㄙ",
    "u": "ㄧ", "j": "ㄨ", "m": "ㄩ",
    "8": "ㄚ", "i": "ㄛ", "k": "ㄜ", ",": "ㄝ",
    "9": "ㄞ", "o": "ㄟ", "l": "ㄠ", ".": "ㄡ",
    "0": "ㄢ", "p": "ㄣ", ";": "ㄤ", "/": "ㄥ",
    "-": "ㄦ",
    " ": "",  # tone 1
    "6": "ˊ", "3": "ˇ", "4": "ˋ", "7": "˙",
}
BPMF_TO_KEY = {v: k for k, v in KEY_TO_BPMF.items() if v}
TONE_KEYS = frozenset(" 6347")

# Physical key centres (x in key widths, y in rows) on an ANSI keyboard.
_ROWS = [
    ("1234567890-=", 1.0, 0.0),
    ("qwertyuiop[]", 1.5, 1.0),
    ("asdfghjkl;'", 1.75, 2.0),
    ("zxcvbnm,./", 2.25, 3.0),
]
KEY_POS: dict[str, tuple[float, float]] = {}
for chars, x0, y in _ROWS:
    for i, ch in enumerate(chars):
        KEY_POS[ch] = (x0 + i, y)


def _space_distance(ch: str) -> float:
    # The space bar is wide: treat c..m on the bottom row as touching it.
    if ch not in KEY_POS:
        return 99.0
    x, y = KEY_POS[ch]
    if y != 3.0:
        return 99.0
    return 1.0 if 4.0 <= x <= 8.5 else 99.0


def key_distance(a: str, b: str) -> float:
    if a == b:
        return 0.0
    if a == " ":
        return _space_distance(b)
    if b == " ":
        return _space_distance(a)
    if a not in KEY_POS or b not in KEY_POS:
        return 99.0
    (x1, y1), (x2, y2) = KEY_POS[a], KEY_POS[b]
    return math.hypot(x1 - x2, y1 - y2)


# Sounds Taiwan Mandarin speakers commonly merge, so they get mistyped as each other.
_PHONETIC_PAIRS = [
    ("ㄓ", "ㄗ"), ("ㄔ", "ㄘ"), ("ㄕ", "ㄙ"),
    ("ㄣ", "ㄥ"), ("ㄢ", "ㄤ"),
    ("ㄈ", "ㄏ"), ("ㄋ", "ㄌ"),
]
PHONETIC_CONFUSABLE = frozenset(
    frozenset((BPMF_TO_KEY[a], BPMF_TO_KEY[b])) for a, b in _PHONETIC_PAIRS
)


@dataclass
class TypoCosts:
    sub_adjacent: float = 2.0     # hit a neighbouring key
    sub_tone: float = 1.5         # wrong tone
    sub_phonetic: float = 1.5     # ㄣ/ㄥ, ㄓ/ㄗ ... confusion
    sub_far: float = 5.0          # any other wrong key (effectively off)
    insert: float = 2.5           # an extra key was typed
    insert_adjacent: float = 2.0  # extra key next to its neighbour (fat finger)
    insert_shifted: float = 8.0   # a capital letter treated as a stray key
    delete: float = 2.5           # a key was skipped
    delete_tone: float = 2.0      # the tone key was skipped
    transpose: float = 2.0        # two keys swapped
    complete: float = 0.3         # per key not yet typed at the end of the buffer
    syllable_limit: float = 4.0   # give up on a syllable beyond this cost
    start_margin: float = 3.0     # drop edges this much worse than the best from the same key

    def sub(self, intended: str, typed: str) -> float:
        if intended == typed:
            return 0.0
        if intended in TONE_KEYS and typed in TONE_KEYS:
            return self.sub_tone
        if frozenset((intended, typed)) in PHONETIC_CONFUSABLE:
            return self.sub_phonetic
        if key_distance(intended, typed) <= 1.25:
            return self.sub_adjacent
        return self.sub_far

    def dele(self, intended: str) -> float:
        return self.delete_tone if intended in TONE_KEYS else self.delete

    def ins(self, typed: str, prev: str | None, nxt: str | None) -> float:
        if typed.isupper():
            return self.insert_shifted  # Shift+letter is deliberate English, never a stray key
        for n in (prev, nxt):
            if n is not None and key_distance(typed, n) <= 1.25:
                return self.insert_adjacent
        return self.insert


def reading_to_keys(syllable: str) -> str:
    """ㄋㄧˇ -> 'su3'; a syllable without a tone mark gets the space key."""
    keys = "".join(BPMF_TO_KEY[ch] for ch in syllable)
    if not keys or keys[-1] not in TONE_KEYS:
        keys += " "
    return keys


def keys_to_reading(keys: str) -> str:
    return "".join(KEY_TO_BPMF.get(k, k) for k in keys)
