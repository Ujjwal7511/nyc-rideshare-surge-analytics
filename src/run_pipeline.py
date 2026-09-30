"""End-to-end pipeline orchestrator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `python -m src.run_pipeline` from repo root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import FIGURES, METRICS_JSON, REPORTS  # noqa: E402
from src.logging_utils import get_logger  # noqa: E402

log = get_logger(__name__)


def main(stop_after: str | None = None) -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    metrics: dict = {}

    from src import ingest

    metrics["ingest"] = ingest.run()
    if stop_after == "ingest":
        _dump(metrics)
        return metrics

    from src import clean

    metrics["clean"] = clean.run()
    if stop_after == "clean":
        _dump(metrics)
        return metrics

    from src import features

    metrics["features"] = features.run()
    if stop_after == "features":
        _dump(metrics)
        return metrics

    from src import aggregate

    metrics["aggregate"] = aggregate.run()
    if stop_after == "aggregate":
        _dump(metrics)
        return metrics

    from src import eda

    metrics["eda"] = eda.run()
    if stop_after == "eda":
        _dump(metrics)
        return metrics

    from src import stats_tests

    metrics["stats"] = stats_tests.run()
    if stop_after == "stats":
        _dump(metrics)
        return metrics

    from src import forecast

    metrics["forecast"] = forecast.run()
    if stop_after == "forecast":
        _dump(metrics)
        return metrics

    from src import reposition

    metrics["reposition"] = reposition.run()
    if stop_after == "reposition":
        _dump(metrics)
        return metrics

    from src import export_powerbi

    metrics["powerbi"] = export_powerbi.run()

    from src import write_docs

    write_docs.run(metrics)
    _dump(metrics)
    log.info("Pipeline complete")
    return metrics


def _dump(metrics: dict) -> None:
    METRICS_JSON.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--stop-after", default=None)
    args = p.parse_args()
    main(args.stop_after)
