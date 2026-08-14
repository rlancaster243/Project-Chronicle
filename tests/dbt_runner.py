"""Run the Chronicle dbt project against an isolated DuckDB file."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DBT_DIR = ROOT / "dbt"


def run_dbt(args: list[str], duckdb_path: Path, extra_env: dict[str, str] | None = None) -> None:
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["CHRONICLE_DUCKDB_PATH"] = str(duckdb_path)
    if extra_env:
        env.update(extra_env)
    command = ["dbt", *args, "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)]
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(
            f"dbt {' '.join(args)} failed ({result.returncode})\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def run_models(
    duckdb_path: Path,
    *,
    full_refresh: bool = False,
    select: str | None = None,
    vars_arg: str | None = None,
) -> None:
    args = ["run"]
    if full_refresh:
        args.append("--full-refresh")
    if select:
        args.extend(["--select", select])
    if vars_arg:
        args.extend(["--vars", vars_arg])
    run_dbt(args, duckdb_path)


def seed_and_run(
    duckdb_path: Path,
    *,
    full_refresh: bool = True,
    select: str | None = None,
    vars_arg: str | None = None,
) -> None:
    run_dbt(["seed", "--full-refresh"], duckdb_path)
    run_models(
        duckdb_path,
        full_refresh=full_refresh,
        select=select,
        vars_arg=vars_arg,
    )
