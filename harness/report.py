"""Render a single static HTML report per run via Jinja2.

Design goal: someone reads a red row and knows what broke without rerunning
anything. Failures sort to the top; the full trace of the first failing
repetition is expanded inline.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .baseline import SuiteComparison, wilson_interval
from .config import AGENT_MODEL, FROZEN_NOW, JUDGE_MODEL, TEMPERATURE
from .runner import CaseRun

_ENV = Environment(
    loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
    autoescape=select_autoescape(["html"]),
)
_OUTCOME_ORDER = {"fail": 0, "flaky": 1, "pass": 2}


def _judged_assertion(name: str) -> bool:
    return name.startswith("JudgedBy(")


def _case_view(cr: CaseRun) -> dict:
    res = cr.result
    per_assertion = [
        {"name": n, "rate": r, "judged": _judged_assertion(n)}
        for n, r in res.per_assertion_pass_rate.items()
    ]
    first_fail = None
    if res.first_failure_rep >= 0:
        rep = res.first_failure_rep
        tr = cr.traces[rep]
        first_fail = {
            "rep": rep,
            "termination_reason": tr.termination_reason,
            "total_steps": tr.total_steps,
            "tokens_in": tr.tokens_in,
            "tokens_out": tr.tokens_out,
            "input": tr.input,
            "final_output": tr.final_output,
            "parse_error": tr.parse_error,
            "tool_calls": [
                {
                    "step": tc.step,
                    "tool_name": tc.tool_name,
                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    "result": json.dumps(tc.result, ensure_ascii=False, default=str)[:1200],
                    "error": tc.error,
                    "duration_ms": tc.duration_ms,
                }
                for tc in tr.tool_calls
            ],
            "assertions": [
                {"name": a.name, "passed": a.passed, "message": a.message}
                for a in cr.per_rep_results[rep]
            ],
        }
    return {
        "id": res.case_id,
        "failure_mode": res.failure_mode,
        "notes": res.notes,
        "outcome": res.outcome,
        "pass_count": res.pass_count,
        "k": res.k,
        "pass_rate": res.pass_rate,
        "per_assertion": per_assertion,
        "first_fail": first_fail,
    }


def build_view(runs: list[CaseRun], k: int,
               comparison: Optional[SuiteComparison] = None) -> dict:
    cases = sorted((_case_view(cr) for cr in runs),
                   key=lambda c: (_OUTCOME_ORDER[c["outcome"]], c["id"]))
    counts = {o: sum(1 for c in cases if c["outcome"] == o)
              for o in ("pass", "flaky", "fail")}
    suite_pass = sum(cr.result.pass_count for cr in runs)
    suite_n = sum(cr.result.k for cr in runs)
    lo, hi = wilson_interval(suite_pass, suite_n)
    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model": AGENT_MODEL,
        "judge_model": JUDGE_MODEL,
        "temperature": TEMPERATURE,
        "frozen_now": FROZEN_NOW,
        "k": k,
        "counts": counts,
        "suite_pass": suite_pass,
        "suite_n": suite_n,
        "suite_rate": round(suite_pass / suite_n, 3) if suite_n else 0.0,
        "suite_ci": (round(lo, 3), round(hi, 3)),
        "cases": cases,
        "comparison": comparison,
    }


def render(runs: list[CaseRun], k: int, out_path: Path,
           comparison: Optional[SuiteComparison] = None) -> Path:
    view = build_view(runs, k, comparison)
    html = _ENV.get_template("report.html.j2").render(**view)
    Path(out_path).write_text(html)
    return Path(out_path)
