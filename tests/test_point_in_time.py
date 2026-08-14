from __future__ import annotations

import csv
from pathlib import Path

import duckdb
import pytest

from tests.dbt_runner import seed_and_run
from tests.interval_helpers import EXPECTED, parse_ts


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory: pytest.TempPathFactory) -> Path:
    duckdb_path = tmp_path_factory.mktemp("chronicle") / "pit.duckdb"
    seed_and_run(duckdb_path, full_refresh=True)
    return duckdb_path


def test_customer_42_events_join_historical_state(warehouse: Path) -> None:
    con = duckdb.connect(str(warehouse), read_only=True)
    actual = con.execute(
        """
        select
            event_id,
            customer_id,
            event_name,
            event_timestamp,
            country_code,
            subscription_tier,
            account_status,
            email_verified,
            source_change_id
        from serving_customer_events_enriched
        where event_id in (
            'evt_042_login',
            'evt_042_purchase',
            'evt_042_renewal',
            'evt_042_support'
        )
        order by event_timestamp, event_id
        """
    ).fetchall()
    expected_path = EXPECTED / "customer_42_events_enriched.csv"
    wanted = list(csv.DictReader(expected_path.open(encoding="utf-8")))
    assert len(actual) == len(wanted) == 4
    for got, row in zip(actual, wanted, strict=True):
        assert got[0] == row["event_id"]
        assert got[2] == row["event_name"]
        assert parse_ts(got[3]) == parse_ts(row["event_timestamp"])
        if row["source_change_id"] == "":
            assert got[4] is None
            assert got[8] is None
        else:
            assert got[4] == row["country_code"]
            assert got[5] == row["subscription_tier"]
            assert got[6] == row["account_status"]
            assert bool(got[7]) == (row["email_verified"].lower() == "true")
            assert got[8] == row["source_change_id"]


def test_enrichment_does_not_use_current_or_latest_state(warehouse: Path) -> None:
    con = duckdb.connect(str(warehouse), read_only=True)
    login = con.execute(
        """
        select country_code, subscription_tier, customer_row_current, source_change_id
        from serving_customer_events_enriched
        where event_id = 'evt_042_login'
        """
    ).fetchone()
    assert login == ("US", "free", False, "chg_042_insert")
    post_delete = con.execute(
        """
        select matched_historical_state, country_code
        from serving_customer_events_enriched
        where event_id = 'evt_042_support'
        """
    ).fetchone()
    assert post_delete == (False, None)
