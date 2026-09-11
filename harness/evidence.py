"""Build the shippable report: python -m harness.evidence

Produces one report that shows BOTH halves of the story:
  * the baseline suite (the agent behaves), rebuilt for free from recorded traces
  * a "proof the tests catch failures" section that runs the mutations live and
    shows which cases turn red, with one real failing trace expanded.

Fifteen greens alone demonstrate nothing; this report demonstrates that breaking
the agent turns specific cases red. Writes to sample_run/report.html (the
committed, deployed report) and a timestamped runs/ copy.
"""
from __future__ import annotations

from pathlib import Path

from . import report as report_mod
from .cases import BY_ID, CASES
from .fixture.db import FixtureDB
from .mutate import MUTATIONS
from .report import _trace_detail
from .runner import CaseRun, _aggregate, run_suite
from .trace import new_run_dir, read_traces

SAMPLE = Path(__file__).resolve().parent.parent / "sample_run"


def caseruns_from_traces(path: Path) -> list[CaseRun]:
    """Rebuild CaseRun objects from recorded traces (no agent calls).

    Note: a JudgedBy assertion re-invokes the judge model, so this is not fully
    free for the one judged case - but the agent itself is never re-run.
    """
    traces = read_traces(path)
    groups: dict[str, list] = {}
    for t in traces:
        groups.setdefault(t.case_id, []).append(t)
    db = FixtureDB()
    runs: list[CaseRun] = []
    try:
        for case in CASES:
            trs = sorted(groups.get(case.id, []), key=lambda t: t.repetition)
            if not trs:
                continue
            per_rep = [[a.check(tr, db) for a in case.assertions] for tr in trs]
            result = _aggregate(case, len(trs), per_rep)
            runs.append(CaseRun(case=case, traces=trs, per_rep_results=per_rep, result=result))
    finally:
        db.close()
    return runs


def run_mutation_evidence(k: int = 2) -> dict:
    """Run each mutation on its target cases and assemble the evidence block."""
    mutations = []
    featured = None
    for m in MUTATIONS:
        cases = [BY_ID[t] for t in m.targets]
        cruns = run_suite(cases, k, **m.kwargs)
        mcases = [{
            "id": cr.result.case_id,
            "red": cr.result.outcome != "pass",
            "pass_count": cr.result.pass_count,
            "k": cr.result.k,
        } for cr in cruns]
        caught = m.expect_catch and all(c["red"] for c in mcases)
        mutations.append({
            "description": m.description,
            "caught": caught,
            "model_intrinsic": not m.expect_catch,
            "note": m.note,
            "cases": mcases,
        })
        # Feature the first genuinely-caught failure with a usable trace.
        if featured is None and caught:
            for cr in cruns:
                if cr.result.first_failure_rep >= 0:
                    rep = cr.result.first_failure_rep
                    featured = {
                        "id": cr.result.case_id,
                        "broke": m.description,
                        "detail": _trace_detail(cr.traces[rep], cr.per_rep_results[rep]),
                    }
                    break
    return {"mutations": mutations, "featured": featured}


def main(k_baseline_traces: Path = SAMPLE / "traces.jsonl") -> int:
    print("Rebuilding baseline from recorded traces ...")
    runs = caseruns_from_traces(k_baseline_traces)
    k = runs[0].result.k if runs else 0
    print(f"  {len(runs)} cases, k={k}")
    print("Running mutation evidence (this calls the model) ...")
    evidence = run_mutation_evidence(k=2)
    for m in evidence["mutations"]:
        red = [c["id"] for c in m["cases"] if c["red"]]
        tag = "caught" if m["caught"] else ("model-intrinsic" if m["model_intrinsic"] else "MISSED")
        print(f"  [{tag}] {m['description']}: red={red}")

    run_dir = new_run_dir()
    for out in (run_dir / "report.html", SAMPLE / "report.html"):
        report_mod.render(runs, k, out, comparison=None, mutation_evidence=evidence)
    print(f"\nreport written to {run_dir / 'report.html'} and {SAMPLE / 'report.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
