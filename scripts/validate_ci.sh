#!/usr/bin/env bash
# Chronicle CI contract: generate inputs, lint, tests, dbt parse/seed/run/test.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if command -v uv >/dev/null 2>&1; then
  RUN=(uv run)
else
  RUN=()
fi

DUCKDB_PATH="${CHRONICLE_DUCKDB_PATH:-${ROOT}/data/chronicle.duckdb}"
mkdir -p "$(dirname "${DUCKDB_PATH}")"
export CHRONICLE_DUCKDB_PATH="${DUCKDB_PATH}"

echo "==> generate deterministic fixtures"
"${RUN[@]}" python -m chronicle --seed 42 --out fixtures

echo "==> ruff check"
"${RUN[@]}" ruff check src tests

echo "==> ruff format --check"
"${RUN[@]}" ruff format --check src tests

echo "==> pytest"
"${RUN[@]}" pytest -q

echo "==> dbt parse"
"${RUN[@]}" dbt parse --project-dir dbt --profiles-dir dbt

echo "==> dbt seed"
"${RUN[@]}" dbt seed --project-dir dbt --profiles-dir dbt --full-refresh

echo "==> dbt run"
"${RUN[@]}" dbt run --project-dir dbt --profiles-dir dbt --full-refresh

echo "==> dbt test"
"${RUN[@]}" dbt test --project-dir dbt --profiles-dir dbt

echo "==> chronicle validation passed"
