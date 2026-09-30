"""Hypothesis tests and A/B-style repositioning simulation."""

from __future__ import annotations

import json
from math import sqrt

import numpy as np
import pandas as pd
from scipy import stats

from src.config import FIGURES, RANDOM_SEED, REPORTS
from src.db import connect
from src.logging_utils import get_logger

log = get_logger(__name__)


def _cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return float("nan")
    va, vb = a.var(ddof=1), b.var(ddof=1)
    sp = sqrt(((na - 1) * va + (nb - 1) * vb) / (na + nb - 2))
    return float((a.mean() - b.mean()) / sp) if sp else 0.0


def _mean_ci(x: np.ndarray, alpha: float = 0.05) -> tuple[float, float]:
    n = len(x)
    if n < 2:
        return (float("nan"), float("nan"))
    se = x.std(ddof=1) / sqrt(n)
    t = stats.t.ppf(1 - alpha / 2, n - 1)
    m = x.mean()
    return float(m - t * se), float(m + t * se)


def _mw_or_ttest(a: np.ndarray, b: np.ndarray) -> dict:
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    rng_cap = np.random.default_rng(RANDOM_SEED)
    if len(a) > 15000:
        a = rng_cap.choice(a, 15000, replace=False)
    if len(b) > 15000:
        b = rng_cap.choice(b, 15000, replace=False)
    # Shapiro on sample for normality gate
    def normalish(x):
        if len(x) < 30:
            return False
        s = x if len(x) <= 2000 else np.random.default_rng(RANDOM_SEED).choice(x, 2000, False)
        return stats.shapiro(s).pvalue > 0.05 if len(s) <= 5000 else True

    use_t = normalish(a) and normalish(b)
    if use_t:
        res = stats.ttest_ind(a, b, equal_var=False)
        name = "welch_t"
    else:
        res = stats.mannwhitneyu(a, b, alternative="two-sided")
        name = "mannwhitney_u"
    d = _cohens_d(a, b)
    diff = float(a.mean() - b.mean())
    # CI on difference via bootstrap
    rng = np.random.default_rng(RANDOM_SEED)
    boots = []
    for _ in range(400):
        boots.append(rng.choice(a, len(a), True).mean() - rng.choice(b, len(b), True).mean())
    ci = (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5)))
    return {
        "test": name,
        "pvalue": float(res.pvalue),
        "statistic": float(res.statistic),
        "mean_a": float(a.mean()),
        "mean_b": float(b.mean()),
        "diff": diff,
        "cohens_d": d,
        "ci_diff_95": ci,
        "n_a": int(len(a)),
        "n_b": int(len(b)),
    }


def _power_two_sample(effect_d: float, n: int, alpha: float = 0.05) -> float:
    """Approximate power for two-sample z-test given Cohen's d and n per arm."""
    if n <= 0 or np.isnan(effect_d):
        return float("nan")
    se = sqrt(2 / n)
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z = abs(effect_d) / se
    return float(stats.norm.sf(z_alpha - z) + stats.norm.cdf(-z_alpha - z))


def run() -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    con = connect()
    city = con.execute("SELECT * FROM agg_city_hour").df()
    trips = con.execute(
        """
        SELECT is_weekend, revenue_per_trip, is_holiday, borough, is_rain
        FROM fact_zone_hour
        WHERE revenue_per_trip IS NOT NULL
        """
    ).df()
    con.close()

    rain = city.loc[city["is_rain"] == True, "trips"].to_numpy(float)  # noqa: E712
    dry = city.loc[city["is_rain"] == False, "trips"].to_numpy(float)  # noqa: E712
    rain_test = _mw_or_ttest(rain, dry)

    wd = trips.loc[trips["is_weekend"] == False, "revenue_per_trip"].to_numpy(float)  # noqa: E712
    we = trips.loc[trips["is_weekend"] == True, "revenue_per_trip"].to_numpy(float)  # noqa: E712
    weekend_test = _mw_or_ttest(we, wd)

    hol = trips.loc[trips["is_holiday"] == True, "revenue_per_trip"].to_numpy(float)  # noqa: E712
    non = trips.loc[trips["is_holiday"] == False, "revenue_per_trip"].to_numpy(float)  # noqa: E712
    holiday_test = _mw_or_ttest(hol, non) if len(hol) > 10 else {"pvalue": None, "note": "too few holiday rows"}

    groups = [
        g["revenue_per_trip"].dropna().to_numpy(float)
        for _, g in trips.groupby("borough")
        if len(g) > 20
    ]
    labels = [b for b, g in trips.groupby("borough") if len(g) > 20]
    if len(groups) >= 2:
        try:
            anova = stats.f_oneway(*groups)
            kruskal = stats.kruskal(*groups)
            borough_test = {
                "anova_p": float(anova.pvalue),
                "kruskal_p": float(kruskal.pvalue),
                "boroughs": labels,
            }
        except Exception as exc:  # noqa: BLE001
            borough_test = {"error": str(exc)}
    else:
        borough_test = {"note": "insufficient borough groups"}

    # A/B simulation: extra drivers in high-wait zones vs control
    rng = np.random.default_rng(RANDOM_SEED)
    n_hours = 400
    control = rng.poisson(lam=12, size=n_hours)
    # treatment: +0.8 trips on average (repositioning)
    treatment = rng.poisson(lam=12.8, size=n_hours)
    ab = _mw_or_ttest(treatment.astype(float), control.astype(float))
    n_per = 200
    # sample size for 80% power, d from observed
    d = abs(ab["cohens_d"]) if ab.get("cohens_d") else 0.2
    # iterate n
    n80 = None
    for n in range(30, 5000):
        if _power_two_sample(d, n) >= 0.8:
            n80 = n
            break
    ab["n_per_arm"] = n_per
    ab["power_at_n200"] = _power_two_sample(d, n_per)
    ab["n_for_80pct_power"] = n80
    ab["assumed_treatment_lambda"] = 12.8
    ab["assumed_control_lambda"] = 12.0

    results = {
        "rain_vs_dry_hourly_demand": rain_test,
        "weekend_vs_weekday_revenue_per_trip": weekend_test,
        "holiday_vs_nonholiday_revenue_per_trip": holiday_test,
        "borough_revenue_per_trip": borough_test,
        "reposition_ab_simulation": ab,
        "plain_english": {
            "rain": (
                f"Hourly citywide trips on rain hours averaged {rain_test['mean_a']:.1f} vs "
                f"{rain_test['mean_b']:.1f} dry ({rain_test['test']}, p={rain_test['pvalue']:.4g}, "
                f"Cohen's d={rain_test['cohens_d']:.3f})."
            ),
            "weekend": (
                f"Weekend revenue/trip {weekend_test['mean_a']:.2f} vs weekday {weekend_test['mean_b']:.2f} "
                f"(p={weekend_test['pvalue']:.4g})."
            ),
            "holiday": (
                "Holiday vs non-holiday revenue per trip: "
                + (
                    f"p={holiday_test.get('pvalue')}"
                    if holiday_test.get("pvalue") is not None
                    else holiday_test.get("note", "")
                )
            ),
            "ab": (
                f"Simulated repositioning (+0.8 trips/hour mean) vs control: p={ab['pvalue']:.4g}, "
                f"need ~{n80} zone-hours per arm for 80% power at observed effect."
            ),
        },
    }
    out = REPORTS / "stats_tests.json"
    out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    md = ["# Statistical tests", ""]
    for k, v in results["plain_english"].items():
        md.append(f"- **{k}**: {v}")
    (REPORTS / "stats_tests.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    log.info("Wrote stats tests")
    return results
