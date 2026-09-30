"""EDA charts with insight-style titles using computed numbers."""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from src.config import FIGURES, REPORTS
from src.db import connect
from src.logging_utils import get_logger

log = get_logger(__name__)
sns.set_theme(style="whitegrid", context="talk")


def run() -> dict:
    FIGURES.mkdir(parents=True, exist_ok=True)
    con = connect()
    city = con.execute("SELECT * FROM agg_city_hour").df()
    zh = con.execute(
        """
        SELECT hour_of_day, weekday, borough, trips, revenue, avg_wait_minutes,
               is_rain, revenue_per_trip, temp_c, avg_take_rate
        FROM fact_zone_hour
        """
    ).df()
    rain_tbl = con.execute("SELECT * FROM analysis_rain_uplift").df()
    borough = con.execute(
        """
        SELECT borough, SUM(trips) trips, SUM(revenue) revenue, AVG(avg_wait_minutes) wait
        FROM fact_zone_hour GROUP BY borough
        """
    ).df()
    con.close()
    city["hour_ts"] = pd.to_datetime(city["hour_ts"])

    # Heatmap hour x weekday
    heat = city.pivot_table(index="hour_of_day", columns="weekday", values="trips", aggfunc="sum")
    peak_idx = np.unravel_index(np.nanargmax(heat.to_numpy()), heat.shape)
    peak_hour = int(heat.index[peak_idx[0]])
    peak_dow = int(heat.columns[peak_idx[1]])
    fig, ax = plt.subplots(figsize=(9, 7))
    sns.heatmap(heat, cmap="Blues", ax=ax)
    ax.set_title(f"Demand peaks at hour {peak_hour}:00 (weekday code {peak_dow}) across Jan–Mar 2024")
    fig.tight_layout()
    fig.savefig(FIGURES / "demand_heatmap_hour_weekday.png", dpi=140)
    plt.close(fig)

    # Borough comparison
    fig, ax = plt.subplots(figsize=(8, 5))
    b = borough.sort_values("revenue", ascending=False)
    ax.bar(b["borough"], b["revenue"] / 1e6, color="#1F4E79")
    top_b = b.iloc[0]
    ax.set_ylabel("Revenue ($ millions)")
    ax.set_title(
        f"{top_b['borough']} leads borough revenue at ${top_b['revenue']/1e6:.1f}M "
        f"({top_b['revenue']/b['revenue'].sum()*100:.0f}% of city)"
    )
    fig.tight_layout()
    fig.savefig(FIGURES / "borough_revenue.png", dpi=140)
    plt.close(fig)

    # Revenue distribution
    fig, ax = plt.subplots(figsize=(8, 5))
    sample = zh["revenue_per_trip"].dropna()
    sample = sample[(sample > 0) & (sample < sample.quantile(0.99))]
    ax.hist(sample, bins=50, color="#5B9BD5", edgecolor="white")
    ax.set_title(
        f"Revenue per zone-hour trip averages ${sample.mean():.2f} (median ${sample.median():.2f})"
    )
    fig.tight_layout()
    fig.savefig(FIGURES / "revenue_per_trip_distribution.png", dpi=140)
    plt.close(fig)

    # Correlation
    corr_cols = ["trips", "revenue", "avg_wait_minutes", "temp_c", "avg_take_rate"]
    cdf = zh[corr_cols].dropna()
    if len(cdf) > 50000:
        cdf = cdf.sample(50000, random_state=42)
    fig, ax = plt.subplots(figsize=(7, 6))
    sns.heatmap(cdf.corr(), annot=True, fmt=".2f", cmap="RdBu_r", center=0, ax=ax)
    ax.set_title("Trips and revenue move together; wait time is weakly related to volume")
    fig.tight_layout()
    fig.savefig(FIGURES / "correlation_matrix.png", dpi=140)
    plt.close(fig)

    # Wait time by hour
    w = zh.groupby("hour_of_day", as_index=False)["avg_wait_minutes"].mean()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(w["hour_of_day"], w["avg_wait_minutes"], color="#1F4E79", marker="o")
    worst = w.loc[w["avg_wait_minutes"].idxmax()]
    ax.set_title(
        f"Longest average waits at {int(worst['hour_of_day'])}:00 "
        f"({worst['avg_wait_minutes']:.1f} min) — supply tightness signal"
    )
    fig.tight_layout()
    fig.savefig(FIGURES / "wait_time_by_hour.png", dpi=140)
    plt.close(fig)

    # Rain vs Manhattan after 6pm
    man = rain_tbl[(rain_tbl["borough"] == "Manhattan") & (rain_tbl["hour_of_day"] >= 18)]
    rain_pct = None
    if len(man):
        dry = man["trips_per_zh_dry"].mean()
        rn = man["trips_per_zh_rain"].mean()
        rain_pct = (rn / dry - 1) * 100 if dry else None
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar(["Dry", "Rain"], [dry, rn], color=["#5B9BD5", "#1F4E79"])
        title = (
            f"Rain lifts Manhattan demand {rain_pct:.1f}% after 6 PM"
            if rain_pct is not None
            else "Manhattan evening demand: rain vs dry"
        )
        ax.set_title(title)
        ax.set_ylabel("Trips per zone-hour")
        fig.tight_layout()
        fig.savefig(FIGURES / "rain_manhattan_evening.png", dpi=140)
        plt.close(fig)

    insights = {
        "peak_hour": peak_hour,
        "peak_weekday_code": peak_dow,
        "top_borough": str(top_b["borough"]),
        "top_borough_revenue": float(top_b["revenue"]),
        "top_borough_share": float(top_b["revenue"] / b["revenue"].sum()),
        "mean_revenue_per_trip": float(sample.mean()),
        "median_revenue_per_trip": float(sample.median()),
        "worst_wait_hour": int(worst["hour_of_day"]),
        "worst_wait_minutes": float(worst["avg_wait_minutes"]),
        "manhattan_rain_uplift_after_6pm_pct": float(rain_pct) if rain_pct is not None else None,
    }
    (REPORTS / "eda_insights.json").write_text(json.dumps(insights, indent=2), encoding="utf-8")
    log.info("EDA figures written")
    return insights
