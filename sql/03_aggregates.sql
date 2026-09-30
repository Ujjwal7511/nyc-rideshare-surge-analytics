-- 03_aggregates.sql: citywide and borough rollups used by EDA and Power BI.

CREATE OR REPLACE TABLE agg_city_hour AS
SELECT
    hour_ts,
    SUM(trips) AS trips,
    SUM(revenue) AS revenue,
    SUM(driver_pay) AS driver_pay,
    AVG(avg_wait_minutes) AS avg_wait_minutes,
    MAX(is_rain) AS is_rain,
    MAX(is_snow) AS is_snow,
    AVG(temp_c) AS temp_c,
    MAX(is_holiday) AS is_holiday,
    MAX(is_weekend) AS is_weekend,
    MAX(is_rush_hour) AS is_rush_hour,
    hour_of_day,
    weekday,
    month,
    date_key
FROM fact_zone_hour
GROUP BY hour_ts, hour_of_day, weekday, month, date_key;

CREATE OR REPLACE TABLE agg_borough_hour AS
SELECT
    borough,
    hour_ts,
    SUM(trips) AS trips,
    SUM(revenue) AS revenue,
    AVG(avg_wait_minutes) AS avg_wait_minutes,
    MAX(is_rain) AS is_rain,
    MAX(is_holiday) AS is_holiday
FROM fact_zone_hour
GROUP BY borough, hour_ts;

CREATE OR REPLACE TABLE agg_zone_summary AS
SELECT
    location_id,
    ANY_VALUE(zone_name) AS zone_name,
    ANY_VALUE(borough) AS borough,
    ANY_VALUE(is_airport) AS is_airport,
    ANY_VALUE(centroid_lat) AS centroid_lat,
    ANY_VALUE(centroid_lon) AS centroid_lon,
    SUM(trips) AS trips,
    SUM(revenue) AS revenue,
    SUM(driver_pay) AS driver_pay,
    AVG(avg_wait_minutes) AS avg_wait_minutes,
    AVG(revenue_per_trip) AS revenue_per_trip,
    AVG(avg_take_rate) AS avg_take_rate,
    SUM(CASE WHEN is_rush_hour THEN trips ELSE 0 END) * 1.0 / NULLIF(SUM(trips), 0) AS rush_share,
    SUM(CASE WHEN hour_of_day >= 20 OR hour_of_day <= 2 THEN trips ELSE 0 END) * 1.0
        / NULLIF(SUM(trips), 0) AS nightlife_share,
    SUM(CASE WHEN weekday IN (0, 6) THEN trips ELSE 0 END) * 1.0 / NULLIF(SUM(trips), 0) AS weekend_share
FROM fact_zone_hour
GROUP BY location_id;
