"""Turn Traditional Chinese text into the Daqian keystrokes that type it.

Used to build test sets. Segments the text into lexicon words (best total
log-prob) so heteronyms get their in-word reading, e.g. 快樂 -> ㄌㄜˋ not ㄩㄝˋ.
"""

from __future__ import annotations

from .keyboard import reading_to_keys
from .lexicon import Lexicon


def text_to_readings(text: str, lex: Lexicon, max_len: int = 8) -> list[str] | None:
    n = len(text)
    best: list[tuple[float, list[str]] | None] = [None] * (n + 1)
    best[0] = (0.0, [])
    for j in range(1, n + 1):
        for i in range(max(0, j - max_len), j):
            if best[i] is None:
                continue
            readings = lex.by_word.get(text[i:j])
            if not readings:
                continue
            reading, logp = readings[0]
            score = best[i][0] + logp
            if best[j] is None or score > best[j][0]:
                best[j] = (score, best[i][1] + reading.split("-"))
    return best[n][1] if best[n] else None


def text_to_keys(text: str, lex: Lexicon) -> str | None:
    readings = text_to_readings(text, lex)
    if readings is None:
        return None
    return "".join(reading_to_keys(r) for r in readings)
