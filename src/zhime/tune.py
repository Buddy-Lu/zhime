"""Cache decoder candidates + LM scores, then grid-search the combination weights.

    uv run python -m zhime.tune --model Qwen/Qwen3-0.6B-Base
Dev split tunes the weights; the held-out test split reports the result.
"""

from __future__ import annotations

import argparse
import itertools
import json
import random

from .decoder import Decoder
from .evaluate import build_testset, char_errors, inject_typos
from .lexicon import ROOT

DEV = slice(0, 300)
TEST = slice(300, 800)


def collect(d: Decoder, rr, rows: list[dict], typos: int, seed: int = 11) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for row in rows:
        keys = inject_typos(row["keys"], typos, rng) if typos else row["keys"]
        cands = d.decode(keys, 10)
        lm = rr.lm_scores([c.text for c in cands]) if cands else []
        out.append({
            "gold": row["text"],
            "cands": [{"text": c.text, "lex": c.score + c.typo_cost, "typo": c.typo_cost, "lm": s}
                      for c, s in zip(cands, lm)],
        })
    return out


def score(items: list[dict], w_lm: float, w_typo: float, w_lex: float) -> dict:
    top1 = errs = chars = 0
    for it in items:
        chars += len(it["gold"])
        if not it["cands"]:
            errs += len(it["gold"])
            continue
        best = max(it["cands"], key=lambda c: w_lm * c["lm"] - w_typo * c["typo"] + w_lex * c["lex"])
        top1 += best["text"] == it["gold"]
        errs += char_errors(best["text"], it["gold"])
    n = len(items)
    return {"top1": round(100 * top1 / n, 1), "char_acc": round(100 * (1 - errs / chars), 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen3-0.6B-Base")
    ap.add_argument("--typos", type=int, nargs="+", default=[0, 1, 2])
    args = ap.parse_args()
    from .rerank import Reranker

    d = Decoder()
    rows = build_testset(d.lex, 800)
    rr = Reranker(args.model)
    cache = ROOT / f"data/cache-{args.model.replace('/', '_')}.json"
    data = {}
    for t in args.typos:
        data[t] = {"dev": collect(d, rr, rows[DEV], t), "test": collect(d, rr, rows[TEST], t, seed=12)}
        print(f"collected typos={t}", flush=True)
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    grid = list(itertools.product([1.0], [0.25, 0.5, 0.75, 1.0, 1.5, 2.0], [0.0, 0.25, 0.5, 1.0]))
    dev_all = [it for t in args.typos for it in data[t]["dev"]]
    best_w = max(grid, key=lambda w: score(dev_all, *w)["top1"])
    print("best weights (lm, typo, lex):", best_w)
    for t in args.typos:
        base = score(data[t]["test"], 0.0, 1.0, 1.0)  # decoder alone
        tuned = score(data[t]["test"], *best_w)
        print(json.dumps({"typos": t, "decoder_only": base, "with_lm": tuned}))


if __name__ == "__main__":
    main()
