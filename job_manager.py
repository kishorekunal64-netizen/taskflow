"""
job_manager.py - Job State Manager and Crash Recovery System for RAGAI.

Responsibilities:
  - Track every generation job in jobs_state.json
  - Manage job lifecycle: pending -> processing -> completed / failed
  - Crash recovery: on startup, detect interrupted jobs and requeue them
  - File lock: write/remove generation.lock inside each output folder
  - Health monitor: periodic checks on scheduler, queue, watcher
  - Dedicated log: logs/job_manager.log

Job structure (jobs_state.json entry):
  {
    "job_id":        "uuid4 hex",
    "topic":         "Village girl becomes IAS officer",
    "status":        "pending | processing | completed | failed",
    "started_at":    "ISO timestamp or null",
    "completed_at":  "ISO timestamp or null",
    "output_folder": "video_20260324_001 or null",
    "error":         "error message or null",
    "retries":       0
  }
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("job_manager")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

JOBS_STATE_FILE  = Path("jobs_state.json")
TOPICS_QUEUE_FILE = Path("topics_queue.json")
LOCK_FILENAME    = "generation.lock"
MIN_VIDEO_BYTES  = 100_000   # 100 KB minimum to consider a video valid

# ---------------------------------------------------------------------------
# Job statuses
# ---------------------------------------------------------------------------

STATUS_PENDING    = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED  = "completed"
STATUS_FAILED     = "failed"

MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not load %s: %s", path, exc)
    return default


def _save_json(path: Path, data) -> None:
    try:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.error("Could not save %s: %s", path, exc)


# ---------------------------------------------------------------------------
# Job Manager
# ---------------------------------------------------------------------------

class JobManager:
    """
    Thread-safe job state manager with crash recovery and health monitoring.

    Usage:
        jm = JobManager(output_dir=Path("output"))
        jm.startup_recovery()          # call once at startup
        job_id = jm.create_job(topic)  # before starting generation
        jm.mark_processing(job_id, output_folder)
        jm.write_lock(output_folder)
        # ... run RAGAI ...
        jm.mark_completed(job_id, output_folder)
        jm.remove_lock(output_folder)
    """

    def __init__(
        self,
        output_dir: Path = Path("output"),
        on_requeue: Optional[Callable[[str], None]] = None,
        on_health_warning: Optional[Callable[[str], None]] = None,
    ):
        self._output_dir       = Path(output_dir)
        self._on_requeue       = on_requeue        # called with topic when job is requeued
        self._on_health_warn   = on_health_warning # called with warning message
        self._lock             = threading.Lock()
        self._jobs: Dict[str, dict] = {}
        self._health_thread: Optional[threading.Thread] = None
        self._health_stop      = threading.Event()
        self._scheduler_alive  = threading.Event()
        self._watcher_alive    = threading.Event()

        self._setup_log()
        self._load_jobs()

    # ------------------------------------------------------------------
    # Logging setup
    # ------------------------------------------------------------------

    def _setup_log(self):
        Path("logs").mkdir(exist_ok=True)
        fh = logging.FileHandler("logs/job_manager.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-8s  %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        ))
        fh.setLevel(logging.DEBUG)
        logger.addHandler(fh)
        logger.setLevel(logging.DEBUG)
        logger.info("JobManager initialised")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_jobs(self):
        data = _load_json(JOBS_STATE_FILE, {})
        with self._lock:
            self._jobs = data
        logger.info("Loaded %d jobs from %s", len(data), JOBS_STATE_FILE)

    def _save_jobs(self):
        """Must be called with self._lock held."""
        _save_json(JOBS_STATE_FILE, self._jobs)

    # ------------------------------------------------------------------
    # Job lifecycle
    # ------------------------------------------------------------------

    def create_job(self, topic: str) -> str:
        """Create a new pending job. Returns job_id."""
        job_id = uuid4().hex
        entry = {
            "job_id":        job_id,
            "topic":         topic,
            "status":        STATUS_PENDING,
            "started_at":    None,
            "completed_at":  None,
            "output_folder": None,
            "error":         None,
            "retries":       0,
        }
        with self._lock:
            self._jobs[job_id] = entry
            self._save_jobs()
        logger.info("Job created: %s | topic=%s", job_id[:8], topic)
        return job_id

    def mark_processing(self, job_id: str, output_folder: str) -> None:
        """Transition job to processing state."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                logger.warning("mark_processing: unknown job %s", job_id[:8])
                return
            job["status"]        = STATUS_PROCESSING
            job["started_at"]    = _now_iso()
            job["output_folder"] = output_folder
            job["error"]         = None
            self._save_jobs()
        logger.info("Job processing: %s | folder=%s", job_id[:8], output_folder)

    def mark_completed(self, job_id: str, output_folder: str) -> bool:
        """
        Verify output is valid, then mark completed.
        Returns True if valid, False if output is missing/incomplete.
        """
        valid, reason = self._verify_output(output_folder)
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            if valid:
                job["status"]       = STATUS_COMPLETED
                job["completed_at"] = _now_iso()
                job["error"]        = None
                logger.info("Job completed: %s | folder=%s", job_id[:8], output_folder)
            else:
                job["status"] = STATUS_FAILED
                job["error"]  = reason
                logger.warning("Job failed verification: %s | %s", job_id[:8], reason)
            self._save_jobs()
        return valid

    def mark_failed(self, job_id: str, error: str = "") -> None:
        """Explicitly mark a job as failed."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["status"] = STATUS_FAILED
            job["error"]  = error
            self._save_jobs()
        logger.warning("Job failed: %s | %s", job_id[:8], error)

    def get_job(self, job_id: str) -> Optional[dict]:
        with self._lock:
            return dict(self._jobs[job_id]) if job_id in self._jobs else None

    def get_all_jobs(self) -> List[dict]:
        with self._lock:
            return [dict(j) for j in self._jobs.values()]

    def get_jobs_by_status(self, status: str) -> List[dict]:
        with self._lock:
            return [dict(j) for j in self._jobs.values() if j["status"] == status]

    # ------------------------------------------------------------------
    # File lock
    # ------------------------------------------------------------------

    def write_lock(self, output_folder: str) -> Path:
        """Write generation.lock inside the output folder. Returns lock path."""
        folder = self._output_dir / output_folder
        folder.mkdir(parents=True, exist_ok=True)
        lock_path = folder / LOCK_FILENAME
        lock_path.write_text(
            json.dumps({"locked_at": _now_iso(), "pid": os.getpid()}),
            encoding="utf-8",
        )
        logger.debug("Lock written: %s", lock_path)
        return lock_path

    def remove_lock(self, output_folder: str) -> None:
        """Remove generation.lock from the output folder."""
        lock_path = self._output_dir / output_folder / LOCK_FILENAME
        try:
            if lock_path.exists():
                lock_path.unlink()
                logger.debug("Lock removed: %s", lock_path)
        except Exception as exc:
            logger.warning("Could not remove lock %s: %s", lock_path, exc)

    @staticmethod
    def folder_is_locked(folder_path: Path) -> bool:
        """Return True if the folder contains a generation.lock file."""
        return (folder_path / LOCK_FILENAME).exists()

    # ------------------------------------------------------------------
    # Output verification
    # ------------------------------------------------------------------

    def _verify_output(self, output_folder: str) -> tuple[bool, str]:
        """
        Check that output_folder contains a valid video.mp4.
        Returns (is_valid, reason_string).
        """
        folder = self._output_dir / output_folder
        if not folder.exists():
            return False, f"Output folder missing: {folder}"

        # Find video file — either video.mp4 or any *.mp4
        video_path = folder / "video.mp4"
        if not video_path.exists():
            mp4s = list(folder.glob("*.mp4"))
            if not mp4s:
                return False, f"No .mp4 found in {folder}"
            video_path = mp4s[0]

        size = video_path.stat().st_size
        if size < MIN_VIDEO_BYTES:
            return False, f"video.mp4 too small ({size} bytes < {MIN_VIDEO_BYTES})"

        # Check file is stable (not still being written)
        time.sleep(0.5)
        size2 = video_path.stat().st_size
        if size2 != size:
            return False, "video.mp4 size still changing — not stable"

        return True, "ok"

    # ------------------------------------------------------------------
    # Crash recovery
    # ------------------------------------------------------------------

    def startup_recovery(self) -> int:
        """
        Called once at scheduler startup.
        Scans jobs_state.json for interrupted (processing) jobs.
        Verifies their output; requeues failed ones.
        Returns number of jobs recovered.
        """
        logger.info("Running startup crash recovery...")
        recovered = 0

        with self._lock:
            processing_jobs = [
                dict(j) for j in self._jobs.values()
                if j["status"] == STATUS_PROCESSING
            ]

        for job in processing_jobs:
            job_id  = job["job_id"]
            topic   = job["topic"]
            folder  = job.get("output_folder") or ""

            logger.warning("Found interrupted job: %s | topic=%s | folder=%s",
                           job_id[:8], topic, folder)

            valid = False
            if folder:
                valid, reason = self._verify_output(folder)
                if valid:
                    # Output is actually complete — mark as completed
                    with self._lock:
                        self._jobs[job_id]["status"]       = STATUS_COMPLETED
                        self._jobs[job_id]["completed_at"] = _now_iso()
                        self._jobs[job_id]["error"]        = None
                        self._save_jobs()
                    logger.info("Recovery: job %s output valid — marked completed", job_id[:8])
                    # Remove stale lock if present
                    self.remove_lock(folder)
                    continue

            # Output missing or incomplete — mark failed and requeue
            with self._lock:
                retries = self._jobs[job_id].get("retries", 0)
                if retries < MAX_RETRIES:
                    self._jobs[job_id]["status"]  = STATUS_FAILED
                    self._jobs[job_id]["error"]   = "Interrupted — requeued for retry"
                    self._jobs[job_id]["retries"] = retries + 1
                    self._save_jobs()
                    logger.info("Recovery: requeuing topic '%s' (retry %d/%d)",
                                topic, retries + 1, MAX_RETRIES)
                    if self._on_requeue:
                        self._on_requeue(topic)
                    self._requeue_topic(topic)
                    recovered += 1
                else:
                    self._jobs[job_id]["status"] = STATUS_FAILED
                    self._jobs[job_id]["error"]  = f"Max retries ({MAX_RETRIES}) exceeded"
                    self._save_jobs()
                    logger.error("Recovery: job %s exceeded max retries — abandoned", job_id[:8])

            # Clean up stale lock
            if folder:
                self.remove_lock(folder)

        logger.info("Crash recovery complete: %d job(s) requeued", recovered)
        return recovered

    def _requeue_topic(self, topic: str) -> None:
        """Prepend topic back to topics_queue.json for retry."""
        queue = _load_json(TOPICS_QUEUE_FILE, [])
        if topic not in queue:
            queue.insert(0, topic)   # prepend so it runs next
            _save_json(TOPICS_QUEUE_FILE, queue)
            logger.info("Topic requeued: %s", topic)

    # ------------------------------------------------------------------
    # Health monitor
    # ------------------------------------------------------------------

    def start_health_monitor(
        self,
        interval_seconds: int = 60,
        scheduler_heartbeat: Optional[threading.Event] = None,
        watcher_heartbeat: Optional[threading.Event] = None,
    ) -> None:
        """Start background health check thread."""
        self._scheduler_heartbeat = scheduler_heartbeat
        self._watcher_heartbeat   = watcher_heartbeat
        self._health_stop.clear()
        self._health_thread = threading.Thread(
            target=self._health_loop,
            args=(interval_seconds,),
            daemon=True,
            name="JobManager-Health",
        )
        self._health_thread.start()
        logger.info("Health monitor started (interval=%ds)", interval_seconds)

    def stop_health_monitor(self) -> None:
        self._health_stop.set()
        if self._health_thread:
            self._health_thread.join(timeout=5)

    def ping_scheduler(self) -> None:
        """Call from scheduler loop to signal it is alive."""
        self._scheduler_alive.set()

    def ping_watcher(self) -> None:
        """Call from watcher to signal it is alive."""
        self._watcher_alive.set()

    def _health_loop(self, interval: int) -> None:
        while not self._health_stop.wait(timeout=interval):
            self._run_health_checks()

    def _run_health_checks(self) -> None:
        warnings = []

        # Check scheduler heartbeat
        if not self._scheduler_alive.is_set():
            warnings.append("Scheduler heartbeat missing — scheduler may have stopped")
        else:
            self._scheduler_alive.clear()   # reset for next interval

        # Check watcher heartbeat
        if not self._watcher_alive.is_set():
            warnings.append("Watcher heartbeat missing — folder watcher may have stopped")
        else:
            self._watcher_alive.clear()

        # Check topic queue size
        queue = _load_json(TOPICS_QUEUE_FILE, [])
        if len(queue) == 0:
            warnings.append("Topic queue is empty — no topics left to generate")

        # Check for stuck processing jobs (running > 30 min)
        with self._lock:
            processing = [j for j in self._jobs.values()
                          if j["status"] == STATUS_PROCESSING]
        for job in processing:
            if job.get("started_at"):
                try:
                    started = datetime.fromisoformat(job["started_at"])
                    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                    if elapsed > 1800:   # 30 minutes
                        warnings.append(
                            f"Job {job['job_id'][:8]} ('{job['topic'][:30]}') "
                            f"has been processing for {int(elapsed/60)} min — possible hang"
                        )
                except Exception:
                    pass

        # Report
        if warnings:
            for w in warnings:
                logger.warning("HEALTH: %s", w)
                if self._on_health_warn:
                    self._on_health_warn(w)
        else:
            logger.debug("Health check OK — scheduler alive, watcher alive, queue has %d topics",
                         len(queue))

    # ------------------------------------------------------------------
    # Stats / reporting
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Return summary counts by status."""
        with self._lock:
            jobs = list(self._jobs.values())
        counts = {STATUS_PENDING: 0, STATUS_PROCESSING: 0,
                  STATUS_COMPLETED: 0, STATUS_FAILED: 0}
        for j in jobs:
            counts[j["status"]] = counts.get(j["status"], 0) + 1
        counts["total"] = len(jobs)
        return counts

    def print_stats(self) -> None:
        s = self.stats()
        logger.info(
            "Job stats — total=%d  pending=%d  processing=%d  completed=%d  failed=%d",
            s["total"], s[STATUS_PENDING], s[STATUS_PROCESSING],
            s[STATUS_COMPLETED], s[STATUS_FAILED],
        )