"""
ragai_diagnose.py — Diagnostic checker for RAGAI Video Factory.

Checks all runtime dependencies and configuration, printing ✅/❌ with
remediation hints for every failed check.

Usage:
    python ragai_diagnose.py
    python ragai.py --diagnose
"""

from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Required packages (importable name, pip install name)
# ---------------------------------------------------------------------------

REQUIRED_PACKAGES = [
    ("dotenv",       "python-dotenv"),
    ("groq",         "groq"),
    ("requests",     "requests"),
    ("PIL",          "Pillow"),
    ("numpy",        "numpy"),
    ("edge_tts",     "edge-tts"),
    ("gtts",         "gTTS"),
    ("cv2",          "opencv-python"),
    ("fast_check",   None),   # optional — skip if missing
]

REQUIRED_PACKAGES_STRICT = [
    ("dotenv",    "python-dotenv"),
    ("groq",      "groq"),
    ("requests",  "requests"),
    ("PIL",       "Pillow"),
    ("numpy",     "numpy"),
    ("edge_tts",  "edge-tts"),
    ("gtts",      "gTTS"),
    ("cv2",       "opencv-python"),
]

EXPECTED_MUSIC_COUNT = 7
MUSIC_DIR = Path("music")
ENV_FILE = Path(".env")
REQUIRED_ENV_KEYS = ["GROQ_API_KEY", "LEONARDO_API_KEY"]


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_python_version() -> tuple[bool, str, str]:
    major, minor = sys.version_info[:2]
    ok = (major, minor) >= (3, 9)
    status = f"Python {major}.{minor}"
    hint = "Install Python 3.9 or newer from https://python.org" if not ok else ""
    return ok, status, hint


def _check_packages() -> list[tuple[bool, str, str]]:
    results = []
    for import_name, pip_name in REQUIRED_PACKAGES_STRICT:
        try:
            importlib.import_module(import_name)
            results.append((True, f"Package: {pip_name or import_name}", ""))
        except ImportError:
            hint = f"Run: pip install {pip_name}" if pip_name else f"Run: pip install {import_name}"
            results.append((False, f"Package: {pip_name or import_name}", hint))
    return results


def _check_ffmpeg() -> tuple[bool, str, str]:
    found = shutil.which("ffmpeg") is not None
    hint = (
        "Install FFmpeg and add it to PATH.\n"
        "  Windows: https://ffmpeg.org/download.html  or  winget install ffmpeg\n"
        "  macOS:   brew install ffmpeg\n"
        "  Linux:   sudo apt install ffmpeg"
    ) if not found else ""
    return found, "FFmpeg on PATH", hint


def _check_env_file() -> tuple[bool, str, str]:
    exists = ENV_FILE.is_file()
    hint = (
        f"Create a '{ENV_FILE}' file with GROQ_API_KEY and LEONARDO_API_KEY.\n"
        "  See .env.example for the template."
    ) if not exists else ""
    return exists, f".env file ({ENV_FILE.resolve()})", hint


def _check_api_keys() -> list[tuple[bool, str, str]]:
    results = []
    if not ENV_FILE.is_file():
        for key in REQUIRED_ENV_KEYS:
            results.append((False, f"API key: {key}", f"Add {key} to your .env file"))
        return results

    try:
        from dotenv import dotenv_values
        values = dotenv_values(ENV_FILE)
    except Exception:
        for key in REQUIRED_ENV_KEYS:
            results.append((False, f"API key: {key}", "Could not parse .env file"))
        return results

    for key in REQUIRED_ENV_KEYS:
        val = values.get(key, "").strip()
        ok = bool(val)
        hint = f"Set {key} in your .env file" if not ok else ""
        results.append((ok, f"API key: {key}", hint))

    return results


def _check_music_library() -> tuple[bool, str, str]:
    if not MUSIC_DIR.is_dir():
        return (
            False,
            f"Music library ({MUSIC_DIR}/ — {EXPECTED_MUSIC_COUNT} tracks)",
            f"Run: python create_music_v2.py  to generate the music library",
        )
    count = len(list(MUSIC_DIR.glob("*.mp3")))
    ok = count >= EXPECTED_MUSIC_COUNT
    hint = (
        f"Found {count}/{EXPECTED_MUSIC_COUNT} tracks. "
        "Run: python create_music_v2.py  to regenerate."
    ) if not ok else ""
    return ok, f"Music library ({count}/{EXPECTED_MUSIC_COUNT} tracks in {MUSIC_DIR}/)", hint


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_diagnostics() -> bool:
    """Run all checks and print results. Returns True if all pass."""
    print("\n🔍  RAGAI Diagnostics\n" + "─" * 50)

    all_checks: list[tuple[bool, str, str]] = []

    # Python version
    all_checks.append(_check_python_version())

    # Packages
    all_checks.extend(_check_packages())

    # FFmpeg
    all_checks.append(_check_ffmpeg())

    # .env file
    all_checks.append(_check_env_file())

    # API keys
    all_checks.extend(_check_api_keys())

    # Music library
    all_checks.append(_check_music_library())

    # Print results
    passed = 0
    failed = 0
    for ok, label, hint in all_checks:
        icon = "✅" if ok else "❌"
        print(f"  {icon}  {label}")
        if not ok and hint:
            for line in hint.splitlines():
                print(f"       → {line}")
        if ok:
            passed += 1
        else:
            failed += 1

    print("─" * 50)
    print(f"\n  {passed} passed  /  {failed} failed\n")

    if failed == 0:
        print("✅  All checks passed. RAGAI is ready to run.\n")
    else:
        print("❌  Fix the issues above, then re-run: python ragai_diagnose.py\n")

    return failed == 0


if __name__ == "__main__":
    ok = run_diagnostics()
    sys.exit(0 if ok else 1)
