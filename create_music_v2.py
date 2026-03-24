"""
create_music_v2.py — Programmatic background music library generator for RAGAI.

Generates exactly 7 MP3 tracks in the music/ directory, one per non-AUTO VisualStyle.
Each track is synthesised from numpy/wave primitives and encoded to MP3 via FFmpeg.

Usage:
    python create_music_v2.py
"""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

# ---------------------------------------------------------------------------
# Track definitions — one per non-AUTO VisualStyle
# Must match STYLE_MUSIC_MAP values in style_detector.py
# ---------------------------------------------------------------------------

SAMPLE_RATE = 44100
DURATION_SECONDS = 120  # 2-minute loops

# Each entry: (filename, base_freq_hz, chord_intervals, tempo_bpm, description)
TRACKS = [
    ("epic.mp3",       55.0,  [0, 7, 12, 19],  90,  "epic"),
    ("mystery.mp3",    46.25, [0, 3, 6, 10],   70,  "mystery"),
    ("devotional.mp3", 65.41, [0, 5, 7, 12],   60,  "devotional"),
    ("nature.mp3",     43.65, [0, 4, 7, 11],   50,  "nature"),
    ("romantic.mp3",   55.0,  [0, 4, 7, 9],    65,  "romantic"),
    ("adventure.mp3",  49.0,  [0, 5, 7, 12],  100,  "adventure"),
    ("neutral.mp3",    52.0,  [0, 4, 7],        75,  "neutral"),
]


# ---------------------------------------------------------------------------
# Audio synthesis helpers
# ---------------------------------------------------------------------------

def _freq(base: float, semitones: int) -> float:
    """Return frequency shifted by semitones from base."""
    return base * (2 ** (semitones / 12.0))


def _sine(freq: float, t: float, phase: float = 0.0) -> float:
    return math.sin(2 * math.pi * freq * t + phase)


def _envelope(t: float, duration: float, attack: float = 0.1, release: float = 0.3) -> float:
    """Simple linear attack/release envelope."""
    if t < attack:
        return t / attack
    if t > duration - release:
        return max(0.0, (duration - t) / release)
    return 1.0


def _generate_samples(
    base_freq: float,
    intervals: list[int],
    tempo_bpm: float,
    duration: float,
    sample_rate: int,
) -> list[float]:
    """Generate a list of normalised float samples [-1, 1]."""
    n_samples = int(duration * sample_rate)
    beat_duration = 60.0 / tempo_bpm
    chord_duration = beat_duration * 4  # one chord per bar

    samples: list[float] = []

    for i in range(n_samples):
        t = i / sample_rate
        chord_index = int(t / chord_duration) % len(intervals)
        root = _freq(base_freq, intervals[chord_index])

        # Pad with octave harmonics for richness
        sig = (
            0.50 * _sine(root, t)
            + 0.25 * _sine(root * 2, t, 0.3)
            + 0.15 * _sine(root * 3, t, 0.6)
            + 0.10 * _sine(root * 0.5, t, 0.1)  # sub-bass
        )

        # Gentle tremolo
        tremolo = 1.0 + 0.05 * _sine(5.0, t)
        sig *= tremolo

        # Global fade-in / fade-out
        sig *= _envelope(t, duration, attack=2.0, release=4.0)

        samples.append(sig)

    # Normalise to [-0.85, 0.85]
    peak = max(abs(s) for s in samples) or 1.0
    return [s / peak * 0.85 for s in samples]


def _write_wav(path: Path, samples: list[float], sample_rate: int) -> None:
    """Write 16-bit mono WAV file."""
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for s in samples:
            clamped = max(-1.0, min(1.0, s))
            frame = struct.pack("<h", int(clamped * 32767))
            wf.writeframes(frame)


def _wav_to_mp3(wav_path: Path, mp3_path: Path) -> None:
    """Convert WAV to MP3 using FFmpeg (192k stereo)."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(wav_path),
        "-ac", "2",          # stereo
        "-b:a", "192k",
        str(mp3_path),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed for {mp3_path.name}:\n{result.stderr.decode()}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def generate_music_library(output_dir: Path = Path("music")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    if not shutil.which("ffmpeg"):
        print("❌  FFmpeg not found on PATH. Install FFmpeg and retry.")
        sys.exit(1)

    print(f"Generating {len(TRACKS)} background tracks → {output_dir.resolve()}\n")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for filename, base_freq, intervals, tempo, label in TRACKS:
            mp3_path = output_dir / filename
            print(f"  [{label:>12}]  generating {filename} ...", end=" ", flush=True)

            samples = _generate_samples(base_freq, intervals, tempo, DURATION_SECONDS, SAMPLE_RATE)
            wav_path = tmp_path / filename.replace(".mp3", ".wav")
            _write_wav(wav_path, samples, SAMPLE_RATE)
            _wav_to_mp3(wav_path, mp3_path)

            size_kb = mp3_path.stat().st_size // 1024
            print(f"done  ({size_kb} KB)")

    mp3_count = len(list(output_dir.glob("*.mp3")))
    print(f"\n✅  Music library ready — {mp3_count} tracks in {output_dir}/")


if __name__ == "__main__":
    generate_music_library()
