# Assumptions

Defaults chosen so the pipeline can run unattended.

## Time and geography
- TLC pickup/dropoff timestamps are treated as **America/New_York naive local time** (TLC convention).
- Analysis window: pickups in **[2024-01-01, 2024-04-01)**.
- Weather is a **single NYC point** (40.71, −74.01), joined to every zone-hour. Microclimate by borough is not modeled.
- Holidays: `holidays` package, **US / New York State**, calendar year 2024.

## Demand and supply
- **Demand** = completed trips with pickup in the zone-hour (revealed demand). Unmatched requests are not in TLC files.
- **Supply proxy** = completed trip count in that zone-hour (fulfilled work). There is **no driver_id** on HVFHV public files.
- **Gap** = `max(0, expected_demand * (1 + unmet_factor) - supply_proxy)` where `unmet_factor = clip((avg_wait_min - 4) / 20, 0, 0.5)`.
- Extra trip capture = `min(gap, drivers_sent * 0.65)` with **max 15 drivers per zone** per hour. Default **X = 50** citywide.
- Revenue uplift uses that hour’s **revenue per trip**.

## Cleaning thresholds
- Miles (0.05, 150]; duration 1–240 minutes; wait 0–60 minutes; fare 0–500; speed ≤ 90 mph; drop location IDs 264/265.

## Features
- Weekend = Sunday/Saturday (`EXTRACT(dow)` 0 and 6 in DuckDB).
- Rush hour = weekdays hours 7–9 and 16–19.
- Rain flag = precipitation_mm > 0; snow flag = snowfall_cm > 0.
- Take rate = `1 - driver_pay / total_passenger_pay` (passenger total includes tolls, tax, congestion, airport, tips).
- Pooled = shared_request_flag in {Y, 1, TRUE}.

## Modeling
- Random seed **42**.
- Top **50** zones by volume for zonal LightGBM plus citywide model (`location_id = 0` in `fact_forecast`).
- Split: train ≤ 2024-02-29, valid 2024-03-01–2024-03-15, test ≥ 2024-03-16.
- Evaluation is **one-step-ahead using observed lags** (not recursive multi-step).
- KMeans **k = min(5, n_zones/8)** on standardized zone summaries.

## Power BI
- Fact table filtered to zones with ≥ 500 trips; further `trips >= 2` if still over 500k rows.
- YoY DAX is included for the model but **will be blank** with only Q1 2024.

## Fallback
- If TLC parquet download fails after 3 tries, a **labeled synthetic** 180k-trip sample is used (`data/raw/DATA_SOURCE.txt`). Reports must say so.
