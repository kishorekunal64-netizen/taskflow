"""
style_engine.py — Channel branding and visual identity for RAGAI.

Loads channel style configurations from channel_styles.json and applies
them to voice selection, music selection, thumbnail color scheme, and
scene color grading.

If channel_styles.json does not exist, the engine operates in passthrough
mode and returns defaults without error.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path("channel_styles.json")

# Built-in default styles (used when no config file exists)
_BUILTIN_STYLES: Dict[str, Dict[str, Any]] = {
    "devotional_channel": {
        "music_style": "devotional",
        "color_palette": "warm",
        "voice_style": "calm",
        "color_grade": "curves=r='0 0 1 1':g='0 0.9 1 1':b='0 0.7 1 0.9'",
        "thumbnail_bg_color": "#FFF3E0",
        "thumbnail_text_color": "#BF360C",
    },
    "mystery_channel": {
        "music_style": "dark",
        "color_palette": "cool",
        "voice_style": "dramatic",
        "color_grade": "curves=r='0 0 1 0.9':g='0 0 1 0.9':b='0 0.1 1 1.1'",
        "thumbnail_bg_color": "#1A1A2E",
        "thumbnail_text_color": "#E0E0FF",
    },
    "adventure_channel": {
        "music_style": "adventure",
        "color_palette": "vibrant",
        "voice_style": "energetic",
        "color_grade": "curves=r='0 0 1 1.1':g='0 0 1 1':b='0 0 1 0.9'",
        "thumbnail_bg_color": "#E8F5E9",
        "thumbnail_text_color": "#1B5E20",
    },
    "default": {
        "music_style": "neutral",
        "color_palette": "natural",
        "voice_style": "calm",
        "color_grade": "null",
        "thumbnail_bg_color": "#FFFFFF",
        "thumbnail_text_color": "#212121",
    },
}


class StyleEngine:
    """Load and apply channel-specific visual identity."""

    def __init__(self, config_path: Path = _DEFAULT_CONFIG_PATH) -> None:
        self.config_path = Path(config_path)
        self._styles: Dict[str, Dict[str, Any]] = dict(_BUILTIN_STYLES)
        self._load()

    def _load(self) -> None:
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                self._styles.update(data)
                logger.info("StyleEngine: loaded %d channel styles from %s",
                            len(data), self.config_path)
            except Exception as exc:
                logger.warning("StyleEngine: failed to load %s — %s", self.config_path, exc)
        else:
            logger.info("StyleEngine: no channel_styles.json found — using built-in defaults")
            # Write defaults for user reference
            try:
                self.config_path.write_text(
                    json.dumps(_BUILTIN_STYLES, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                logger.info("StyleEngine: wrote default channel_styles.json")
            except Exception:
                pass

    def get_style(self, channel_name: str) -> Dict[str, Any]:
        """Return style config for a channel. Falls back to 'default'."""
        style = self._styles.get(channel_name) or self._styles.get("default", {})
        logger.debug("StyleEngine: style for %r = %s", channel_name, style)
        return style

    def music_style(self, channel_name: str) -> str:
        return self.get_style(channel_name).get("music_style", "neutral")

    def voice_style(self, channel_name: str) -> str:
        return self.get_style(channel_name).get("voice_style", "calm")

    def color_grade(self, channel_name: str) -> str:
        return self.get_style(channel_name).get("color_grade", "null")

    def thumbnail_colors(self, channel_name: str) -> Dict[str, str]:
        s = self.get_style(channel_name)
        return {
            "bg": s.get("thumbnail_bg_color", "#FFFFFF"),
            "text": s.get("thumbnail_text_color", "#212121"),
        }

    def list_channels(self):
        return [k for k in self._styles if k != "default"]
