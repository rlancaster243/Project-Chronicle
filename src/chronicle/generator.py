"""Deterministic synthetic CDC and activity-event generator.

Problem: Chronicle needs known ground truth, not an external API.
Decision: emit a fixed-seed append-only change log plus activity facts.
Mechanism: scripted anomaly customers (including customer 42) plus a seeded
population that fills the remaining ids to ~100 / ~500 / ~1000.
Failure mode: a non-deterministic clock or unstable sort would make tests lie.
Verification: `tests/test_generator.py` asserts byte-identical reruns and
the customer-42 physical arrival order.
"""

from __future__ import annotations

import argparse
import csv
import random
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from pathlib import Path

SEED_DEFAULT = 42
CUSTOMER_COUNT = 100
TARGET_EVENTS = 1000

COUNTRIES = ("US", "CA", "GB", "DE", "FR", "AU", "JP", "BR")
TIERS = ("free", "plus", "premium")
STATUSES = ("active", "paused", "suspended")
EVENT_NAMES = (
    "login",
    "purchase",
    "renewal",
    "cancel_request",
    "support_contact",
    "plan_view",
)

CDC_COLUMNS = (
    "change_id",
    "customer_id",
    "operation",
    "country_code",
    "subscription_tier",
    "account_status",
    "email_verified",
    "source_updated_at",
    "ingested_at",
    "scenario_tag",
)
EVENT_COLUMNS = ("event_id", "customer_id", "event_name", "event_timestamp")

SCRIPTED_CUSTOMER_IDS = frozenset({1, 2, 3, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 42})

TS_FMT = "%Y-%m-%d %H:%M:%S"


def ts(value: str) -> datetime:
    return datetime.strptime(value, TS_FMT)


def fmt(value: datetime) -> str:
    return value.strftime(TS_FMT)


@dataclass(frozen=True)
class CdcRow:
    change_id: str
    customer_id: int
    operation: str
    country_code: str
    subscription_tier: str
    account_status: str
    email_verified: bool
    source_updated_at: datetime
    ingested_at: datetime
    scenario_tag: str


@dataclass(frozen=True)
class EventRow:
    event_id: str
    customer_id: int
    event_name: str
    event_timestamp: datetime


def _row(
    change_id: str,
    customer_id: int,
    operation: str,
    source_updated_at: datetime,
    ingested_at: datetime,
    scenario_tag: str,
    country_code: str = "US",
    subscription_tier: str = "free",
    account_status: str = "active",
    email_verified: bool = False,
) -> CdcRow:
    return CdcRow(
        change_id=change_id,
        customer_id=customer_id,
        operation=operation,
        country_code=country_code,
        subscription_tier=subscription_tier,
        account_status=account_status,
        email_verified=email_verified,
        source_updated_at=source_updated_at,
        ingested_at=ingested_at,
        scenario_tag=scenario_tag,
    )


def customer_42_rows() -> list[CdcRow]:
    """Canonical late + duplicate + delete scenario.

    Logical source history is Jul 1 insert, Jul 8 move, Jul 10 upgrade, Jul 20
    delete. Physical arrival delivers the Jul 10 upgrade before the Jul 8 move,
    then repeats the move, then the delete.
    """
    insert = _row(
        "chg_042_insert",
        42,
        "INSERT",
        ts("2026-07-01 09:00:00"),
        ts("2026-07-01 09:05:00"),
        "customer_42_canonical",
        country_code="US",
        subscription_tier="free",
    )
    upgrade = _row(
        "chg_042_upgrade",
        42,
        "UPDATE",
        ts("2026-07-10 14:00:00"),
        ts("2026-07-10 14:05:00"),
        "customer_42_canonical",
        country_code="CA",
        subscription_tier="premium",
    )
    move = _row(
        "chg_042_move",
        42,
        "UPDATE",
        ts("2026-07-08 12:00:00"),
        ts("2026-07-11 08:00:00"),
        "customer_42_canonical",
        country_code="CA",
        subscription_tier="free",
    )
    move_dup = _row(
        "chg_042_move",
        42,
        "UPDATE",
        ts("2026-07-08 12:00:00"),
        ts("2026-07-11 08:00:01"),
        "customer_42_canonical",
        country_code="CA",
        subscription_tier="free",
    )
    delete = _row(
        "chg_042_delete",
        42,
        "DELETE",
        ts("2026-07-20 18:00:00"),
        ts("2026-07-20 18:05:00"),
        "customer_42_canonical",
        country_code="CA",
        subscription_tier="premium",
    )
    return [insert, upgrade, move, move_dup, delete]


def customer_42_events() -> list[EventRow]:
    return [
        EventRow("evt_042_login", 42, "login", ts("2026-07-05 10:00:00")),
        EventRow("evt_042_purchase", 42, "purchase", ts("2026-07-09 11:00:00")),
        EventRow("evt_042_renewal", 42, "renewal", ts("2026-07-15 16:00:00")),
        EventRow("evt_042_support", 42, "support_contact", ts("2026-07-25 09:00:00")),
    ]


def scripted_scenario_rows() -> list[CdcRow]:
    """Hand-built customers that each prove one mutation class."""
    rows: list[CdcRow] = []

    # Customer 1 — normal INSERT, still current.
    rows.append(
        _row(
            "chg_001_insert",
            1,
            "INSERT",
            ts("2026-01-15 09:00:00"),
            ts("2026-01-15 09:01:00"),
            "normal_insert",
        )
    )

    # Customer 2 — normal INSERT + UPDATE.
    rows.extend(
        [
            _row(
                "chg_002_insert",
                2,
                "INSERT",
                ts("2026-01-20 09:00:00"),
                ts("2026-01-20 09:01:00"),
                "normal_update",
            ),
            _row(
                "chg_002_update",
                2,
                "UPDATE",
                ts("2026-03-01 10:00:00"),
                ts("2026-03-01 10:01:00"),
                "normal_update",
                country_code="CA",
                subscription_tier="plus",
            ),
        ]
    )

    # Customer 3 — in-order INSERT + UPDATE + DELETE.
    rows.extend(
        [
            _row(
                "chg_003_insert",
                3,
                "INSERT",
                ts("2026-02-01 09:00:00"),
                ts("2026-02-01 09:01:00"),
                "normal_delete",
            ),
            _row(
                "chg_003_update",
                3,
                "UPDATE",
                ts("2026-02-10 09:00:00"),
                ts("2026-02-10 09:01:00"),
                "normal_delete",
                subscription_tier="plus",
            ),
            _row(
                "chg_003_delete",
                3,
                "DELETE",
                ts("2026-02-20 09:00:00"),
                ts("2026-02-20 09:01:00"),
                "normal_delete",
                subscription_tier="plus",
            ),
        ]
    )

    # Customer 10 — duplicate delivery of one UPDATE change_id.
    update_10 = _row(
        "chg_010_update",
        10,
        "UPDATE",
        ts("2026-03-05 12:00:00"),
        ts("2026-03-05 12:01:00"),
        "duplicate_delivery",
        country_code="GB",
        subscription_tier="plus",
    )
    rows.extend(
        [
            _row(
                "chg_010_insert",
                10,
                "INSERT",
                ts("2026-03-01 09:00:00"),
                ts("2026-03-01 09:01:00"),
                "duplicate_delivery",
            ),
            update_10,
            _row(
                "chg_010_update",
                10,
                "UPDATE",
                ts("2026-03-05 12:00:00"),
                ts("2026-03-05 12:02:00"),
                "duplicate_delivery",
                country_code="GB",
                subscription_tier="plus",
            ),
        ]
    )

    # Customer 11 — full batch replay (same change_ids, later ingested_at).
    c11 = [
        _row(
            "chg_011_insert",
            11,
            "INSERT",
            ts("2026-03-10 09:00:00"),
            ts("2026-03-10 09:01:00"),
            "full_batch_replay",
            country_code="DE",
        ),
        _row(
            "chg_011_update",
            11,
            "UPDATE",
            ts("2026-03-15 09:00:00"),
            ts("2026-03-15 09:01:00"),
            "full_batch_replay",
            country_code="DE",
            subscription_tier="premium",
        ),
    ]
    replay = [
        _row(
            row.change_id,
            row.customer_id,
            row.operation,
            row.source_updated_at,
            row.ingested_at + timedelta(days=7),
            "full_batch_replay",
            country_code=row.country_code,
            subscription_tier=row.subscription_tier,
            account_status=row.account_status,
            email_verified=row.email_verified,
        )
        for row in c11
    ]
    rows.extend(c11 + replay)

    # Customer 12 — late-arriving mutation (update source time before a later update).
    rows.extend(
        [
            _row(
                "chg_012_insert",
                12,
                "INSERT",
                ts("2026-04-01 09:00:00"),
                ts("2026-04-01 09:01:00"),
                "late_arriving",
            ),
            _row(
                "chg_012_later",
                12,
                "UPDATE",
                ts("2026-04-20 09:00:00"),
                ts("2026-04-20 09:01:00"),
                "late_arriving",
                subscription_tier="premium",
            ),
            _row(
                "chg_012_late",
                12,
                "UPDATE",
                ts("2026-04-10 09:00:00"),
                ts("2026-04-22 09:00:00"),
                "late_arriving",
                country_code="FR",
                subscription_tier="free",
            ),
        ]
    )

    # Customer 13 — out-of-order delivery of two updates.
    rows.extend(
        [
            _row(
                "chg_013_insert",
                13,
                "INSERT",
                ts("2026-04-01 08:00:00"),
                ts("2026-04-01 08:01:00"),
                "out_of_order",
            ),
            _row(
                "chg_013_second",
                13,
                "UPDATE",
                ts("2026-04-08 08:00:00"),
                ts("2026-04-06 08:00:00"),
                "out_of_order",
                country_code="AU",
                subscription_tier="plus",
            ),
            _row(
                "chg_013_first",
                13,
                "UPDATE",
                ts("2026-04-04 08:00:00"),
                ts("2026-04-09 08:00:00"),
                "out_of_order",
                country_code="AU",
                subscription_tier="free",
            ),
        ]
    )

    # Customer 14 — stale change arrives after a newer mutation.
    rows.extend(
        [
            _row(
                "chg_014_insert",
                14,
                "INSERT",
                ts("2026-05-01 09:00:00"),
                ts("2026-05-01 09:01:00"),
                "stale_change",
            ),
            _row(
                "chg_014_newer",
                14,
                "UPDATE",
                ts("2026-05-20 09:00:00"),
                ts("2026-05-20 09:01:00"),
                "stale_change",
                country_code="JP",
                subscription_tier="premium",
            ),
            _row(
                "chg_014_stale",
                14,
                "UPDATE",
                ts("2026-05-10 09:00:00"),
                ts("2026-05-21 09:00:00"),
                "stale_change",
                country_code="JP",
                subscription_tier="plus",
            ),
        ]
    )

    # Customer 15 — many in-order changes on one entity.
    state_15 = {
        "country_code": "US",
        "subscription_tier": "free",
        "account_status": "active",
        "email_verified": False,
    }
    rows.append(
        _row(
            "chg_015_insert",
            15,
            "INSERT",
            ts("2026-01-05 09:00:00"),
            ts("2026-01-05 09:01:00"),
            "multiple_changes",
            **state_15,
        )
    )
    multi_updates = [
        ("chg_015_u1", ts("2026-01-12 09:00:00"), {"country_code": "CA"}),
        ("chg_015_u2", ts("2026-01-20 09:00:00"), {"subscription_tier": "plus"}),
        ("chg_015_u3", ts("2026-02-01 09:00:00"), {"email_verified": True}),
        ("chg_015_u4", ts("2026-02-15 09:00:00"), {"account_status": "paused"}),
        ("chg_015_u5", ts("2026-03-01 09:00:00"), {"subscription_tier": "premium"}),
    ]
    for change_id, when, patch in multi_updates:
        state_15.update(patch)
        rows.append(
            _row(
                change_id,
                15,
                "UPDATE",
                when,
                when + timedelta(minutes=1),
                "multiple_changes",
                **state_15,
            )
        )

    # Customer 16 — one mutation changes several attributes.
    rows.extend(
        [
            _row(
                "chg_016_insert",
                16,
                "INSERT",
                ts("2026-06-01 09:00:00"),
                ts("2026-06-01 09:01:00"),
                "multi_attribute",
            ),
            _row(
                "chg_016_multi",
                16,
                "UPDATE",
                ts("2026-06-08 09:00:00"),
                ts("2026-06-08 09:01:00"),
                "multi_attribute",
                country_code="BR",
                subscription_tier="premium",
                account_status="paused",
                email_verified=True,
            ),
        ]
    )

    # Customer 17 — same-day changes.
    rows.extend(
        [
            _row(
                "chg_017_insert",
                17,
                "INSERT",
                ts("2026-06-10 08:00:00"),
                ts("2026-06-10 08:01:00"),
                "same_day",
            ),
            _row(
                "chg_017_afternoon",
                17,
                "UPDATE",
                ts("2026-06-10 16:30:00"),
                ts("2026-06-10 16:31:00"),
                "same_day",
                subscription_tier="plus",
                email_verified=True,
            ),
        ]
    )

    # Customer 18 — same-timestamp conflicting updates (tie-break by change_id).
    rows.extend(
        [
            _row(
                "chg_018_insert",
                18,
                "INSERT",
                ts("2026-04-01 09:00:00"),
                ts("2026-04-01 09:01:00"),
                "same_timestamp_conflict",
            ),
            _row(
                "chg_018_a",
                18,
                "UPDATE",
                ts("2026-04-15 12:00:00"),
                ts("2026-04-15 12:05:00"),
                "same_timestamp_conflict",
                country_code="FR",
            ),
            _row(
                "chg_018_b",
                18,
                "UPDATE",
                ts("2026-04-15 12:00:00"),
                ts("2026-04-15 12:06:00"),
                "same_timestamp_conflict",
                country_code="GB",
            ),
        ]
    )

    # Customer 19 — update then later delete, in order.
    rows.extend(
        [
            _row(
                "chg_019_insert",
                19,
                "INSERT",
                ts("2026-05-01 09:00:00"),
                ts("2026-05-01 09:01:00"),
                "update_then_delete",
                country_code="AU",
            ),
            _row(
                "chg_019_update",
                19,
                "UPDATE",
                ts("2026-05-08 09:00:00"),
                ts("2026-05-08 09:01:00"),
                "update_then_delete",
                country_code="AU",
                subscription_tier="plus",
            ),
            _row(
                "chg_019_delete",
                19,
                "DELETE",
                ts("2026-05-12 09:00:00"),
                ts("2026-05-12 09:01:00"),
                "update_then_delete",
                country_code="AU",
                subscription_tier="plus",
            ),
        ]
    )

    # Customer 20 — late update repairs an already-materialized interval; stays current.
    rows.extend(
        [
            _row(
                "chg_020_insert",
                20,
                "INSERT",
                ts("2026-01-01 09:00:00"),
                ts("2026-01-01 09:01:00"),
                "late_interval_repair",
            ),
            _row(
                "chg_020_later",
                20,
                "UPDATE",
                ts("2026-01-20 09:00:00"),
                ts("2026-01-20 09:01:00"),
                "late_interval_repair",
                subscription_tier="premium",
            ),
            _row(
                "chg_020_late",
                20,
                "UPDATE",
                ts("2026-01-10 09:00:00"),
                ts("2026-01-25 09:00:00"),
                "late_interval_repair",
                country_code="DE",
                subscription_tier="free",
            ),
        ]
    )

    # Customer 21 — delete closes the current record (no tombstone row).
    rows.extend(
        [
            _row(
                "chg_021_insert",
                21,
                "INSERT",
                ts("2026-06-01 10:00:00"),
                ts("2026-06-01 10:01:00"),
                "delete_closes_current",
                country_code="FR",
                subscription_tier="plus",
            ),
            _row(
                "chg_021_delete",
                21,
                "DELETE",
                ts("2026-06-15 10:00:00"),
                ts("2026-06-15 10:01:00"),
                "delete_closes_current",
                country_code="FR",
                subscription_tier="plus",
            ),
        ]
    )

    # Customer 22 — two legitimate change_ids with identical business values.
    rows.extend(
        [
            _row(
                "chg_022_insert",
                22,
                "INSERT",
                ts("2026-03-01 09:00:00"),
                ts("2026-03-01 09:01:00"),
                "identical_values_distinct_ids",
            ),
            _row(
                "chg_022_noop",
                22,
                "UPDATE",
                ts("2026-03-08 09:00:00"),
                ts("2026-03-08 09:01:00"),
                "identical_values_distinct_ids",
            ),
            _row(
                "chg_022_real",
                22,
                "UPDATE",
                ts("2026-03-15 09:00:00"),
                ts("2026-03-15 09:01:00"),
                "identical_values_distinct_ids",
                country_code="CA",
            ),
        ]
    )

    rows.extend(customer_42_rows())
    return rows


def _random_state(rng: random.Random) -> dict[str, object]:
    return {
        "country_code": rng.choice(COUNTRIES),
        "subscription_tier": rng.choice(TIERS),
        "account_status": rng.choice(STATUSES),
        "email_verified": rng.choice((True, False)),
    }


def generated_population_rows(rng: random.Random) -> list[CdcRow]:
    """Fill remaining customer ids so the lab stays small but not toy-empty."""
    rows: list[CdcRow] = []
    generated_ids = [
        cid for cid in range(1, CUSTOMER_COUNT + 1) if cid not in SCRIPTED_CUSTOMER_IDS
    ]
    for customer_id in generated_ids:
        start = datetime(2026, 1, 1, 8, 0, 0) + timedelta(
            days=rng.randint(0, 150), hours=rng.randint(0, 10)
        )
        state = _random_state(rng)
        state["account_status"] = "active"
        insert = _row(
            f"chg_{customer_id:03d}_000",
            customer_id,
            "INSERT",
            start,
            start + timedelta(minutes=rng.randint(1, 30)),
            "generated_population",
            **state,
        )
        rows.append(insert)
        n_updates = rng.randint(2, 5)
        cursor = start
        last = insert
        for seq in range(1, n_updates + 1):
            cursor = cursor + timedelta(days=rng.randint(2, 12), hours=rng.randint(0, 8))
            patch_keys = rng.sample(
                ["country_code", "subscription_tier", "account_status", "email_verified"],
                k=rng.randint(1, 3),
            )
            for key in patch_keys:
                if key == "email_verified":
                    state[key] = not bool(state[key])
                elif key == "country_code":
                    state[key] = rng.choice(COUNTRIES)
                elif key == "subscription_tier":
                    state[key] = rng.choice(TIERS)
                else:
                    state[key] = rng.choice(STATUSES)
            ingested = cursor + timedelta(minutes=rng.randint(1, 20))
            if rng.random() < 0.18:
                ingested = cursor + timedelta(days=rng.randint(3, 14))
            change = _row(
                f"chg_{customer_id:03d}_{seq:03d}",
                customer_id,
                "UPDATE",
                cursor,
                ingested,
                "generated_population",
                **state,
            )
            rows.append(change)
            if rng.random() < 0.12:
                rows.append(
                    _row(
                        change.change_id,
                        customer_id,
                        "UPDATE",
                        cursor,
                        ingested + timedelta(seconds=30),
                        "generated_population",
                        **state,
                    )
                )
            last = change
        if rng.random() < 0.22:
            delete_at = last.source_updated_at + timedelta(days=rng.randint(3, 20))
            rows.append(
                _row(
                    f"chg_{customer_id:03d}_del",
                    customer_id,
                    "DELETE",
                    delete_at,
                    delete_at + timedelta(minutes=2),
                    "generated_population",
                    country_code=last.country_code,
                    subscription_tier=last.subscription_tier,
                    account_status=last.account_status,
                    email_verified=last.email_verified,
                )
            )
    return rows


def generated_events(
    rng: random.Random,
    cdc_rows: list[CdcRow],
    extra: list[EventRow],
) -> list[EventRow]:
    events = list(extra)
    by_customer: dict[int, list[CdcRow]] = {}
    for row in cdc_rows:
        by_customer.setdefault(row.customer_id, []).append(row)

    remaining = TARGET_EVENTS - len(events)
    customer_ids = sorted(cid for cid in by_customer if cid != 42)
    index = 0
    while remaining > 0:
        customer_id = customer_ids[index % len(customer_ids)]
        index += 1
        history = sorted(by_customer[customer_id], key=lambda r: (r.source_updated_at, r.change_id))
        start = history[0].source_updated_at
        deletes = [r for r in history if r.operation == "DELETE"]
        end = deletes[0].source_updated_at if deletes else start + timedelta(days=40)
        span = max(int((end - start).total_seconds()), 3600)
        offset = rng.randint(0, span)
        when = start + timedelta(seconds=offset)
        if deletes and rng.random() < 0.08:
            when = deletes[0].source_updated_at + timedelta(days=rng.randint(1, 10))
        events.append(
            EventRow(
                event_id=f"evt_{customer_id:03d}_{len(events):04d}",
                customer_id=customer_id,
                event_name=rng.choice(EVENT_NAMES),
                event_timestamp=when,
            )
        )
        remaining -= 1
    return events


def build_dataset(seed: int = SEED_DEFAULT) -> tuple[list[CdcRow], list[EventRow]]:
    rng = random.Random(seed)
    cdc = scripted_scenario_rows() + generated_population_rows(rng)
    cdc.sort(key=lambda r: (r.ingested_at, r.change_id, r.source_updated_at))
    events = generated_events(rng, cdc, customer_42_events())
    events.sort(key=lambda r: (r.event_timestamp, r.event_id))
    return cdc, events


def _cdc_to_dict(row: CdcRow) -> dict[str, str]:
    payload = {name: getattr(row, name) for name in CDC_COLUMNS}
    payload["source_updated_at"] = fmt(row.source_updated_at)
    payload["ingested_at"] = fmt(row.ingested_at)
    payload["email_verified"] = "true" if row.email_verified else "false"
    payload["customer_id"] = str(row.customer_id)
    return payload


def _event_to_dict(row: EventRow) -> dict[str, str]:
    return {
        "event_id": row.event_id,
        "customer_id": str(row.customer_id),
        "event_name": row.event_name,
        "event_timestamp": fmt(row.event_timestamp),
    }


def write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_dataset(out_dir: Path, seed: int = SEED_DEFAULT) -> tuple[Path, Path]:
    cdc, events = build_dataset(seed)
    cdc_path = out_dir / "customer_cdc_log.csv"
    events_path = out_dir / "customer_activity_events.csv"
    write_csv(cdc_path, CDC_COLUMNS, [_cdc_to_dict(row) for row in cdc])
    write_csv(events_path, EVENT_COLUMNS, [_event_to_dict(row) for row in events])
    return cdc_path, events_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Chronicle synthetic CDC fixtures")
    parser.add_argument("--seed", type=int, default=SEED_DEFAULT)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "fixtures",
    )
    args = parser.parse_args(argv)
    cdc_path, events_path = write_dataset(args.out, args.seed)
    print(f"wrote {cdc_path}")
    print(f"wrote {events_path}")
    return 0


# dataclasses imported for tests that introspect the row contract
assert {f.name for f in fields(CdcRow)} == set(CDC_COLUMNS)
