"""Code-switching check: Taiwan-style mixed sentences, plus pure-Chinese controls.

Each case is a list of segments; Chinese is typed as Daqian keys, ASCII as typed.
    uv run python -m zhime.mixed_eval
"""

from __future__ import annotations

import argparse
import json

from .decoder import Decoder
from .english import EnglishCosts
from .goldkeys import text_to_keys

MIXED = [
    ["我明天有", "meeting"], ["這個", "bug", "好煩"], ["幫我", "check", "一下"],
    ["等等要", "demo"], ["你有看那個", "YouTube", "影片嗎"], ["今天的", "deadline", "是幾點"],
    ["我覺得這個", "feature", "很好用"], ["這個", "API", "回傳錯誤"], ["我要去買", "iPhone"],
    ["這家餐廳", "CP", "值很高"], ["你的", "LINE", "是什麼"], ["等一下再", "call", "你"],
    ["這個", "project", "快完成了"], ["我剛剛有", "upload", "檔案"], ["你先", "commit", "再", "push"],
    ["我在寫", "code"], ["明天要交", "report"], ["他的", "email", "是多少"],
    ["我們用", "Google", "表單"], ["這個", "app", "很好用"], ["要不要", "update"],
    ["我的", "password", "忘記了"], ["你", "online", "嗎"], ["今天", "weekend", "耶"],
]
CHINESE = [
    ["今天好累喔"], ["我們下午開會討論"], ["他最近很忙"], ["要不要一起吃飯"], ["明天放假"],
    ["你吃飽了嗎"], ["我等一下打給你"], ["這部電影很好看"], ["我快到了"], ["謝謝你的幫忙"],
    ["好喔沒問題"], ["我先去洗澡"],
]


def case_keys(segments: list[str], d: Decoder) -> tuple[str, str] | None:
    keys, text = "", ""
    for seg in segments:
        if seg.isascii():
            keys += seg
        else:
            k = text_to_keys(seg, d.lex)
            if k is None:
                return None
            keys += k
        text += seg
    return keys, text


def evaluate(d: Decoder, cases: list[list[str]], show: bool = False) -> float:
    ok = 0
    for segs in cases:
        keys, gold = case_keys(segs, d)
        cands = d.decode(keys, 5)
        top = cands[0].text if cands else ""
        ok += top == gold
        if show and top != gold:
            print(f"   miss: {gold} <- {keys!r} got {top!r}")
    return round(100 * ok / len(cases), 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--switch", type=float, nargs="+", default=[EnglishCosts().switch])
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    d = Decoder()
    for sw in args.switch:
        d.english.costs.switch = sw
        print(json.dumps({"switch": sw, "mixed_top1": evaluate(d, MIXED, args.show),
                          "chinese_top1": evaluate(d, CHINESE, args.show)}), flush=True)


if __name__ == "__main__":
    main()
