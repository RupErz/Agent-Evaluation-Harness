"""Baseline recording and regression detection.

Two decision surfaces (see docs/design.md for the full reasoning):

  * Per case  - Wilson score interval on the baseline proportion at n=k. Flag a
    case when the new pass count falls below the interval's lower bound. This is
    a TRIAGE FLAG, not a verdict: at k=5 it only detects large drops.

  * Suite     - a two-proportion z-test over total passes (n = k x case count).
    This is the number to trust for "did this change make things worse overall",
    because the interval is meaningfully tighter.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from .runner import CaseRun


def wilson_interval(passes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    p = passes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def two_proportion_z(pass1: int, n1: int, pass2: int, n2: int) -> tuple[float, float]:
    """Two-proportion z-test. Returns (z, two-sided p-value).

    Group 1 = baseline, group 2 = current. A large negative z means current is
    worse than baseline.
    """
    if n1 == 0 or n2 == 0:
        return (0.0, 1.0)
    p1, p2 = pass1 / n1, pass2 / n2
    pool = (pass1 + pass2) / (n1 + n2)
    se = math.sqrt(pool * (1 - pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return (0.0, 1.0)
    z = (p2 - p1) / se
    # two-sided p-value from the standard normal survival function
    p_value = math.erfc(abs(z) / math.sqrt(2))
    return (z, p_value)


def build_baseline(runs: list[CaseRun], model: str) -> dict:
    return {
        "meta": {"model": model, "date": date.today().isoformat(),
                 "k_by_case": {cr.case.id: cr.result.k for cr in runs}},
        "cases": {
            cr.case.id: {
                "pass_count": cr.result.pass_count,
                "k": cr.result.k,
                "failure_mode": cr.case.failure_mode,
            } for cr in runs
        },
    }


def write_baseline(path: Path, runs: list[CaseRun], model: str) -> None:
    Path(path).write_text(json.dumps(build_baseline(runs, model), indent=2) + "\n")


def load_baseline(path: Path) -> dict:
    return json.loads(Path(path).read_text())


@dataclass
class CaseComparison:
    case_id: str
    baseline_pass: int
    baseline_k: int
    current_pass: int
    current_k: int
    wilson_lo: float
    wilson_hi: float
    regressed: bool          # current rate below baseline Wilson lower bound
    note: str = ""


@dataclass
class SuiteComparison:
    baseline_total: int
    baseline_n: int
    current_total: int
    current_n: int
    z: float
    p_value: float
    regressed: bool          # significant AND in the worse direction
    cases: list[CaseComparison] = field(default_factory=list)


def compare(runs: list[CaseRun], baseline: dict, alpha: float = 0.05) -> SuiteComparison:
    b_cases = baseline["cases"]
    case_cmps: list[CaseComparison] = []
    b_total = c_total = b_n = c_n = 0

    for cr in runs:
        cur_pass, cur_k = cr.result.pass_count, cr.result.k
        c_total += cur_pass
        c_n += cur_k
        base = b_cases.get(cr.case.id)
        if base is None:
            case_cmps.append(CaseComparison(
                cr.case.id, 0, 0, cur_pass, cur_k, 0.0, 0.0, False,
                note="no baseline entry (new case)"))
            continue
        b_pass, b_k = base["pass_count"], base["k"]
        b_total += b_pass
        b_n += b_k
        lo, hi = wilson_interval(b_pass, b_k)
        cur_rate = cur_pass / cur_k if cur_k else 0.0
        regressed = cur_rate < lo - 1e-9
        case_cmps.append(CaseComparison(
            cr.case.id, b_pass, b_k, cur_pass, cur_k, lo, hi, regressed))

    z, p = two_proportion_z(b_total, b_n, c_total, c_n)
    suite_regressed = (p < alpha) and (c_total / max(c_n, 1) < b_total / max(b_n, 1))
    # Regressions first for the report.
    case_cmps.sort(key=lambda c: (not c.regressed, c.case_id))
    return SuiteComparison(b_total, b_n, c_total, c_n, z, p, suite_regressed, case_cmps)
