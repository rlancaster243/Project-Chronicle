# START HERE — Project Chronicle

> **Overview:** [`README.md`](README.md) — what Chronicle is, the temporal contract, and how to verify it.

**Status:** temporal correctness lab · local DuckDB + dbt · no cloud deploy

## Quick validate

```bash
uv sync
bash scripts/validate_ci.sh
```

Validation generates the deterministic CDC/event inputs before running the test
and dbt contracts.

## Docs

- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Temporal contract: [`docs/adr/ADR-001-temporal-modeling-contract.md`](docs/adr/ADR-001-temporal-modeling-contract.md)
- Failure report: [`docs/failure-report-temporal-overlap.md`](docs/failure-report-temporal-overlap.md)
- Validation evidence: [`docs/validation-report.md`](docs/validation-report.md)
