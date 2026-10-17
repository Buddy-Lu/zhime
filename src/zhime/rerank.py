"""Rerank decoder candidates with a small causal LM (context-aware scoring)."""

from __future__ import annotations

import math
import os

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from .decoder import Candidate

# Qwen3-0.6B-Base: 2x faster on CPU than Qwen3.5-0.8B-Base (whose accuracy is not yet measured).
DEFAULT_MODEL = os.environ.get("ZHIME_LM", "Qwen/Qwen3-0.6B-Base")
_LN10 = math.log(10)


class Reranker:
    # Weights tuned on the dev split (zhime.tune): LM 1.0, typo 2.5, lexicon 1.0.
    def __init__(self, model: str = DEFAULT_MODEL, lm_weight: float = 1.0,
                 typo_weight: float = 2.5, lex_weight: float = 1.0) -> None:
        torch.set_num_threads(os.cpu_count() // 2 or 1)
        self.tok = AutoTokenizer.from_pretrained(model)
        self.model = AutoModelForCausalLM.from_pretrained(model, dtype=torch.float32)
        self.model.eval()
        self.start = self.tok.eos_token or self.tok.bos_token
        self.lm_weight, self.typo_weight, self.lex_weight = lm_weight, typo_weight, lex_weight

    @torch.inference_mode()
    def lm_scores(self, texts: list[str], context: str = "") -> list[float]:
        """log10 P(text | context) for each text."""
        prefix_ids = self.tok(self.start + context, add_special_tokens=False)["input_ids"]
        seqs = [prefix_ids + self.tok(t, add_special_tokens=False)["input_ids"] for t in texts]
        width = max(map(len, seqs))
        pad = self.tok.pad_token_id if self.tok.pad_token_id is not None else 0
        ids = torch.full((len(seqs), width), pad, dtype=torch.long)
        mask = torch.zeros_like(ids)
        for r, s in enumerate(seqs):
            ids[r, : len(s)] = torch.tensor(s)
            mask[r, : len(s)] = 1
        logits = self.model(input_ids=ids, attention_mask=mask).logits.float()
        logp = torch.log_softmax(logits[:, :-1], dim=-1)
        target = ids[:, 1:]
        tok_lp = logp.gather(-1, target.unsqueeze(-1)).squeeze(-1)
        out = []
        for r, s in enumerate(seqs):
            span = tok_lp[r, len(prefix_ids) - 1 : len(s) - 1]
            out.append(span.sum().item() / _LN10)
        return out

    def rerank(self, cands: list[Candidate], context: str = "") -> list[Candidate]:
        if len(cands) <= 1:
            return cands
        lm = self.lm_scores([c.text for c in cands], context)
        for c, s in zip(cands, lm):
            c.score = (self.lm_weight * s - self.typo_weight * c.typo_cost
                       + self.lex_weight * (c.score + c.typo_cost))
        return sorted(cands, key=lambda c: -c.score)
