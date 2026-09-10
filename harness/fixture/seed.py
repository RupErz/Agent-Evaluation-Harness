"""Build the SQLite fixture DB from the committed transactions.json.

Run `python -m harness.fixture.seed`. Idempotent: drops and recreates tables.
"""
from __future__ import annotations

import json
import sqlite3

from ..config import DB_PATH, FIXTURE_JSON


def build() -> None:
    data = json.loads(FIXTURE_JSON.read_text())
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.executescript(
            """
            DROP TABLE IF EXISTS transactions;
            DROP TABLE IF EXISTS accounts;
            CREATE TABLE accounts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                balance REAL
            );
            CREATE TABLE transactions (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                account_id TEXT NOT NULL,
                merchant TEXT,
                memo TEXT,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            );
            """
        )
        cur.executemany(
            "INSERT INTO accounts VALUES (:id,:name,:type,:status,:balance)",
            data["accounts"],
        )
        cur.executemany(
            "INSERT INTO transactions VALUES "
            "(:id,:date,:category,:amount,:account_id,:merchant,:memo)",
            data["transactions"],
        )
        conn.commit()
        print(f"Seeded {len(data['transactions'])} transactions, "
              f"{len(data['accounts'])} accounts into {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    build()
