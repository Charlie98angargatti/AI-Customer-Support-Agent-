"""
services/db_service.py
======================
Provides a thread-safe, singleton DuckDB connection.

DuckDB is a lightweight, in-process analytical database — perfect for our use
case because:
  - No server to run (unlike PostgreSQL)
  - Handles concurrent reads well (write lock is per-connection)
  - SQL interface familiar to any developer
  - Single .duckdb file makes the project fully portable

Thread-safety: DuckDB connections are not thread-safe by default.
We use a threading.Lock() so multiple simultaneous API requests don't
collide on the same connection.

How it connects:
  tools/*.py → import get_connection() → run SQL queries → return results
"""

import duckdb
import threading
import os

# ─── Singleton pattern ─────────────────────────────────────────────────────────
# _connection: duckdb.DuckDBPyConnection | None = None
# _lock = threading.Lock()

_connection = None
_lock = threading.RLock()

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "crm.duckdb")


def get_connection() -> duckdb.DuckDBPyConnection:
    """
    Returns the shared DuckDB connection, creating it on first call.
    Using a single connection object in read-heavy workloads is efficient
    because DuckDB caches query plans and column statistics.
    """
    global _connection
    if _connection is None:
        with _lock:
            if _connection is None:
                _connection = duckdb.connect(DB_PATH, read_only=False)
    return _connection


def execute_query(sql: str, params: list = None):
    """
    Thread-safe wrapper for DuckDB queries.
    Returns a list of dicts — easy to serialize as JSON.

    params: positional parameters (avoids SQL injection)
    """
    with _lock:
        con = get_connection()
        if params:
            result = con.execute(sql, params).fetchall()
            cols = [d[0] for d in con.execute(sql, params).description or []]
        else:
            # cursor = con.execute(sql)
            # result = cursor.fetchall()
            # cols = [d[0] for d in cursor.description] if cursor.description else []
            cursor = con.execute(sql, params) if params else con.execute(sql)
            result = cursor.fetchall()
            cols = [d[0] for d in cursor.description] if cursor.description else []

    return [dict(zip(cols, row)) for row in result]


def execute_write(sql: str, params: list = None) -> int:
    """
    Executes INSERT / UPDATE statements.
    Returns the number of rows affected.
    """
    with _lock:
        con = get_connection()
        if params:
            con.execute(sql, params)
        else:
            con.execute(sql)
        # DuckDB auto-commits in the default mode
        return 1
    
    if __name__ == "__main__":
        from db_service import execute_query

    result = execute_query("SELECT * FROM customers LIMIT 3")
    print(result)