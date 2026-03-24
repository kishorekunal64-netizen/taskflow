"""
log_setup.py — Structured logging configuration for RAGAI Video Factory.

Provides:
  - Timestamped log files in logs/
  - ISO-8601 timestamps, log level, module, scene context in every entry
  - A sanitising filter that strips API key patterns before any write
  - A single call `configure_logging()` used by ragai.py at startup

Usage:
    from log_setup import configure_logging
    configure_logging(level="INFO")
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Patterns to strip from log messages (API keys, bearer tokens)
# ---------------------------------------------------------------------------

_SANITISE_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]+"),
    re.compile(r"Bearer [A-Za-z0-9]{20,}"),
]

_REDACTED = "[REDACTED]"


# ---------------------------------------------------------------------------
# Sanitising filter
# ---------------------------------------------------------------------------

class SanitiseFilter(logging.Filter):
    """Strips API key patterns from log records before they are written.

    Sanitises the fully-formatted message so numeric args are never touched,
    avoiding TypeError when %d format specifiers receive integers.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Let Python format the message normally first, then sanitise the result.
        # We do this by temporarily replacing getMessage so the formatter uses
        # our sanitised version.
        original_msg = record.msg
        original_args = record.args
        try:
            # Format with original args to get the final string
            if record.args:
                try:
                    formatted = record.msg % record.args
                except Exception:
                    formatted = str(record.msg)
            else:
                formatted = str(record.msg)
            # Sanitise the fully-formatted string
            sanitised = formatted
            for pattern in _SANITISE_PATTERNS:
                sanitised = pattern.sub(_REDACTED, sanitised)
            # Replace msg with sanitised string and clear args so no double-format
            record.msg = sanitised
            record.args = None
        except Exception:
            # Never break logging — restore originals on any error
            record.msg = original_msg
            record.args = original_args
        return True


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def configure_logging(level: str = "INFO", log_dir: Path = Path("logs")) -> Path:
    """Configure root logger with a sanitising file handler and console handler.

    Creates a timestamped log file in *log_dir* (e.g. ``logs/ragai_20260323_120000.log``).

    Args:
        level:   Log level string (DEBUG, INFO, WARNING, ERROR).
        log_dir: Directory where log files are written.

    Returns:
        Path to the log file created for this session.
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"ragai_{timestamp}.log"

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    sanitise = SanitiseFilter()
    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)

    # File handler — full detail
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(sanitise)

    # Console handler — WARNING and above only (keeps CLI output clean)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(sanitise)

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Avoid duplicate handlers if called more than once
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    logging.getLogger(__name__).info(
        "Logging initialised — level=%s file=%s", level, log_file
    )

    return log_file
