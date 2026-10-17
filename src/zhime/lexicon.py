"""Traditional Chinese lexicon built from McBopomofo's data.txt (MIT)."""

from __future__ import annotations

import pickle
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .keyboard import BPMF_TO_KEY

ROOT = Path(__file__).resolve().parents[2]
DATA_TXT = ROOT / "third_party/McBopomofo/Source/Data/data.txt"
CACHE = ROOT / "data/lexicon.pkl"

_BPMF_CHARS = set(BPMF_TO_KEY) | {"-"}


@dataclass
class Lexicon:
    syllables: set[str] = field(default_factory=set)
    # "ㄋㄧˇ-ㄏㄠˇ" -> [("你好", -5.09), ...] best first
    by_reading: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    # every proper prefix of a multi-syllable reading, e.g. "ㄋㄧˇ"
    prefixes: set[str] = field(default_factory=set)
    # "你好" -> [("ㄋㄧˇ-ㄏㄠˇ", -5.09), ...] best first
    by_word: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    max_syllables: int = 0

    @classmethod
    def load(cls) -> "Lexicon":
        # Installed builds ship only the cache, not data.txt.
        if CACHE.exists() and (not DATA_TXT.exists()
                               or CACHE.stat().st_mtime > DATA_TXT.stat().st_mtime):
            with CACHE.open("rb") as f:
                return pickle.load(f)
        lex = cls._build()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        with CACHE.open("wb") as f:
            pickle.dump(lex, f, protocol=pickle.HIGHEST_PROTOCOL)
        return lex

    @classmethod
    def _build(cls) -> "Lexicon":
        by_reading: dict[str, list[tuple[str, float]]] = defaultdict(list)
        by_word: dict[str, list[tuple[str, float]]] = defaultdict(list)
        with DATA_TXT.open(encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) != 3 or line.startswith(("_", "#")):
                    continue
                reading, word, score = parts
                if not set(reading) <= _BPMF_CHARS:
                    continue
                if len(reading.split("-")) != len(word):
                    continue  # symbols / macros, not plain words
                logp = float(score)
                by_reading[reading].append((word, logp))
                by_word[word].append((reading, logp))
        lex = cls()
        for reading, words in by_reading.items():
            words.sort(key=lambda w: -w[1])
            syls = reading.split("-")
            lex.max_syllables = max(lex.max_syllables, len(syls))
            if len(syls) == 1:
                lex.syllables.add(reading)
            for k in range(1, len(syls)):
                lex.prefixes.add("-".join(syls[:k]))
        for readings in by_word.values():
            readings.sort(key=lambda r: -r[1])
        lex.by_reading = dict(by_reading)
        lex.by_word = dict(by_word)
        return lex
