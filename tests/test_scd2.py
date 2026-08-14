from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from tests.dbt_runner import seed_and_run
from tests.interval_helpers import (
    assert_intervals_match,
    fetch_customer_intervals,
    load_expected_intervals,
)


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory: pytest.TempPathFactory) -> Path:
    duckdb_path = tmp_path_factory.mktemp("chronicle") / "scd2.duckdb"
    seed_and_run(duckdb_path, select="+dimension_customers_t2")
    return duckdb_path


def test_customer_42_matches_hand_written_intervals(warehouse: Path) -> None:
    con = duckdb.connect(str(warehouse), read_only=True)
    actual = fetch_customer_intervals(con, 42)
    expected = load_expected_intervals("customer_42_intervals.csv")
    assert_intervals_match(actual, expected)


def test_delete_closes_current_row(warehouse: Path) -> None:
    con = duckdb.connect(str(warehouse), read_only=True)
    rows = fetch_customer_intervals(con, 21)
    assert len(rows) == 1
    assert rows[0]["row_current"] is False
    assert rows[0]["valid_to"] is not None
    assert rows[0]["source_change_id"] == "chg_021_insert"


def test_stale_change_does_not_become_current(warehouse: Path) -> None:
    con = duckdb.connect(str(warehouse), read_only=True)
    current = con.execute(
        """
        select subscription_tier, source_change_id, row_current
        from dimension_customers_t2
        where customer_id = 14 and row_current
        """
    ).fetchall()
    assert current == [("premium", "chg_014_newer", True)]
    stale = con.execute(
        """
        select subscription_tier, row_current
        from dimension_customers_t2
        where source_change_id = 'chg_014_stale'
        """
    ).fetchone()
    assert stale == ("plus", False)


def test_duplicate_change_id_does_not_add_a_version(warehouse: Path) -> None:
    con = duckdb.connect(str(warehouse), read_only=True)
    count = con.execute(
        "select count(*) from dimension_customers_t2 where customer_id = 10"
    ).fetchone()[0]
    assert count == 2


def test_distinct_change_ids_with_identical_values_keep_two_versions(
    warehouse: Path,
) -> None:
    con = duckdb.connect(str(warehouse), read_only=True)
    rows = con.execute(
        """
        select source_change_id, country_code, subscription_tier
        from dimension_customers_t2
        where customer_id = 22
        order by valid_from, source_change_id
        """
    ).fetchall()
    assert [row[0] for row in rows] == ["chg_022_insert", "chg_022_noop", "chg_022_real"]
    assert rows[0][1:] == rows[1][1:] == ("US", "free")
    assert rows[2][1:] == ("CA", "free")


def test_same_timestamp_conflict_keeps_last_change_id(warehouse: Path) -> None:
    con = duckdb.connect(str(warehouse), read_only=True)
    rows = con.execute(
        """
        select source_change_id, country_code, valid_from < valid_to or valid_to is null
        from dimension_customers_t2
        where customer_id = 18
        order by valid_from, source_change_id
        """
    ).fetchall()
    assert [row[0] for row in rows] == ["chg_018_insert", "chg_018_b"]
    assert rows[-1][1] == "GB"
    assert all(row[2] for row in rows)
