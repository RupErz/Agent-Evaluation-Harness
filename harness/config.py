"""Central configuration for the evaluation harness.

Everything that could introduce non-model variance is pinned here: the model
string is a *dated snapshot* (never an alias, never "latest"), the clock is
frozen, and temperature is 0. See docs/design.md for why each of these matters.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- Paths -----------------------------------------------------------------
PKG_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PKG_DIR.parent
FIXTURE_DIR = PKG_DIR / "fixture"
FIXTURE_JSON = FIXTURE_DIR / "transactions.json"
DB_PATH = FIXTURE_DIR / "finance.db"
RUNS_DIR = PROJECT_DIR / "runs"


def _load_dotenv() -> None:
    """Minimal .env loader (avoids a python-dotenv dependency).

    Only sets keys that are not already present in the environment, so an
    explicit `export` always wins over the file.
    """
    env_path = PROJECT_DIR / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


def get_api_key() -> str:
    """The key is stored in .env as CLAUDE_API_KEY (also accept the SDK default)."""
    key = os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "No API key found. Set CLAUDE_API_KEY in .env (or ANTHROPIC_API_KEY)."
        )
    return key


# --- Pinned run parameters -------------------------------------------------
# Dated snapshot, NOT an alias: an alias can silently move and invalidate the
# baseline, which is the entire point of the project.
AGENT_MODEL = os.environ.get("AGENT_MODEL", "claude-haiku-4-5-20251001")
# Judge is pinned separately and recorded separately (see spec 4.2).
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "claude-sonnet-5")

# Frozen clock. "last month" relative to this resolves to 2026-07-01..2026-07-31,
# matching the oracle example in the spec. The agent never calls datetime.now().
FROZEN_NOW = os.environ.get("FROZEN_NOW", "2026-08-15T12:00:00")

TEMPERATURE = float(os.environ.get("TEMPERATURE", "0.0"))
STEP_CAP = int(os.environ.get("STEP_CAP", "8"))
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "1024"))

# list_transactions returns at most this many rows plus an omitted count. Tool
# results are re-sent in context every turn, so an uncapped result is paid for
# repeatedly. Also more realistic tool design.
MAX_TOOL_ROWS = int(os.environ.get("MAX_TOOL_ROWS", "25"))

DEFAULT_K = int(os.environ.get("DEFAULT_K", "5"))


def sampling_extra_body(model: str, temperature: float) -> dict:
    """Return the extra_body for pinning sampling, only where the model accepts it.

    This SDK/model generation removed `temperature` as a named parameter. Haiku
    4.5 still honours it via extra_body (so we genuinely pin the agent to 0), but
    newer models such as Sonnet 5 reject it with a 400. For those we omit it and
    rely on the model default (documented in docs/design.md).
    """
    if "haiku-4-5" in model:
        return {"temperature": temperature}
    return {}
