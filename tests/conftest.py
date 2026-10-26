"""Shared test setup: the project root on sys.path, and a clean summary cache per test."""

import sys
from pathlib import Path

import pytest

pytest_plugins = ["nicegui.testing.user_plugin"]

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag import summarizer  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_summary_cache():
    summarizer.clear_cache()
    yield
    summarizer.clear_cache()
