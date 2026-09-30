"""Driver repositioning: gap = expected demand - supply proxy; sensitivity on X."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.config import (
    COMPLETION_RATE_PER_EXTRA_DRIVER,
    DEFAULT_REPOSITION_DRIVERS,
    FIGURES,
    MAX_DRIVERS_PER_ZONE,
    RANDOM_SEED,
    REPORTS,
)
from src.db import connect
from src.logging_utils import get_logger

log = get_logger(__name__)


def _allocate(gaps: pd.DataFrame, x_drivers: int, max_per_zone: int) -> pd.DataFrame:
    remaining = x_drivers
    recs = []
    for _, row in gaps.sort_values("gap", ascending=False).iterrows():
        if remaining <= 0 or row["gap"] <= 0:
            break
        send = int(min(max_per_zone, remaining, np.ceil(row["gap"])))
        if send <= 0:
            continue
        captured = min(row["gap"], send * COMPLETION_RATE_PER_EXTRA_DRIVER)
        recs.append(
            {
                "location_id": int(row["location_id"]),
                "zone_name": row["zone_name"],
                "borough": row["borough"],
                "hour_ts": row["hour_ts"],
                "expected_demand": float(row["expected_demand"]),
                "supply_proxy": float(row["supply_proxy"]),
                "gap": float(row["gap"]),
                "drivers_sent": send,
                "est_extra_trips": float(captured),
                "est_extra_revenue": float(captured * row["revenue_per_trip"]),
            }
        )
        remaining -= send
    return pd.DataFrame(recs)


def run(x_drivers: int = DEFAULT_REPOSITION_DRIVERS) -> dict:
    FIGURES.mkdir(parents=True, exist_ok=True)
    con = connect()
    has_fc = con.execute(
        "SELECT COUNT(*) FROM duckdb_tables() WHERE table_name = 'fact_forecast'"
    ).fetchone()[0]
    if has_fc:
        df = con.execute(
            """
            SELECT
                f.location_id,
                z.zone_name,
                z.borough,
                l.hour_ts,
                COALESCE(f.pred_lgb, l.trips) AS expected_demand,
                l.supply_proxy,
                COALESCE(l.revenue_per_trip, 0) AS revenue_per_trip,
                l.avg_wait_minutes,
                l.trips AS actual_trips
            FROM fact_zone_hour_lags l
            LEFT JOIN fact_forecast f
              ON f.location_id = l.location_id AND f.hour_ts = l.hour_ts
            JOIN dim_zone z ON z.location_id = l.location_id
            WHERE l.hour_ts >= TIMESTAMP '2024-03-16'
            """
        ).df()
    else:
        df = con.execute(
            """
            SELECT
                l.location_id,
                z.zone_name,
                z.borough,
                l.hour_ts,
                COALESCE(l.demand_roll_24h, l.trips) AS expected_demand,
                l.supply_proxy,
                COALESCE(l.revenue_per_trip, 0) AS revenue_per_trip,
                l.avg_wait_minutes,
                l.trips AS actual_trips
            FROM fact_zone_hour_lags l
            JOIN dim_zone z ON z.location_id = l.location_id
            WHERE l.hour_ts >= TIMESTAMP '2024-03-16'
            """
        ).df()
    con.close()
    df["hour_ts"] = pd.to_datetime(df["hour_ts"])
    # Unmet demand proxy: wait-inflated demand minus completed trips
    wait = df["avg_wait_minutes"].fillna(5).clip(0, 40)
    df["unmet_factor"] = np.clip((wait - 4) / 20.0, 0, 0.5)
    df["gap"] = (df["expected_demand"] * (1 + df["unmet_factor"]) - df["supply_proxy"]).clip(lower=0)

    hours = sorted(df["hour_ts"].unique())
    all_recs = []
    hourly_uplift = []
    rng = np.random.default_rng(RANDOM_SEED)
    sample_hours = hours if len(hours) <= 200 else list(rng.choice(hours, 200, replace=False))
    use_hours = hours  # full test window
    for ts in use_hours:
        slice_ = df[df["hour_ts"] == ts]
        rec = _allocate(slice_, x_drivers, MAX_DRIVERS_PER_ZONE)
        if rec.empty:
            hourly_uplift.append({"hour_ts": ts, "extra_trips": 0, "extra_revenue": 0})
            continue
        rec["x_drivers"] = x_drivers
        all_recs.append(rec)
        hourly_uplift.append(
            {
                "hour_ts": ts,
                "extra_trips": float(rec["est_extra_trips"].sum()),
                "extra_revenue": float(rec["est_extra_revenue"].sum()),
            }
        )
    recs = pd.concat(all_recs, ignore_index=True) if all_recs else pd.DataFrame()
    upl = pd.DataFrame(hourly_uplift)

    sensitivity = []
    for x in (10, 25, 50, 100, 200):
        extra_t = extra_r = 0.0
        for ts in sample_hours:
            rec = _allocate(df[df["hour_ts"] == ts], x, MAX_DRIVERS_PER_ZONE)
            if not rec.empty:
                extra_t += rec["est_extra_trips"].sum()
                extra_r += rec["est_extra_revenue"].sum()
        scale = len(use_hours) / max(len(sample_hours), 1)
        sensitivity.append(
            {
                "x_drivers": x,
                "est_extra_trips_test_window": extra_t * scale,
                "est_extra_revenue_test_window": extra_r * scale,
            }
        )

    summary = {
        "x_drivers": x_drivers,
        "completion_rate_per_extra_driver": COMPLETION_RATE_PER_EXTRA_DRIVER,
        "max_drivers_per_zone": MAX_DRIVERS_PER_ZONE,
        "test_hours": int(len(use_hours)),
        "total_est_extra_trips": float(upl["extra_trips"].sum()) if len(upl) else 0.0,
        "total_est_extra_revenue": float(upl["extra_revenue"].sum()) if len(upl) else 0.0,
        "avg_extra_trips_per_hour": float(upl["extra_trips"].mean()) if len(upl) else 0.0,
        "sensitivity": sensitivity,
        "assumptions": {
            "gap": "max(0, expected_demand * (1 + unmet_from_wait) - supply_proxy)",
            "supply_proxy": "completed trips in zone-hour (fulfilled demand)",
            "unmet_from_wait": "clip((avg_wait_min - 4) / 20, 0, 0.5)",
            "capture": "min(gap, drivers_sent * 0.65)",
            "revenue": "extra_trips * zone-hour revenue_per_trip",
        },
    }

    con = connect()
    con.execute("DROP TABLE IF EXISTS fact_reposition_recommendations")
    if len(recs):
        con.register("recs", recs)
        con.execute("CREATE TABLE fact_reposition_recommendations AS SELECT * FROM recs")
    else:
        con.execute(
            """
            CREATE TABLE fact_reposition_recommendations AS
            SELECT
                0 AS location_id, '' AS zone_name, '' AS borough,
                TIMESTAMP '2024-03-16' AS hour_ts,
                0.0 AS expected_demand, 0.0 AS supply_proxy, 0.0 AS gap,
                0 AS drivers_sent, 0.0 AS est_extra_trips, 0.0 AS est_extra_revenue,
                0 AS x_drivers
            WHERE FALSE
            """
        )
    con.close()
    (REPORTS / "reposition_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    if len(recs):
        recs.to_csv(REPORTS / "reposition_top_actions.csv", index=False)
    log.info(
        "Reposition X=%s extra trips=%.0f extra revenue=%.0f",
        x_drivers,
        summary["total_est_extra_trips"],
        summary["total_est_extra_revenue"],
    )
    return summary
