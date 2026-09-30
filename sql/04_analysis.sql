-- 04_analysis.sql: window functions, ranks, MoM, airport split, driver $/hour.

CREATE OR REPLACE TABLE analysis_zone_rank AS
WITH zone_rev AS (
    SELECT
        location_id,
        ANY_VALUE(zone_name) AS zone_name,
        ANY_VALUE(borough) AS borough,
        SUM(revenue) AS revenue,
        SUM(trips) AS trips,
        SUM(revenue) / NULLIF(SUM(trips), 0) AS revenue_per_trip,
        AVG(avg_wait_minutes) AS avg_wait
    FROM fact_zone_hour
    GROUP BY location_id
)
SELECT
    *,
    RANK() OVER (ORDER BY revenue DESC) AS revenue_rank,
    RANK() OVER (ORDER BY revenue ASC) AS revenue_rank_asc,
    RANK() OVER (PARTITION BY borough ORDER BY revenue DESC) AS borough_revenue_rank,
    SUM(revenue) OVER (ORDER BY revenue DESC ROWS UNBOUNDED PRECEDING) AS running_revenue,
    SUM(revenue) OVER () AS city_revenue,
    SUM(revenue) OVER (ORDER BY revenue DESC ROWS UNBOUNDED PRECEDING)
        / NULLIF(SUM(revenue) OVER (), 0) AS revenue_cumulative_share
FROM zone_rev;

CREATE OR REPLACE TABLE analysis_take_rate_borough AS
SELECT
    borough,
    AVG(avg_take_rate) AS avg_take_rate,
    SUM(revenue) AS revenue,
    SUM(driver_pay) AS driver_pay,
    1 - SUM(driver_pay) / NULLIF(SUM(revenue), 0) AS take_rate_from_totals
FROM fact_zone_hour
GROUP BY borough
ORDER BY take_rate_from_totals DESC;

CREATE OR REPLACE TABLE analysis_peak_hours AS
SELECT
    hour_of_day,
    weekday,
    SUM(trips) AS trips,
    SUM(revenue) AS revenue,
    RANK() OVER (ORDER BY SUM(trips) DESC) AS demand_rank
FROM fact_zone_hour
GROUP BY hour_of_day, weekday;

CREATE OR REPLACE TABLE analysis_mom_growth AS
WITH m AS (
    SELECT
        month,
        SUM(trips) AS trips,
        SUM(revenue) AS revenue
    FROM fact_zone_hour
    GROUP BY month
)
SELECT
    month,
    trips,
    revenue,
    LAG(trips) OVER (ORDER BY month) AS trips_prev,
    LAG(revenue) OVER (ORDER BY month) AS revenue_prev,
    (trips - LAG(trips) OVER (ORDER BY month)) * 1.0
        / NULLIF(LAG(trips) OVER (ORDER BY month), 0) AS trips_mom,
    (revenue - LAG(revenue) OVER (ORDER BY month))
        / NULLIF(LAG(revenue) OVER (ORDER BY month), 0) AS revenue_mom
FROM m;

CREATE OR REPLACE TABLE analysis_airport AS
SELECT
    is_airport,
    SUM(trips) AS trips,
    SUM(revenue) AS revenue,
    SUM(revenue) / NULLIF(SUM(trips), 0) AS revenue_per_trip,
    AVG(avg_wait_minutes) AS avg_wait,
    AVG(avg_miles) AS avg_miles
FROM fact_zone_hour
GROUP BY is_airport;

CREATE OR REPLACE TABLE analysis_driver_earnings AS
-- Driver $ per hour approximated as zone-hour driver_pay / supply_proxy hours
SELECT
    location_id,
    ANY_VALUE(zone_name) AS zone_name,
    ANY_VALUE(borough) AS borough,
    SUM(driver_pay) AS driver_pay,
    SUM(supply_proxy) AS driver_hours_proxy,
    SUM(driver_pay) / NULLIF(SUM(supply_proxy), 0) AS driver_pay_per_hour,
    RANK() OVER (ORDER BY SUM(driver_pay) / NULLIF(SUM(supply_proxy), 0) DESC) AS pay_rank
FROM fact_zone_hour
GROUP BY location_id;

CREATE OR REPLACE TABLE analysis_rain_uplift AS
WITH borough_hour AS (
    SELECT
        borough,
        hour_of_day,
        is_rain,
        SUM(trips) AS trips,
        COUNT(*) AS zone_hours
    FROM fact_zone_hour
    GROUP BY borough, hour_of_day, is_rain
)
SELECT
    borough,
    hour_of_day,
    SUM(CASE WHEN is_rain THEN trips ELSE 0 END) * 1.0
        / NULLIF(SUM(CASE WHEN is_rain THEN zone_hours ELSE 0 END), 0) AS trips_per_zh_rain,
    SUM(CASE WHEN NOT is_rain THEN trips ELSE 0 END) * 1.0
        / NULLIF(SUM(CASE WHEN NOT is_rain THEN zone_hours ELSE 0 END), 0) AS trips_per_zh_dry
FROM borough_hour
GROUP BY borough, hour_of_day;

CREATE OR REPLACE TABLE analysis_cohort_week AS
-- Cohort-style: first week a zone exceeds city median demand, then subsequent week demand
WITH zone_week AS (
    SELECT
        location_id,
        date_trunc('week', hour_ts) AS week_start,
        SUM(trips) AS trips
    FROM fact_zone_hour
    GROUP BY 1, 2
),
med AS (
    SELECT quantile_cont(trips, 0.5) AS med_trips FROM zone_week
),
first_hit AS (
    SELECT location_id, MIN(week_start) AS cohort_week
    FROM zone_week, med
    WHERE trips >= med.med_trips
    GROUP BY location_id
)
SELECT
    f.cohort_week,
    date_diff('week', f.cohort_week, z.week_start) AS weeks_since_cohort,
    AVG(z.trips) AS avg_weekly_trips,
    COUNT(DISTINCT z.location_id) AS zones
FROM zone_week z
JOIN first_hit f ON z.location_id = f.location_id
GROUP BY 1, 2
ORDER BY 1, 2;
