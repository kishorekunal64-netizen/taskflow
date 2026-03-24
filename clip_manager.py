"""
clip_manager.py — Clip Library for RAGAI Editor.

Stores clip metadata, extracts thumbnails via FFmpeg, persists to JSON.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

CLIPS_DB = Path("editor_clips.json")
THUMB_DIR = Path("compiled") / ".thumbs"

# Clip states
STATE_AVAILABLE  = "available"
STATE_IN_TIMELINE = "in_timeline"
STATE_EXPORTED   = "exported"


@dataclass
class Clip:
    clip_id: str          # unique — stem of filename
    filepath: str
    filename: str
    duration: float       # seconds
    width: int
    height: int
    created_at: str       # ISO string
    topic: str = ""
    tags: List[str] = field(default_factory=list)
    thumbnail: str = ""   # path to extracted thumb PNG
    state: str = STATE_AVAILABLE
    # trim points (seconds); -1 = not set
    trim_in: float = -1.0
    trim_out: float = -1.0

    @property
    def display_duration(self) -> str:
        s = int(self.duration)
        return f"{s // 60}:{s % 60:02d}"

    @property
    def resolution(self) -> str:
        return f"{self.width}×{self.height}"


class ClipManager:
    """Thread-safe clip store with FFmpeg thumbnail extraction."""

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self._ffmpeg = ffmpeg_path
        self._lock = threading.Lock()
        self._clips: Dict[str, Clip] = {}
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def import_clip(self, path: Path, on_done: Optional[Callable[[Clip], None]] = None) -> Optional[Clip]:
        """Import a video file. Runs thumbnail extraction in background thread."""
        path = Path(path)
        clip_id = path.stem
        with self._lock:
            if clip_id in self._clips:
                logger.debug("Clip already imported: %s", clip_id)
                return self._clips[clip_id]

        def _work():
            clip = self._build_clip(path)
            if clip is None:
                return
            with self._lock:
                self._clips[clip_id] = clip
                self._save()
            logger.info("Imported clip: %s (%.1fs)", clip.filename, clip.duration)
            if on_done:
                on_done(clip)

        threading.Thread(target=_work, daemon=True).start()
        return None  # result delivered via callback

    def get_all(self) -> List[Clip]:
        with self._lock:
            return list(self._clips.values())

    def get(self, clip_id: str) -> Optional[Clip]:
        with self._lock:
            return self._clips.get(clip_id)

    def set_state(self, clip_id: str, state: str):
        with self._lock:
            if clip_id in self._clips:
                self._clips[clip_id].state = state
                self._save()

    def set_trim(self, clip_id: str, trim_in: float, trim_out: float):
        with self._lock:
            if clip_id in self._clips:
                self._clips[clip_id].trim_in = trim_in
                self._clips[clip_id].trim_out = trim_out
                self._save()

    def remove(self, clip_id: str):
        with self._lock:
            self._clips.pop(clip_id, None)
            self._save()

    def clear_all(self):
        with self._lock:
            self._clips.clear()
            self._save()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_clip(self, path: Path) -> Optional[Clip]:
        """Probe video, extract thumbnail, read metadata.txt."""
        probe = self._probe(path)
        if probe is None:
            return None
        duration, width, height = probe

        # Read metadata.txt if present
        topic, tags = self._read_metadata(path)

        # Extract thumbnail
        thumb_path = self._extract_thumb(path)

        clip = Clip(
            clip_id=path.stem,
            filepath=str(path.resolve()),
            filename=path.name,
            duration=duration,
            width=width,
            height=height,
            created_at=datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            topic=topic,
            tags=tags,
            thumbnail=str(thumb_path) if thumb_path else "",
        )
        return clip

    def _probe(self, path: Path):
        """Return (duration, width, height) via ffprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_streams", "-show_format", str(path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            data = json.loads(result.stdout)
            duration = float(data.get("format", {}).get("duration", 0))
            width = height = 0
            for s in data.get("streams", []):
                if s.get("codec_type") == "video":
                    width = int(s.get("width", 0))
                    height = int(s.get("height", 0))
                    break
            return duration, width, height
        except Exception as exc:
            logger.warning("ffprobe failed for %s: %s", path.name, exc)
            return None

    def _extract_thumb(self, path: Path) -> Optional[Path]:
        """Extract frame at 3s as PNG thumbnail."""
        thumb = THUMB_DIR / f"{path.stem}_thumb.png"
        if thumb.exists():
            return thumb
        try:
            cmd = [
                self._ffmpeg, "-y", "-ss", "3", "-i", str(path),
                "-vframes", "1", "-vf", "scale=160:90",
                "-q:v", "2", str(thumb)
            ]
            subprocess.run(cmd, capture_output=True, timeout=15)
            return thumb if thumb.exists() else None
        except Exception as exc:
            logger.debug("Thumbnail extraction failed: %s", exc)
            return None

    def _read_metadata(self, path: Path) -> tuple[str, list]:
        """
        Read metadata.txt from the same folder as the video.
        Supports both flat layout (output/video_metadata.txt) and
        folder layout (output/video_folder/metadata.txt).
        """
        # Folder-based: metadata.txt sits alongside the video
        candidates = [
            path.parent / "metadata.txt",
            path.parent / (path.stem + "_metadata.txt"),
            path.parent / (path.stem + ".txt"),
        ]
        topic = path.stem.replace("_", " ")
        tags: List[str] = []
        for meta_path in candidates:
            if meta_path.exists():
                try:
                    text = meta_path.read_text(encoding="utf-8", errors="ignore")
                    for line in text.splitlines():
                        ll = line.lower()
                        if ll.startswith("title"):
                            topic = line.split(":", 1)[-1].strip()
                        if "#" in line:
                            tags = re.findall(r"#\w+", line)
                except Exception:
                    pass
                break
        return topic, tags

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self):
        """Must be called with self._lock held."""
        try:
            data = {k: asdict(v) for k, v in self._clips.items()}
            CLIPS_DB.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to save clips DB: %s", exc)

    def _load(self):
        if not CLIPS_DB.exists():
            return
        try:
            data = json.loads(CLIPS_DB.read_text(encoding="utf-8"))
            for k, v in data.items():
                # Only load clips whose file still exists
                if Path(v["filepath"]).exists():
                    self._clips[k] = Clip(**v)
            logger.info("Loaded %d clips from DB", len(self._clips))
        except Exception as exc:
            logger.warning("Failed to load clips DB: %s", exc)
