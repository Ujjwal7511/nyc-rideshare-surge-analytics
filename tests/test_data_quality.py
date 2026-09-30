"""Data-quality tests against the DuckDB warehouse (run after pipeline)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from src.config import WAREHOUSE


@pytest.fixture(scope="module")
def con():
    if not WAREHOUSE.exists():
        pytest.skip("warehouse missing; run pipeline first")
    return duckdb.connect(str(WAREHOUSE), read_only=True)


def test_clean_table_exists(con):
    n = con.execute("SELECT COUNT(*) FROM trips_clean").fetchone()[0]
    assert n > 1000


def test_no_negative_fares(con):
    n = con.execute("SELECT COUNT(*) FROM trips_clean WHERE base_passenger_fare < 0").fetchone()[0]
    assert n == 0


def test_no_nonpositive_miles(con):
    n = con.execute("SELECT COUNT(*) FROM trips_clean WHERE trip_miles <= 0").fetchone()[0]
    assert n == 0


def test_timestamps_ordered(con):
    n = con.execute(
        """
        SELECT COUNT(*) FROM trips_clean
        WHERE dropoff_datetime < pickup_datetime
           OR pickup_datetime < request_datetime
        """
    ).fetchone()[0]
    assert n == 0


def test_no_unknown_pu_zones(con):
    n = con.execute(
        "SELECT COUNT(*) FROM trips_clean WHERE pu_location_id IN (264, 265)"
    ).fetchone()[0]
    assert n == 0


def test_fact_grain_unique(con):
    dups = con.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT location_id, hour_ts, COUNT(*) c
            FROM fact_zone_hour
            GROUP BY 1, 2
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    assert dups == 0


def test_lags_not_from_future(con):
    n = con.execute(
        """
        SELECT COUNT(*) FROM fact_zone_hour_lags
        WHERE demand_lag_1h IS NOT NULL
          AND hour_ts = (
              SELECT MIN(hour_ts) FROM fact_zone_hour_lags t2
              WHERE t2.location_id = fact_zone_hour_lags.location_id
          )
        """
    ).fetchone()[0]
    assert n == 0


def test_powerbi_export_exists():
    root = Path(__file__).resolve().parents[1] / "data" / "powerbi"
    for name in [
        "fact_zone_hour.parquet",
        "fact_forecast.parquet",
        "dim_zone.parquet",
        "dim_date.parquet",
        "dim_weather.parquet",
        "fact_reposition_recommendations.parquet",
    ]:
        assert (root / name).exists(), name
