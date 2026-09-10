"""FixtureDB: read access to the seeded DB plus the oracle helpers.

The oracle helpers (`sum_category`, `count_category`, ...) are what
`NumericAnswerEquals` calls at test time to compute the expected value directly
from the fixture. Because the expectation is computed from the same data the
agent sees, it can never drift out of sync with the fixture the way a hardcoded
literal would.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from ..config import DB_PATH


class FixtureDB:
    def __init__(self, path=DB_PATH):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- raw access --------------------------------------------------------
    def categories(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT category FROM transactions ORDER BY category"
        ).fetchall()
        return [r["category"] for r in rows]

    def accounts(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, name, type, status, balance FROM accounts ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_account(self, account_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT id, name, type, status, balance FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_transactions(
        self, start_date: str, end_date: str, category: Optional[str] = None
    ) -> list[dict]:
        """Inclusive date range. Assumes ISO YYYY-MM-DD (lexical == chronological)."""
        sql = ("SELECT id, date, category, amount, account_id, merchant, memo "
               "FROM transactions WHERE date >= ? AND date <= ?")
        params: list = [start_date, end_date]
        if category is not None:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY date"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # --- oracle helpers ----------------------------------------------------
    def sum_category(self, category: str, start_date: str, end_date: str) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(amount), 0.0) AS total FROM transactions "
            "WHERE category = ? AND date >= ? AND date <= ?",
            (category, start_date, end_date),
        ).fetchone()
        return round(row["total"], 2)

    def count_category(self, category: str, start_date: str, end_date: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM transactions "
            "WHERE category = ? AND date >= ? AND date <= ?",
            (category, start_date, end_date),
        ).fetchone()
        return row["n"]

    def sum_all_spending(self, start_date: str, end_date: str) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(amount), 0.0) AS total FROM transactions "
            "WHERE category != 'income' AND date >= ? AND date <= ?",
            (start_date, end_date),
        ).fetchone()
        return round(row["total"], 2)

    def net_income(self, start_date: str, end_date: str) -> float:
        """Income minus spending across the range (needs both tools' data)."""
        income = self.conn.execute(
            "SELECT COALESCE(SUM(amount),0.0) AS t FROM transactions "
            "WHERE category = 'income' AND date >= ? AND date <= ?",
            (start_date, end_date),
        ).fetchone()["t"]
        spend = self.sum_all_spending(start_date, end_date)
        return round(income - spend, 2)

    def total_balance(self, active_only: bool = True) -> float:
        sql = "SELECT COALESCE(SUM(balance),0.0) AS t FROM accounts WHERE balance IS NOT NULL"
        if active_only:
            sql += " AND status = 'active'"
        return round(self.conn.execute(sql).fetchone()["t"], 2)
