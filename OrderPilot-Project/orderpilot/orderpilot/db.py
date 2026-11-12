"""Database access layer.

Two interchangeable backends with the same tiny interface:

    query(sql, params)   -> list of dict rows
    execute(sql, params) -> None (used only for the approved-draft insert)

Both accept named parameters in ":name" style, which SQLite and the
Databricks SQL connector support natively.
"""

import sqlite3
from typing import Any

from orderpilot import config


class LocalDB:
    """SQLite database in a single local file, for development and tests."""

    def __init__(self, path: str | None = None):
        self.path = path or config.LOCAL_DB_PATH

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row  # lets us turn each row into a dict
        return conn

    def query(self, sql: str, params: dict | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(sql, params or {}).fetchall()
            return [dict(r) for r in rows]

    def execute(self, sql: str, params: dict | None = None) -> None:
        with self._connect() as conn:
            conn.execute(sql, params or {})
            conn.commit()


class DatabricksDB:
    """Unity Catalog tables queried through a Databricks SQL warehouse."""

    def __init__(self):
        # Imported lazily so local mode works without the Databricks packages.
        from databricks.sdk.core import Config

        # Config() finds credentials on its own: DATABRICKS_HOST + DATABRICKS_TOKEN
        # on your laptop, or the app's service principal inside a Databricks App.
        self.cfg = Config()
        self.http_path = config.databricks_http_path()
        if not self.http_path:
            raise RuntimeError("Set DATABRICKS_HTTP_PATH or DATABRICKS_WAREHOUSE_ID in .env")

    def _connect(self):
        from databricks import sql

        return sql.connect(
            server_hostname=self.cfg.host.replace("https://", "").rstrip("/"),
            http_path=self.http_path,
            credentials_provider=lambda: self.cfg.authenticate,
        )

    def query(self, sql: str, params: dict | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params or None)
            columns = [c[0] for c in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    def execute(self, sql: str, params: dict | None = None) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params or None)


def get_db():
    """Return the backend that matches ORDERPILOT_MODE."""
    if config.MODE == "databricks":
        return DatabricksDB()
    return LocalDB()
