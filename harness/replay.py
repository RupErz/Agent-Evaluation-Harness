"""Replay mode: python -m harness.replay runs/<ts>/traces.jsonl

Feeds recorded traces back through the assertion layer WITHOUT calling the
model. Because raw_messages and all trace fields are recorded, the assertion
logic can be re-checked deterministically and for free - the harness's own
assertions are testable without spending tokens.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .cases import BY_ID
from .fixture.db import FixtureDB
from .trace import read_traces


def replay(path: Path) -> int:
    traces = read_traces(path)
    db = FixtureDB()
    unknown = 0
    try:
        by_case: dict[str, list] = {}
        for tr in traces:
            by_case.setdefault(tr.case_id, []).append(tr)
        for case_id, trs in by_case.items():
            case = BY_ID.get(case_id)
            if case is None:
                print(f"[skip] {case_id}: not in current case registry")
                unknown += 1
                continue
            passes = 0
            for tr in trs:
                if all(a.check(tr, db).passed for a in case.assertions):
                    passes += 1
            print(f"{case_id}: {passes}/{len(trs)} reps pass on replay")
    finally:
        db.close()
    return 0 if unknown == 0 else 1


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: python -m harness.replay <traces.jsonl>", file=sys.stderr)
        return 2
    return replay(Path(argv[0]))


if __name__ == "__main__":
    raise SystemExit(main())
