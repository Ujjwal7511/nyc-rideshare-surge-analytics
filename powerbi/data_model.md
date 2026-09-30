# Power BI data model

Load parquet (preferred) or CSV from `data/powerbi/`.

## Tables
| table | grain | role |
|---|---|---|
| fact_zone_hour | location_id × hour_ts | primary fact |
| fact_forecast | location_id × hour_ts | forecast fact (location_id 0 = citywide) |
| fact_reposition_recommendations | location_id × hour_ts (allocated rows) | decision fact |
| dim_zone | location_id | zone dimension + cluster + lat/long |
| dim_date | date_key | calendar + holiday |
| dim_weather | hour_ts | citywide weather |

## Relationships (star)

| from | to | cardinality | cross filter |
|---|---|---|---|
| fact_zone_hour[location_id] | dim_zone[location_id] | * : 1 | single |
| fact_zone_hour[date_key] | dim_date[date_key] | * : 1 | single |
| fact_zone_hour[hour_ts] | dim_weather[hour_ts] | * : 1 | single |
| fact_forecast[location_id] | dim_zone[location_id] | * : 1 | single (treat citywide 0 as unmatched or add a City row) |
| fact_reposition_recommendations[location_id] | dim_zone[location_id] | * : 1 | single |

Inactive alternative: relate forecast to date via `DATE(fact_forecast[hour_ts])` calculated column `forecast_date`.

```mermaid
erDiagram
  DIM_ZONE ||--o{ FACT_ZONE_HOUR : location_id
  DIM_DATE ||--o{ FACT_ZONE_HOUR : date_key
  DIM_WEATHER ||--o{ FACT_ZONE_HOUR : hour_ts
  DIM_ZONE ||--o{ FACT_FORECAST : location_id
  DIM_ZONE ||--o{ FACT_REPOSITION : location_id
  FACT_ZONE_HOUR {
    int location_id
    datetime hour_ts
    float trips
    float revenue
  }
  DIM_ZONE {
    int location_id
    string borough
    string cluster_name
    float centroid_lat
    float centroid_lon
  }
```
