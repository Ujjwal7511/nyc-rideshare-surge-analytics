# Power BI Desktop build guide

You assemble the `.pbix` locally. The repo does not ship a binary.

## 1. Get files
Run `make all`. Tables live in `data/powerbi/*.parquet` (CSV twins available).

## 2. New report
1. Open Power BI Desktop.
2. **File → Options → Regional** as needed (USD).
3. **View → Themes → Browse** → select `powerbi/theme.json`.

## 3. Load data
1. **Get data → Parquet** (or Folder) and load:
   - fact_zone_hour, fact_forecast, fact_reposition_recommendations
   - dim_zone, dim_date, dim_weather
2. In Power Query, set `dim_date[date_key]` to Date; timestamps to Date/Time.
3. Close & Apply.

## 4. Model view
Create relationships exactly as `powerbi/data_model.md`. Hide fact foreign keys from report view if you like. Mark `dim_date` as a date table on `date_key`.

Optional: add a calculated table dummy zone `location_id = 0`, `zone_name = "Citywide"` so city forecasts join.

## 5. Measures
1. New measure table `_Measures`.
2. Paste `powerbi/measures.dax` (skip comments that describe UI-only steps).
3. **Modeling → New parameter → Numeric range**: 1 to 200, increment 5, name `Drivers To Send`, default 50.

## 6. Pages
Create five pages named as in `dashboard_wireframes.md`. Add slicers: `dim_date[date_key]` (between), `dim_zone[borough]`, `dim_zone[cluster_name]`, `fact_zone_hour[is_holiday]`, `fact_zone_hour[is_rain]`.

### Executive
Insert 6 card visuals bound to the KPI measures. Map visual: latitude `centroid_lat`, longitude `centroid_lon`.

### Heatmap
Matrix visual; conditional formatting background on Trips. Enable **drill through** to this page from zone.

### Weather
Legend on `is_rain`. Card for [Rain Uplift %] formatted as percent.

### Forecast
Filter `fact_forecast[split]` contains `test`. Line chart with multiple y fields.

### Repositioning
Hour slicer on `fact_reposition_recommendations[hour_ts]`. Table of zone_name, gap, drivers_sent, est_extra_trips.

## 7. Bookmarks
View → Bookmarks. Add buttons for Revenue/Trips (page 1) and X=25/50/100 (page 5) using Bookmark navigator.

## 8. Publish
Save `NYC_HVFHV_Demand.pbix` outside git (large). Screenshots can be dropped into `reports/figures/` as `pbi_page1.png` etc.
