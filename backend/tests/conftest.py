"""Shared fixtures.

The suite runs against the built database (scripts/build_platform.py). Tests
that write work on a throwaway copy, never the built one. No test calls a
model: the key is cleared, so the deterministic paths are what is tested, and
model behaviour is graded separately by evals/run_agent_eval.py.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="plexxcon-tests-"))
os.environ["DUCKDB_PATH"] = str(_TMP / "platform.duckdb")
os.environ["DEMO_WRITE_TOKEN"] = "test-token"
os.environ["LLM_BASE_URL"] = ""
os.environ["LLM_API_KEY"] = ""
os.environ["HUBSPOT_TOKEN"] = ""

from src.settings import settings  # noqa: E402

WRITE = {"X-Write-Token": "test-token"}


def as_(actor: str) -> dict[str, str]:
    return {**WRITE, "X-Actor": actor}


def pytest_collection_modifyitems(config, items):
    if not settings.build_db_path.exists():
        skip = pytest.mark.skip(reason="build first: uv run python ../scripts/build_platform.py")
        for item in items:
            item.add_marker(skip)


@pytest.fixture()
def fresh_db():
    from src.app.services import db
    db.reset_to_build()
    yield db
    db.reset_to_build()


@pytest.fixture()
def client(fresh_db):
    from fastapi.testclient import TestClient

    from src.main import app
    return TestClient(app)


def pytest_sessionfinish(session, exitstatus):
    from src.app.services import db
    try:
        if db._con is not None:
            db._con.close()
    except Exception:  # noqa: BLE001
        pass
    shutil.rmtree(_TMP, ignore_errors=True)
