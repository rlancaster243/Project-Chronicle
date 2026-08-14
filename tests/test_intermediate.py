from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from tests.dbt_runner import seed_and_run


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory: pytest.TempPathFactory) -> Path:
    duckdb_path = tmp_path_factory.mktemp("chronicle") / "intermediate.duckdb"
    seed_and_run(duckdb_path, select="staging intermediate")
    return duckdb_path


def test_duplicate_change_id_is_collapsed(warehouse: Path) -> None:
    con = duckdb.connect(str(warehouse), read_only=True)
    staged = con.execute(
        "select count(*) from stg_customer_cdc_log where change_id = 'chg_042_move'"
    ).fetchone()[0]
    deduped = con.execute(
        "select count(*) from itm_customer_changes_deduplicated where change_id = 'chg_042_move'"
    ).fetchone()[0]
    assert staged == 2
    assert deduped == 1


def test_identical_values_keep_distinct_change_ids(warehouse: Path) -> None:
    con = duckdb.connect(str(warehouse), read_only=True)
    rows = con.execute(
        """
        select change_id, country_code, subscription_tier
        from itm_customer_changes_deduplicated
        where change_id in ('chg_022_insert', 'chg_022_noop')
        order by change_id
        """
    ).fetchall()
    assert [row[0] for row in rows] == ["chg_022_insert", "chg_022_noop"]
    assert rows[0][1:] == rows[1][1:]


def test_customer_42_logical_sequence_ignores_arrival_order(warehouse: Path) -> None:
    con = duckdb.connect(str(warehouse), read_only=True)
    rows = con.execute(
        """
        select change_id, change_seq, is_ambiguous_tie
        from itm_customer_change_sequence
        where customer_id = 42
        order by change_seq
        """
    ).fetchall()
    assert [row[0] for row in rows] == [
        "chg_042_insert",
        "chg_042_move",
        "chg_042_upgrade",
        "chg_042_delete",
    ]
    assert all(row[2] is False for row in rows)


def test_same_timestamp_conflict_is_flagged(warehouse: Path) -> None:
    con = duckdb.connect(str(warehouse), read_only=True)
    rows = con.execute(
        """
        select change_id, is_ambiguous_tie
        from itm_customer_change_sequence
        where customer_id = 18 and change_id in ('chg_018_a', 'chg_018_b')
        order by change_id
        """
    ).fetchall()
    assert [row[0] for row in rows] == ["chg_018_a", "chg_018_b"]
    assert all(row[1] is True for row in rows)
