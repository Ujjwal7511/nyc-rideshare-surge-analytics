"""DuckDB connection helper."""

from __future__ import annotations

from pathlib import Path

import duckdb

from src.config import WAREHOUSE, DATA_PROCESSED
from src.logging_utils import get_logger

log = get_logger(__name__)


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(WAREHOUSE), read_only=read_only)
    con.execute("SET threads TO 4")
    con.execute("SET memory_limit = '6GB'")
    return con


def run_sql_file(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    log.info("Running SQL %s", path.name)
    sql = path.read_text(encoding="utf-8")
    con.execute(sql)
