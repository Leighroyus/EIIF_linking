from __future__ import annotations

from pathlib import Path

import duckdb


def connect(database_path: str = ":memory:") -> duckdb.DuckDBPyConnection:
    if database_path != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(database_path)
    conn.execute("PRAGMA threads=4")
    conn.execute("CREATE SCHEMA IF NOT EXISTS lnk")
    conn.execute("CREATE SCHEMA IF NOT EXISTS wrk")
    conn.execute("CREATE SCHEMA IF NOT EXISTS out")
    return conn
