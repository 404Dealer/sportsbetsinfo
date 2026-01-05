"""SQLite database connection management."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


def get_connection(db_path: Path | str) -> sqlite3.Connection:
    """Create a new database connection.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        SQLite connection with optimized settings
    """
    db_path = Path(db_path)

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")

    # Optimize for reliability over speed
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")

    return conn


@contextmanager
def get_connection_context(
    db_path: Path | str,
) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database connections.

    Automatically commits on success, rolls back on exception.

    Args:
        db_path: Path to the SQLite database file

    Yields:
        SQLite connection
    """
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
