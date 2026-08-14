from __future__ import annotations

from pathlib import Path

import pytest

from chronicle.generator import SEED_DEFAULT, write_dataset

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def generate_synthetic_inputs() -> None:
    """Make a fresh clone testable without committing generated source CSVs."""
    write_dataset(FIXTURES, SEED_DEFAULT)
