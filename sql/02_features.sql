-- 02_features.sql: trip features + zone-hour grain with weather, holidays, lags.

CREATE OR REPLACE TABLE dim_date AS
SELECT
    d::DATE AS date_key,
    EXTRACT(year FROM d) AS year,
    EXTRACT(month FROM d) AS month,
    EXTRACT(day FROM d) AS day,
    EXTRACT(dow FROM d) AS weekday, -- 0 Sunday
    CASE WHEN EXTRACT(dow FROM d) IN (0, 6) THEN TRUE ELSE FALSE END AS is_weekend,
    CASE WHEN h.holiday_date IS NOT NULL THEN TRUE ELSE FALSE END AS is_holiday,
    h.holiday_name
FROM generate_series(DATE '2024-01-01', DATE '2024-03-31', INTERVAL 1 DAY) AS t(d)
LEFT JOIN raw_holidays h ON h.holiday_date = CAST(d AS DATE);

CREATE OR REPLACE TABLE dim_weather AS
SELECT
    date_trunc('hour', ts) AS hour_ts,
    temp_c,
    precipitation_mm,
    snowfall_cm,
    precipitation_mm > 0 AS is_rain,
    snowfall_cm > 0 AS is_snow
FROM raw_weather;

CREATE OR REPLACE TABLE dim_zone AS
SELECT
    z.location_id,
    z.borough,
    z.zone_name,
    z.service_zone,
    COALESCE(c.centroid_lat, 40.71) AS centroid_lat,
    COALESCE(c.centroid_lon, -74.01) AS centroid_lon,
    CASE
        WHEN lower(z.zone_name) LIKE '%airport%' OR z.service_zone = 'Airports' THEN TRUE
        ELSE FALSE
    END AS is_airport
FROM raw_zones z
LEFT JOIN zone_centroids c ON z.location_id = c.location_id;

CREATE OR REPLACE TABLE trips_featured AS
SELECT
    t.*,
    EXTRACT(hour FROM t.pickup_datetime) AS pickup_hour,
    EXTRACT(dow FROM t.pickup_datetime) AS pickup_weekday,
    EXTRACT(month FROM t.pickup_datetime) AS pickup_month,
    date_trunc('hour', t.pickup_datetime) AS pickup_hour_ts,
    CAST(t.pickup_datetime AS DATE) AS pickup_date,
    CASE WHEN EXTRACT(dow FROM t.pickup_datetime) IN (0, 6) THEN TRUE ELSE FALSE END AS is_weekend,
    CASE WHEN d.is_holiday THEN TRUE ELSE FALSE END AS is_holiday,
    CASE
        WHEN EXTRACT(dow FROM t.pickup_datetime) NOT IN (0, 6)
             AND (
                EXTRACT(hour FROM t.pickup_datetime) BETWEEN 7 AND 9
                OR EXTRACT(hour FROM t.pickup_datetime) BETWEEN 16 AND 19
             )
        THEN TRUE ELSE FALSE
    END AS is_rush_hour,
    CASE WHEN t.shared_request_flag IN ('Y', '1', 'TRUE') THEN TRUE ELSE FALSE END AS is_pooled,
    CASE WHEN t.total_passenger_pay > 0
         THEN t.driver_pay / t.total_passenger_pay ELSE NULL END AS driver_share,
    CASE WHEN t.total_passenger_pay > 0
         THEN 1.0 - (t.driver_pay / t.total_passenger_pay) ELSE NULL END AS take_rate,
    CASE WHEN t.base_passenger_fare > 0
         THEN t.tips / t.base_passenger_fare ELSE NULL END AS tip_pct,
    w.temp_c,
    w.precipitation_mm,
    w.snowfall_cm,
    w.is_rain,
    w.is_snow
FROM trips_clean t
LEFT JOIN dim_date d ON CAST(t.pickup_datetime AS DATE) = d.date_key
LEFT JOIN dim_weather w ON date_trunc('hour', t.pickup_datetime) = w.hour_ts;

CREATE OR REPLACE TABLE fact_zone_hour AS
WITH base AS (
    SELECT
        pu_location_id AS location_id,
        pickup_hour_ts AS hour_ts,
        COUNT(*) AS trips,
        SUM(total_passenger_pay) AS revenue,
        SUM(driver_pay) AS driver_pay,
        SUM(base_passenger_fare) AS base_fare,
        SUM(tips) AS tips,
        AVG(wait_minutes) AS avg_wait_minutes,
        AVG(duration_minutes) AS avg_duration_minutes,
        AVG(trip_miles) AS avg_miles,
        AVG(take_rate) AS avg_take_rate,
        AVG(tip_pct) AS avg_tip_pct,
        SUM(CASE WHEN is_pooled THEN 1 ELSE 0 END) AS pooled_trips,
        COUNT(DISTINCT dispatching_base_num) AS n_bases,
        -- supply proxy: fulfilled trips (completed demand) at this zone-hour
        COUNT(*) AS supply_proxy
    FROM trips_featured
    GROUP BY 1, 2
)
SELECT
    b.*,
    z.borough,
    z.zone_name,
    z.is_airport,
    z.centroid_lat,
    z.centroid_lon,
    EXTRACT(hour FROM b.hour_ts) AS hour_of_day,
    EXTRACT(dow FROM b.hour_ts) AS weekday,
    EXTRACT(month FROM b.hour_ts) AS month,
    CAST(b.hour_ts AS DATE) AS date_key,
    d.is_weekend,
    d.is_holiday,
    d.holiday_name,
    CASE
        WHEN EXTRACT(dow FROM b.hour_ts) NOT IN (0, 6)
             AND (
                EXTRACT(hour FROM b.hour_ts) BETWEEN 7 AND 9
                OR EXTRACT(hour FROM b.hour_ts) BETWEEN 16 AND 19
             )
        THEN TRUE ELSE FALSE
    END AS is_rush_hour,
    w.temp_c,
    w.precipitation_mm,
    w.snowfall_cm,
    COALESCE(w.is_rain, FALSE) AS is_rain,
    COALESCE(w.is_snow, FALSE) AS is_snow,
    b.revenue / NULLIF(b.trips, 0) AS revenue_per_trip,
    CASE WHEN b.supply_proxy > 0 THEN b.trips * 1.0 / b.supply_proxy ELSE NULL END AS demand_supply_ratio
FROM base b
LEFT JOIN dim_zone z ON b.location_id = z.location_id
LEFT JOIN dim_date d ON CAST(b.hour_ts AS DATE) = d.date_key
LEFT JOIN dim_weather w ON b.hour_ts = w.hour_ts;

CREATE OR REPLACE TABLE fact_zone_hour_lags AS
SELECT
    f.*,
    LAG(trips, 1) OVER (PARTITION BY location_id ORDER BY hour_ts) AS demand_lag_1h,
    LAG(trips, 24) OVER (PARTITION BY location_id ORDER BY hour_ts) AS demand_lag_24h,
    LAG(trips, 168) OVER (PARTITION BY location_id ORDER BY hour_ts) AS demand_lag_168h,
    AVG(trips) OVER (
        PARTITION BY location_id
        ORDER BY hour_ts
        ROWS BETWEEN 24 PRECEDING AND 1 PRECEDING
    ) AS demand_roll_24h,
    AVG(trips) OVER (
        PARTITION BY location_id
        ORDER BY hour_ts
        ROWS BETWEEN 168 PRECEDING AND 1 PRECEDING
    ) AS demand_roll_168h,
    AVG(avg_wait_minutes) OVER (
        PARTITION BY location_id
        ORDER BY hour_ts
        ROWS BETWEEN 24 PRECEDING AND 1 PRECEDING
    ) AS wait_roll_24h
FROM fact_zone_hour f;
