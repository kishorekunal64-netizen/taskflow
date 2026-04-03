"""
scheduler_v2.py — Overnight batch queue scheduler for RAGAI v9.0.

Extends scheduler.py with:
  - Background trend fetch thread (every 1 hour)
  - Quota awareness (Groq tokens + Leonardo credits)
  - Sleep until midnight IST when quota exhausted
  - Status written to tmp/scheduler_status.json (Web UI reads this)
  - Crash recovery preserved from v1
  - Flags: --once, --no-trends, --recover-only, --interval N
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_TOPICS_QUEUE = Path("topics_queue.json")
_STATUS_FILE = Path("tmp/scheduler_status.json")
_JOBS_STATE = Path("jobs_state.json")

# Conservative daily quota estimates (free tier)
_GROQ_DAILY_TOKENS = 500_000
_GROQ_TOKENS_PER_VIDEO = 50_000   # ~8 scenes × 6000 tokens
_LEONARDO_DAILY_CREDITS = 150
_LEONARDO_CREDITS_PER_VIDEO = 16  # 8 scenes × 2 credits

# IST = UTC+5:30
_IST_OFFSET = timedelta(hours=5, minutes=30)


def _now_ist() -> datetime:
    return datetime.now(timezone.utc) + _IST_OFFSET


def _seconds_until_midnight_ist() -> float:
    now = _now_ist()
    midnight = now.replace(hour=0, minute=5, second=0, microsecond=0) + timedelta(days=1)
    return (midnight - now).total_seconds()


# ---------------------------------------------------------------------------
# Quota tracker
# ---------------------------------------------------------------------------

class QuotaTracker:
    def __init__(self) -> None:
        self.groq_used = 0
        self.leonardo_used = 0
        self._reset_date = _now_ist().date()

    def _check_reset(self) -> None:
        today = _now_ist().date()
        if today != self._reset_date:
            logger.info("Quota reset — new day %s", today)
            self.groq_used = 0
            self.leonardo_used = 0
            self._reset_date = today

    def can_generate(self) -> bool:
        self._check_reset()
        groq_ok = (self.groq_used + _GROQ_TOKENS_PER_VIDEO) <= _GROQ_DAILY_TOKENS
        leo_ok = (self.leonardo_used + _LEONARDO_CREDITS_PER_VIDEO) <= _LEONARDO_DAILY_CREDITS
        return groq_ok and leo_ok

    def record_generation(self) -> None:
        self.groq_used += _GROQ_TOKENS_PER_VIDEO
        self.leonardo_used += _LEONARDO_CREDITS_PER_VIDEO
        logger.info("Quota used — Groq: %d/%d tokens, Leonardo: %d/%d credits",
                    self.groq_used, _GROQ_DAILY_TOKENS,
                    self.leonardo_used, _LEONARDO_DAILY_CREDITS)

    def summary(self) -> dict:
        return {
            "groq_used": self.groq_used,
            "groq_limit": _GROQ_DAILY_TOKENS,
            "leonardo_used": self.leonardo_used,
            "leonardo_limit": _LEONARDO_DAILY_CREDITS,
        }


# ---------------------------------------------------------------------------
# Status file
# ---------------------------------------------------------------------------

def _write_status(current_topic: str = "", running: bool = True,
                  quota: Optional[dict] = None) -> None:
    _STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "running": running,
        "current_topic": current_topic,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "quota": quota or {},
    }
    try:
        _STATUS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Topic queue helpers
# ---------------------------------------------------------------------------

def _pop_topic() -> Optional[str]:
    if not _TOPICS_QUEUE.exists():
        return None
    try:
        topics = json.loads(_TOPICS_QUEUE.read_text(encoding="utf-8"))
        if not topics:
            return None
        topic = topics.pop(0)
        _TOPICS_QUEUE.write_text(json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8")
        return topic
    except Exception as exc:
        logger.error("Failed to pop topic: %s", exc)
        return None


def _prepend_topic(topic: str) -> None:
    topics = []
    if _TOPICS_QUEUE.exists():
        try:
            topics = json.loads(_TOPICS_QUEUE.read_text(encoding="utf-8"))
        except Exception:
            pass
    topics.insert(0, topic)
    _TOPICS_QUEUE.write_text(json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8")


def _queue_size() -> int:
    if not _TOPICS_QUEUE.exists():
        return 0
    try:
        return len(json.loads(_TOPICS_QUEUE.read_text(encoding="utf-8")))
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Crash recovery
# ---------------------------------------------------------------------------

def _startup_recovery() -> None:
    if not _JOBS_STATE.exists():
        return
    try:
        jobs = json.loads(_JOBS_STATE.read_text(encoding="utf-8"))
    except Exception:
        return

    recovered = 0
    for job_id, job in jobs.items():
        if job.get("status") == "processing":
            folder = job.get("output_folder", "")
            video = Path("output") / folder / "video.mp4" if folder else None
            if video and video.exists() and video.stat().st_size > 100_000:
                job["status"] = "completed"
                logger.info("Recovery: job %s marked completed (video exists)", job_id[:8])
            else:
                job["status"] = "failed"
                topic = job.get("topic", "")
                if topic:
                    _prepend_topic(topic)
                    logger.info("Recovery: job %s failed — topic re-queued: %s", job_id[:8], topic)
            recovered += 1

    if recovered:
        _JOBS_STATE.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Startup recovery: %d interrupted jobs processed", recovered)


# ---------------------------------------------------------------------------
# Trend fetch thread
# ---------------------------------------------------------------------------

def _trend_fetch_loop(interval_seconds: int = 3600, stop_event: threading.Event = None) -> None:
    """Background thread: fetch trends every interval_seconds."""
    if stop_event is None:
        stop_event = threading.Event()
    while not stop_event.is_set():
        try:
            from trend_fetcher_v2 import fetch_and_queue
            new = fetch_and_queue()
            if new:
                logger.info("Trend fetch: %d new topics added to queue", len(new))
        except Exception as exc:
            logger.warning("Trend fetch failed: %s", exc)
        stop_event.wait(interval_seconds)


# ---------------------------------------------------------------------------
# Generate one video
# ---------------------------------------------------------------------------

def _generate_video(topic: str) -> bool:
    """Run ragai.py --cli for one topic. Returns True on success."""
    logger.info("Generating: %s", topic)
    cmd = [
        sys.executable, "ragai.py", "--cli",
        "--topic", topic,
        "--quality", "standard",  # overnight: standard quality for speed
        "--scenes", "8",
        "--language", "hi",
        "--format", "landscape",
    ]
    try:
        result = subprocess.run(cmd, timeout=1800, cwd=str(Path(__file__).parent))
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.error("Generation timed out for: %s", topic)
        return False
    except Exception as exc:
        logger.error("Generation error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Main scheduler loop
# ---------------------------------------------------------------------------

def run(
    interval: int = 300,
    once: bool = False,
    no_trends: bool = False,
    recover_only: bool = False,
) -> None:
    logger.info("RAGAI Scheduler v2 starting")
    _startup_recovery()

    if recover_only:
        logger.info("Recovery-only mode — exiting")
        return

    quota = QuotaTracker()
    stop_event = threading.Event()

    # Start background trend fetch thread
    if not no_trends:
        trend_thread = threading.Thread(
            target=_trend_fetch_loop,
            args=(3600, stop_event),
            daemon=True,
        )
        trend_thread.start()
        logger.info("Trend fetch thread started (every 1 hour)")

    _write_status(running=True, quota=quota.summary())

    try:
        while True:
            # Check quota
            if not quota.can_generate():
                secs = _seconds_until_midnight_ist()
                logger.info("Daily quota exhausted — sleeping %.0f seconds until midnight IST", secs)
                _write_status(current_topic="Quota exhausted — sleeping until midnight",
                              running=True, quota=quota.summary())
                time.sleep(min(secs, 3600))  # wake up every hour to re-check
                continue

            # Get next topic
            topic = _pop_topic()
            if not topic:
                logger.info("Queue empty — waiting %d seconds", interval)
                _write_status(current_topic="Queue empty", running=True, quota=quota.summary())
                time.sleep(interval)
                continue

            # Generate
            _write_status(current_topic=topic, running=True, quota=quota.summary())
            success = _generate_video(topic)

            if success:
                quota.record_generation()
                logger.info("✅ Done: %s", topic)
            else:
                logger.warning("❌ Failed: %s — re-queuing", topic)
                _prepend_topic(topic)

            if once:
                break

            logger.info("Cooldown %d seconds before next job", interval)
            time.sleep(interval)

    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")
    finally:
        stop_event.set()
        _write_status(running=False, quota=quota.summary())
        logger.info("Scheduler v2 stopped")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                Path("logs") / f"scheduler_{datetime.now().strftime('%Y%m%d')}.log",
                encoding="utf-8",
            ),
        ],
    )
    Path("logs").mkdir(exist_ok=True)

    parser = argparse.ArgumentParser(description="RAGAI Scheduler v2")
    parser.add_argument("--once", action="store_true", help="Process one topic and exit")
    parser.add_argument("--interval", type=int, default=300, help="Seconds between jobs")
    parser.add_argument("--no-trends", action="store_true", help="Disable background trend fetch")
    parser.add_argument("--recover-only", action="store_true", help="Run crash recovery and exit")
    args = parser.parse_args()

    run(
        interval=args.interval,
        once=args.once,
        no_trends=args.no_trends,
        recover_only=args.recover_only,
    )
