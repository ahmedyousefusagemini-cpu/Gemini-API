"""Shared pytest fixtures.

Live integration tests are gated by the `live` marker registered in
`pyproject.toml` and excluded from the default unit-test run via
`-m 'not live'` in CI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Filesystem path to the tests/fixtures directory."""
    return _FIXTURES_DIR


@pytest.fixture(scope="session")
def otaq7b_sample(fixtures_dir: Path) -> Any:
    """Decoded golden `otAQ7b` response captured from the live web UI.

    The fixture is a minimal but structurally faithful slice of the real
    response (three modes plus a thinking-level policy block). Tests should
    treat positional indices and shape as the contract, not exact strings.
    """
    with (fixtures_dir / "otaq7b_response.json").open("r", encoding="utf-8") as fh:
        return json.load(fh)
