"""Paths, constants, and analysis defaults (documented in docs/ASSUMPTIONS.md)."""

from __future__ import annotations

from pathlib import Path

RANDOM_SEED = 42

ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
DATA_POWERBI = ROOT / "data" / "powerbi"
SQL_DIR = ROOT / "sql"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
DOCS = ROOT / "docs"

WAREHOUSE = DATA_PROCESSED / "warehouse.duckdb"
METRICS_JSON = REPORTS / "metrics.json"
CLEANING_LOG = REPORTS / "cleaning_log.md"

TLC_MONTHS = ("2024-01", "2024-02", "2024-03")
TLC_BASE = "https://d37ci6vzurychx.cloudfront.net/trip-data"
ZONE_LOOKUP_URL = "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv"
ZONE_SHAPES_URL = "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zones.zip"

NYC_LAT = 40.71
NYC_LON = -74.01
WEATHER_START = "2024-01-01"
WEATHER_END = "2024-03-31"

# Timezone: TLC timestamps are America/New_York naive local time (assumption).
RUSH_HOURS_AM = {7, 8, 9}
RUSH_HOURS_PM = {16, 17, 18, 19}
UNKNOWN_ZONE_IDS = {264, 265}

# Cleaning thresholds
MAX_TRIP_MILES = 150.0
MIN_TRIP_MILES = 0.05
MAX_TRIP_MINUTES = 240.0
MIN_TRIP_MINUTES = 1.0
MAX_WAIT_MINUTES = 60.0
MAX_ABS_FARE = 500.0
MAX_SPEED_MPH = 90.0

# Forecast
TOP_N_ZONES = 50
TRAIN_END = "2024-02-29 23:00:00"
VALID_END = "2024-03-15 23:00:00"
TEST_START = "2024-03-16 00:00:00"

# Repositioning
DEFAULT_REPOSITION_DRIVERS = 50
MAX_DRIVERS_PER_ZONE = 15
COMPLETION_RATE_PER_EXTRA_DRIVER = 0.65  # trips/hour captured per extra driver, capped by gap
AVG_TAKE_RATE_FALLBACK = 0.25

# Power BI row cap
MAX_FACT_ROWS = 500_000
MIN_ZONE_TRIPS_FOR_FACT = 500

DOWNLOAD_TIMEOUT = 600
DOWNLOAD_RETRIES = 3
