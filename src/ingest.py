"""Download TLC, zones, weather; load into DuckDB. Synthetic fallback if downloads fail."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import requests

from src.config import (
    DATA_RAW,
    DATA_PROCESSED,
    DOWNLOAD_RETRIES,
    DOWNLOAD_TIMEOUT,
    NYC_LAT,
    NYC_LON,
    RANDOM_SEED,
    TLC_BASE,
    TLC_MONTHS,
    WEATHER_END,
    WEATHER_START,
    ZONE_LOOKUP_URL,
    ZONE_SHAPES_URL,
)
from src.db import connect
from src.logging_utils import get_logger

log = get_logger(__name__)


def _download(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        log.info("Already exists: %s", dest.name)
        return True
    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        try:
            log.info("Downloading %s (attempt %s)", url, attempt)
            with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT) as r:
                r.raise_for_status()
                tmp = dest.with_suffix(dest.suffix + ".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                tmp.replace(dest)
            log.info("Saved %s (%.1f MB)", dest.name, dest.stat().st_size / 1e6)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("Download failed attempt %s: %s", attempt, exc)
    return False


def download_trip_parquets() -> tuple[list[Path], bool]:
    paths: list[Path] = []
    ok = True
    for month in TLC_MONTHS:
        dest = DATA_RAW / f"fhvhv_tripdata_{month}.parquet"
        url = f"{TLC_BASE}/fhvhv_tripdata_{month}.parquet"
        if not _download(url, dest):
            ok = False
        elif dest.exists():
            paths.append(dest)
    return paths, ok and len(paths) == len(TLC_MONTHS)


def download_zone_lookup() -> Path | None:
    dest = DATA_RAW / "taxi_zone_lookup.csv"
    return dest if _download(ZONE_LOOKUP_URL, dest) else None


def download_zone_centroids() -> Path | None:
    zip_path = DATA_RAW / "taxi_zones.zip"
    out_csv = DATA_RAW / "zone_centroids.csv"
    if out_csv.exists():
        return out_csv
    if not _download(ZONE_SHAPES_URL, zip_path):
        return None
    try:
        import shapefile  # pyshp

        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(DATA_RAW / "taxi_zones")
        shp_files = list((DATA_RAW / "taxi_zones").rglob("*.shp"))
        if not shp_files:
            raise FileNotFoundError("No .shp in taxi_zones zip")
        sf = shapefile.Reader(str(shp_files[0]))
        rows = []
        loc_idx = None
        for i, field in enumerate(sf.fields[1:]):
            if field[0].lower() in {"locationid", "location_id"}:
                loc_idx = i
                break
        for rec, shape in zip(sf.iterRecords(), sf.shapes()):
            pts = shape.points
            if not pts:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            loc_id = rec[loc_idx] if loc_idx is not None else rec[0]
            rows.append(
                {
                    "LocationID": int(loc_id),
                    "centroid_lon": float(np.mean(xs)),
                    "centroid_lat": float(np.mean(ys)),
                }
            )
        pd.DataFrame(rows).to_csv(out_csv, index=False)
        log.info("Wrote %s zone centroids", len(rows))
        return out_csv
    except Exception as exc:  # noqa: BLE001
        log.warning("Centroid derivation failed: %s", exc)
        return None


def download_weather() -> Path | None:
    dest = DATA_RAW / "weather_hourly.parquet"
    if dest.exists():
        return dest
    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={NYC_LAT}&longitude={NYC_LON}"
        f"&start_date={WEATHER_START}&end_date={WEATHER_END}"
        "&hourly=temperature_2m,precipitation,snowfall"
        "&timezone=America%2FNew_York"
    )
    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        try:
            log.info("Fetching Open-Meteo (attempt %s)", attempt)
            r = requests.get(url, timeout=DOWNLOAD_TIMEOUT)
            r.raise_for_status()
            payload = r.json()
            hourly = payload["hourly"]
            df = pd.DataFrame(
                {
                    "ts": pd.to_datetime(hourly["time"]),
                    "temp_c": hourly["temperature_2m"],
                    "precipitation_mm": hourly["precipitation"],
                    "snowfall_cm": hourly["snowfall"],
                }
            )
            df.to_parquet(dest, index=False)
            return dest
        except Exception as exc:  # noqa: BLE001
            log.warning("Weather download failed: %s", exc)
    return None


def _synthetic_zones() -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED)
    boroughs = ["Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island"]
    names = []
    rows = []
    for i in range(1, 81):
        b = boroughs[(i - 1) % 5]
        service = "Airports" if i in (1, 2, 3) else "Boro Zone" if b != "Manhattan" else "Yellow Zone"
        zone = f"{b} Zone {i}"
        if i == 1:
            zone = "JFK Airport"
        elif i == 2:
            zone = "LaGuardia Airport"
        elif i == 3:
            zone = "Newark Airport"
        rows.append(
            {
                "LocationID": i,
                "Borough": "EWR" if i == 3 else b,
                "Zone": zone,
                "service_zone": service,
            }
        )
        names.append(i)
    return pd.DataFrame(rows)


def write_synthetic_sample() -> Path:
    """Labeled synthetic HVFHV-like trips so the pipeline can run without TLC files."""
    log.warning("Using SYNTHETIC sample trips (not official TLC data).")
    rng = np.random.default_rng(RANDOM_SEED)
    n = 180_000
    zones_df = _synthetic_zones()
    zone_ids = zones_df["LocationID"].to_numpy()
    start = pd.Timestamp("2024-01-01")
    end = pd.Timestamp("2024-03-31 23:00:00")
    hours = pd.date_range(start, end, freq="h")
    # Weight Manhattan-ish zones and rush hours
    zone_w = np.array([4.0 if z <= 20 else 1.5 if z <= 40 else 0.6 for z in zone_ids], dtype=float)
    zone_w = zone_w / zone_w.sum()
    request = start + pd.to_timedelta(rng.integers(0, int((end - start).total_seconds()), size=n), unit="s")
    hour = request.hour.to_numpy() if hasattr(request, "hour") else pd.DatetimeIndex(request).hour.to_numpy()
    wait_sec = rng.integers(60, 900, size=n)
    trip_min = rng.integers(5, 45, size=n).astype(float)
    rain_boost = (pd.DatetimeIndex(request).dayofweek >= 0).astype(int)
    miles = np.clip(rng.lognormal(1.1, 0.6, size=n), 0.2, 40)
    fare = np.clip(3.5 + miles * 2.8 + trip_min * 0.4 + rng.normal(0, 2, n), 5, 200)
    tips = np.clip(fare * rng.choice([0, 0.1, 0.15, 0.2], n, p=[0.4, 0.2, 0.25, 0.15]), 0, 40)
    driver_pay = fare * rng.uniform(0.65, 0.85, n)
    pu = rng.choice(zone_ids, size=n, p=zone_w)
    do = rng.choice(zone_ids, size=n)
    df = pd.DataFrame(
        {
            "hvfhs_license_num": rng.choice(["HV0003", "HV0005"], n, p=[0.7, 0.3]),
            "dispatching_base_num": rng.choice(["B02887", "B02510", "B02764"], n),
            "originating_base_num": rng.choice(["B02887", "B02510", "B02764"], n),
            "request_datetime": request,
            "on_scene_datetime": request + pd.to_timedelta(wait_sec * 0.6, unit="s"),
            "pickup_datetime": request + pd.to_timedelta(wait_sec, unit="s"),
            "dropoff_datetime": request
            + pd.to_timedelta(wait_sec, unit="s")
            + pd.to_timedelta(trip_min, unit="m"),
            "PULocationID": pu,
            "DOLocationID": do,
            "trip_miles": miles,
            "trip_time": trip_min * 60,
            "base_passenger_fare": fare,
            "tolls": rng.choice([0, 6.94], n, p=[0.9, 0.1]),
            "bcf": fare * 0.02,
            "sales_tax": fare * 0.08875,
            "congestion_surcharge": np.where(np.array(pu) <= 25, 2.75, 0),
            "airport_fee": np.where(np.isin(pu, [1, 2, 3]), 2.5, 0),
            "tips": tips,
            "driver_pay": driver_pay,
            "shared_request_flag": rng.choice(["Y", "N"], n, p=[0.08, 0.92]),
            "shared_match_flag": rng.choice(["Y", "N"], n, p=[0.04, 0.96]),
            "access_a_ride_flag": "N",
            "wav_request_flag": "N",
            "wav_match_flag": "N",
        }
    )
    # Inject a small share of dirty rows for the cleaner to catch
    dirty_n = 800
    df.loc[df.index[: dirty_n // 4], "base_passenger_fare"] = -5
    df.loc[df.index[dirty_n // 4 : dirty_n // 2], "trip_miles"] = 0
    df.loc[df.index[dirty_n // 2 : 3 * dirty_n // 4], "PULocationID"] = 264
    swap = df.index[3 * dirty_n // 4 : dirty_n]
    df.loc[swap, "dropoff_datetime"] = df.loc[swap, "request_datetime"] - pd.Timedelta(hours=1)

    dest = DATA_RAW / "SYNTHETIC_fhvhv_tripdata_2024q1.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(dest, index=False)
    zones_df.to_csv(DATA_RAW / "taxi_zone_lookup.csv", index=False)
    cents = pd.DataFrame(
        {
            "LocationID": zones_df["LocationID"],
            "centroid_lon": -74.01 + rng.normal(0, 0.08, len(zones_df)),
            "centroid_lat": 40.71 + rng.normal(0, 0.08, len(zones_df)),
        }
    )
    cents.to_csv(DATA_RAW / "zone_centroids.csv", index=False)
    marker = DATA_RAW / "DATA_SOURCE.txt"
    marker.write_text("SYNTHETIC: TLC parquet download failed; sample generated locally.\n", encoding="utf-8")
    return dest


def ensure_weather(path: Path | None) -> Path:
    if path and path.exists():
        return path
    log.warning("Using SYNTHETIC weather.")
    hours = pd.date_range("2024-01-01", "2024-03-31 23:00:00", freq="h")
    rng = np.random.default_rng(RANDOM_SEED)
    df = pd.DataFrame(
        {
            "ts": hours,
            "temp_c": 5 + 10 * np.sin(np.arange(len(hours)) / 24) + rng.normal(0, 3, len(hours)),
            "precipitation_mm": np.where(rng.random(len(hours)) < 0.18, rng.exponential(2, len(hours)), 0),
            "snowfall_cm": np.where(rng.random(len(hours)) < 0.04, rng.exponential(1, len(hours)), 0),
        }
    )
    dest = DATA_RAW / "weather_hourly.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(dest, index=False)
    return dest


def build_holidays_csv() -> Path:
    import holidays as hol

    ny = hol.country_holidays("US", subdiv="NY", years=[2024])
    rows = [{"date": d, "holiday_name": name} for d, name in sorted(ny.items())]
    dest = DATA_RAW / "us_ny_holidays.csv"
    pd.DataFrame(rows).to_csv(dest, index=False)
    return dest


def load_warehouse(trip_paths: list[Path], synthetic: bool) -> None:
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    con = connect()
    files_sql = ", ".join(f"'{p.as_posix()}'" for p in trip_paths)
    con.execute("DROP TABLE IF EXISTS raw_trips")
    con.execute(
        f"""
        CREATE TABLE raw_trips AS
        SELECT * FROM read_parquet([{files_sql}], union_by_name=true)
        """
    )
    lookup = DATA_RAW / "taxi_zone_lookup.csv"
    con.execute("DROP TABLE IF EXISTS raw_zones")
    con.execute(
        f"""
        CREATE TABLE raw_zones AS
        SELECT
            CAST(LocationID AS INTEGER) AS location_id,
            Borough AS borough,
            Zone AS zone_name,
            service_zone
        FROM read_csv_auto('{lookup.as_posix()}')
        """
    )
    cents = DATA_RAW / "zone_centroids.csv"
    con.execute("DROP TABLE IF EXISTS zone_centroids")
    if cents.exists():
        con.execute(
            f"""
            CREATE TABLE zone_centroids AS
            SELECT CAST(LocationID AS INTEGER) AS location_id,
                   centroid_lat, centroid_lon
            FROM read_csv_auto('{cents.as_posix()}')
            """
        )
    else:
        con.execute(
            """
            CREATE TABLE zone_centroids AS
            SELECT location_id, 40.71 AS centroid_lat, -74.01 AS centroid_lon
            FROM raw_zones
            """
        )
    weather = DATA_RAW / "weather_hourly.parquet"
    con.execute("DROP TABLE IF EXISTS raw_weather")
    con.execute(
        f"""
        CREATE TABLE raw_weather AS
        SELECT
            CAST(ts AS TIMESTAMP) AS ts,
            CAST(temp_c AS DOUBLE) AS temp_c,
            CAST(precipitation_mm AS DOUBLE) AS precipitation_mm,
            CAST(snowfall_cm AS DOUBLE) AS snowfall_cm
        FROM read_parquet('{weather.as_posix()}')
        """
    )
    hols = DATA_RAW / "us_ny_holidays.csv"
    con.execute("DROP TABLE IF EXISTS raw_holidays")
    con.execute(
        f"""
        CREATE TABLE raw_holidays AS
        SELECT CAST(date AS DATE) AS holiday_date, holiday_name
        FROM read_csv_auto('{hols.as_posix()}')
        """
    )
    n = con.execute("SELECT COUNT(*) FROM raw_trips").fetchone()[0]
    con.execute("DROP TABLE IF EXISTS ingest_meta")
    con.execute(
        f"""
        CREATE TABLE ingest_meta AS
        SELECT
            {n}::BIGINT AS raw_trip_count,
            {'TRUE' if synthetic else 'FALSE'} AS is_synthetic,
            CURRENT_TIMESTAMP AS ingested_at
        """
    )
    log.info("Warehouse loaded: %s raw trips (synthetic=%s)", n, synthetic)
    con.close()


def run() -> dict:
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    trip_paths, trips_ok = download_trip_parquets()
    lookup = download_zone_lookup()
    cents = download_zone_centroids()
    weather = download_weather()
    synthetic = False
    if not trips_ok or not trip_paths:
        write_synthetic_sample()
        synthetic = True
        trip_paths = [DATA_RAW / "SYNTHETIC_fhvhv_tripdata_2024q1.parquet"]
        lookup = DATA_RAW / "taxi_zone_lookup.csv"
    elif lookup is None:
        log.warning("Zone lookup missing; generating synthetic zones (trips still real if present).")
        _synthetic_zones().to_csv(DATA_RAW / "taxi_zone_lookup.csv", index=False)
    ensure_weather(weather)
    if cents is None and not (DATA_RAW / "zone_centroids.csv").exists():
        log.warning("Centroids missing; using NYC center placeholder.")
    build_holidays_csv()
    load_warehouse(trip_paths, synthetic)
    return {"synthetic": synthetic, "trip_files": [str(p) for p in trip_paths]}
