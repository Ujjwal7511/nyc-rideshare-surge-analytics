-- 01_clean.sql: trip-level quality rules. Counts captured in Python around this script.

CREATE OR REPLACE TABLE trips_clean AS
WITH zoned AS (
    SELECT
        t.*,
        pu.borough AS pu_borough,
        pu.zone_name AS pu_zone,
        pu.service_zone AS pu_service_zone,
        dz.borough AS do_borough,
        dz.zone_name AS do_zone
    FROM raw_trips t
    LEFT JOIN raw_zones pu ON CAST(t.PULocationID AS INTEGER) = pu.location_id
    LEFT JOIN raw_zones dz ON CAST(t.DOLocationID AS INTEGER) = dz.location_id
),
typed AS (
    SELECT
        hvfhs_license_num,
        dispatching_base_num,
        CAST(request_datetime AS TIMESTAMP) AS request_datetime,
        CAST(on_scene_datetime AS TIMESTAMP) AS on_scene_datetime,
        CAST(pickup_datetime AS TIMESTAMP) AS pickup_datetime,
        CAST(dropoff_datetime AS TIMESTAMP) AS dropoff_datetime,
        CAST(PULocationID AS INTEGER) AS pu_location_id,
        CAST(DOLocationID AS INTEGER) AS do_location_id,
        CAST(trip_miles AS DOUBLE) AS trip_miles,
        CAST(trip_time AS DOUBLE) AS trip_time_seconds,
        CAST(base_passenger_fare AS DOUBLE) AS base_passenger_fare,
        COALESCE(CAST(tolls AS DOUBLE), 0) AS tolls,
        COALESCE(CAST(bcf AS DOUBLE), 0) AS bcf,
        COALESCE(CAST(sales_tax AS DOUBLE), 0) AS sales_tax,
        COALESCE(CAST(congestion_surcharge AS DOUBLE), 0) AS congestion_surcharge,
        COALESCE(CAST(airport_fee AS DOUBLE), 0) AS airport_fee,
        COALESCE(CAST(tips AS DOUBLE), 0) AS tips,
        CAST(driver_pay AS DOUBLE) AS driver_pay,
        UPPER(TRIM(CAST(shared_request_flag AS VARCHAR))) AS shared_request_flag,
        UPPER(TRIM(CAST(shared_match_flag AS VARCHAR))) AS shared_match_flag,
        pu_borough,
        pu_zone,
        pu_service_zone,
        do_borough,
        do_zone
    FROM zoned
)
SELECT
    *,
    date_diff('second', request_datetime, pickup_datetime) / 60.0 AS wait_minutes,
    date_diff('second', pickup_datetime, dropoff_datetime) / 60.0 AS duration_minutes,
    CASE WHEN date_diff('second', pickup_datetime, dropoff_datetime) > 0
         THEN trip_miles / (date_diff('second', pickup_datetime, dropoff_datetime) / 3600.0)
         ELSE NULL END AS speed_mph,
    base_passenger_fare + tolls + bcf + sales_tax + congestion_surcharge + airport_fee + tips AS total_passenger_pay
FROM typed
WHERE pickup_datetime IS NOT NULL
  AND request_datetime IS NOT NULL
  AND dropoff_datetime IS NOT NULL
  AND pu_location_id IS NOT NULL
  AND pu_location_id NOT IN (264, 265)
  AND pu_borough IS NOT NULL
  AND pu_borough NOT IN ('Unknown', 'N/A')
  AND do_location_id IS NOT NULL
  AND dropoff_datetime >= pickup_datetime
  AND pickup_datetime >= request_datetime
  AND base_passenger_fare IS NOT NULL
  AND base_passenger_fare >= 0
  AND base_passenger_fare <= 500
  AND driver_pay IS NOT NULL
  AND driver_pay >= 0
  AND trip_miles > 0.05
  AND trip_miles <= 150
  AND date_diff('second', pickup_datetime, dropoff_datetime) BETWEEN 60 AND 14400
  AND date_diff('second', request_datetime, pickup_datetime) BETWEEN 0 AND 3600
  AND (
        date_diff('second', pickup_datetime, dropoff_datetime) = 0
        OR trip_miles / (date_diff('second', pickup_datetime, dropoff_datetime) / 3600.0) <= 90
      )
  AND pickup_datetime >= TIMESTAMP '2024-01-01'
  AND pickup_datetime < TIMESTAMP '2024-04-01';
