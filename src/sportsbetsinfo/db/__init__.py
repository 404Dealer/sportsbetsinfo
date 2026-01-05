"""Database layer with append-only repositories."""

from sportsbetsinfo.db.connection import get_connection
from sportsbetsinfo.db.schema import create_all_tables

__all__ = ["get_connection", "create_all_tables"]
