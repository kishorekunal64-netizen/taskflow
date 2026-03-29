"""
FinIntelligence Market Analysis System — cross-cutting logger.
Wraps Python's logging module with rotating file handler and stderr output.
Implements rolling 60-minute error counter for CRITICAL threshold alerts.
"""

import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from typing import Optional

# Module-level state
_logger: Optional[logging.Logger] = None
_error_timestamps: list[datetime] = []
_critical_alert_emitted: bool = False
_last_window_key: Optional[str] = None


def get_logger(name: str) -> logging.Logger:
    """
    Returns a configured logging.Logger instance.
    On first call, sets up handlers (RotatingFileHandler + StreamHandler).
    Subsequent calls return the cached logger.
    
    Configuration:
    - RotatingFileHandler: max 10 MB, 5 backups, ALL levels
    - StreamHandler(sys.stderr): WARNING and above only
    - Log file path: finintelligence/logs/finintelligence.log
    
    Logger never raises — if file handler fails, falls back to stderr only.
    """
    global _logger
    
    if _logger is not None:
        return _logger
    
    # Create logger
    _logger = logging.getLogger(name)
    _logger.setLevel(logging.DEBUG)
    
    # Formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Rotating file handler — ALL levels
    try:
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "finintelligence.log")
        
        file_handler = RotatingFileHandler(
            filename=log_path,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        _logger.addHandler(file_handler)
    except Exception:
        # File handler failed — fall back to stderr only (never raise)
        pass
    
    # Stderr handler — WARNING and above only
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)
    _logger.addHandler(stderr_handler)
    
    return _logger


def record_error(component: str) -> None:
    """
    Records an error occurrence for the given component.
    Appends current UTC timestamp to _error_timestamps, then calls check_error_threshold().
    """
    global _error_timestamps
    _error_timestamps.append(datetime.utcnow())
    check_error_threshold()


def _reset_logger_state() -> None:
    """
    Resets all module-level state to initial values.
    FOR TESTING PURPOSES ONLY — do not call in production code.
    """
    global _logger, _error_timestamps, _critical_alert_emitted, _last_window_key
    _logger = None
    _error_timestamps = []
    _critical_alert_emitted = False
    _last_window_key = None


def check_error_threshold() -> None:
    """
    Prunes _error_timestamps entries older than 60 minutes.
    If more than 10 errors remain in the rolling window, emits exactly one
    CRITICAL log entry (uses a flag to avoid duplicate CRITICAL per window).
    """
    global _error_timestamps, _critical_alert_emitted, _last_window_key
    
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=60)
    
    # Prune entries older than 60 minutes
    _error_timestamps = [ts for ts in _error_timestamps if ts >= cutoff]
    
    # Determine the current window key (hourly bucket) to detect window resets
    window_key = now.strftime("%Y-%m-%d %H")
    
    # Reset the flag when we enter a new hour window
    if window_key != _last_window_key:
        _critical_alert_emitted = False
        _last_window_key = window_key
    
    # Emit CRITICAL once if threshold exceeded
    if len(_error_timestamps) > 10 and not _critical_alert_emitted:
        _critical_alert_emitted = True
        window_start = _error_timestamps[0] if _error_timestamps else cutoff
        logger = get_logger("finintelligence.logger")
        logger.critical(
            "Error threshold exceeded: %d errors in 60-minute window starting %s",
            len(_error_timestamps),
            window_start.strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
