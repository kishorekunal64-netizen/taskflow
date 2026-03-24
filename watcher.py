"""
watcher.py — Auto Video Collector for RAGAI Editor.

Monitors ./output/ folder for new .mp4 files using watchdog.
Implements file-stability polling: only imports a file once its size
has been unchanged for 2 consecutive 500ms checks (prevents importing
in-progress RAGAI renders).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent
    _WATCHDOG_AVAILABLE = True
except ImportError:
    _WATCHDOG_AVAILABLE = False
    logger.warning("watchdog not installed — folder watching disabled")

try:
    from plyer import notification as _plyer_notification
    _PLYER_AVAILABLE = True
except ImportError:
    _PLYER_AVAILABLE = False


# ---------------------------------------------------------------------------
# File stability checker
# ---------------------------------------------------------------------------

class _StabilityChecker:
    """Polls a file until its size stops changing, then fires the callback."""

    def __init__(self, path: Path, on_stable: Callable[[Path], None], interval: float = 0.5, stable_count: int = 2):
        self._path = path
        self._on_stable = on_stable
        self._interval = interval
        self._stable_count = stable_count
        self._last_size: int = -1
        self._stable_hits: int = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while True:
            time.sleep(self._interval)
            try:
                size = self._path.stat().st_size
            except OSError:
                continue
            if size == self._last_size and size > 0:
                self._stable_hits += 1
                if self._stable_hits >= self._stable_count:
                    logger.info("File stable: %s (%d bytes)", self._path.name, size)
                    self._on_stable(self._path)
                    return
            else:
                self._stable_hits = 0
                self._last_size = size


# ---------------------------------------------------------------------------
# Watchdog event handler
# ---------------------------------------------------------------------------

class _OutputFolderHandler(FileSystemEventHandler if _WATCHDOG_AVAILABLE else object):

    def __init__(self, on_new_video: Callable[[Path], None]):
        if _WATCHDOG_AVAILABLE:
            super().__init__()
        self._on_new_video = on_new_video
        self._pending: Dict[str, _StabilityChecker] = {}

    def on_created(self, event):
        path = Path(event.src_path)
        if event.is_directory:
            logger.debug("New folder detected: %s", path.name)
            return
        if path.suffix.lower() != ".mp4":
            return
        # Ignore videos inside locked folders (generation still in progress)
        if (path.parent / "generation.lock").exists():
            logger.debug("Skipping locked folder: %s", path.parent.name)
            return
        logger.info("New file detected: %s — waiting for stability", path.name)
        self._pending[str(path)] = _StabilityChecker(path, self._on_stable)

    def _on_stable(self, path: Path):
        self._pending.pop(str(path), None)
        self._on_new_video(path)


# ---------------------------------------------------------------------------
# Public Watcher class
# ---------------------------------------------------------------------------

class OutputWatcher:
    """Watches ./output/ for new RAGAI .mp4 files and fires a callback."""

    def __init__(self, output_dir: Path, on_new_video: Callable[[Path], None]):
        self._output_dir = Path(output_dir)
        self._on_new_video = on_new_video
        self._observer: Optional[object] = None

    def start(self):
        if not _WATCHDOG_AVAILABLE:
            logger.warning("watchdog unavailable — auto-watch disabled")
            return
        self._output_dir.mkdir(parents=True, exist_ok=True)
        handler = _OutputFolderHandler(self._fire)
        self._observer = Observer()
        self._observer.schedule(handler, str(self._output_dir), recursive=False)
        self._observer.start()
        logger.info("Watching folder: %s", self._output_dir)

    def stop(self):
        if self._observer:
            self._observer.stop()
            self._observer.join()

    def scan_existing(self) -> list[Path]:
        """
        Return all existing .mp4 files in output_dir (sorted by mtime).
        Supports both flat layout (output/*.mp4) and folder layout
        (output/video_YYYYMMDD_NNN/video.mp4).
        Skips folders that contain a generation.lock file.
        """
        if not self._output_dir.exists():
            return []
        files: list[Path] = []
        # Flat files directly in output/
        files += [p for p in self._output_dir.glob("*.mp4") if p.is_file()]
        # Folder-based: output/<folder>/video.mp4
        for sub in self._output_dir.iterdir():
            if sub.is_dir():
                if (sub / "generation.lock").exists():
                    logger.debug("scan_existing: skipping locked folder %s", sub.name)
                    continue
                files += [p for p in sub.glob("*.mp4") if p.is_file()]
        files = sorted(files, key=lambda p: p.stat().st_mtime)
        logger.info("Found %d existing videos in %s", len(files), self._output_dir)
        return files

    def _fire(self, path: Path):
        """Called when a new stable .mp4 is ready."""
        _notify(path.name)
        self._on_new_video(path)

    def ping(self) -> None:
        """Signal to JobManager health monitor that watcher is alive."""
        pass  # caller passes this to jm.ping_watcher()


def _notify(filename: str):
    """Show desktop notification. Falls back silently if plyer unavailable."""
    msg = f"New RAGAI video ready: {filename}"
    logger.info("Notification: %s", msg)
    if _PLYER_AVAILABLE:
        try:
            _plyer_notification.notify(
                title="RAGAI Editor",
                message=msg,
                app_name="RAGAI Editor",
                timeout=5,
            )
        except Exception as exc:
            logger.debug("Desktop notification failed: %s", exc)
