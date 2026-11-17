"""Schema migrations, one folder per feature, applied in order and recorded.

Each feature owns its tables: adding to the Material Supply Register means a
new numbered file in migrations/material_register/, never an edit to one that
has run. The runner records a checksum, so a file changed after it was applied
is caught rather than silently skipped.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import duckdb

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
# Order matters only where one feature's views read another's tables.
FEATURES = ["core", "finance", "bid_summary", "trade_planner", "material_register", "agent"]


def pending(con: duckdb.DuckDBPyConnection) -> list[tuple[str, str, Path, str]]:
    con.execute("""CREATE TABLE IF NOT EXISTS schema_migrations
                   (feature VARCHAR, version VARCHAR, checksum VARCHAR, applied_at TIMESTAMP)""")
    applied = {(f, v): c for f, v, c in con.execute("SELECT feature, version, checksum FROM schema_migrations").fetchall()}
    todo = []
    for feature in FEATURES:
        for path in sorted((MIGRATIONS / feature).glob("*.sql")):
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            known = applied.get((feature, path.stem))
            if known is None:
                todo.append((feature, path.stem, path, checksum))
            elif known != checksum:
                raise RuntimeError(f"migration {feature}/{path.name} changed after it was applied; add a new file instead")
    return todo


def apply(con: duckdb.DuckDBPyConnection, at: datetime) -> list[str]:
    done = []
    for feature, version, path, checksum in pending(con):
        con.execute("BEGIN")
        try:
            con.execute(path.read_text(encoding="utf-8"))
            con.execute("INSERT INTO schema_migrations VALUES (?, ?, ?, ?)", [feature, version, checksum, at])
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        done.append(f"{feature}/{version}")
    return done
