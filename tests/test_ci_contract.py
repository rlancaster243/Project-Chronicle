from __future__ import annotations

from pathlib import Path

from tests.dbt_runner import run_dbt


def test_dbt_seed_creates_missing_parent_directory(tmp_path: Path) -> None:
    """DuckDB cannot open a file whose parent directory does not exist.

    CI and validate_ci.sh use the default path data/chronicle.duckdb, and
    data/ is gitignored. Seed must create that parent instead of failing.
    """
    duckdb_path = tmp_path / "data" / "chronicle.duckdb"
    assert not duckdb_path.parent.exists()
    run_dbt(["seed", "--full-refresh"], duckdb_path)
    assert duckdb_path.exists()
