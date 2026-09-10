import pytest

from harness.config import MAX_TOOL_ROWS
from harness.fixture.db import FixtureDB
from harness.tools import ToolBox, ToolError


@pytest.fixture
def box():
    db = FixtureDB()
    yield ToolBox(db)
    db.close()


def test_list_transactions_caps_rows_and_reports_omitted(box):
    # Whole range has >25 groceries rows; result must be capped with an omitted count.
    res = box.list_transactions("2025-06-01", "2026-08-15", "groceries")
    assert res["returned"] <= MAX_TOOL_ROWS
    assert res["total_matching"] == 33
    assert res["omitted"] == 33 - res["returned"]
    assert len(res["transactions"]) == res["returned"]


def test_list_transactions_unknown_category_raises_structured_error(box):
    with pytest.raises(ToolError) as ei:
        box.list_transactions("2025-06-01", "2026-08-15", "crypto")
    assert "valid_categories" in ei.value.payload
    assert "groceries" in ei.value.payload["valid_categories"]


def test_list_transactions_date_range_is_inclusive(box):
    res = box.list_transactions("2026-07-01", "2026-07-31", "groceries")
    assert res["total_matching"] == 9
    for t in res["transactions"]:
        assert "2026-07-01" <= t["date"] <= "2026-07-31"


def test_get_accounts_includes_closed_with_null_balance(box):
    accts = box.get_accounts()["accounts"]
    closed = [a for a in accts if a["status"] == "closed"]
    assert closed and closed[0]["balance"] is None


def test_calculate_returns_result(box):
    assert box.calculate("100 + 27.61")["result"] == pytest.approx(127.61)


def test_stale_mutation_corrupts_amounts(box):
    box.stale = True
    res = box.list_transactions("2026-07-01", "2026-07-31", "groceries")
    # Corrupted amounts must not equal the true July groceries sum semantics.
    with FixtureDB() as clean_db:
        real = clean_db.list_transactions("2026-07-01", "2026-07-31", "groceries")
    assert res["transactions"][0]["amount"] != real[0]["amount"]
