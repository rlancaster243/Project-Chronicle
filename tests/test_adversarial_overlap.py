from __future__ import annotations

import subprocess
from pathlib import Path

import duckdb

from tests.dbt_runner import DBT_DIR, ROOT, seed_and_run

EVIDENCE = ROOT / "docs" / "evidence"


def _dbt_test(
    duckdb_path: Path, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    import os

    env = os.environ.copy()
    env["CHRONICLE_DUCKDB_PATH"] = str(duckdb_path)
    if extra_env:
        env.update(extra_env)
    command = [
        "dbt",
        "test",
        "--project-dir",
        str(DBT_DIR),
        "--profiles-dir",
        str(DBT_DIR),
        "--select",
        "dimension_customers_t2",
    ]
    return subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)


def test_ingest_order_scd2_fails_temporal_integrity(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "ingest_order.duckdb"
    seed_and_run(
        duckdb_path,
        select="+dimension_customers_t2",
        vars_arg="scd2_sort: ingest_time",
    )
    result = _dbt_test(duckdb_path)
    output = result.stdout + result.stderr
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "ingest_order_dbt_test_failure.txt").write_text(output, encoding="utf-8")
    assert result.returncode != 0
    assert "no_overlapping_validity_windows" in output
    assert "FAIL" in output
    assert "Parser Error" not in output


def test_generic_test_catches_injected_overlap(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "inject.duckdb"
    seed_and_run(duckdb_path, select="+dimension_customers_t2")
    con = duckdb.connect(str(duckdb_path))
    con.execute(
        """
        insert into dimension_customers_t2
        select
            customer_version_id || '-overlap',
            customer_id,
            country_code,
            subscription_tier,
            account_status,
            email_verified,
            valid_from + interval '1 hour',
            valid_to,
            false,
            source_change_id,
            last_seen_ingested_at
        from dimension_customers_t2
        where customer_id = 1
        """
    )
    con.close()
    result = _dbt_test(duckdb_path)
    output = result.stdout + result.stderr
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "injected_overlap_dbt_test_failure.txt").write_text(output, encoding="utf-8")
    assert result.returncode != 0
    assert "no_overlapping_validity_windows" in output
    assert "FAIL" in output
    assert "Parser Error" not in output
