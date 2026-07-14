"""Shared pytest fixtures for the kanuni_ingest test suite."""

import sys
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# This tests/ tree has no __init__.py (apps/api/tests and apps/ingestion/tests
# would otherwise both resolve to the same dotted module name "tests" and
# collide during conftest collection). Adding this directory to sys.path lets
# test modules do a plain `from fakes import ...` regardless of nesting depth.
sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the directory containing the real fixture PDFs."""
    return FIXTURES_DIR
