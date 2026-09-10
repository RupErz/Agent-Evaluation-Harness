"""LLM-judge helper for the single non-deterministic assertion type.

Pinned to JUDGE_MODEL (separate from the agent model, recorded separately). The
rubric must be answerable YES/NO; we return a bool. The caller runs this k times
and takes majority (see JudgedBy).
"""
from __future__ import annotations

from .agent import get_client
from .config import JUDGE_MODEL, sampling_extra_body
from .models import Trace

_TEMPLATE = """You are grading a personal-finance assistant's answer against a binary rubric.
Answer with exactly one word: YES or NO.

Rubric (answer YES only if fully satisfied): {rubric}

The assistant's final answer was:
---
{answer}
---

Does the answer satisfy the rubric? Reply YES or NO only."""


def judge_binary(rubric: str, trace: Trace, model: str = JUDGE_MODEL) -> bool:
    client = get_client()
    prompt = _TEMPLATE.format(rubric=rubric, answer=trace.final_output or "(no answer)")
    resp = client.messages.create(
        model=model,
        max_tokens=8,
        messages=[{"role": "user", "content": prompt}],
        extra_body=sampling_extra_body(model, 0),
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    return text.strip().upper().startswith("YES")
