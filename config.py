"""
config.py — Environment loading and validation for RAGAI Video Factory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

from models import ConfigError


@dataclass
class AppConfig:
    groq_api_key: str
    leonardo_api_key: str
    use_edge_tts: bool = True
    default_language: str = "hi"
    default_format: str = "landscape"
    log_level: str = "INFO"
    hf_token: str = ""   # optional HuggingFace token for FLUX fallback


def load_config(env_path: Path = Path(".env")) -> AppConfig:
    """Load and validate .env. Raises ConfigError if required keys are missing."""
    values = dotenv_values(env_path)

    missing = [key for key in ("GROQ_API_KEY", "LEONARDO_API_KEY") if not values.get(key)]
    if missing:
        raise ConfigError(f"Missing required config key(s): {', '.join(missing)}")

    use_edge_tts_raw = values.get("USE_EDGE_TTS", "true").strip().lower()
    use_edge_tts = use_edge_tts_raw not in ("false", "0", "no")

    return AppConfig(
        groq_api_key=values["GROQ_API_KEY"],
        leonardo_api_key=values["LEONARDO_API_KEY"],
        use_edge_tts=use_edge_tts,
        default_language=values.get("DEFAULT_LANGUAGE", "hi"),
        default_format=values.get("DEFAULT_FORMAT", "landscape"),
        log_level=values.get("LOG_LEVEL", "INFO"),
        hf_token=values.get("HF_TOKEN", ""),
    )
