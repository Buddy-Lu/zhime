"""IME session logic, independent of any Windows framework (so it is testable).

The front end feeds raw keys in; the session keeps the key buffer, the ranked
candidates, which one is highlighted, recent committed text (LM context) and
learns from what the user commits.
"""

from __future__ import annotations

import json
import math
import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .decoder import Candidate, Decoder

USER_DIR = Path(os.environ.get("APPDATA", Path.home())) / "zhime"
MAX_CANDIDATES = 8
CONTEXT_CHARS = 30


class UserModel:
    """Words the user has committed; boosts them next time. Stored as JSON."""

    def __init__(self, path: Path = USER_DIR / "user_words.json") -> None:
        self.path = path
        self.counts: dict[str, int] = {}
        try:
            self.counts = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass

    def bonus(self, word: str) -> float:
        c = self.counts.get(word)
        return 0.6 * math.log10(1 + c) if c else 0.0

    def learn(self, words: tuple[str, ...]) -> None:
        for w in words:
            self.counts[w] = self.counts.get(w, 0) + 1
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.counts, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass


class Engine:
    """Shared, loaded once per process.

    The Qwen reranker is opt-in (ZHIME_RERANK=1): ~0.5 s per keystroke on CPU, and on
    the GPU it holds VRAM that ComfyUI needs. The bigram LM in the decoder is always on.
    """

    def __init__(self, use_lm: bool = bool(os.environ.get("ZHIME_RERANK"))) -> None:
        self.user = UserModel()
        self.decoder = Decoder(user_bonus=self.user.bonus)
        self.reranker = None
        if use_lm:
            threading.Thread(target=self._load_lm, daemon=True).start()

    def _load_lm(self) -> None:
        try:
            from .rerank import Reranker
            self.reranker = Reranker()
        except Exception as e:  # the IME must keep working without the LM
            # stderr: stdout carries the PIME protocol
            print("zhime: LM unavailable:", e, file=sys.stderr, flush=True)

    def suggest(self, keys: str, context: str = "") -> list[Candidate]:
        cands = self.decoder.decode(keys, 10)
        rr = self.reranker
        if rr is not None and len(cands) > 1:
            cands = rr.rerank(cands, context)
        out: list[Candidate] = []
        seen: set[str] = set()
        for c in cands:
            if c.text not in seen:
                seen.add(c.text)
                out.append(c)
        if keys.isascii() and keys.isalpha() and keys not in seen:
            out.append(Candidate(-1e9, keys, (keys,), ("",)))  # keep exactly what I typed
        return out[:MAX_CANDIDATES]


@dataclass
class Session:
    engine: Engine
    keys: str = ""
    cands: list[Candidate] = field(default_factory=list)
    sel: int = 0
    context: str = ""

    @property
    def composing(self) -> bool:
        return bool(self.keys)

    @property
    def preview(self) -> str:
        """Inline text shown while typing: the highlighted candidate."""
        if not self.cands:
            return self.keys
        return self.cands[self.sel].text

    def type(self, ch: str) -> None:
        self.keys += ch
        self._refresh()

    def backspace(self) -> None:
        self.keys = self.keys[:-1]
        self._refresh()

    def clear(self) -> None:
        self.keys, self.cands, self.sel = "", [], 0

    def move(self, delta: int) -> None:
        if self.cands:
            self.sel = (self.sel + delta) % len(self.cands)

    def commit(self, index: int | None = None) -> str:
        if not self.keys:
            return ""
        if index is not None and 0 <= index < len(self.cands):
            self.sel = index
        chosen = self.cands[self.sel] if self.cands else None
        text = chosen.text if chosen else self.keys
        if chosen is not None:
            self.engine.user.learn(chosen.words)
        self.context = (self.context + text)[-CONTEXT_CHARS:]
        self.clear()
        return text

    def _refresh(self) -> None:
        self.sel = 0
        self.cands = self.engine.suggest(self.keys, self.context) if self.keys else []
