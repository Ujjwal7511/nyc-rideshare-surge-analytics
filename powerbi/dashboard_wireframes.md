# Dashboard wireframes (5 pages)

Theme: navy `#1F4E79`, steel `#5B9BD5`, gray `#D6DCE4`. Slicers on every page: **Date**, **Borough**, **Cluster**, **Holiday**, **Rain**.

## Page 1 — Executive Summary
- KPI cards: Total Revenue, Trips, Revenue per Trip, Take Rate, Avg Wait, MoM %
- Map: dim_zone lat/long, size = Trips, color = Revenue per Trip
- Bar: top 10 zones by [Total Revenue] with [Zone Rank Revenue]
- Line: trips by date_key
- Bookmark: "Revenue" vs "Trips" (same visuals, swapped measure)
- Drill-through target: Page 2 (pass zone_name)

## Page 2 — Demand Heatmap
- Matrix: hour_of_day (rows) × weekday (columns), values = Trips, color scale
- Clustered bar: borough trips
- Line: wait minutes by hour_of_day
- Tooltip page: zone name, revenue per trip, wait
- Drill-through from exec map

## Page 3 — Weather and Holiday Impact
- Toggle slicer is_rain / is_holiday
- Column chart: trips by hour, legend rain vs dry
- KPI: Rain Uplift %
- Scatter: temp_c vs trips (aggregated hour)
- Table: holiday_name, trips, revenue per trip

## Page 4 — Forecast vs Actual
- Filter split = test (and exclude location_id 0 for zonal, or include for city)
- Line: actual_trips vs pred_lgb vs pred_naive_168 vs pred_ma by hour_ts
- KPI: MAPE, Forecast Variance %
- Bar: feature importance is a static image (`reports/figures/forecast_feature_importance.png`) or a small imported table if you flatten JSON
- Ribbon chart: residuals optional (actual - pred)

## Page 5 — Driver Repositioning Simulator
- What-if: Drivers To Send (1–200)
- KPI: Est Extra Trips, Est Extra Revenue, Uplift Scaled to Parameter, Gap
- Map: color = gap, size = drivers_sent
- Table: top recommended zones for selected hour (hour slicer)
- Bookmark: X=25 / X=50 / X=100 (sets parameter)
- Note in text box: capture 0.65, max 15 drivers/zone (ASSUMPTIONS.md)
