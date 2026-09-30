"""Export star-schema files for Power BI (<500k fact rows)."""

from __future__ import annotations

from src.config import DATA_POWERBI, MAX_FACT_ROWS, MIN_ZONE_TRIPS_FOR_FACT
from src.db import connect
from src.logging_utils import get_logger

log = get_logger(__name__)


def run() -> dict:
    DATA_POWERBI.mkdir(parents=True, exist_ok=True)
    con = connect()
    con.execute(
        f"""
        CREATE OR REPLACE TABLE pbi_zones AS
        SELECT location_id FROM agg_zone_summary
        WHERE trips >= {MIN_ZONE_TRIPS_FOR_FACT}
        ORDER BY trips DESC
        """
    )
    n_keep = con.execute("SELECT COUNT(*) FROM pbi_zones").fetchone()[0]
    fact_n = con.execute(
        """
        SELECT COUNT(*) FROM fact_zone_hour f
        JOIN pbi_zones p ON f.location_id = p.location_id
        """
    ).fetchone()[0]
    extra_filter = ""
    if fact_n > MAX_FACT_ROWS:
        extra_filter = "AND f.trips >= 2"
        fact_n = con.execute(
            f"""
            SELECT COUNT(*) FROM fact_zone_hour f
            JOIN pbi_zones p ON f.location_id = p.location_id
            WHERE TRUE {extra_filter}
            """
        ).fetchone()[0]
    log.info("Exporting fact_zone_hour rows=%s zones=%s", fact_n, n_keep)

    def parquet(sql: str, name: str) -> int:
        path = (DATA_POWERBI / name).as_posix()
        con.execute(f"COPY ({sql}) TO '{path}' (FORMAT PARQUET)")
        return int(con.execute(f"SELECT COUNT(*) FROM read_parquet('{path}')").fetchone()[0])

    n_fact = parquet(
        f"""
        SELECT
            f.location_id,
            f.hour_ts,
            f.date_key,
            f.hour_of_day,
            f.weekday,
            f.month,
            f.trips,
            f.revenue,
            f.driver_pay,
            f.avg_wait_minutes,
            f.avg_take_rate,
            f.revenue_per_trip,
            f.supply_proxy,
            f.is_rain,
            f.is_snow,
            f.is_holiday,
            f.is_weekend,
            f.is_rush_hour,
            f.temp_c
        FROM fact_zone_hour f
        JOIN pbi_zones p ON f.location_id = p.location_id
        WHERE TRUE {extra_filter}
        """,
        "fact_zone_hour.parquet",
    )
    n_fc = parquet(
        """
        SELECT location_id, hour_ts, trips AS actual_trips,
               pred_lgb, pred_naive_168, pred_ma, split
        FROM fact_forecast
        """,
        "fact_forecast.parquet",
    )
    n_z = parquet(
        """
        SELECT location_id, borough, zone_name, service_zone,
               centroid_lat, centroid_lon, is_airport, cluster_id, cluster_name
        FROM dim_zone
        """,
        "dim_zone.parquet",
    )
    n_d = parquet("SELECT * FROM dim_date", "dim_date.parquet")
    n_w = parquet("SELECT * FROM dim_weather", "dim_weather.parquet")
    n_r = parquet("SELECT * FROM fact_reposition_recommendations", "fact_reposition_recommendations.parquet")

    # CSV copies for Power BI users who prefer CSV (may be larger)
    for name in [
        "fact_zone_hour",
        "fact_forecast",
        "dim_zone",
        "dim_date",
        "dim_weather",
        "fact_reposition_recommendations",
    ]:
        src = (DATA_POWERBI / f"{name}.parquet").as_posix()
        dst = (DATA_POWERBI / f"{name}.csv").as_posix()
        con.execute(f"COPY (SELECT * FROM read_parquet('{src}')) TO '{dst}' (HEADER, DELIMITER ',')")

    con.close()
    out = {
        "fact_zone_hour_rows": n_fact,
        "fact_forecast_rows": n_fc,
        "dim_zone_rows": n_z,
        "dim_date_rows": n_d,
        "dim_weather_rows": n_w,
        "fact_reposition_rows": n_r,
        "zones_in_fact": int(n_keep),
    }
    log.info("Power BI export %s", out)
    return out
