"""SQL aggregates, analysis tables, and KMeans zone clusters."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from src.config import RANDOM_SEED, SQL_DIR, DATA_PROCESSED
from src.db import connect, run_sql_file
from src.logging_utils import get_logger

log = get_logger(__name__)


def _name_cluster(row: pd.Series) -> str:
    if row["is_airport"] >= 0.5:
        return "Airport"
    if row["nightlife_share"] > 0.28 and row["weekend_share"] > 0.32:
        return "Nightlife"
    if row["rush_share"] > 0.28:
        return "Commuter hubs"
    if row["trips"] < row.get("_trips_p25", 0):
        return "Low-demand"
    if row["revenue_per_trip"] > row.get("_rpt_p75", 0):
        return "High-yield"
    return "Mixed residential"


def cluster_zones(con) -> pd.DataFrame:
    df = con.execute("SELECT * FROM agg_zone_summary").df()
    if df.empty:
        return df
    feat_cols = [
        "trips",
        "revenue",
        "avg_wait_minutes",
        "revenue_per_trip",
        "rush_share",
        "nightlife_share",
        "weekend_share",
    ]
    X = df[feat_cols].fillna(0).to_numpy()
    X[:, 0] = np.log1p(X[:, 0])
    X[:, 1] = np.log1p(np.clip(X[:, 1], 0, None))
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    k = min(5, max(2, len(df) // 8))
    km = KMeans(n_clusters=k, random_state=RANDOM_SEED, n_init=10)
    df["cluster_id"] = km.fit_predict(Xs)
    p25 = df["trips"].quantile(0.25)
    p75_rpt = df["revenue_per_trip"].quantile(0.75)
    names = {}
    for cid, g in df.groupby("cluster_id"):
        prof = {
            "is_airport": g["is_airport"].mean(),
            "nightlife_share": g["nightlife_share"].mean(),
            "weekend_share": g["weekend_share"].mean(),
            "rush_share": g["rush_share"].mean(),
            "trips": g["trips"].median(),
            "revenue_per_trip": g["revenue_per_trip"].mean(),
            "_trips_p25": p25,
            "_rpt_p75": p75_rpt,
        }
        names[cid] = _name_cluster(pd.Series(prof))
    # Ensure unique names
    used = {}
    for cid, name in names.items():
        used[name] = used.get(name, 0) + 1
        if used[name] > 1:
            names[cid] = f"{name} {used[name]}"
    df["cluster_name"] = df["cluster_id"].map(names)
    con.execute("DROP TABLE IF EXISTS zone_clusters")
    con.register("c_df", df[["location_id", "cluster_id", "cluster_name"]])
    con.execute("CREATE TABLE zone_clusters AS SELECT * FROM c_df")
    con.execute(
        """
        CREATE OR REPLACE TABLE dim_zone AS
        SELECT z.*, c.cluster_id, c.cluster_name
        FROM dim_zone z
        LEFT JOIN zone_clusters c ON z.location_id = c.location_id
        """
    )
    out = DATA_PROCESSED / "zone_clusters.csv"
    df.to_csv(out, index=False)
    log.info("Clustered %s zones into %s groups", len(df), k)
    return df


def run() -> dict:
    con = connect()
    run_sql_file(con, SQL_DIR / "03_aggregates.sql")
    run_sql_file(con, SQL_DIR / "04_analysis.sql")
    clusters = cluster_zones(con)
    top = con.execute(
        """
        SELECT zone_name, borough, revenue, trips, revenue_per_trip
        FROM analysis_zone_rank ORDER BY revenue_rank LIMIT 5
        """
    ).df()
    mom = con.execute("SELECT * FROM analysis_mom_growth ORDER BY month").df()
    airport = con.execute("SELECT * FROM analysis_airport").df()
    take = con.execute("SELECT * FROM analysis_take_rate_borough").df()
    con.close()
    return {
        "n_clusters": int(clusters["cluster_id"].nunique()) if len(clusters) else 0,
        "cluster_sizes": clusters.groupby("cluster_name").size().to_dict() if len(clusters) else {},
        "top_zones": top.to_dict(orient="records"),
        "mom": mom.to_dict(orient="records"),
        "airport": airport.to_dict(orient="records"),
        "take_rate_borough": take.to_dict(orient="records"),
    }
