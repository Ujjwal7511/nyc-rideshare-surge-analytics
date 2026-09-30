#!/usr/bin/env python
"""Pipeline runner with file logging."""
import sys
import logging
from pathlib import Path

# Setup file logging
log_file = Path("pipeline_run.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

log = logging.getLogger(__name__)
log.info("Starting pipeline...")

try:
    from src.run_pipeline import main
    result = main()
    log.info(f"Pipeline completed: {result}")
except Exception as e:
    log.exception(f"Pipeline failed: {e}")
    sys.exit(1)
