"""English word edges for mixed Chinese/English typing (no mode switch).

A run of letter keys can be read as an English word. Costs are log10 units like
the rest of the decoder: word log-prob + a switch penalty + a spelling cost.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from wordfreq import top_n_list, word_frequency

_SHORT_OK = {"ok", "hi", "no", "so", "go", "ya", "oh", "yo", "id", "ai", "pc", "tv", "ui", "ux", "io"}


@dataclass
class EnglishCosts:
    switch: float = 1.5      # entering an English word inside Chinese text (tuned: mixed_eval + dev)
    misspell: float = 2.0    # one edit away from a real word
    literal_base: float = 6.0   # unknown letters kept as typed
    literal_per_char: float = 0.5
    acronym_logp: float = -4.0   # log10 P for an unknown ALL-CAPS token


class English:
    def __init__(self, vocab_size: int = 60000, costs: EnglishCosts | None = None) -> None:
        self.costs = costs or EnglishCosts()
        self.logp: dict[str, float] = {}
        for w in top_n_list("en", vocab_size):
            if not (w.isascii() and w.isalpha()):
                continue
            if len(w) < 3 and w not in _SHORT_OK:
                continue
            self.logp[w] = math.log10(word_frequency(w, "en"))
        # SymSpell-style delete index for distance-1 corrections (words of 4+ letters)
        self.deletes: dict[str, list[str]] = {}
        for w in self.logp:
            if len(w) >= 4:
                for k in range(len(w)):
                    self.deletes.setdefault(w[:k] + w[k + 1:], []).append(w)
        self.max_len = max(map(len, self.logp))

    def lookup(self, typed: str) -> list[tuple[str, float, float]]:
        """[(word, log10 P(word), penalty)]; penalty = switch + spelling (typo-like) cost."""
        c = self.costs
        lower = typed.lower()
        out: dict[str, tuple[float, float]] = {}

        def add(word: str, extra: float) -> None:
            text = _match_case(word, typed)
            entry = (self.logp[word], c.switch + extra)
            if text not in out or entry[0] - entry[1] > out[text][0] - out[text][1]:
                out[text] = entry

        if lower in self.logp:
            add(lower, 0.0)
        if len(lower) >= 4:
            for w in self.deletes.get(lower, ()):          # typed is missing a letter
                add(w, c.misspell)
            for k in range(len(lower)):
                d = lower[:k] + lower[k + 1:]
                if d in self.logp and len(d) >= 3:          # typed has an extra letter
                    add(d, c.misspell)
                for w in self.deletes.get(d, ()):           # substitution / swap
                    if w != lower:
                        add(w, c.misspell)
        if len(typed) >= 2 and typed.isupper():
            # ALL-CAPS acronyms (CP, API, LINE) are words even when the dictionary lacks them
            out.setdefault(typed, (c.acronym_logp, c.switch))
        out.setdefault(typed, (-c.literal_per_char * len(typed), c.literal_base))
        ranked = sorted(out.items(), key=lambda x: x[1][1] - x[1][0])[:5]
        return [(w, lp, pen) for w, (lp, pen) in ranked]

    def edges(self, keys: str) -> list[list[tuple[int, str, float, float]]]:
        """ends[j] = [(i, word, logp, penalty)] for letter runs keys[i:j] (optionally eating one trailing space)."""
        n = len(keys)
        ends: list[list[tuple[int, str, float, float]]] = [[] for _ in range(n + 1)]
        for i in range(n):
            if not keys[i].isalpha():
                continue
            j = i
            while j < n and keys[j].isascii() and keys[j].isalpha() and j - i < self.max_len:
                j += 1
                span = keys[i:j]
                if len(span) < 2:
                    continue
                for edge in self.lookup(span):
                    ends[j].append((i, *edge))
                    if j < n and keys[j] == " ":
                        ends[j + 1].append((i, *edge))
        return ends


def _match_case(word: str, typed: str) -> str:
    if word == typed.lower():
        return typed  # keep the user's own casing: YouTube, iPhone
    if typed.isupper() and len(typed) > 1:
        return word.upper()
    if typed[:1].isupper():
        return word[:1].upper() + word[1:]
    return word
