"""Build everything from nothing.

  1. apply every feature's schema migrations to an empty database
  2. generate the synthetic group: ledger, bids, trade requests, supply registers
  3. reconcile every supplier invoice at docket level
  4. run the acceptance checks - a build that fails one is not a build
  5. check every table against the digests pinned in infra-azure/build.sha256

Usage (from backend/):
  uv run python ../scripts/build_platform.py              # build, verify against the manifest
  uv run python ../scripts/build_platform.py --write-manifest
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from src.app.pipeline import acceptance, migrate  # noqa: E402
from src.app.pipeline import reference as ref  # noqa: E402
from src.app.pipeline.generate import generate  # noqa: E402
from src.app.services import msr_recon  # noqa: E402
from src.settings import settings  # noqa: E402

MANIFEST = REPO_ROOT / "infra-azure" / "build.sha256"
# Binary columns are rendered by a PDF library and are not part of the pinned output.
UNPINNED = {"schema_migrations", "msr_document_blob", "bid_revision_pdf", "kv"}


def table_digests(con: duckdb.DuckDBPyConnection) -> list[str]:
    lines = []
    tables = [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_type = 'BASE TABLE' ORDER BY 1").fetchall()]
    for table in tables:
        if table in UNPINNED:
            continue
        digest = hashlib.sha256()
        for row in con.execute(f"SELECT * FROM {table} ORDER BY ALL").fetchall():
            digest.update(("\x1f".join("" if v is None else str(v) for v in row) + "\n").encode("utf-8"))
        lines.append(f"{digest.hexdigest()}  {table}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args()
    t0 = time.perf_counter()

    db_path = Path(settings.build_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    for stale in (db_path, db_path.with_name(db_path.name + ".wal")):
        stale.unlink(missing_ok=True)
    con = duckdb.connect(str(db_path))

    print("1/5 migrations")
    applied = migrate.apply(con, ref.DEMO_NOW)
    print(f"    {len(applied)} applied: {', '.join(applied)}")

    print("2/5 generating the synthetic group")
    generate(con)

    print("3/5 reconciling supplier invoices at docket level")
    for project_id in ref.MSR_PROJECTS:
        msr_recon.recompute(con, project_id)
    print("    " + ", ".join(f"{n} {s}" for s, n in con.execute(
        "SELECT recon_status, count(*) FROM msr_invoice GROUP BY 1 ORDER BY 1").fetchall()))

    print("4/5 acceptance checks")
    failed = [(name, detail) for name, ok, detail in acceptance.run(con) if not ok]
    if failed:
        for name, detail in failed:
            print(f"    FAILED {name}: {detail}", file=sys.stderr)
        return 1
    print(f"    all {len(acceptance.CHECKS)} pass")

    print("5/5 manifest")
    lines = table_digests(con)
    con.execute("INSERT INTO kv VALUES ('build_seconds', ?), ('git_sha', ?)",
                [f"{time.perf_counter() - t0:.1f}", settings.git_sha or "dev"])
    con.close()
    body = "\n".join(lines) + "\n"
    if args.write_manifest or not MANIFEST.exists():
        MANIFEST.write_text("# SHA-256 of every table the build produces.\n"
                            "# Regenerate with: uv run python ../scripts/build_platform.py --write-manifest\n" + body,
                            encoding="utf-8", newline="\n")
        print(f"    manifest written: {len(lines)} tables")
    else:
        pinned = [ln for ln in MANIFEST.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")]
        if sorted(pinned) != sorted(lines):
            changed = sorted(set(lines) ^ set(pinned))
            print(f"    MISMATCH against the pinned manifest in: {sorted({ln.split('  ')[1] for ln in changed})}", file=sys.stderr)
            return 1
        print(f"    verified: {len(lines)} tables match the pinned manifest")

    from src.app.services.db import copy_build
    copy_build()
    print(f"done in {time.perf_counter() - t0:.1f} s -> {db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
