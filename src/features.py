"""Run feature SQL (calendar, weather, trip features, zone-hour lags)."""

from __future__ import annotations

from src.config import SQL_DIR
from src.db import connect, run_sql_file
from src.logging_utils import get_logger

log = get_logger(__name__)


def run() -> dict:
    con = connect()
    run_sql_file(con, SQL_DIR / "02_features.sql")
    n = con.execute("SELECT COUNT(*) FROM fact_zone_hour").fetchone()[0]
    n_lag = con.execute("SELECT COUNT(*) FROM fact_zone_hour_lags").fetchone()[0]
    con.close()
    log.info("fact_zone_hour rows=%s", n)
    return {"fact_zone_hour_rows": int(n), "fact_zone_hour_lag_rows": int(n_lag)}
