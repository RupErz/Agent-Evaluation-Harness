"""CLI entry point: python -m harness.run

    python -m harness.run --k 5 --cases all
    python -m harness.run --k 1 --cases scope,injection
    python -m harness.run --k 5 --compare-baseline baseline.json
    python -m harness.run --k 5 --write-baseline baseline.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import report as report_mod
from .baseline import compare, load_baseline, write_baseline
from .cases import select
from .config import AGENT_MODEL, DEFAULT_K, FROZEN_NOW, TEMPERATURE
from .runner import CaseRun, run_suite
from .trace import new_run_dir, write_traces

_BADGE = {"pass": "PASS ", "flaky": "FLAKY", "fail": "FAIL "}


def _print_summary(runs: list[CaseRun]) -> None:
    print("\n" + "=" * 72)
    print(f"model={AGENT_MODEL}  temp={TEMPERATURE}  frozen_now={FROZEN_NOW}")
    print("=" * 72)
    order = {"fail": 0, "flaky": 1, "pass": 2}
    for cr in sorted(runs, key=lambda r: order[r.result.outcome]):
        res = cr.result
        print(f"\n[{_BADGE[res.outcome]}] {res.case_id}  ({res.failure_mode})  "
              f"{res.pass_count}/{res.k}")
        for name, rate in res.per_assertion_pass_rate.items():
            mark = "ok" if rate == 1.0 else ("--" if rate == 0.0 else "~~")
            print(f"        [{mark}] {rate:>4.0%}  {name}")
        if res.first_failure_rep >= 0:
            tr = cr.traces[res.first_failure_rep]
            print(f"        first failing rep #{res.first_failure_rep}: "
                  f"termination={tr.termination_reason}, "
                  f"tools={[t.tool_name for t in tr.tool_calls]}")
            if tr.parse_error:
                print(f"          parse_error: {tr.parse_error}")
    totals = {k: sum(1 for r in runs if r.result.outcome == k)
              for k in ("pass", "flaky", "fail")}
    print("\n" + "-" * 72)
    print(f"pass={totals['pass']}  flaky={totals['flaky']}  fail={totals['fail']}  "
          f"(suite pass rate "
          f"{sum(r.result.pass_count for r in runs)}/{sum(r.result.k for r in runs)})")
    print("-" * 72)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="harness.run")
    p.add_argument("--k", type=int, default=DEFAULT_K, help="repetitions per case")
    p.add_argument("--cases", default="all",
                   help="'all' or comma list of ids / failure-mode letters / slugs")
    p.add_argument("--workers", type=int, default=4, help="bounded concurrency")
    p.add_argument("--write-baseline", metavar="PATH", default=None,
                   help="write results as the committed baseline (do this deliberately)")
    p.add_argument("--compare-baseline", metavar="PATH", default=None,
                   help="compare this run against a baseline and flag regressions")
    args = p.parse_args(argv)

    cases = select(args.cases)
    print(f"Running {len(cases)} case(s) x k={args.k} on {AGENT_MODEL} ...")
    runs = run_suite(cases, args.k, max_workers=args.workers)

    comparison = None
    if args.compare_baseline:
        comparison = compare(runs, load_baseline(Path(args.compare_baseline)))

    run_dir = new_run_dir()
    write_traces(run_dir / "traces.jsonl", [t for cr in runs for t in cr.traces])
    report_path = report_mod.render(runs, args.k, run_dir / "report.html", comparison)
    _print_summary(runs)

    if comparison:
        verdict = "SUITE REGRESSION" if comparison.regressed else "no significant suite change"
        print(f"\nbaseline: z={comparison.z:.2f} p={comparison.p_value:.3f} -> {verdict}")
        for c in comparison.cases:
            if c.regressed:
                print(f"  ⚠ {c.case_id}: {c.current_pass}/{c.current_k} "
                      f"below baseline Wilson lower {c.wilson_lo:.0%}")

    if args.write_baseline:
        write_baseline(Path(args.write_baseline), runs, AGENT_MODEL)
        print(f"\nbaseline written to {args.write_baseline}")

    print(f"traces: {run_dir / 'traces.jsonl'}")
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
