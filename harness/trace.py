"""Read/write traces as JSONL to runs/<timestamp>/traces.jsonl."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

from .config import RUNS_DIR
from .models import Trace


def new_run_dir(base: Path = RUNS_DIR) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    d = base / stamp
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_traces(path: Path, traces: Iterable[Trace]) -> None:
    with open(path, "w") as f:
        for t in traces:
            f.write(t.model_dump_json() + "\n")


def read_traces(path: Path) -> list[Trace]:
    out: list[Trace] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(Trace.model_validate_json(line))
    return out
