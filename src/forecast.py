"""Hourly demand forecast: seasonal naive, MA, LightGBM. Top-50 zones + citywide."""

from __future__ import annotations

import json

import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from src.config import (
    FIGURES,
    RANDOM_SEED,
    REPORTS,
    TEST_START,
    TOP_N_ZONES,
    TRAIN_END,
    VALID_END,
)
from src.db import connect
from src.logging_utils import get_logger

log = get_logger(__name__)


def _metrics(y: np.ndarray, yhat: np.ndarray) -> dict:
    y = np.asarray(y, float)
    yhat = np.asarray(yhat, float)
    mask = np.isfinite(y) & np.isfinite(yhat)
    y, yhat = y[mask], yhat[mask]
    mae = float(mean_absolute_error(y, yhat))
    rmse = float(np.sqrt(mean_squared_error(y, yhat)))
    mape = float(np.mean(np.abs((y - yhat) / np.clip(y, 1e-6, None))) * 100)
    wape = float(np.sum(np.abs(y - yhat)) / np.clip(np.sum(np.abs(y)), 1e-6, None) * 100)
    return {"mae": mae, "rmse": rmse, "mape": mape, "wape": wape}


def _split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = df[df["hour_ts"] <= pd.Timestamp(TRAIN_END)]
    valid = df[(df["hour_ts"] > pd.Timestamp(TRAIN_END)) & (df["hour_ts"] <= pd.Timestamp(VALID_END))]
    test = df[df["hour_ts"] >= pd.Timestamp(TEST_START)]
    return train, valid, test


def run() -> dict:
    FIGURES.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    con = connect()
    top = con.execute(
        f"""
        SELECT location_id FROM agg_zone_summary
        ORDER BY trips DESC LIMIT {TOP_N_ZONES}
        """
    ).df()["location_id"].tolist()
    lags = con.execute(
        f"""
        SELECT *
        FROM fact_zone_hour_lags
        WHERE location_id IN ({",".join(str(int(i)) for i in top)})
        ORDER BY location_id, hour_ts
        """
    ).df()
    city = con.execute(
        """
        SELECT hour_ts, trips, is_rain, is_snow, is_holiday, is_weekend, is_rush_hour,
               temp_c, hour_of_day, weekday, month
        FROM agg_city_hour
        ORDER BY hour_ts
        """
    ).df()
    con.close()
    lags["hour_ts"] = pd.to_datetime(lags["hour_ts"])
    city["hour_ts"] = pd.to_datetime(city["hour_ts"])

    feat = [
        "hour_of_day",
        "weekday",
        "month",
        "is_weekend",
        "is_holiday",
        "is_rush_hour",
        "is_rain",
        "is_snow",
        "temp_c",
        "demand_lag_1h",
        "demand_lag_24h",
        "demand_lag_168h",
        "demand_roll_24h",
        "demand_roll_168h",
        "location_id",
    ]
    for c in ["is_weekend", "is_holiday", "is_rush_hour", "is_rain", "is_snow"]:
        lags[c] = lags[c].astype(int)
        if c in city.columns:
            city[c] = city[c].astype(int)

    model_df = lags.dropna(subset=["demand_lag_1h", "demand_lag_24h", "trips"])
    train, valid, test = _split(model_df)
    X_cols = feat
    y_col = "trips"

    def fit_lgb(tr, va):
        ds_tr = lgb.Dataset(tr[X_cols], label=tr[y_col])
        ds_va = lgb.Dataset(va[X_cols], label=va[y_col], reference=ds_tr)
        params = {
            "objective": "regression",
            "metric": "mae",
            "learning_rate": 0.05,
            "num_leaves": 31,
            "min_data_in_leaf": 40,
            "verbosity": -1,
            "seed": RANDOM_SEED,
            "feature_fraction": 0.9,
        }
        return lgb.train(
            params,
            ds_tr,
            num_boost_round=400,
            valid_sets=[ds_va],
            callbacks=[lgb.early_stopping(30), lgb.log_evaluation(0)],
        )

    booster = fit_lgb(train, valid if len(valid) else train)
    test = test.copy()
    test["pred_lgb"] = booster.predict(test[X_cols])
    # Baselines on test using lags (no leakage: lag columns are historical)
    test["pred_naive_168"] = test["demand_lag_168h"].fillna(test["demand_lag_24h"])
    test["pred_ma"] = test["demand_roll_24h"].fillna(test["demand_lag_1h"])

    zone_metrics = {
        "lightgbm": _metrics(test[y_col], test["pred_lgb"]),
        "seasonal_naive_168h": _metrics(test[y_col], test["pred_naive_168"]),
        "moving_average_24h": _metrics(test[y_col], test["pred_ma"]),
        "n_test_rows": int(len(test)),
        "n_train_rows": int(len(train)),
        "n_valid_rows": int(len(valid)),
        "n_zones": int(test["location_id"].nunique()),
    }

    # Citywide
    city = city.sort_values("hour_ts")
    city["demand_lag_1h"] = city["trips"].shift(1)
    city["demand_lag_24h"] = city["trips"].shift(24)
    city["demand_lag_168h"] = city["trips"].shift(168)
    city["demand_roll_24h"] = city["trips"].shift(1).rolling(24).mean()
    city["demand_roll_168h"] = city["trips"].shift(1).rolling(168).mean()
    city["location_id"] = 0
    city_m = city.dropna(subset=["demand_lag_1h", "demand_lag_24h", "trips"])
    ctr, cva, cte = _split(city_m)
    cboost = fit_lgb(ctr, cva if len(cva) else ctr)
    cte = cte.copy()
    cte["pred_lgb"] = cboost.predict(cte[X_cols])
    cte["pred_naive_168"] = cte["demand_lag_168h"]
    cte["pred_ma"] = cte["demand_roll_24h"]
    city_metrics = {
        "lightgbm": _metrics(cte[y_col], cte["pred_lgb"]),
        "seasonal_naive_168h": _metrics(cte[y_col], cte["pred_naive_168"]),
        "moving_average_24h": _metrics(cte[y_col], cte["pred_ma"]),
        "n_test_rows": int(len(cte)),
    }

    imp = pd.DataFrame(
        {"feature": X_cols, "importance": booster.feature_importance(importance_type="gain")}
    ).sort_values("importance", ascending=False)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(imp["feature"][::-1], imp["importance"][::-1], color="#1F4E79")
    ax.set_title("LightGBM gain importance for zone-hour demand")
    fig.tight_layout()
    fig.savefig(FIGURES / "forecast_feature_importance.png", dpi=140)
    plt.close(fig)

    resid = test[y_col] - test["pred_lgb"]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(resid, bins=40, color="#5B9BD5", edgecolor="white")
    ax.set_title(
        f"Zone-hour LightGBM residuals (test MAE={zone_metrics['lightgbm']['mae']:.2f})"
    )
    fig.tight_layout()
    fig.savefig(FIGURES / "forecast_residuals.png", dpi=140)
    plt.close(fig)

    # Save forecast fact
    fc = test[["location_id", "hour_ts", "trips", "pred_lgb", "pred_naive_168", "pred_ma"]].copy()
    fc["split"] = "test"
    fc_city = cte[["hour_ts", "trips", "pred_lgb", "pred_naive_168", "pred_ma"]].copy()
    fc_city["location_id"] = 0
    fc_city["split"] = "test_city"
    all_fc = pd.concat([fc, fc_city], ignore_index=True)
    con = connect()
    con.execute("DROP TABLE IF EXISTS fact_forecast")
    con.register("fc", all_fc)
    con.execute("CREATE TABLE fact_forecast AS SELECT * FROM fc")
    con.close()

    payload = {
        "zone_top50": zone_metrics,
        "citywide": city_metrics,
        "feature_importance": imp.to_dict(orient="records"),
        "split": {"train_end": TRAIN_END, "valid_end": VALID_END, "test_start": TEST_START},
    }
    (REPORTS / "forecast_metrics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info("Forecast zone LGB MAE=%.3f WAPE=%.2f", zone_metrics["lightgbm"]["mae"], zone_metrics["lightgbm"]["wape"])
    return payload
