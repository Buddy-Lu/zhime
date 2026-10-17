"""Typo-tolerant Zhuyin decoder.

keystrokes --(weighted edit distance against every valid syllable)--> syllable lattice
           --(lexicon lookup)--> word lattice
           --(k-best search: word bigram log10 prob minus typo cost)--> ranked sentences
"""

from __future__ import annotations

import heapq
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from .english import English
from .keyboard import TypoCosts, reading_to_keys
from .lexicon import Lexicon
from .ngram import BOS, EN, BigramLM


class _Node:
    __slots__ = ("children", "syllable", "depth")

    def __init__(self, depth: int) -> None:
        self.children: dict[str, _Node] = {}
        self.syllable: str | None = None
        self.depth = depth


@dataclass(order=True)
class Candidate:
    score: float
    text: str = field(compare=False)
    words: tuple[str, ...] = field(compare=False, default=())
    readings: tuple[str, ...] = field(compare=False, default=())
    typo_cost: float = field(compare=False, default=0.0)


@dataclass
class _Hyp:
    score: float
    words: tuple[str, ...]
    readings: tuple[str, ...]
    typo_cost: float
    last: int = 0  # bigram id of the last word


class Decoder:
    def __init__(self, lexicon: Lexicon | None = None, costs: TypoCosts | None = None,
                 words_per_reading: int = 6, beam: int = 12,
                 english: English | None | bool = True,
                 user_bonus: Callable[[str], float] | None = None,
                 ngram: BigramLM | None | bool = True,
                 ngram_weight: float = 1.0, lex_weight: float = 0.0) -> None:
        self.lex = lexicon or Lexicon.load()
        self.ngram = BigramLM.load() if ngram is True else (ngram or None)
        self.ngram_weight, self.lex_weight = ngram_weight, lex_weight
        self.user_bonus = user_bonus or (lambda word: 0.0)
        self.english = English() if english is True else (english or None)
        self.costs = costs or TypoCosts()
        self.words_per_reading = words_per_reading
        self.beam = beam
        self.root = _Node(0)
        self.max_keys = 0
        for syl in self.lex.syllables:
            keys = reading_to_keys(syl)
            self.max_keys = max(self.max_keys, len(keys))
            node = self.root
            for ch in keys:
                node = node.children.setdefault(ch, _Node(node.depth + 1))
            node.syllable = syl
        self._sub_cache: dict[tuple[str, str], float] = {}
        # syllable edges per (key window, window reaches buffer end), relative to the window
        self._memo: dict[tuple[str, bool], dict[tuple[int, str], float]] = {}

    # ---- syllable lattice -------------------------------------------------

    def _sub(self, intended: str, typed: str) -> float:
        key = (intended, typed)
        c = self._sub_cache.get(key)
        if c is None:
            c = self._sub_cache[key] = self.costs.sub(intended, typed)
        return c

    def syllable_edges(self, keys: str) -> list[dict[tuple[int, str], float]]:
        """edges[i][(j, syllable)] = cheapest cost of reading keys[i:j] as that syllable."""
        n = len(keys)
        edges: list[dict[tuple[int, str], float]] = [dict() for _ in range(n)]
        margin = self.costs.start_margin
        w = self.max_keys + 2
        for i in range(n):
            window = keys[i:i + w]
            reaches_end = i + len(window) == n
            memo_key = (window, reaches_end)
            rel = self._memo.get(memo_key)
            if rel is None:
                e: dict[tuple[int, str], float] = {}
                self._match_from(window, reaches_end, e)
                if e:
                    cutoff = min(e.values()) + margin
                    e = {k: v for k, v in e.items() if v <= cutoff}
                rel = e
                if len(self._memo) > 50000:
                    self._memo.clear()
                self._memo[memo_key] = rel
            edges[i] = {(i + j, syl): c for (j, syl), c in rel.items()}
        return edges

    def _match_from(self, s: str, reaches_end: bool, out: dict[tuple[int, str], float]) -> None:
        """Edges for the key window s, as (end offset within s, syllable) -> cost."""
        c = self.costs
        limit = c.syllable_limit
        L = len(s)
        ins = [c.ins(s[j], s[j - 1] if j else None, s[j + 1] if j + 1 < L else None)
               for j in range(L)]
        root_row = [0.0] * (L + 1)
        for j in range(1, L + 1):
            root_row[j] = root_row[j - 1] + ins[j - 1]
        # stack of (node, its row, parent row, char into node)
        stack: list[tuple[_Node, list[float], list[float] | None, str | None]] = [
            (self.root, root_row, None, None)]
        while stack:
            node, prev, grand, pch = stack.pop()
            for ch, child in node.children.items():
                dele = c.dele(ch)
                row = [0.0] * (L + 1)
                row[0] = prev[0] + dele
                best = row[0]
                for j in range(1, L + 1):
                    t = s[j - 1]
                    v = prev[j - 1] + self._sub(ch, t)
                    w = prev[j] + dele
                    if w < v:
                        v = w
                    w = row[j - 1] + ins[j - 1]
                    if w < v:
                        v = w
                    if (grand is not None and j >= 2 and ch != pch
                            and s[j - 2] == ch and s[j - 1] == pch):
                        w = grand[j - 2] + c.transpose
                        if w < v:
                            v = w
                    row[j] = v
                    if v < best:
                        best = v
                if best > limit:
                    continue
                if child.syllable is not None:
                    for j in range(1, L + 1):
                        if row[j] <= limit:
                            self._add(out, (j, child.syllable), row[j])
                if reaches_end and row[L] <= limit and child.syllable is None:
                    # Buffer ends mid-syllable: offer completions at a small cost per missing key.
                    self._complete(child, row[L], L, out)
                stack.append((child, row, prev, ch))

    def _complete(self, node: _Node, base: float, end: int,
                  out: dict[tuple[int, str], float]) -> None:
        stack = [node]
        while stack:
            nd = stack.pop()
            for child in nd.children.values():
                cost = base + (child.depth - node.depth) * self.costs.complete
                if child.syllable is not None:
                    self._add(out, (end, child.syllable), cost)
                stack.append(child)

    @staticmethod
    def _add(out: dict, key, cost: float) -> None:
        old = out.get(key)
        if old is None or cost < old:
            out[key] = cost

    # ---- word lattice + search -------------------------------------------

    def word_edges(self, keys: str) -> list[list[tuple[int, str, float]]]:
        """ends[j] = [(i, reading, typo_cost)] for lexicon readings spanning keys[i:j]."""
        n = len(keys)
        syl = [
            [(j, s, cost) for (j, s), cost in e.items()] for e in self.syllable_edges(keys)
        ]
        best: dict[tuple[int, int, str], float] = {}
        by_reading, prefixes = self.lex.by_reading, self.lex.prefixes
        max_syl = self.lex.max_syllables
        for i in range(n):
            stack = [(i, "", 0.0, 0)]
            while stack:
                pos, prefix, cost, k = stack.pop()
                if pos >= n:
                    continue
                for j, s, c in syl[pos]:
                    r = s if not prefix else prefix + "-" + s
                    total = cost + c
                    if r in by_reading:
                        key = (i, j, r)
                        if total < best.get(key, 1e9):
                            best[key] = total
                    if k + 1 < max_syl and r in prefixes:
                        stack.append((j, r, total, k + 1))
        ends: list[list[tuple[int, str, float]]] = [[] for _ in range(n + 1)]
        for (i, j, r), cost in best.items():
            ends[j].append((i, r, cost))
        return ends

    def decode(self, keys: str, k: int = 10) -> list[Candidate]:
        n = len(keys)
        if n == 0:
            return []
        ends = self.word_edges(keys)
        en_ends = self.english.edges(keys) if self.english else [[] for _ in range(n + 1)]
        ng = self.ngram
        bos = ng.ids[BOS] if ng else 0
        en_id = ng.ids[EN] if ng else 0
        lex_w = self.lex_weight if ng else 1.0
        B = self.beam
        neg = -1e30

        # Each position's beam as arrays, so every extension ending at j is scored
        # in one (edges x beam) matrix operation instead of a Python loop.
        bscore = np.full((n + 1, B), neg)
        blast = np.zeros((n + 1, B), np.int64)
        beams: list[list[_Hyp]] = [[] for _ in range(n + 1)]
        beams[0] = [_Hyp(0.0, (), (), 0.0, bos)]
        bscore[0, 0], blast[0, 0] = 0.0, bos
        for j in range(1, n + 1):
            starts: list[int] = []
            parts: list[float] = []   # edge score without the bigram term
            wids: list[int] = []
            info: list[tuple[str, str, float]] = []
            for i, reading, typo in ends[j]:
                if not beams[i]:
                    continue
                for word, logp in self.lex.by_reading[reading][: self.words_per_reading]:
                    starts.append(i)
                    parts.append(lex_w * logp + self.user_bonus(word) - typo)
                    wids.append(ng.word_id(word) if ng else 0)
                    info.append((word, reading, typo))
            for i, word, logp, penalty in en_ends[j]:
                if not beams[i]:
                    continue
                # P(<en> | prev) * P(word | English) when the bigram model is on
                starts.append(i)
                parts.append(logp + self.user_bonus(word) - penalty)
                wids.append(en_id)
                info.append((word, "", penalty))
            if not starts:
                continue
            st = np.asarray(starts)
            scores = bscore[st] + np.asarray(parts)[:, None]
            if ng is not None:
                lp = ng.logp_many(blast[st].ravel(), np.repeat(np.asarray(wids), B))
                scores += self.ngram_weight * lp.reshape(len(starts), B)
            flat = scores.ravel()
            take = min(flat.size, B * 3)
            top = np.argpartition(-flat, take - 1)[:take] if take < flat.size else np.arange(flat.size)
            cands = []
            for t in top[flat[top] > neg / 2]:
                e, b = divmod(int(t), B)
                h = beams[starts[e]][b]
                word, reading, typo = info[e]
                cands.append(_Hyp(float(flat[t]), h.words + (word,), h.readings + (reading,),
                                  h.typo_cost + typo, wids[e]))
            beams[j] = self._prune(cands, B)
            for b, h in enumerate(beams[j]):
                bscore[j, b], blast[j, b] = h.score, h.last
        return [Candidate(h.score, join_words(h.words), h.words, h.readings, h.typo_cost)
                for h in beams[n][:k]]

    @staticmethod
    def _prune(cands: list[_Hyp], k: int) -> list[_Hyp]:
        seen: set[str] = set()
        out: list[_Hyp] = []
        for h in heapq.nlargest(k * 3, cands, key=lambda h: h.score):
            text = join_words(h.words)
            if text in seen:
                continue
            seen.add(text)
            out.append(h)
            if len(out) == k:
                break
        return out


def join_words(words: tuple[str, ...]) -> str:
    """Concatenate, putting a space only between two adjacent English words."""
    out = ""
    for w in words:
        if out and out[-1].isascii() and out[-1].isalnum() and w[:1].isascii() and w[:1].isalnum():
            out += " "
        out += w
    return out
