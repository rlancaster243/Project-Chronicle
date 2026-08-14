from __future__ import annotations

import csv
from pathlib import Path

import yaml

from chronicle.generator import (
    CDC_COLUMNS,
    CUSTOMER_COUNT,
    SEED_DEFAULT,
    TARGET_EVENTS,
    build_dataset,
    write_dataset,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
CATALOG = FIXTURES / "expected" / "scenario_catalog.yml"


def _load_catalog() -> dict:
    return yaml.safe_load(CATALOG.read_text(encoding="utf-8"))


def test_same_seed_is_byte_identical(tmp_path: Path) -> None:
    first_cdc, first_events = write_dataset(tmp_path / "a", SEED_DEFAULT)
    second_cdc, second_events = write_dataset(tmp_path / "b", SEED_DEFAULT)
    assert first_cdc.read_bytes() == second_cdc.read_bytes()
    assert first_events.read_bytes() == second_events.read_bytes()


def test_dataset_scale_and_schema() -> None:
    cdc, events = build_dataset(SEED_DEFAULT)
    customer_ids = {row.customer_id for row in cdc}
    assert customer_ids == set(range(1, CUSTOMER_COUNT + 1))
    assert 400 <= len(cdc) <= 700
    assert len(events) == TARGET_EVENTS
    assert {row.operation for row in cdc} == {"INSERT", "UPDATE", "DELETE"}


def test_generated_fixtures_match_generator() -> None:
    cdc, events = build_dataset(SEED_DEFAULT)
    generated_cdc = list(csv.DictReader((FIXTURES / "customer_cdc_log.csv").open()))
    generated_events = list(csv.DictReader((FIXTURES / "customer_activity_events.csv").open()))
    assert len(generated_cdc) == len(cdc)
    assert len(generated_events) == len(events)
    assert generated_cdc[0].keys() == set(CDC_COLUMNS)
    assert generated_cdc[0]["change_id"] == cdc[0].change_id
    assert generated_events[0]["event_id"] == events[0].event_id


def test_customer_42_physical_arrival_order() -> None:
    catalog = _load_catalog()
    expected_order = next(
        item["physical_change_id_order"]
        for item in catalog["mutation_classes"]
        if item["id"] == "customer_42_canonical"
    )
    cdc, _ = build_dataset(SEED_DEFAULT)
    actual = [row.change_id for row in cdc if row.customer_id == 42]
    assert actual == expected_order
    assert actual.count("chg_042_move") == 2
    move_rows = [row for row in cdc if row.change_id == "chg_042_move"]
    assert move_rows[0].source_updated_at < move_rows[0].ingested_at
    upgrade = next(row for row in cdc if row.change_id == "chg_042_upgrade")
    assert upgrade.ingested_at < move_rows[0].ingested_at


def test_every_catalog_class_is_present() -> None:
    catalog = _load_catalog()
    cdc, _ = build_dataset(SEED_DEFAULT)
    tags = {row.scenario_tag for row in cdc}
    customers = {row.customer_id for row in cdc}
    for item in catalog["mutation_classes"]:
        assert item["tag"] in tags, item["id"]
        assert item["customer_id"] in customers, item["id"]


def test_duplicate_delivery_is_not_identical_value_pair() -> None:
    cdc, _ = build_dataset(SEED_DEFAULT)
    change_ids = [row.change_id for row in cdc]
    assert change_ids.count("chg_010_update") == 2
    identical = [
        row
        for row in cdc
        if row.customer_id == 22 and row.change_id in {"chg_022_insert", "chg_022_noop"}
    ]
    assert len({row.change_id for row in identical}) == 2
    assert identical[0].country_code == identical[1].country_code
    assert identical[0].subscription_tier == identical[1].subscription_tier
