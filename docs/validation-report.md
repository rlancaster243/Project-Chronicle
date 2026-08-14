# Chronicle validation report

Executable evidence for the claims in the README. The public repository keeps
the tests and deterministic expected fixtures as the primary evidence; GitHub
Actions reruns the complete CI contract on pushes and pull requests.

| Claim | Reproducible evidence |
| --- | --- |
| Generator is deterministic | `tests/test_generator.py::test_same_seed_is_byte_identical` |
| Dataset stays small | 100 customers, 464 CDC rows, 1,000 events; scale assertion in `test_generator.py` |
| Every mutation class exists | `fixtures/expected/scenario_catalog.yml` + `test_every_catalog_class_is_present` |
| Customer 42 arrives out of order | Physical order insert → upgrade → move → move → delete |
| Duplicates are idempotent | `test_intermediate.py`, `test_scd2.py` |
| Distinct ids with identical values survive | Customer 22 scenario and SCD2 assertions |
| Late arrivals repair history | T1/T2 expected fixtures + `tests/test_incremental.py` |
| Stale change does not become current | Customer 14 assertions |
| Deletes close current state | Customer 21 and 42 assertions |
| No overlapping windows | dbt generic `no_overlapping_validity_windows` |
| Exactly one current row per active entity | dbt generic `exactly_one_current_record` |
| Closed intervals are ordered | `dbt/tests/assert_closed_intervals_ordered.sql` |
| Point-in-time join works | `tests/test_point_in_time.py` + expected customer 42 event fixture |
| Incremental equals full refresh | `tests/test_incremental.py` |
| Rerun is safe | idempotency assertions in the executable test suite |
| CI blocks ingest-order corruption | `tests/test_adversarial_overlap.py` |
| Injected overlap is caught | `tests/test_adversarial_overlap.py` |
| Full CI contract | `.github/workflows/chronicle-ci.yml` + `scripts/validate_ci.sh` |

## Customer 42 expected history

| State | Interval | `row_current` |
| --- | --- | --- |
| US / free | 2026-07-01 09:00 → 2026-07-08 12:00 | false |
| CA / free | 2026-07-08 12:00 → 2026-07-10 14:00 | false |
| CA / premium | 2026-07-10 14:00 → 2026-07-20 18:00 | false |
| deleted | 2026-07-20 18:00 | no row |

After T1 only (upgrade arrived, move has not):

| State | Interval | `row_current` |
| --- | --- | --- |
| US / free | 2026-07-01 09:00 → 2026-07-10 14:00 | false |
| CA / premium | 2026-07-10 14:00 → open | true |

That T1 table is incomplete history, not a different algorithm. T2 repairs it.

## Point-in-time fixture

| Event | Time | Joined state |
| --- | --- | --- |
| login | Jul 5 | US / free |
| purchase | Jul 9 | CA / free |
| renewal | Jul 15 | CA / premium |
| support_contact | Jul 25 | unmatched (deleted) |

## How to reproduce

```bash
uv sync
bash scripts/validate_ci.sh
```

Adversarial path only:

```bash
uv run pytest tests/test_adversarial_overlap.py -q
```
