# Data dictionary

Warehouse: `data/processed/warehouse.duckdb`. Trip-level processing is SQL-only.

## raw_trips
HVFHV TLC parquet (or synthetic with the same names).

| column | type | description |
|---|---|---|
| hvfhs_license_num | varchar | HVFHS license (e.g. Uber HV0003, Lyft HV0005) |
| dispatching_base_num | varchar | Dispatching base |
| originating_base_num | varchar | Originating base |
| request_datetime | timestamp | Rider request |
| on_scene_datetime | timestamp | Driver on scene |
| pickup_datetime | timestamp | Pickup |
| dropoff_datetime | timestamp | Dropoff |
| PULocationID / DOLocationID | int | TLC taxi zone |
| trip_miles | double | Trip distance |
| trip_time | double | Trip time (seconds in TLC) |
| base_passenger_fare | double | Base fare |
| tolls, bcf, sales_tax, congestion_surcharge, airport_fee, tips | double | Add-ons |
| driver_pay | double | Driver pay |
| shared_request_flag / shared_match_flag | varchar | Pooled request/match |

## trips_clean / trips_featured
Cleaned trips plus wait_minutes, duration_minutes, speed_mph, total_passenger_pay, calendar flags, take_rate, tip_pct, weather.

## fact_zone_hour / fact_zone_hour_lags
Grain: **pickup zone × pickup hour**.

| column | description |
|---|---|
| trips | Completed pickups |
| revenue | Sum of total_passenger_pay |
| driver_pay | Sum of driver_pay |
| supply_proxy | Same as trips (fulfilled demand) |
| avg_wait_minutes | Mean request-to-pickup minutes |
| demand_lag_1h / 24h / 168h | LAG of trips |
| demand_roll_24h / 168h | Rolling mean of prior trips |

## dim_zone
location_id, borough, zone_name, service_zone, centroid_lat/lon, is_airport, cluster_id, cluster_name.

## dim_date
date_key, year, month, day, weekday (0=Sun), is_weekend, is_holiday, holiday_name.

## dim_weather
hour_ts, temp_c, precipitation_mm, snowfall_cm, is_rain, is_snow.

## fact_forecast
location_id (0 = citywide), hour_ts, actual trips, pred_lgb, pred_naive_168, pred_ma, split.

## fact_reposition_recommendations
Per hour allocation: gap, drivers_sent, est_extra_trips, est_extra_revenue.

## Analysis tables
`analysis_zone_rank`, `analysis_take_rate_borough`, `analysis_peak_hours`, `analysis_mom_growth`, `analysis_airport`, `analysis_driver_earnings`, `analysis_rain_uplift`, `analysis_cohort_week`.
