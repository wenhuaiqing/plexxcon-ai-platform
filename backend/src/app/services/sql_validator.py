"""The gate every model-written query passes before it runs.

SELECT-only, one statement, a fixed allowlist of semantic views, no function
that reaches outside the query, and a row limit injected or clamped. The
database connection also has external access switched off, so the gate is not
the only thing between a prompt and a file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The agent's whole world is the semantic views (migrations/agent). It never
# sees a base table, the audit log, a draft, or anything a person typed as
# free text into a workflow.
ALLOWED_TABLES = {
    "v_project", "v_gl", "v_pnl_monthly", "v_balance_sheet", "v_related_party_balance",
    "v_crm_deal", "v_bid_revision", "v_bid_cost_line",
    "v_rate_library", "v_trade_request", "v_trade_request_trade",
    "v_msr_budget", "v_msr_delivery", "v_msr_docket", "v_msr_invoice", "v_msr_price",
}

# Functions that reach outside the query: the environment, files, settings.
FORBIDDEN_FUNCTIONS = {
    "getenv", "current_setting", "read_text", "read_blob", "read_csv", "read_csv_auto", "read_json",
    "read_json_auto", "read_parquet", "glob", "query", "query_table", "sql_auto_complete",
}

# DDL/DML keywords that must NEVER appear in a generated query.
FORBIDDEN_KEYWORDS = {
    "insert", "update", "delete", "drop", "truncate", "alter", "create",
    "attach", "detach", "copy", "export", "import", "pragma", "set", "call",
    "grant", "revoke", "merge", "vacuum", "install", "load",
}

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


@dataclass
class ValidationOutcome:
    ok: bool
    sql: str          # post-rewrite SQL ready to execute (or the original on failure)
    errors: list[str]
    tables_referenced: list[str]


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", "", sql)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql


def _statement_count(sql: str) -> int:
    # Count top-level semicolons (ignoring those inside strings is overkill for
    # a demo - the LLM rarely produces string literals containing ; here).
    cleaned = sql.strip().rstrip(";")
    return cleaned.count(";") + 1 if cleaned else 0


# FROM/JOIN followed by a string literal is DuckDB's replacement scan over a
# file path or URL (`FROM 'data.csv'`, `FROM 'https://host/x.parquet'`).
# The identifier regex below would silently skip it, so reject explicitly.
_QUOTED_SOURCE = re.compile(r"\b(?:from|join)\s+'", re.IGNORECASE)


def _extract_tables(sql: str) -> set[str]:
    # Match FROM <name> and JOIN <name>, optionally schema-qualified. Strip
    # quoting. Good enough for the demo allowlist check.
    pattern = re.compile(r"\b(?:from|join)\s+([\"`\w\.]+)", re.IGNORECASE)
    tables: set[str] = set()
    for match in pattern.finditer(sql):
        raw = match.group(1).strip().strip('"').strip("`")
        # Take the last segment of a dotted name (e.g. schema.table -> table)
        last = raw.split(".")[-1]
        tables.add(last.lower())
    return tables


def _extract_cte_names(sql: str) -> set[str]:
    """Capture CTE names defined in WITH clauses so they're allowed in FROM."""
    # Match `WITH name AS (` and `, name AS (`.
    pattern = re.compile(
        r"(?:\bwith\s+recursive\s+|\bwith\s+|,\s*)([\"`\w]+)\s+as\s*\(",
        re.IGNORECASE,
    )
    return {
        m.group(1).strip().strip('"').strip("`").lower()
        for m in pattern.finditer(sql)
    }


# A function in table position (duckdb_tables(), read_csv(...), range(...)) names
# no table for the allowlist to check, so none is allowed.
_TABLE_FUNCTION = re.compile(r"\b(?:from|join)\s+[\w\.]+\s*\(", re.IGNORECASE)


def _parsed_tables(sql: str) -> set[str] | None:
    """Every table the query touches, according to DuckDB's own parser - which
    sees comma joins and subqueries that a regular expression misses. None when
    the query does not parse; the caller treats that as a refusal."""
    import duckdb
    try:
        con = duckdb.connect(":memory:")
        try:
            return {str(t).split(".")[-1].lower() for t in con.get_table_names(sql)}
        finally:
            con.close()
    except Exception:  # noqa: BLE001 - fail closed on anything the parser will not accept
        return None


def _has_limit(sql: str) -> bool:
    return re.search(r"\blimit\s+\d+", sql, re.IGNORECASE) is not None


def _inject_limit(sql: str, limit: int) -> str:
    stripped = sql.rstrip().rstrip(";")
    return f"{stripped}\nLIMIT {limit}"


def validate(sql: str) -> ValidationOutcome:
    errors: list[str] = []

    if not sql or not sql.strip():
        return ValidationOutcome(ok=False, sql=sql, errors=["empty SQL"], tables_referenced=[])

    cleaned = _strip_comments(sql).strip().rstrip(";")
    lowered = cleaned.lower()

    if _statement_count(cleaned) > 1:
        errors.append("multiple statements are not allowed")

    if not lowered.lstrip("(").startswith(("select", "with")):
        errors.append("only SELECT/WITH queries are allowed")

    for kw in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", lowered):
            errors.append(f"forbidden keyword: {kw}")

    for fn in FORBIDDEN_FUNCTIONS:
        if re.search(rf"\b{re.escape(fn)}\s*\(", lowered):
            errors.append(f"forbidden function: {fn}")

    if _QUOTED_SOURCE.search(lowered):
        errors.append("file or URL sources are not allowed; query the allowlisted tables")

    if _TABLE_FUNCTION.search(cleaned):
        errors.append("table functions are not allowed; query the allowlisted views")

    tables = _extract_tables(cleaned)
    cte_names = _extract_cte_names(cleaned)
    if not errors:
        parsed = _parsed_tables(cleaned)
        if parsed is None:
            errors.append("the query does not parse as a single SELECT")
        else:
            tables |= parsed - cte_names
    not_allowed = sorted(
        t for t in tables
        if t not in ALLOWED_TABLES and t not in cte_names
    )
    if not_allowed:
        errors.append(f"table(s) not in allowlist: {', '.join(not_allowed)}")

    if errors:
        return ValidationOutcome(ok=False, sql=sql, errors=errors, tables_referenced=sorted(tables))

    final_sql = cleaned
    if not _has_limit(final_sql):
        final_sql = _inject_limit(final_sql, DEFAULT_LIMIT)
    else:
        # Clamp any explicit LIMIT above the ceiling
        def clamp(match: re.Match[str]) -> str:
            n = int(match.group(1))
            return f"LIMIT {min(n, MAX_LIMIT)}"
        final_sql = re.sub(r"\bLIMIT\s+(\d+)", clamp, final_sql, flags=re.IGNORECASE)

    return ValidationOutcome(ok=True, sql=final_sql, errors=[], tables_referenced=sorted(tables))
