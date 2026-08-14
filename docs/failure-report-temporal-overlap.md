# Failure report: ingest-order SCD2 overlap

This is a real injected defect path, not a mocked failure.

## Defect

`dimension_customers_t2` can be built with:

```bash
dbt run --vars 'scd2_sort: ingest_time'
```

That path orders mutations by `ingested_at, change_id` while still labeling
intervals with `source_updated_at`. It represents the tempting but incorrect
approach: process rows as they arrive and close the previous row with the next
row's source time.

For customer 42 the physical arrival is:

1. Jul 1 insert (arrives Jul 1)
2. Jul 10 upgrade (arrives Jul 10)
3. Jul 8 move (arrives Jul 11)
4. Jul 8 move again
5. Jul 20 delete

Ingest-order `LEAD(source_updated_at)` then assigns the upgrade row
`valid_from = Jul 10` and `valid_to = Jul 8`. That window is inverted and
overlaps the late move's `[Jul 8, Jul 20)` interval.

## Observed validation result

The adversarial path produced inverted closed intervals and overlapping
validity windows while the current-record check still passed. That is the
important failure mode: current-state checks alone can remain green while
historical truth is corrupted.

## Root cause

Validity intervals were computed from processing order. Source time was used
only as a label. When a late mutation has an earlier `source_updated_at` than
the already-materialized current row, `LEAD` over ingest order produces
inverted and overlapping windows.

Customer 42's historically correct state (US/free → CA/free → CA/premium →
closed) cannot be recovered from ingest order. The late CA/free move lands
after premium.

## Repair

Default `scd2_sort` is `source_time`:

```text
ORDER BY source_updated_at, change_id
```

Late mutations reopen the affected customer's history and rebuild every
interval from the full logical change log. Zero-width same-timestamp
intermediates are dropped so every closed row satisfies `valid_from < valid_to`.

Customer 42 is then expected to match
[`fixtures/expected/customer_42_intervals.csv`](../fixtures/expected/customer_42_intervals.csv).

## Regression protection

`tests/test_adversarial_overlap.py` keeps both experiments:

1. Build with `scd2_sort: ingest_time` and assert the generic tests fail
2. Inject an overlapping row into a correct dimension and assert the generic
   test fails

The default remains source-time order. Tests are not weakened to make
processing-order history look correct.
