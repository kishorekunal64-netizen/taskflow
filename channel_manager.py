"""
channel_manager.py - Multi-channel content distribution for RAGAI ecosystem.

Maps compiled videos to YouTube channels based on topic category,
organises output into per-channel subfolders, and maintains upload queues.

Config: channels_config.json
Output: compiled/<channel_slug>/
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CHANNELS_CONFIG = Path("channels_config.json")
COMPILED_DIR    = Path("compiled")

_DEFAULT_CONFIG: Dict[str, Any] = {
    "channels": [
        {"name": "Village Stories",    "slug": "village_channel",    "category": "village"},
        {"name": "Devotional Kahani",  "slug": "devotional_channel", "category": "devotional"},
        {"name": "Motivational Hindi", "slug": "motivational_channel","category": "motivational"},
        {"name": "Love Stories",       "slug": "love_channel",       "category": "love"},
        {"name": "General RAGAI",      "slug": "general_channel",    "category": "general"},
    ]
}

# Tag/keyword → category mapping (mirrors topic_engine clusters)
_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "village":      ["village", "villagelife", "villagestory", "gaon", "gramin", "rural"],
    "devotional":   ["devotional", "bhakti", "spiritual", "god", "mandir", "pooja", "prayer"],
    "motivational": ["motivational", "motivation", "inspire", "inspirational", "success"],
    "love":         ["love", "romantic", "romance", "pyar", "ishq", "dil"],
    "mystery":      ["mystery", "thriller", "suspense", "horror"],
    "family":       ["family", "mother", "father", "children", "ghar"],
    "history":      ["history", "historical", "ancient", "mythology", "legend"],
    "comedy":       ["comedy", "funny", "humor", "hasya"],
}


def _load_config() -> Dict[str, Any]:
    if CHANNELS_CONFIG.exists():
        try:
            return json.loads(CHANNELS_CONFIG.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not load channels_config.json: %s", exc)
    return _DEFAULT_CONFIG


def _save_config(cfg: Dict[str, Any]) -> None:
    try:
        CHANNELS_CONFIG.write_text(
            json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as exc:
        logger.warning("Could not save channels_config.json: %s", exc)


def _detect_category(title: str, tags: List[str]) -> str:
    """Detect category from title + tags using keyword matching."""
    text = " ".join([title] + tags).lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return category
    return "general"


class ChannelManager:
    """
    Routes compiled videos to the correct channel subfolder and
    maintains a per-channel upload queue (queue.json inside each channel folder).
    """

    def __init__(self, compiled_dir: Path = COMPILED_DIR):
        self._compiled_dir = Path(compiled_dir)
        self._cfg = _load_config()
        self._channels: List[Dict[str, Any]] = self._cfg.get("channels", [])
        self._ensure_channel_dirs()
        logger.info("ChannelManager: %d channels configured", len(self._channels))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assign_video(
        self,
        video_path: Path,
        title: str = "",
        tags: Optional[List[str]] = None,
        category: Optional[str] = None,
    ) -> Optional[Path]:
        """
        Copy video (+ sidecar files) into the correct channel subfolder.
        Returns the destination path, or None on failure.
        """
        video_path = Path(video_path)
        if not video_path.exists():
            logger.error("Video not found: %s", video_path)
            return None

        tags = tags or []
        cat = category or _detect_category(title or video_path.stem, tags)
        channel = self._channel_for_category(cat)
        if not channel:
            channel = self._channel_for_category("general")

        slug = channel["slug"]
        dest_dir = self._compiled_dir / slug
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Copy video
        dest_video = dest_dir / video_path.name
        try:
            shutil.copy2(str(video_path), str(dest_video))
            logger.info("Assigned %s -> %s/%s", video_path.name, slug, video_path.name)
        except Exception as exc:
            logger.error("Copy failed: %s", exc)
            return None

        # Copy sidecar files (thumbnail, title.txt) if present
        for ext in ["_thumbnail.jpg", ".jpg"]:
            sidecar = video_path.parent / (video_path.stem + ext)
            if sidecar.exists():
                shutil.copy2(str(sidecar), str(dest_dir / sidecar.name))

        title_txt = video_path.parent / "title.txt"
        if title_txt.exists():
            shutil.copy2(str(title_txt), str(dest_dir / "title.txt"))

        # Add to upload queue
        self._enqueue(slug, dest_video, title, cat)
        return dest_video

    def get_upload_queue(self, slug: str) -> List[Dict[str, Any]]:
        """Return pending upload queue for a channel slug."""
        queue_path = self._compiled_dir / slug / "queue.json"
        if queue_path.exists():
            try:
                return json.loads(queue_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def mark_uploaded(self, slug: str, video_filename: str) -> None:
        """Mark a video as uploaded in the channel queue."""
        queue = self.get_upload_queue(slug)
        for item in queue:
            if item.get("filename") == video_filename:
                item["status"] = "uploaded"
                item["uploaded_at"] = datetime.now().isoformat()
        self._save_queue(slug, queue)
        logger.info("Marked uploaded: %s/%s", slug, video_filename)

    def list_channels(self) -> List[Dict[str, Any]]:
        return list(self._channels)

    def get_channel_for_topic(self, topic: str, tags: Optional[List[str]] = None) -> str:
        """Return channel name for a given topic string."""
        cat = _detect_category(topic, tags or [])
        ch = self._channel_for_category(cat)
        return ch["name"] if ch else "General RAGAI"

    def add_channel(self, name: str, slug: str, category: str) -> None:
        """Add a new channel to the config."""
        self._channels.append({"name": name, "slug": slug, "category": category})
        self._cfg["channels"] = self._channels
        _save_config(self._cfg)
        (self._compiled_dir / slug).mkdir(parents=True, exist_ok=True)
        logger.info("Channel added: %s (%s)", name, slug)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_channel_dirs(self) -> None:
        for ch in self._channels:
            (self._compiled_dir / ch["slug"]).mkdir(parents=True, exist_ok=True)

    def _channel_for_category(self, category: str) -> Optional[Dict[str, Any]]:
        for ch in self._channels:
            if ch.get("category") == category:
                return ch
        return None

    def _enqueue(self, slug: str, video_path: Path, title: str, category: str) -> None:
        queue = self.get_upload_queue(slug)
        entry = {
            "filename": video_path.name,
            "title": title or video_path.stem,
            "category": category,
            "status": "pending",
            "queued_at": datetime.now().isoformat(),
            "uploaded_at": None,
        }
        # Avoid duplicates
        if not any(q["filename"] == entry["filename"] for q in queue):
            queue.append(entry)
            self._save_queue(slug, queue)
            logger.info("Queued for upload: %s -> %s", video_path.name, slug)

    def _save_queue(self, slug: str, queue: List[Dict[str, Any]]) -> None:
        queue_path = self._compiled_dir / slug / "queue.json"
        try:
            queue_path.write_text(
                json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as exc:
            logger.warning("Could not save queue for %s: %s", slug, exc)
