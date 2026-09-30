"""Fill docs and README from pipeline metrics (no fabricated numbers)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src.config import DOCS, METRICS_JSON, ROOT, REPORTS
from src.logging_utils import get_logger

log = get_logger(__name__)


def _fmt(x, nd=1, pct=False, money=False):
    if x is None:
        return "TBD"
    try:
        if pct:
            return f"{float(x)*100:.1f}%" if abs(float(x)) <= 1.5 else f"{float(x):.1f}%"
        if money:
            v = float(x)
            if abs(v) >= 1e6:
                return f"${v/1e6:.2f}M"
            if abs(v) >= 1e3:
                return f"${v/1e3:.1f}k"
            return f"${v:.2f}"
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return "TBD"


def _g(d, *keys, default=None):
    cur = d
    for k in keys:
        if cur is None or not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def run(metrics: dict) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    m = metrics
    raw = _g(m, "clean", "raw_trips")
    clean = _g(m, "clean", "clean_trips")
    removed = _g(m, "clean", "removed_trips")
    synth = _g(m, "ingest", "synthetic", default=False)
    fact_n = _g(m, "features", "fact_zone_hour_rows")
    pbi_n = _g(m, "powerbi", "fact_zone_hour_rows")
    lgb = _g(m, "forecast", "zone_top50", "lightgbm") or {}
    naive = _g(m, "forecast", "zone_top50", "seasonal_naive_168h") or {}
    ma = _g(m, "forecast", "zone_top50", "moving_average_24h") or {}
    city_lgb = _g(m, "forecast", "citywide", "lightgbm") or {}
    rain = _g(m, "eda", "manhattan_rain_uplift_after_6pm_pct")
    top_b = _g(m, "eda", "top_borough")
    extra_t = _g(m, "reposition", "total_est_extra_trips")
    extra_r = _g(m, "reposition", "total_est_extra_revenue")
    rain_p = _g(m, "stats", "rain_vs_dry_hourly_demand", "pvalue")
    rain_d = _g(m, "stats", "rain_vs_dry_hourly_demand", "cohens_d")
    rain_ma = _g(m, "stats", "rain_vs_dry_hourly_demand", "mean_a")
    rain_mb = _g(m, "stats", "rain_vs_dry_hourly_demand", "mean_b")
    wape = lgb.get("wape")
    mae = lgb.get("mae")
    wape_naive = naive.get("wape")
    take = _g(m, "aggregate", "take_rate_borough") or []
    mom = _g(m, "aggregate", "mom") or []
    top_zones = _g(m, "aggregate", "top_zones") or []
    clusters = _g(m, "aggregate", "cluster_sizes") or {}
    src_note = (
        "Source is a **labeled synthetic sample** because TLC parquet download failed."
        if synth
        else "Source is NYC TLC High Volume FHV trip files for 2024-01 through 2024-03."
    )

    millions = (clean or 0) / 1_000_000

    resume = [
        f"Processed {millions:.2f} million NYC HVFHV trips (2024 Q1) in DuckDB to a {pbi_n or fact_n:,}-row zone-hour star schema for Power BI (never loading full trip grain into pandas)."
        if clean
        else "TBD — pipeline metrics missing.",
        f"Forecasted hourly demand for top-50 zones with LightGBM (test WAPE {wape:.1f}%) vs seasonal-naive WAPE {wape_naive:.1f}% using lag, holiday, and weather features with a time-based split."
        if wape is not None and wape_naive is not None
        else "TBD — forecast metrics missing.",
        f"Built a wait-aware driver repositioning model (X=50) estimating {extra_t:,.0f} extra completed trips and {_fmt(extra_r, money=True)} revenue in the holdout window under documented capture assumptions."
        if extra_t is not None
        else "TBD — repositioning metrics missing.",
    ]
    (REPORTS / "resume_bullets.md").write_text(
        "# Resume bullets (from pipeline metrics)\n\n" + "\n".join(f"- {b}" for b in resume) + "\n",
        encoding="utf-8",
    )

    # insights
    bullets = []
    if top_zones:
        z0 = top_zones[0]
        bullets.append(
            f"**{z0.get('zone_name')}** ({z0.get('borough')}) is the top revenue zone at {_fmt(z0.get('revenue'), money=True)} across {_fmt(z0.get('trips'), 0)} trips."
        )
    if top_b:
        bullets.append(
            f"**{top_b}** is the highest-revenue borough ({_fmt(_g(m,'eda','top_borough_share'), pct=True)} of city revenue)."
        )
    if rain is not None:
        bullets.append(
            f"Rain is associated with a **{rain:.1f}%** change in Manhattan zone-hour demand after 6 PM vs dry hours."
        )
    if rain_p is not None:
        bullets.append(
            f"Citywide hourly trips average { _fmt(rain_ma,1)} on rain hours vs {_fmt(rain_mb,1)} dry (p={rain_p:.4g}, Cohen's d={_fmt(rain_d,3)})."
        )
    if mae is not None:
        bullets.append(
            f"LightGBM zone-hour test MAE is **{mae:.2f} trips** (WAPE {wape:.1f}%) vs seasonal naive WAPE {wape_naive:.1f}%."
        )
    if extra_t is not None:
        bullets.append(
            f"Repositioning 50 drivers/hour in the test window is estimated to add **{extra_t:,.0f} trips** and {_fmt(extra_r, money=True)} revenue (assumption-bound)."
        )
    if take:
        t0 = take[0]
        bullets.append(
            f"Highest platform take rate (from totals) is **{t0.get('borough')}** at {_fmt(t0.get('take_rate_from_totals'), pct=True)}."
        )
    if mom and len(mom) > 1:
        last = mom[-1]
        bullets.append(
            f"Month {last.get('month')} trips month-over-month change is {_fmt(last.get('trips_mom'), pct=True)}."
        )
    wait_h = _g(m, "eda", "worst_wait_hour")
    wait_m = _g(m, "eda", "worst_wait_minutes")
    if wait_h is not None:
        bullets.append(
            f"Average waits peak at **{wait_h}:00** ({_fmt(wait_m,1)} minutes), a supply-scarcity signal for repositioning."
        )
    if clusters:
        bullets.append(
            "Zone clusters: " + ", ".join(f"{k} ({v})" for k, v in clusters.items()) + "."
        )
    while len(bullets) < 10:
        bullets.append(
            "Additional insight TBD until more segments are exported — see reports/metrics.json."
        )
    insights_md = "# Top 10 insights\n\n" + "\n".join(
        f"{i}. {b}" for i, b in enumerate(bullets[:10], 1)
    )
    (DOCS / "insights.md").write_text(insights_md + "\n", encoding="utf-8")

    biz = f"""# Business report: Predicting surge demand and optimizing driver allocation in NYC

**Date:** {date.today().isoformat()}  
**Data:** {src_note}

## Problem
Ride-hail platforms lose completed trips when demand outruns nearby supply. The business questions: where and when is the city short of drivers, what drives revenue, how weather and holidays shift demand, and which zones should idle drivers move toward next hour.

## Approach
Trip files were ingested into DuckDB and cleaned in SQL (never full-trip pandas). Features include calendar, rush-hour, wait time, take rate, weather, and demand lags. Analysis uses window functions for ranks and MoM growth. LightGBM forecasts hourly demand for the top 50 zones plus a citywide model on a time-based split. A repositioning layer allocates X drivers to the largest wait-adjusted demand gaps.

## Top findings
- Cleaned trips: **{clean:,}** of **{raw:,}** raw ({_fmt((removed or 0)/(raw or 1), pct=True)} removed). See `reports/cleaning_log.md`.
- Power BI grain: **{pbi_n:,}** zone-hour rows from **{millions:.2f} million** cleaned trips.
- Borough leader: **{top_b or 'TBD'}**.
- Rain vs dry citywide hours: means { _fmt(rain_ma,1)} vs {_fmt(rain_mb,1)}, p={rain_p if rain_p is not None else 'TBD'}.
- Manhattan after-6PM rain demand change: **{_fmt(rain,1) if rain is not None else 'TBD'}%**.
- Forecast (top-50 zones, test): LightGBM MAE **{_fmt(mae,2)}**, WAPE **{_fmt(wape,1)}%**; seasonal naive WAPE **{_fmt(wape_naive,1)}%**; 24h MA WAPE **{_fmt(ma.get('wape'),1)}%**.
- Citywide LightGBM WAPE: **{_fmt(city_lgb.get('wape'),1)}%**.
- Repositioning (X=50, test window): **{_fmt(extra_t,0)}** extra trips, **{_fmt(extra_r, money=True)}** extra revenue (see assumptions).

## Recommendations
1. Pre-position drivers into high-gap zones 30–60 minutes before historically tight hours (see wait-by-hour chart).
2. Treat rain evenings in Manhattan as a distinct surge playbook; staff and incentives should differ from dry weekdays.
3. Use the LightGBM forecast as the demand prior and the wait-adjusted gap as the dispatch signal — not raw last-hour trips alone.
4. Review airport vs non-airport revenue per trip before blanket citywide incentives.

## Expected impact
Under the documented capture rate (0.65 trips per extra driver per hour, capped by gap), moving 50 drivers each test-window hour is estimated at { _fmt(extra_t,0)} incremental trips. Sensitivity by X is in `reports/reposition_summary.json`. These are **scenario estimates**, not guaranteed lift.

## Limitations
- HVFHV files have no driver ID; supply is proxied by completed trips and wait time.
- One-step forecasts use observed lags (operationally you need recursive or as-available lags).
- Three months cannot support true YoY in-sample; YoY DAX is wired for later years.
- {"Synthetic data — do not use for production decisions." if synth else "TLC public data may omit some negotiated fares / quality flags."}

## Next steps
Add 12+ months, true vehicle GPS pings, surge multiplier if licensed, and online allocation with a live wait-time feed. Assemble the Power BI file from `data/powerbi` using `powerbi/build_guide.md`.
"""
    (DOCS / "business_report.md").write_text(biz, encoding="utf-8")

    qa = f"""# Interview Q&A (grounded in this repo's metrics)

1. **What was the business problem?** Map where hourly demand exceeds a supply proxy, quantify weather/holiday effects, forecast zone-hour demand, and recommend driver repositioning.
2. **Why DuckDB not Spark/pandas?** ~trip-level HVFHV is large; DuckDB scans parquet/SQL with limited RAM. Pandas is used only on aggregates (zone-hour, top-50). Cleaned trips: {clean:,}.
3. **How did you clean data?** SQL filters for nulls, unknown zones 264/265, unordered timestamps, fare/distance/duration/speed bounds. Removed {removed:,} rows. Logged in reports/cleaning_log.md.
4. **What is the grain of the model?** Zone × hour. Lags are partitioned by location_id ordered by hour_ts.
5. **How is leakage prevented?** Train through { _g(m,'forecast','split','train_end') }, validate through { _g(m,'forecast','split','valid_end') }, test from { _g(m,'forecast','split','test_start') }. Lags use past rows only (SQL LAG / shift).
6. **Forecast results?** Top-50 LightGBM test MAE { _fmt(mae,2) }, WAPE { _fmt(wape,1) }% vs seasonal naive WAPE { _fmt(wape_naive,1) }% and MA WAPE { _fmt(ma.get('wape'),1) }%.
7. **Why seasonal naive 168h?** Weekly seasonality in ride-hail is strong; 168h is a hard baseline.
8. **Weather source?** Open-Meteo hourly temp, precipitation, snowfall for 40.71, -74.01, America/New_York.
9. **Rain finding?** { _g(m,'stats','plain_english','rain') }
10. **Which tests and why?** Mann-Whitney/Welch for two groups when Shapiro fails; Kruskal/ANOVA across boroughs; bootstrap CI on mean difference; simulated A/B with power.
11. **Supply proxy without driver IDs?** Completed trips as fulfilled demand; unmet inferred from wait above 4 minutes, capped at 50%.
12. **Repositioning math?** Allocate X drivers to largest gaps, max 15 per zone; capture min(gap, 0.65×drivers). Test-window extra trips { _fmt(extra_t,0) }.
13. **Why 0.65 capture?** Conservative utilization assumption documented in ASSUMPTIONS.md; sensitivity at X=10,25,50,100,200.
14. **Clustering?** KMeans on log demand, revenue, wait, rush/nightlife/weekend shares; names from centroid rules (Airport, Nightlife, Commuter hubs, Low-demand, High-yield).
15. **Airport vs rest?** See analysis_airport in DuckDB / metrics aggregate.airport {json.dumps(_g(m,'aggregate','airport'), default=str)[:400]}.
16. **Power BI row cap?** Aggregated to zone-hour; exported {pbi_n:,} fact rows (<500k target).
17. **Take rate definition?** 1 − driver_pay / total_passenger_pay at trip level; borough rollup uses sums.
18. **What would you do with 12 months?** True YoY, better LightGBM seasonality, holiday interactions, and recursive multi-horizon forecasts.
19. **Biggest caveat?** Gap is not observed unmatched requests; wait-time inflation is a proxy. { 'Synthetic fallback was used.' if synth else 'Public TLC may differ from vendor internal tables.' }
20. **Resume numbers source?** reports/metrics.json produced by src/run_pipeline.py — not typed by hand.
"""
    (DOCS / "interview_qa.md").write_text(qa, encoding="utf-8")

    readme = f"""# Predicting Surge Demand and Optimizing Driver Allocation in NYC Ride-Hailing

## Problem
NYC high-volume FHV platforms need to know **where and when demand exceeds supply**, what drives revenue, how **weather and holidays** shift rides, **forecast hourly demand by zone**, and **reposition drivers** before waits spike.

## Architecture

```mermaid
flowchart LR
  TLC[TLC parquet + zones] --> Ingest[ingest.py]
  Weather[Open-Meteo] --> Ingest
  Holidays[holidays package] --> Ingest
  Ingest --> DuckDB[(warehouse.duckdb)]
  DuckDB --> SQL[SQL clean / features / analysis]
  SQL --> Models[LightGBM + KMeans + tests]
  Models --> PBI[data/powerbi star schema]
  Models --> Rpts[reports + docs]
```

## Tech stack
Python 3.11, DuckDB, pandas, scikit-learn, LightGBM, statsmodels, scipy, matplotlib/seaborn, pytest, Jupyter. Power BI consumes exported parquet/CSV (you assemble the `.pbix`).

## How to run
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\python -m pip install -r requirements.txt
# Unix: .venv/bin/pip install -r requirements.txt
make all
# or: .venv/Scripts/python -m src.run_pipeline && .venv/Scripts/python -m pytest -q
```

## Key results
- {src_note}
- Cleaned **{clean:,}** trips from **{raw:,}** raw.
- **Aggregated {millions:.2f} million trips to {pbi_n or fact_n:,} rows before loading into Power BI.**
- LightGBM top-50 test **WAPE {_fmt(wape,1)}%**, MAE {_fmt(mae,2)} vs seasonal naive WAPE {_fmt(wape_naive,1)}%.
- Reposition X=50 estimated **{_fmt(extra_t,0)}** extra trips and **{_fmt(extra_r, money=True)}** in the test window.
- Manhattan evening rain demand change: **{rain if rain is not None else 'TBD'}%**.

## Resume bullets
{chr(10).join('- ' + b for b in resume)}

## Screenshot placeholders
- Executive summary: `reports/figures/borough_revenue.png`
- Demand heatmap: `reports/figures/demand_heatmap_hour_weekday.png`
- Weather: `reports/figures/rain_manhattan_evening.png`
- Forecast: `reports/figures/forecast_feature_importance.png`
- Residuals: `reports/figures/forecast_residuals.png`

## Project layout
`src/`, `sql/`, `notebooks/`, `powerbi/`, `docs/`, `tests/`, `data/raw|processed|powerbi`, `reports/`.

## Manual step
Open Power BI Desktop and follow `powerbi/build_guide.md` (no `.pbix` is generated in this repo).
"""
    (ROOT / "README.md").write_text(readme, encoding="utf-8")
    log.info("Docs written from metrics")
