"""Serve the evaluation reports. Entry point for Replit.

    python main.py            # serves at http://0.0.0.0:8000
      /            -> latest run's report.html
      /runs/<id>   -> a specific run's report.html
      /runs        -> index of all runs

If no run exists yet, the index explains how to produce one.
"""
from __future__ import annotations

import html
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from harness.config import RUNS_DIR

PORT = int(os.environ.get("PORT", "8000"))


def _runs() -> list[str]:
    if not RUNS_DIR.exists():
        return []
    return sorted((d.name for d in RUNS_DIR.iterdir()
                   if d.is_dir() and (d / "report.html").exists()), reverse=True)


def _index_html() -> str:
    runs = _runs()
    if not runs:
        return ("<h1>Agent Eval Harness</h1><p>No runs yet. Produce one with:</p>"
                "<pre>python -m harness.run --k 1 --cases all</pre>")
    items = "".join(
        f'<li><a href="/runs/{html.escape(r)}">{html.escape(r)}</a>'
        f'{" — latest" if i == 0 else ""}</li>' for i, r in enumerate(runs))
    return (f"<h1>Agent Eval Harness — runs</h1><ul>{items}</ul>"
            f'<p><a href="/">/ always shows the latest ({html.escape(runs[0])})</a></p>')


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, status: int = 200, ctype: str = "text/html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        path = self.path.rstrip("/") or "/"
        runs = _runs()
        if path == "/":
            if runs:
                return self._send((RUNS_DIR / runs[0] / "report.html").read_bytes())
            return self._send(_index_html().encode())
        if path == "/runs":
            return self._send(_index_html().encode())
        if path.startswith("/runs/"):
            rid = path[len("/runs/"):]
            report = RUNS_DIR / rid / "report.html"
            if report.exists() and RUNS_DIR in report.resolve().parents:
                return self._send(report.read_bytes())
            return self._send(b"<h1>404</h1> run not found", 404)
        return self._send(b"<h1>404</h1>", 404)

    def log_message(self, *a):  # quiet
        pass


def main() -> None:
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"serving eval reports on http://0.0.0.0:{PORT}  (latest at /)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
