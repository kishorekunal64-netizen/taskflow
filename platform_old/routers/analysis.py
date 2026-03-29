"""Analysis trigger endpoint — admin and analyst roles only."""

import dataclasses
import logging
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from platform.result_cache import cache
from platform.monitoring import alert_manager

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_analyst_or_admin(request: Request):
    role = getattr(request.state, "role", None)
    if role not in ("admin", "analyst"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")


def _run_analysis_background() -> None:
    try:
        from finintelligence import cache_manager as engine_cache
        from finintelligence.ai_analysis_engine import generate_signal
        from finintelligence.sentiment_engine import compute_sentiment

        sector_df = engine_cache.read_sector_metrics()
        flows_df = engine_cache.read_institutional_flows()
        sentiment = compute_sentiment()

        candles: dict = {}
        for symbol in ["^NSEI", "^NSEBANK"]:
            df_1d = engine_cache.read_candles(symbol, "1D")
            df_4h = engine_cache.read_candles(symbol, "4H")
            candles[symbol] = {}
            if not df_1d.empty:
                candles[symbol]["1D"] = df_1d
            if not df_4h.empty:
                candles[symbol]["4H"] = df_4h

        if not candles or sentiment is None:
            logger.warning("analysis_trigger: insufficient data")
            return

        signal = generate_signal(candles, sector_df, sentiment, flows_df)
        if signal is not None:
            cache.set("ai_signals", dataclasses.asdict(signal))
            logger.info("analysis_trigger: ai_signals cache updated")
            logger.info("scheduler_event: analysis_trigger_run completed")

    except Exception as exc:
        logger.error("analysis_trigger: background run failed: %s", exc)
        alert_manager.record("ai_analysis_failures")


@router.post("/analysis/run", dependencies=[Depends(_require_analyst_or_admin)])
def trigger_analysis():
    """Trigger AI analysis engine asynchronously. Results stored in result cache."""
    now = datetime.now(tz=timezone.utc).isoformat()
    threading.Thread(target=_run_analysis_background, daemon=True).start()
    return {"analysis_triggered": True, "timestamp": now, "status": "queued"}
