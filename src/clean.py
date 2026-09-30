"""Profile raw trips and apply SQL cleaning; write reports/cleaning_log.md."""

from __future__ import annotations

from pathlib import Path

from src.config import CLEANING_LOG, REPORTS, SQL_DIR
from src.db import connect, run_sql_file
from src.logging_utils import get_logger

log = get_logger(__name__)

RULES = [
    ("raw", "SELECT COUNT(*) FROM raw_trips"),
    (
        "drop_null_timestamps_or_pu",
        """
        SELECT COUNT(*) FROM raw_trips
        WHERE pickup_datetime IS NULL OR request_datetime IS NULL
           OR dropoff_datetime IS NULL OR PULocationID IS NULL
        """,
    ),
    (
        "unknown_or_unmapped_pu_zone",
        """
        SELECT COUNT(*) FROM raw_trips t
        LEFT JOIN raw_zones z ON CAST(t.PULocationID AS INTEGER) = z.location_id
        WHERE CAST(t.PULocationID AS INTEGER) IN (264, 265)
           OR z.location_id IS NULL
           OR z.borough IN ('Unknown', 'N/A')
        """,
    ),
    (
        "timestamps_out_of_order",
        """
        SELECT COUNT(*) FROM raw_trips
        WHERE dropoff_datetime < pickup_datetime
           OR pickup_datetime < request_datetime
        """,
    ),
    (
        "negative_or_huge_fare",
        """
        SELECT COUNT(*) FROM raw_trips
        WHERE base_passenger_fare IS NULL
           OR base_passenger_fare < 0
           OR base_passenger_fare > 500
           OR driver_pay IS NULL
           OR driver_pay < 0
        """,
    ),
    (
        "impossible_distance",
        """
        SELECT COUNT(*) FROM raw_trips
        WHERE trip_miles IS NULL OR trip_miles <= 0.05 OR trip_miles > 150
        """,
    ),
    (
        "impossible_duration",
        """
        SELECT COUNT(*) FROM raw_trips
        WHERE date_diff('second', CAST(pickup_datetime AS TIMESTAMP), CAST(dropoff_datetime AS TIMESTAMP))
              NOT BETWEEN 60 AND 14400
        """,
    ),
    (
        "wait_over_60min",
        """
        SELECT COUNT(*) FROM raw_trips
        WHERE date_diff('second', CAST(request_datetime AS TIMESTAMP), CAST(pickup_datetime AS TIMESTAMP))
              NOT BETWEEN 0 AND 3600
        """,
    ),
]


def _scalar(con, sql: str) -> int:
    return int(con.execute(sql).fetchone()[0])


def run() -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    con = connect()
    raw = _scalar(con, "SELECT COUNT(*) FROM raw_trips")
    # null profile
    cols = [r[0] for r in con.execute("DESCRIBE raw_trips").fetchall()]
    null_lines = ["| column | nulls | pct |", "|---|---:|---:|"]
    for col in cols:
        n = _scalar(con, f"SELECT COUNT(*) FROM raw_trips WHERE {col} IS NULL")
        null_lines.append(f"| {col} | {n} | {n / raw * 100 if raw else 0:.3f}% |")

    rule_counts = []
    for name, sql in RULES:
        try:
            n = _scalar(con, sql)
        except Exception as exc:  # noqa: BLE001
            log.warning("Rule %s failed: %s", name, exc)
            n = -1
        rule_counts.append((name, n))

    run_sql_file(con, SQL_DIR / "01_clean.sql")
    clean = _scalar(con, "SELECT COUNT(*) FROM trips_clean")
    removed = raw - clean
    con.close()

    lines = [
        "# Cleaning log",
        "",
        f"- Raw trips: **{raw:,}**",
        f"- Clean trips: **{clean:,}**",
        f"- Removed: **{removed:,}** ({removed / raw * 100 if raw else 0:.2f}%)",
        "",
        "Rules are overlapping (a row can fail multiple checks). Final `trips_clean` applies all filters jointly.",
        "",
        "## Rule hit counts (not sequential exclusive removals)",
        "",
        "| rule | rows matching |",
        "|---|---:|",
    ]
    for name, n in rule_counts:
        lines.append(f"| {name} | {n:,} |")
    lines.extend(
        [
            "",
            "## Null profile (raw)",
            "",
            *null_lines,
            "",
            "## Filters applied",
            "",
            "- Drop null request/pickup/dropoff or PULocationID",
            "- Drop unknown zones 264/265 and unmapped/Unknown borough",
            "- Drop dropoff before pickup or pickup before request",
            "- Drop fares/driver pay null, negative, or fare > $500",
            "- Drop miles <= 0.05 or > 150",
            "- Drop duration outside 1–240 minutes",
            "- Drop wait outside 0–60 minutes",
            "- Drop speed > 90 mph",
            "- Keep pickups in 2024-01-01 inclusive to 2024-04-01 exclusive",
            "",
        ]
    )
    CLEANING_LOG.write_text("\n".join(lines), encoding="utf-8")
    log.info("Cleaning: %s -> %s", raw, clean)
    return {"raw_trips": raw, "clean_trips": clean, "removed_trips": removed}
