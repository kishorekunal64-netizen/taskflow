"""
scheduler.py - Automated RAGAI video generation scheduler.

Reads topics from topics_queue.json, runs RAGAI CLI for each topic,
manages job state via JobManager, and integrates crash recovery.

Usage:
    python scheduler.py                  # run continuously
    python scheduler.py --interval 120   # 120s between jobs
    python scheduler.py --once           # run one job and exit
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from job_manager import JobManager, TOPICS_QUEUE_FILE, STATUS_COMPLETED
from editor_config import load_editor_config
from log_setup import configure_logging

logger = logging.getLogger("scheduler")

LOCK_FILENAME = "generation.lock"


def _load_queue() -> list:
    from job_manager import _load_json
    return _load_json(TOPICS_QUEUE_FILE, [])


def _save_queue(queue: list) -> None:
    from job_manager import _save_json
    _save_json(TOPICS_QUEUE_FILE, queue)


def _next_output_folder(output_dir: Path) -> str:
    """Generate a unique output folder name: video_YYYYMMDD_NNN."""
    date_str = datetime.now().strftime("%Y%m%d")
    existing = [
        d.name for d in output_dir.iterdir()
        if d.is_dir() and d.name.startswith(f"video_{date_str}_")
    ] if output_dir.exists() else []
    idx = len(existing) + 1
    return f"video_{date_str}_{idx:03d}"


class Scheduler:
    """Runs RAGAI generation jobs from the topic queue."""

    def __init__(
        self,
        output_dir: Path,
        interval_seconds: int = 300,
        job_manager: JobManager = None,
    ):
        self._output_dir = Path(output_dir)
        self._interval   = interval_seconds
        self._jm         = job_manager or JobManager(output_dir=self._output_dir)
        self._stop       = threading.Event()

    def run_once(self) -> bool:
        """
        Pop one topic from the queue, run RAGAI, manage job state.
        Returns True if a job was processed, False if queue was empty.
        """
        self._jm.ping_scheduler()

        queue = _load_queue()
        if not queue:
            logger.info("Topic queue empty — nothing to do")
            return False

        topic = queue.pop(0)
        _save_queue(queue)
        logger.info("Dequeued topic: %s (%d remaining)", topic, len(queue))

        output_folder = _next_output_folder(self._output_dir)
        job_id = self._jm.create_job(topic)
        self._jm.mark_processing(job_id, output_folder)
        self._jm.write_lock(output_folder)

        success = False
        try:
            success = self._run_ragai(topic, output_folder)
        except Exception as exc:
            logger.error("RAGAI run raised exception: %s", exc)
            self._jm.mark_failed(job_id, str(exc))
        finally:
            self._jm.remove_lock(output_folder)

        if success:
            valid = self._jm.mark_completed(job_id, output_folder)
            if not valid:
                logger.warning("Output verification failed for job %s — requeueing", job_id[:8])
                self._jm._requeue_topic(topic)
        else:
            self._jm.mark_failed(job_id, "RAGAI process returned non-zero exit code")
            logger.warning("Job failed — requeueing topic: %s", topic)
            self._jm._requeue_topic(topic)

        self._jm.print_stats()
        return True

    def run_continuous(self) -> None:
        """Run jobs continuously until stopped or queue exhausted."""
        logger.info("Scheduler started (interval=%ds)", self._interval)
        while not self._stop.is_set():
            self._jm.ping_scheduler()
            had_work = self.run_once()
            if not had_work:
                logger.info("Queue empty — sleeping %ds before retry", self._interval)
            else:
                logger.info("Job done — waiting %ds before next job", self._interval)
            self._stop.wait(timeout=self._interval)
        logger.info("Scheduler stopped")

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------
    # RAGAI invocation
    # ------------------------------------------------------------------

    def _run_ragai(self, topic: str, output_folder: str) -> bool:
        """
        Invoke RAGAI CLI as a subprocess.
        Output folder is passed via --output-dir so files land in the right place.
        Returns True on success (exit code 0).
        """
        output_path = self._output_dir / output_folder
        output_path.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable, "ragai.py",
            "--cli",
            "--topic", topic,
            "--output-dir", str(output_path),
        ]
        logger.info("Running RAGAI: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                timeout=3600,   # 1 hour max per job
                text=True,
            )
            if result.returncode == 0:
                logger.info("RAGAI completed successfully for: %s", topic)
                return True
            else:
                logger.error("RAGAI exited %d for topic: %s", result.returncode, topic)
                return False
        except subprocess.TimeoutExpired:
            logger.error("RAGAI timed out (>60min) for topic: %s", topic)
            return False
        except FileNotFoundError:
            logger.error("ragai.py not found — is scheduler running from project root?")
            return False


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    configure_logging()

    parser = argparse.ArgumentParser(description="RAGAI Scheduler")
    parser.add_argument("--interval", type=int, default=300,
                        help="Seconds between jobs (default: 300)")
    parser.add_argument("--once", action="store_true",
                        help="Run one job and exit")
    parser.add_argument("--recover-only", action="store_true",
                        help="Run crash recovery only, then exit")
    args = parser.parse_args()

    cfg        = load_editor_config()
    output_dir = Path(cfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    jm = JobManager(
        output_dir=output_dir,
        on_requeue=lambda t: logger.info("Requeued: %s", t),
        on_health_warning=lambda w: logger.warning("HEALTH WARNING: %s", w),
    )

    # Always run crash recovery on startup
    recovered = jm.startup_recovery()
    if recovered:
        logger.info("Recovered %d interrupted job(s)", recovered)

    if args.recover_only:
        jm.print_stats()
        return

    scheduler = Scheduler(
        output_dir=output_dir,
        interval_seconds=args.interval,
        job_manager=jm,
    )

    # Start health monitor
    jm.start_health_monitor(interval_seconds=60)

    try:
        if args.once:
            scheduler.run_once()
        else:
            scheduler.run_continuous()
    except KeyboardInterrupt:
        logger.info("Scheduler interrupted by user")
    finally:
        jm.stop_health_monitor()
        jm.print_stats()


if __name__ == "__main__":
    main()