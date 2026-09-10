"""Serve the evaluation reports. Entry point for Replit.

    python main.py            # serves at http://0.0.0.0:$PORT (default 8000)
      /            -> latest report (newest run, else the committed sample_run)
      /runs        -> index of all available reports
      /runs/<id>   -> a specific report

`sample_run/` is a committed run so a fresh deploy shows a real report out of
the box; live runs written to `runs/<timestamp>/` take precedence.
"""
from __future__ import annotations

import html
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from harness.config import RUNS_DIR

PORT = int(os.environ.get("PORT", "8000"))
SAMPLE_DIR = Path(__file__).resolve().parent / "sample_run"


def _report_dirs() -> list[tuple[str, Path]]:
    """(id, dir) for every available report, newest live runs first, sample last."""
    out: list[tuple[str, Path]] = []
    if RUNS_DIR.exists():
        for d in sorted((p for p in RUNS_DIR.iterdir() if p.is_dir()),
                        key=lambda p: p.name, reverse=True):
            if (d / "report.html").exists():
                out.append((d.name, d))
    if (SAMPLE_DIR / "report.html").exists():
        out.append(("sample_run", SAMPLE_DIR))
    return out


def _index_html() -> str:
    rows = _report_dirs()
    if not rows:
        body = ("<p>No reports yet. Generate one with:</p>"
                "<pre>python -m harness.run --k 1 --cases all</pre>")
    else:
        items = "".join(
            f'<li><a href="/runs/{html.escape(rid)}">{html.escape(rid)}</a>'
            f'{"  — latest" if i == 0 else ""}'
            f'{"  (committed sample)" if rid == "sample_run" else ""}</li>'
            for i, (rid, _) in enumerate(rows))
        body = (f'<p><a href="/">→ open the latest report</a></p><ul>{items}</ul>')
    return f"""<!doctype html><meta charset="utf-8">
<title>Agent Evaluation Harness</title>
<style>body{{font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
max-width:720px;margin:60px auto;padding:0 20px;color:#e6e9ef;background:#0f1115}}
a{{color:#58a6ff}} h1{{font-size:22px}} pre{{background:#171a21;padding:10px;border-radius:6px}}
li{{margin:4px 0;font-family:ui-monospace,Menlo,monospace}}</style>
<h1>Agent Evaluation Harness</h1>
<p>A test harness that runs an AI agent against a suite of cases and reports whether
it behaved correctly — so a prompt or model change can be checked for regressions
before it reaches users.</p>{body}"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, status: int = 200, ctype: str = "text/html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        path = self.path.rstrip("/") or "/"
        rows = dict(_report_dirs())
        order = list(rows)
        if path == "/":
            if order:
                return self._send((rows[order[0]] / "report.html").read_bytes())
            return self._send(_index_html().encode())
        if path == "/runs":
            return self._send(_index_html().encode())
        if path.startswith("/runs/"):
            rid = path[len("/runs/"):]
            if rid in rows:
                return self._send((rows[rid] / "report.html").read_bytes())
            return self._send(b"<h1>404</h1> report not found", 404)
        if path in ("/health", "/healthz"):
            return self._send(b"ok", ctype="text/plain")
        return self._send(b"<h1>404</h1>", 404)

    def log_message(self, *a):  # quiet
        pass


def main() -> None:
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"serving eval reports on http://0.0.0.0:{PORT}  (latest at /)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
