"""Accuracy harness: real zh-TW sentences -> Daqian keys -> injected typos -> decode.

    uv run python -m zhime.evaluate --n 500 --typos 0 1 2
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import time
from pathlib import Path

from .keyboard import KEY_TO_BPMF, TONE_KEYS, key_distance
from .lexicon import ROOT, Lexicon
from .goldkeys import text_to_keys

CV_DIR = ROOT / "third_party/common-voice/server/data/zh-TW"
TESTSET = ROOT / "data/testset.jsonl"
_CJK_ONLY = re.compile(r"^[一-鿿]+$")
_LAYOUT_KEYS = [k for k in KEY_TO_BPMF if k != " "]


def build_testset(lex: Lexicon, n: int, seed: int = 7) -> list[dict]:
    sentences: set[str] = set()
    for f in CV_DIR.glob("*.txt"):
        for line in f.read_text(encoding="utf-8").splitlines():
            s = re.sub(r"[，。！？、；：「」『』（）,.!?\s]", "", line.strip())
            if 4 <= len(s) <= 20 and _CJK_ONLY.match(s):
                sentences.add(s)
    pool = sorted(sentences)
    random.Random(seed).shuffle(pool)
    out = []
    for s in pool:
        keys = text_to_keys(s, lex)
        if keys:
            out.append({"text": s, "keys": keys})
        if len(out) == n:
            break
    TESTSET.parent.mkdir(parents=True, exist_ok=True)
    with TESTSET.open("w", encoding="utf-8") as f:
        for row in out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return out


def neighbours(key: str) -> list[str]:
    if key in TONE_KEYS:
        return [t for t in TONE_KEYS if t != key]
    return [k for k in _LAYOUT_KEYS if k != key and key_distance(k, key) <= 1.25]


def inject_typos(keys: str, count: int, rng: random.Random) -> str:
    """Realistic slips: neighbouring key, missed tone, missed key, doubled neighbour, swap."""
    k = list(keys)
    for _ in range(count):
        op = rng.choices(["adjacent", "drop_tone", "drop", "extra", "swap"],
                         weights=[45, 15, 10, 15, 15])[0]
        if op == "drop_tone":
            tones = [p for p, ch in enumerate(k) if ch in TONE_KEYS]
            if tones:
                del k[rng.choice(tones)]
                continue
            op = "adjacent"
        p = rng.randrange(len(k))
        if op == "adjacent" and neighbours(k[p]):
            k[p] = rng.choice(neighbours(k[p]))
        elif op == "drop" and len(k) > 1:
            del k[p]
        elif op == "extra" and neighbours(k[p]):
            k.insert(p + rng.randint(0, 1), rng.choice(neighbours(k[p])))
        elif op == "swap" and p + 1 < len(k) and k[p] != k[p + 1]:
            k[p], k[p + 1] = k[p + 1], k[p]
    return "".join(k)


def char_errors(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]


def run(decode, rows: list[dict], typos: int, seed: int = 11, show: int = 0) -> dict:
    rng = random.Random(seed)
    top1 = top5 = errs = chars = 0
    lat = []
    misses = []
    for row in rows:
        keys = inject_typos(row["keys"], typos, rng) if typos else row["keys"]
        t = time.perf_counter()
        cands = decode(keys)
        lat.append((time.perf_counter() - t) * 1000)
        texts = [c.text for c in cands]
        best = texts[0] if texts else ""
        top1 += best == row["text"]
        top5 += row["text"] in texts[:5]
        errs += char_errors(best, row["text"])
        chars += len(row["text"])
        if best != row["text"]:
            misses.append((row["text"], keys, best))
    n = len(rows)
    for m in misses[:show]:
        print("   miss:", m)
    return {
        "typos": typos, "n": n,
        "top1": round(100 * top1 / n, 1), "top5": round(100 * top5 / n, 1),
        "char_acc": round(100 * (1 - errs / chars), 1),
        "ms_mean": round(statistics.mean(lat), 1),
        "ms_p95": round(sorted(lat)[int(0.95 * n) - 1], 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], default="dev",
                    help="dev = sentences 0-299 (tune on these), test = 300-799 (report these)")
    ap.add_argument("--typos", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--show", type=int, default=0)
    ap.add_argument("--no-ngram", action="store_true")
    ap.add_argument("--ngram-weight", type=float, default=1.0)
    ap.add_argument("--lex-weight", type=float, default=0.0)
    ap.add_argument("--beam", type=int, default=12)
    ap.add_argument("--wpr", type=int, default=6, help="words kept per reading")
    ap.add_argument("--rerank", action="store_true", help="rerank with the neural LM")
    args = ap.parse_args()

    from .decoder import Decoder
    d = Decoder(ngram=not args.no_ngram, ngram_weight=args.ngram_weight,
                lex_weight=args.lex_weight, beam=args.beam, words_per_reading=args.wpr)
    rows = build_testset(d.lex, 800)
    rows = rows[:300] if args.split == "dev" else rows[300:800]
    decode = lambda k: d.decode(k, 10)
    if args.rerank:
        from .rerank import Reranker
        rr = Reranker()
        decode = lambda k: rr.rerank(d.decode(k, 10))
    for t in args.typos:
        seed = 11 if args.split == "dev" else 12
        print(json.dumps(run(decode, rows, t, seed=seed, show=args.show), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
