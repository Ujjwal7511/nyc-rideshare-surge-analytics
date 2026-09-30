"""Lightweight unit tests that do not need the warehouse."""

from src.forecast import _metrics
import numpy as np

from src.reposition import _allocate
import pandas as pd


def test_metrics_perfect_forecast():
    y = np.array([1.0, 2.0, 3.0])
    m = _metrics(y, y)
    assert m["mae"] == 0
    assert m["wape"] == 0


def test_allocate_respects_x_and_cap():
    df = pd.DataFrame(
        {
            "location_id": [1, 2, 3],
            "zone_name": ["a", "b", "c"],
            "borough": ["Manhattan"] * 3,
            "hour_ts": pd.Timestamp("2024-03-16") ,
            "expected_demand": [20, 10, 5],
            "supply_proxy": [5, 5, 5],
            "gap": [40, 20, 1],
            "revenue_per_trip": [20.0, 15.0, 10.0],
        }
    )
    rec = _allocate(df, x_drivers=20, max_per_zone=15)
    assert rec["drivers_sent"].sum() <= 20
    assert rec["drivers_sent"].max() <= 15
