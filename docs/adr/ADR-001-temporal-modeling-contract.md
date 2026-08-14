# ADR-001: Temporal modeling contract

## Status

Accepted

## Context

Chronicle must reconstruct historically correct customer state when mutations
arrive duplicated, late, out of order, replayed, or deleted. Chronicle's
purpose is to isolate and prove temporal truth under those conditions.

## Decision

Chronicle defines temporal truth as the source system's mutation time, not
the warehouse's arrival time.

### Source timestamp versus ingestion timestamp

| Clock | Meaning | Used for |
| --- | --- | --- |
| `source_updated_at` | When the source entity changed | Validity intervals, logical order, PIT joins |
| `ingested_at` | When Chronicle received the row | Incremental watermark, late-arrival detection |

Processing a Jul 8 mutation on Jul 11 does not move the Jul 8 change to Jul 11.

### Mutation ordering

```text
ORDER BY source_updated_at, change_id
```

`ingested_at` is never the sort key for history. Warehouse row order is never
relied on.

### Tie-breaking and known ambiguity

If two different `change_id`s share `source_updated_at`:

- order is still deterministic (`change_id` ascending)
- zero-width intermediate versions are not emitted (`valid_from < valid_to`)
- `is_ambiguous_tie` is true when attributes also conflict

Chronicle flags that case instead of claiming to know which mutation was first.
Customer 18 is the fixture: `chg_018_a` (FR) and `chg_018_b` (GB) at the same
instant; the emitted state is GB.

### Duplicate identity

Mutation identity is `change_id`. First-write wins (`min(ingested_at)`).

This is not the same as two legitimate changes with identical business values.
Customer 10 (`chg_010_update` delivered twice) collapses to one version.
Customer 22 (`chg_022_insert` and `chg_022_noop`) keeps two adjacent
identical-attribute versions.

### Validity interval semantics

Half-open `[valid_from, valid_to)`:

```text
valid_from <= event_timestamp
AND (event_timestamp < valid_to OR valid_to IS NULL)
```

`valid_from` is inclusive. `valid_to` is exclusive, or null if the entity is
still current.

### Deletion handling

No tombstone row.

A `DELETE` closes the currently valid version at the delete's
`source_updated_at` and leaves `row_current = false` on every version.
Prior history is preserved. Events after delete do not match a dimension row.

A tombstone row would invent a "deleted" attribute state and would make
`exactly_one_current_record` harder to reason about. Closing the interval is
enough to represent "this entity ended."

### Late-arrival repair

A newly arrived mutation for a customer marks that customer as affected.
Chronicle deletes that customer's SCD2 rows and rebuilds them from the full
logical CDC history now visible. Late rows repair the middle of the timeline
instead of appending to the end.

Customer 42 after T1 (`ingested_at <= 2026-07-10 23:59:59`) is missing the
Jul 8 CA/free interval. After T2 the late move is applied and the intervals
match the hand-written fixture.

### Incremental boundary

- Identity: `change_id`
- Watermark: `max(last_seen_ingested_at)`
- Reconsidered records: all logical history for affected `customer_id`s
- Recovery: `dbt run --full-refresh`

## Rejected alternatives

| Alternative | Why not |
| --- | --- |
| Current-state-only table | Cannot answer "what was true at event time" |
| Type 1 overwrite | Late/stale rows corrupt current and erase history |
| dbt `snapshot` | Check/`updated_at` strategies follow arrival or current image; they do not rebuild out-of-order CDC |
| Ingest-order SCD2 | Reconstructs arrival, not source history; fails customer 42 and overlap tests |
| Rebuild-all-every-run labeled incremental | Does not exercise late-data repair |
| Tombstone dimension row | Invents a state that never existed as a profile image |

Custom SCD2 from an append-only change log is selected because Chronicle's
learning objective is historical reconstruction under mutable source behavior,
not because it is universally superior to snapshots in production.

## Consequences

- Tests must compare reconstructed intervals to hand-written expected output
- Incremental jobs must be able to reopen closed intervals
- Operators can explain every major choice without reading generated SQL
