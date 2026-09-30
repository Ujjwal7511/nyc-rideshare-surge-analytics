# Business Report: NYC HVFHV Demand Surge and Driver Repositioning

## Executive Summary

Surge pricing and efficient driver allocation are critical to ride-hailing profitability. This analysis of NYC's HVFHV (High Volume For Hire Vehicles) market across Q1 2024 identifies **where and when demand outpaces driver supply**, quantifies the impact of weather and holidays on demand, and recommends a data-driven driver repositioning strategy.

**Key findings will be populated after pipeline completion with real numbers from the warehouse.**

## Problem Statement

1. **Unmet demand**: During peak hours, many zones have long wait times (>5 min), suggesting insufficient drivers.
2. **Inefficient supply allocation**: Drivers may cluster in high-demand zones while other areas go under-served.
3. **External drivers**: Weather and holidays significantly shift demand patterns, but current allocation is static.
4. **Revenue opportunity**: Rebalancing driver supply can increase completed trips and gross revenue.

## Approach

- **Data**: 60+ million HVFHV trips (Jan–Mar 2024) + weather + US holiday calendar.
- **Grain**: Zone-hour demand and supply proxy (completed trips).
- **Methods**: SQL aggregation for demand/revenue/wait-time profiles; LightGBM time-series forecasting; KMeans zone clustering; statistical hypothesis testing; A/B-style simulation of repositioning.
- **Outputs**: Hourly demand forecasts by zone, zone classification clusters, driver reposition recommendations, and Power BI dashboard for real-time decisions.

## Key Findings

*To be populated with computed metrics from pipeline:*

1. **Total trips and revenue**: [TBD - from agg_zone_summary and agg_city_hour]
2. **Peak demand pattern**: [TBD - hour and weekday; from analysis_peak_hours]
3. **Top revenue-generating zones**: [TBD - top 5 by revenue; from analysis_zone_rank]
4. **Weather impact**: [TBD - rain uplift %; effect size and p-value; from stats_tests.py output]
5. **Holiday demand shift**: [TBD - holiday vs non-holiday revenue/trip; from stats_tests.py]
6. **Forecast accuracy**: [TBD - LightGBM MAPE and RMSE vs baselines; from forecast.py]
7. **Zone clusters**: [TBD - cluster names, size, profiles; from aggregate.py]
8. **Reposition uplift**: [TBD - estimated extra trips and revenue from repositioning X drivers citywide; from reposition.py]

## Recommendations

1. **Implement hourly supply rebalancing**: Use the predicted demand (forecast tables) to adjust driver allocation in low-supply-high-demand zones.
2. **Weather-informed dispatch**: Increase driver concentration pre-emptively 1–2 hours before rain/snow based on weather forecast API.
3. **Holiday surge planning**: Assign surplus drivers to non-airport zones on holidays (predicted +X% demand).
4. **Pilot: Reposition 50–100 drivers citywide** during evening rush (5–7 PM) to test sensitivity (measured in completed trips and revenue delta).

## Expected Impact

- **Completed trips**: +[TBD]% (sample size and power from A/B simulation)
- **Gross revenue**: +$[TBD]K per day assuming repositioning costs <5% uplift value
- **Customer satisfaction**: Reduced wait times (proxy metric: avg_wait_minutes) by [TBD]%

## Limitations

- **Unmatched demand**: TLC files record only completed trips; unmatched requests are unknown.
- **Driver supply data**: No individual driver or vehicle counts; supply proxy = completed trips only.
- **Microclimate**: Single-point weather; borough or zone-level microclimates not modeled.
- **Q1 sample**: Only 3 months of data; seasonal patterns (summer, winter surge) not captured.
- **No causality**: Lag/weather features are correlates, not causal interventions.

## Next Steps

1. **Validate forecast**: Compare Q2 2024 actual demand to predictions.
2. **AB test repositioning**: Randomize 20% of zones to reposition recommendations; measure KPI lift.
3. **Integrate ML into dispatch**: Feed hourly forecasts + gap estimates into real-time driver assignment optimization.
4. **Expand horizons**: Add more features (events, POI density, competitor pricing) and longer history for year-over-year models.

---

**Data source**: NYC Taxi and Limousine Commission (TLC) HVFHV public data, Jan–Mar 2024  
**Aggregated**: [TBD - N million] trips to [TBD - K thousand] zone-hours  
**Analysis date**: Sept 30, 2026
