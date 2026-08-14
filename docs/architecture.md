# Chronicle architecture

Chronicle is a local DuckDB + dbt lab. There is no orchestrator, no cloud
warehouse, and no streaming bus. The pipeline exists to make temporal
correctness testable.

## Pipeline

```text
generator (seed=42)
    → fixtures/customer_cdc_log.csv
    → fixtures/customer_activity_events.csv
        → dbt seeds
            → staging
            → intermediate (dedup + logical sequence)
            → core (SCD2 dimension + activity facts)
            → serving (point-in-time enrichment)
```

`source_updated_at` and `ingested_at` are stored as separate columns from the
first seed onward. Staging may filter on `ingest_cutoff` (arrival time) so
tests can simulate incremental delivery. Staging never filters on source time.

## Model grain

| Model | Grain |
| --- | --- |
| `stg_customer_cdc_log` | one received mutation record |
| `stg_customer_activity_events` | one activity event |
| `itm_customer_changes_deduplicated` | one canonical `change_id` |
| `itm_customer_change_sequence` | one `change_id` plus logical sequence metadata |
| `dimension_customers_t2` | one customer × one validity interval |
| `fact_customer_events` | one activity event |
| `serving_customer_events_enriched` | one event plus the state valid at `event_timestamp` |

Every model states grain in SQL comments and YAML. If a model does not change
grain or semantics, it is not added.

## Interval contract

Half-open `[valid_from, valid_to)`:

- `valid_from` is inclusive and equals the creating mutation's `source_updated_at`
- `valid_to` is exclusive and equals the next logical mutation's `source_updated_at`
- current entities have `valid_to IS NULL` and `row_current = true`
- a `DELETE` closes the open interval; Chronicle does not emit a tombstone row

Point-in-time join:

```sql
event.customer_id = dimension.customer_id
and event.event_timestamp >= dimension.valid_from
and (
    event.event_timestamp < dimension.valid_to
    or dimension.valid_to is null
)
```

## Incremental repair

`dimension_customers_t2` is incremental with `unique_key = customer_id` and
`delete+insert`.

- Watermark: `max(last_seen_ingested_at)` on the existing dimension
- Affected set: customers with any staged CDC row newer than that watermark
- Repair: delete those customers' versions and rebuild them from the entire
  visible logical CDC history
- `last_seen_ingested_at` is watermark metadata. It is never `valid_from`.

This is bounded recomputation of affected entities, not a full-table rebuild
labeled incremental. Full refresh rebuilds every customer and is the recovery
path. Parity is asserted in `tests/test_incremental.py`.

## Temporal tests

Reusable generic tests in `dbt/macros/`:

- `no_overlapping_validity_windows` — half-open overlap or inverted/zero-width
- `exactly_one_current_record` — open interval ⇒ exactly one current row;
  no open interval ⇒ zero current rows

The ingest-order defect path is `dbt run --vars 'scd2_sort: ingest_time'`.
It is not the default. See [`failure-report-temporal-overlap.md`](failure-report-temporal-overlap.md).
