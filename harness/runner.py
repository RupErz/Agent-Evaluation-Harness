"""Run cases k times, evaluate assertions, aggregate to CaseResult.

Agent invocations run concurrently on a bounded worker pool (each with its own
DB connection, since sqlite connections are not shareable across threads).
Assertions are evaluated single-threaded afterwards against one eval DB.

An exception inside a run is already caught by run_agent (termination_reason=
"error"); such a repetition simply fails its assertions. One crashed run never
kills the suite.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from .agent import run_agent
from .assertions import AssertionResult
from .cases import Case
from .config import AGENT_MODEL, STEP_CAP
from .fixture.db import FixtureDB
from .models import CaseResult, Trace
from .tools import ToolBox


@dataclass
class CaseRun:
    """Everything produced for one case: raw traces + per-rep assertion results."""
    case: Case
    traces: list[Trace]
    per_rep_results: list[list[AssertionResult]]
    result: CaseResult


def run_case(case: Case, k: int, *, model: str = AGENT_MODEL,
             system_prompt=None, max_workers: int = 4, stale_tools: bool = False,
             step_cap_override: int = None, tools=None) -> CaseRun:
    traces: list[Trace] = [None] * k  # type: ignore
    # Effective cap: a mutation override wins, else the case's own cap, else global.
    effective_cap = step_cap_override or case.step_cap or STEP_CAP

    def worker(rep: int) -> Trace:
        db = FixtureDB()
        try:
            return run_agent(case.input, ToolBox(db, stale=stale_tools),
                             case_id=case.id, repetition=rep, model=model,
                             system_prompt=system_prompt, step_cap=effective_cap,
                             tools=tools)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(worker, rep): rep for rep in range(k)}
        for f in as_completed(futs):
            traces[futs[f]] = f.result()

    # Evaluate assertions single-threaded against one shared eval DB.
    eval_db = FixtureDB()
    per_rep: list[list[AssertionResult]] = []
    try:
        for tr in traces:
            per_rep.append([a.check(tr, eval_db) for a in case.assertions])
    finally:
        eval_db.close()

    result = _aggregate(case, k, per_rep)
    return CaseRun(case=case, traces=traces, per_rep_results=per_rep, result=result)


def _aggregate(case: Case, k: int, per_rep: list[list[AssertionResult]]) -> CaseResult:
    rep_passed = [all(r.passed for r in reps) for reps in per_rep]
    pass_count = sum(rep_passed)
    outcome = "pass" if pass_count == k else ("fail" if pass_count == 0 else "flaky")

    # Per-assertion pass rate across reps.
    names = [a.name for a in case.assertions]
    per_assertion: dict[str, float] = {}
    for i, name in enumerate(names):
        passed = sum(1 for reps in per_rep if reps[i].passed)
        per_assertion[name] = round(passed / k, 3) if k else 0.0

    first_fail = next((i for i, ok in enumerate(rep_passed) if not ok), -1)
    return CaseResult(
        case_id=case.id, failure_mode=case.failure_mode, notes=case.notes, k=k,
        outcome=outcome, pass_count=pass_count,
        pass_rate=round(pass_count / k, 3) if k else 0.0,
        per_assertion_pass_rate=per_assertion, first_failure_rep=first_fail,
    )


def run_suite(cases: list[Case], k: int, *, model: str = AGENT_MODEL,
              system_prompt=None, max_workers: int = 4, stale_tools: bool = False,
              step_cap_override: int = None, tools=None) -> list[CaseRun]:
    return [run_case(c, k, model=model, system_prompt=system_prompt,
                     max_workers=max_workers, stale_tools=stale_tools,
                     step_cap_override=step_cap_override, tools=tools) for c in cases]
