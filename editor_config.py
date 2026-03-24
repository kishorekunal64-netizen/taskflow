"""
editor_config.py — Shared configuration loader for RAGAI Editor V2.

Reads ragai_config.json. Both RAGAI and RAGAI Editor import from here.
Falls back to safe defaults if the file is missing or malformed.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

_CONFIG_FILE = Path("ragai_config.json")

_DEFAULTS: Dict[str, Any] = {
    "output_dir":       "./output",
    "compiled_dir":     "./compiled",
    "default_quality":  "cinema",
    "default_language": "hi",
    "enable_qsv":       True,
    "hook_enabled":     True,
    "outro_enabled":    True,
    "auto_thumbnail":   True,
    "auto_titles":      True,
}


def load_editor_config() -> Dict[str, Any]:
    """Return merged config dict (file values override defaults)."""
    cfg = dict(_DEFAULTS)
    if _CONFIG_FILE.exists():
        try:
            data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            cfg.update(data)
            logger.debug("Loaded ragai_config.json")
        except Exception as exc:
            logger.warning("Could not parse ragai_config.json: %s — using defaults", exc)
    else:
        logger.info("ragai_config.json not found — using defaults")
    return cfg


def save_editor_config(cfg: Dict[str, Any]) -> None:
    """Persist config dict back to ragai_config.json."""
    try:
        _CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        logger.info("Saved ragai_config.json")
    except Exception as exc:
        logger.warning("Could not save ragai_config.json: %s", exc)
