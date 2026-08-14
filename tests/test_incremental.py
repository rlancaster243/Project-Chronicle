from __future__ import annotations

from pathlib import Path

import duckdb

from tests.dbt_runner import run_models, seed_and_run
from tests.interval_helpers import (
    assert_intervals_match,
    fetch_customer_intervals,
    load_expected_intervals,
)

T1_VARS = 'ingest_cutoff: "2026-07-10 23:59:59"'
CANONICAL_SQL = """
    select
        customer_id,
        country_code,
        subscription_tier,
        account_status,
        email_verified,
        valid_from,
        valid_to,
        row_current,
        source_change_id
    from dimension_customers_t2
    order by customer_id, valid_from, source_change_id
"""


def _canonical_rows(path: Path) -> list[tuple]:
    con = duckdb.connect(str(path), read_only=True)
    rows = con.execute(CANONICAL_SQL).fetchall()
    con.close()
    return rows


def test_late_arrival_repairs_customer_42_then_matches_full_refresh(
    tmp_path: Path,
) -> None:
    incremental_db = tmp_path / "incremental.duckdb"
    full_db = tmp_path / "full.duckdb"

    seed_and_run(incremental_db, full_refresh=True, vars_arg=T1_VARS)
    con = duckdb.connect(str(incremental_db), read_only=True)
    after_t1 = fetch_customer_intervals(con, 42)
    con.close()
    assert_intervals_match(after_t1, load_expected_intervals("customer_42_intervals_after_t1.csv"))

    run_models(incremental_db, full_refresh=False)
    con = duckdb.connect(str(incremental_db), read_only=True)
    after_t2 = fetch_customer_intervals(con, 42)
    con.close()
    assert_intervals_match(after_t2, load_expected_intervals("customer_42_intervals.csv"))

    seed_and_run(full_db, full_refresh=True)
    incremental_rows = _canonical_rows(incremental_db)
    full_rows = _canonical_rows(full_db)
    assert incremental_rows == full_rows
    assert len(full_rows) > 0

    evidence = Path(__file__).resolve().parents[1] / "docs" / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "incremental_full_refresh_parity.txt").write_text(
        f"canonical_row_count={len(full_rows)}\nparity=equal\n",
        encoding="utf-8",
    )


def test_rerun_is_idempotent(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "idempotent.duckdb"
    seed_and_run(duckdb_path, full_refresh=True)
    first = _canonical_rows(duckdb_path)
    run_models(duckdb_path, full_refresh=False)
    second = _canonical_rows(duckdb_path)
    run_models(duckdb_path, full_refresh=True)
    third = _canonical_rows(duckdb_path)
    assert first == second == third

    evidence = Path(__file__).resolve().parents[1] / "docs" / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "idempotent_rerun.txt").write_text(
        f"canonical_row_count={len(first)}\nidempotent=true\n",
        encoding="utf-8",
    )
