from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = ROOT / "fixtures" / "expected"

TS_FMT = "%Y-%m-%d %H:%M:%S"


def parse_ts(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    return datetime.strptime(str(value)[:19], TS_FMT)


def load_expected_intervals(name: str) -> list[dict]:
    path = EXPECTED / name
    rows = []
    with path.open(encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            rows.append(
                {
                    "customer_id": int(raw["customer_id"]),
                    "country_code": raw["country_code"],
                    "subscription_tier": raw["subscription_tier"],
                    "account_status": raw["account_status"],
                    "email_verified": raw["email_verified"].lower() == "true",
                    "valid_from": parse_ts(raw["valid_from"]),
                    "valid_to": parse_ts(raw["valid_to"]),
                    "row_current": raw["row_current"].lower() == "true",
                    "source_change_id": raw["source_change_id"],
                }
            )
    return rows


def fetch_customer_intervals(con, customer_id: int) -> list[dict]:
    result = con.execute(
        """
        select
            customer_id,
            country_code,
            subscription_tier,
            account_status,
            email_verified,
            valid_from,
            valid_to,
            row_current,
            source_change_id
        from dimension_customers_t2
        where customer_id = ?
        order by valid_from, source_change_id
        """,
        [customer_id],
    ).fetchall()
    columns = [
        "customer_id",
        "country_code",
        "subscription_tier",
        "account_status",
        "email_verified",
        "valid_from",
        "valid_to",
        "row_current",
        "source_change_id",
    ]
    return [dict(zip(columns, row, strict=True)) for row in result]


def assert_intervals_match(actual: list[dict], expected: list[dict]) -> None:
    assert len(actual) == len(expected), (actual, expected)
    for got, want in zip(actual, expected, strict=True):
        assert got["customer_id"] == want["customer_id"]
        assert got["country_code"] == want["country_code"]
        assert got["subscription_tier"] == want["subscription_tier"]
        assert got["account_status"] == want["account_status"]
        assert bool(got["email_verified"]) == want["email_verified"]
        assert parse_ts(got["valid_from"]) == want["valid_from"]
        assert parse_ts(got["valid_to"]) == want["valid_to"]
        assert bool(got["row_current"]) == want["row_current"]
        assert got["source_change_id"] == want["source_change_id"]
