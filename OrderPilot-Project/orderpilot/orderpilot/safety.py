"""Read-only guard for SQL written by the model.

Rules enforced before any query runs:
1. exactly one statement
2. it must be a SELECT (or WITH ... SELECT)
3. no data-changing or admin keywords
4. only tables on the allow-list
5. a LIMIT is added when missing

This is defence layer one. Layer two is Unity Catalog permissions on the
account the app runs as (SELECT only on the order tables).
"""

import re

from orderpilot import config

FORBIDDEN_WORDS = [
    "insert", "update", "delete", "merge", "drop", "alter", "create",
    "truncate", "grant", "revoke", "copy", "optimize", "vacuum", "call", "use",
    "attach", "pragma",
]


class UnsafeSQLError(ValueError):
    """Raised when a query breaks one of the rules."""


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)  # -- line comments
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)  # /* block comments */
    return sql


def _strip_strings(sql: str) -> str:
    # Blank out quoted text so a value like 'drop shipping' is not flagged.
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def check_sql(sql: str) -> str:
    """Return a safe, LIMITed version of the query or raise UnsafeSQLError."""
    cleaned = _strip_comments(sql).strip().rstrip(";").strip()
    if not cleaned:
        raise UnsafeSQLError("The query is empty.")

    words_only = _strip_strings(cleaned).lower()

    # Rule 1: one statement only.
    if ";" in words_only:
        raise UnsafeSQLError("Only one SQL statement is allowed.")

    # Rule 2: must be a read.
    first_word = words_only.split()[0]
    if first_word not in ("select", "with"):
        raise UnsafeSQLError("Only SELECT queries are allowed.")

    # Rule 3: no forbidden keywords anywhere.
    for word in FORBIDDEN_WORDS:
        if re.search(rf"\b{word}\b", words_only):
            raise UnsafeSQLError(f"The word '{word.upper()}' is not allowed.")

    # Rule 4: every table after FROM / JOIN must be allowed (CTE names are fine).
    allowed = {config.table(t).lower() for t in config.READ_TABLES}
    allowed |= {t.lower() for t in config.READ_TABLES}
    cte_names = set(re.findall(r"\b(\w+)\s+as\s*\(", words_only))
    # Functions such as EXTRACT(month FROM order_date) also contain FROM; hide them.
    no_functions = re.sub(r"\b(?:extract|substring|trim|position|overlay)\s*\([^()]*\)", "x", words_only)
    for name in re.findall(r"\b(?:from|join)\s+([\w.`]+)", no_functions):
        name = name.replace("`", "")
        if name not in allowed and name not in cte_names:
            raise UnsafeSQLError(f"Table '{name}' is not on the allowed list.")

    # Rule 5: cap the result size.
    if not re.search(r"\blimit\s+\d+\s*$", words_only):
        cleaned = f"{cleaned}\nLIMIT {config.MAX_ROWS}"

    return cleaned
