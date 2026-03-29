"""
FinIntelligence Market Analysis System — main entry point.

Bootstraps the logger, ensures data directories exist, starts the APScheduler
background scheduler, and blocks until interrupted.

Requirements: 9.1, 9.2, 9.3, 9.4
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from datetime import datetime, timezone

from finintelligence.config import (
    INSTITUTIONAL_DIR,
    MARKET_DIR,
    SECTOR_DIR,
    SENTIMENT_DIR,
)
from finintelligence.logger import get_logger
from finintelligence.scheduler import build_scheduler

_VERSION = "1.0.0"


def main() -> None:
    """
    Entry point for the FinIntelligence Market Analysis System.

    1. Bootstrap logger.
    2. Log startup message with version and UTC timestamp.
    3. Ensure all data directories exist.
    4. Build and start the APScheduler background scheduler.
    5. Block in a loop until KeyboardInterrupt or fatal exception.
    """
    logger = get_logger("finintelligence.main")

    startup_ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    logger.info("FinIntelligence Market Analysis System v%s starting — %s", _VERSION, startup_ts)

    # Ensure all data directories exist
    for directory in (MARKET_DIR, SECTOR_DIR, INSTITUTIONAL_DIR, SENTIMENT_DIR):
        os.makedirs(directory, exist_ok=True)
    logger.info("Data directories verified")

    # Build and start the scheduler
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("Scheduler started — press Ctrl+C to stop")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped gracefully")
        sys.exit(0)
    except Exception:
        logger.error(
            "Fatal exception in main loop:\n%s",
            traceback.format_exc(),
        )
        scheduler.shutdown(wait=False)
        raise


if __name__ == "__main__":
    main()
