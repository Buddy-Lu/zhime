"""Word bigram LM (interpolated Kneser-Ney) over the lexicon's words.

Built from PTT (casual Taiwan register) + zh-TW Wikipedia. Every English word
in the corpus becomes the token <en>, so the model learns where people switch
to English. Build:

    uv run python -m zhime.ngram build
"""

from __future__ import annotations

import itertools
import json
import math
import pickle
import re
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

from .lexicon import ROOT, Lexicon

MODEL = ROOT / "data/bigram.pkl"
BOS, EN = "<s>", "<en>"
DISCOUNT = 0.75
MIN_BIGRAM_COUNT = 2

_TOKEN = re.compile(r"[一-鿿]+|[A-Za-z]+")
_MAX_WORD = 8

_best: dict[str, float] = {}
_ids: dict[str, int] = {}
_SHIFT = 20  # word ids < 2**20; a bigram key is (prev_id << 20) | word_id


def vocabulary(lex: Lexicon) -> list[str]:
    return [BOS, EN] + sorted(lex.by_word)


def _init_worker() -> None:
    global _best, _ids
    lex = Lexicon.load()
    _best = {w: r[0][1] for w, r in lex.by_word.items() if len(w) <= _MAX_WORD}
    _ids = {w: i for i, w in enumerate(vocabulary(lex))}


def segment(run: str, best: dict[str, float]) -> list[str] | None:
    """Max-probability split of a CJK run into lexicon words (None if impossible)."""
    n = len(run)
    score = [-1e18] * (n + 1)
    back = [0] * (n + 1)
    score[0] = 0.0
    for j in range(1, n + 1):
        for i in range(max(0, j - _MAX_WORD), j):
            if score[i] <= -1e17:
                continue
            lp = best.get(run[i:j])
            if lp is not None and score[i] + lp > score[j]:
                score[j], back[j] = score[i] + lp, i
    if score[n] <= -1e17:
        return None
    out = []
    j = n
    while j > 0:
        out.append(run[back[j]:j])
        j = back[j]
    return out[::-1]


def _count(lines: list[str]):
    """-> (bigram keys, counts) as numpy arrays for this chunk."""
    import numpy as np

    bi: Counter = Counter()
    bos, en = _ids[BOS], _ids[EN]
    for text in lines:
        for sentence in _SENT.split(text):
            prev = bos
            for m in _TOKEN.finditer(sentence):
                tok = m.group()
                if tok.isascii():
                    ids = [en]
                else:
                    words = segment(tok, _best)
                    if words is None:  # a character the lexicon lacks: restart the sentence
                        prev = bos
                        continue
                    ids = [_ids[w] for w in words]
                for w in ids:
                    bi[(prev << _SHIFT) | w] += 1
                    prev = w
    keys = np.fromiter(bi.keys(), dtype=np.int64, count=len(bi))
    counts = np.fromiter(bi.values(), dtype=np.int64, count=len(bi))
    return keys, counts


_SENT = re.compile(r"[。！？!?，,；;：:、「」『』（）()\[\]【】…~～\s]+")


def _corpus_lines():
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download

    ptt = hf_hub_download("yuhuanstudio/PTT-pretrain-zhtw", "ppt_pretrain.json", repo_type="dataset")
    # Stream it: the file is a pretty-printed list with one `"text": "..."` per line;
    # json.load of all 850 MB would take several GB of RAM.
    with open(ptt, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith('"text":'):
                text = json.loads(line[len('"text":'):].strip().rstrip(","))
                yield text.split("內文:", 1)[-1]  # drop the author/board/title header
    for name in ["data/train-00001-of-00044-d8fed27bdaea9d3a.parquet",
                 "data/train-00002-of-00044-6313f560cbe36f40.parquet",
                 "data/train-00003-of-00044-823689c957a6e9cb.parquet"]:
        path = hf_hub_download("zetavg/zh-tw-wikipedia", name, repo_type="dataset")
        table = pq.read_table(path)
        col = "markdown" if "markdown" in table.column_names else "text"
        for text in table.column(col).to_pylist():
            if text:
                yield text


def _chunks(it, size: int):
    buf = []
    for x in it:
        buf.append(x)
        if len(buf) == size:
            yield buf
            buf = []
    if buf:
        yield buf


def build() -> None:
    import os

    parts_k, parts_c = [], []
    tokens = 0
    workers = min(6, os.cpu_count() or 1)  # each worker holds the lexicon
    chunks = _chunks(_corpus_lines(), 2000)
    done = 0
    with Pool(workers, initializer=_init_worker) as pool:
        while True:
            # Feed a bounded batch: imap would read the whole corpus into its task queue.
            batch = list(itertools.islice(chunks, workers * 4))
            if not batch:
                break
            for keys, counts in pool.imap_unordered(_count, batch):
                parts_k.append(keys)
                parts_c.append(counts)
                tokens += int(counts.sum())
            done += len(batch)
            merged_k, merged_c = _merge(parts_k, parts_c)
            parts_k, parts_c = [merged_k], [merged_c]
            print(f"chunk {done}: {tokens:,} tokens, {len(merged_k):,} bigram types", flush=True)
    keys, counts = _merge(parts_k, parts_c)
    lm = BigramLM.estimate(keys, counts, vocabulary(Lexicon.load()))
    lm.save()
    print(f"saved {MODEL}: {tokens:,} tokens, {len(lm.keys):,} bigrams kept of {len(keys):,}")


def _merge(parts_k, parts_c):
    import numpy as np

    keys = np.concatenate(parts_k)
    counts = np.concatenate(parts_c)
    uniq, inv = np.unique(keys, return_inverse=True)
    return uniq, np.bincount(inv, weights=counts).astype(np.int64)


class BigramLM:
    """log10 P(w | prev) = log10( max(c(prev,w)-D, 0)/c(prev) + lambda(prev) * P_cont(w) )."""

    def __init__(self) -> None:
        import numpy as np

        self.ids: dict[str, int] = {}
        # Compact storage (~12 bytes per bigram) so the always-running IME stays small:
        self.keys = np.zeros(0, np.int64)    # sorted (prev_id << 20) | word_id
        self.vals = np.zeros(0, np.float32)  # discounted part max(c-D, 0) / c(prev)
        self.lam = np.zeros(0, np.float32)   # backoff mass per history id (-1 = never a history)
        self.cont = np.zeros(0, np.float32)  # continuation probability per word id
        self.floor = 1e-9

    @classmethod
    def estimate(cls, keys, counts, vocab: list[str]) -> "BigramLM":
        import numpy as np

        lm = cls()
        lm.ids = {w: i for i, w in enumerate(vocab)}
        size = len(vocab)
        prev = keys >> _SHIFT
        word = keys & ((1 << _SHIFT) - 1)
        hist_count = np.bincount(prev, weights=counts, minlength=size)
        hist_types = np.bincount(prev, minlength=size)
        cont_types = np.bincount(word, minlength=size)
        total = cont_types.sum()
        lm.floor = 0.5 / total
        lm.cont = np.maximum(cont_types / total, lm.floor).astype(np.float32)
        with np.errstate(divide="ignore", invalid="ignore"):
            lam = np.where(hist_count > 0, DISCOUNT * hist_types / hist_count, -1.0)
        lm.lam = lam.astype(np.float32)
        keep = counts >= MIN_BIGRAM_COUNT
        lm.keys = keys[keep]  # np.unique output: already sorted
        lm.vals = ((counts[keep] - DISCOUNT) / hist_count[prev[keep]]).astype(np.float32)
        return lm

    def word_id(self, word: str) -> int:
        """Id for scoring; ASCII words share the <en> id, unknown words get -1."""
        i = self.ids.get(word)
        if i is None:
            return self.ids[EN] if word.isascii() else -1
        return i

    def logp(self, prev: int, word: int) -> float:
        pc = float(self.cont[word]) if word >= 0 else self.floor
        lam = float(self.lam[prev]) if prev >= 0 else -1.0
        if lam < 0:
            return math.log10(pc)
        key = (prev << _SHIFT) | word if word >= 0 else -1
        i = int(self.keys.searchsorted(key))
        disc = float(self.vals[i]) if i < len(self.keys) and self.keys[i] == key else 0.0
        return math.log10(disc + lam * pc)

    def logp_many(self, prev, word):
        """Vectorized logp over numpy int arrays (word id -1 = unknown word)."""
        import numpy as np

        known = word >= 0
        w = np.where(known, word, 0)
        pc = np.where(known, self.cont[w], self.floor).astype(np.float64)
        lam = self.lam[prev].astype(np.float64)
        key = np.where(known, (prev.astype(np.int64) << _SHIFT) | w, -1)
        idx = np.minimum(self.keys.searchsorted(key), len(self.keys) - 1)
        disc = np.where(self.keys[idx] == key, self.vals[idx], 0.0)
        return np.log10(np.where(lam < 0, pc, disc + lam * pc))

    _FIELDS = ("keys", "vals", "lam", "cont", "floor")

    def save(self) -> None:
        # Plain data only: pickling the instance ties the file to the module path it was built from.
        vocab = sorted(self.ids, key=self.ids.get)
        data = {"vocab": vocab, **{k: getattr(self, k) for k in self._FIELDS}}
        with MODEL.open("wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls) -> "BigramLM | None":
        if not MODEL.exists():
            return None
        with MODEL.open("rb") as f:
            data = pickle.load(f)
        lm = cls()
        lm.ids = {w: i for i, w in enumerate(data["vocab"])}
        for k in cls._FIELDS:
            setattr(lm, k, data[k])
        return lm


if __name__ == "__main__":
    if sys.argv[1:] == ["build"]:
        build()
