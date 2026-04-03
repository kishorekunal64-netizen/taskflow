"""
procedural_bgm_engine.py — Procedural Background Music Engine for RAGAI.

Generates copyright-free background music locally using numpy + soundfile.
No external API, no copyright risk, unlimited generation.

Style mapping:
  DYNAMIC_EPIC         → orchestral strings + percussion (minor, 110 BPM)
  MYSTERY_DARK         → ambient pad + piano (minor, 70 BPM)
  SPIRITUAL_DEVOTIONAL → flute + tanpura drone (pentatonic, 80 BPM)
  PEACEFUL_NATURE      → ambient pad (major, 70 BPM)
  ROMANTIC_DRAMA       → piano + strings (major, 90 BPM)
  ADVENTURE_ACTION     → rhythmic percussion + brass (minor, 120 BPM)

Cache: bgm_cache/style_<name>.wav — reused if present.
Fallback: if generation fails, returns None (caller falls back to music/ folder).
"""

from __future__ import annotations

import logging
import math
import random
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_CACHE_DIR = Path("bgm_cache")

# ── Style profiles ────────────────────────────────────────────────────────────

_STYLE_PROFILES = {
    "DYNAMIC_EPIC": {
        "bpm": 110, "scale": "minor",
        "chord_prog": [(0, "m"), (5, "M"), (3, "M"), (7, "m")],
        "instruments": ["strings", "percussion"],
        "volume": 0.55,
    },
    "MYSTERY_DARK": {
        "bpm": 70, "scale": "minor",
        "chord_prog": [(0, "m"), (2, "dim"), (5, "m"), (3, "M")],
        "instruments": ["pad", "piano"],
        "volume": 0.40,
    },
    "SPIRITUAL_DEVOTIONAL": {
        "bpm": 80, "scale": "pentatonic",
        "chord_prog": [(0, "M"), (4, "M"), (7, "M"), (4, "M")],
        "instruments": ["flute", "drone"],
        "volume": 0.45,
    },
    "PEACEFUL_NATURE": {
        "bpm": 70, "scale": "major",
        "chord_prog": [(0, "M"), (5, "M"), (9, "m"), (7, "M")],
        "instruments": ["pad"],
        "volume": 0.38,
    },
    "ROMANTIC_DRAMA": {
        "bpm": 90, "scale": "major",
        "chord_prog": [(0, "M"), (5, "M"), (9, "m"), (4, "M")],
        "instruments": ["piano", "strings"],
        "volume": 0.48,
    },
    "ADVENTURE_ACTION": {
        "bpm": 120, "scale": "minor",
        "chord_prog": [(0, "m"), (7, "M"), (5, "M"), (3, "M")],
        "instruments": ["percussion", "brass"],
        "volume": 0.60,
    },
}

# ── Scale definitions (semitone intervals from root) ─────────────────────────

_SCALES = {
    "major":      [0, 2, 4, 5, 7, 9, 11],
    "minor":      [0, 2, 3, 5, 7, 8, 10],
    "pentatonic": [0, 2, 4, 7, 9],
}

# ── Chord intervals ───────────────────────────────────────────────────────────

_CHORD_INTERVALS = {
    "M":   [0, 4, 7],
    "m":   [0, 3, 7],
    "dim": [0, 3, 6],
    "aug": [0, 4, 8],
}

_SAMPLE_RATE = 44100
_ROOT_MIDI   = 57   # A3 — comfortable mid-range root


# ── Core synthesis helpers ────────────────────────────────────────────────────

def _midi_to_hz(midi: int) -> float:
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def _sine(freq: float, duration: float, sr: int = _SAMPLE_RATE,
          phase: float = 0.0) -> "np.ndarray":
    import numpy as np
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return np.sin(2 * math.pi * freq * t + phase).astype(np.float32)


def _adsr(n: int, attack: float = 0.05, decay: float = 0.1,
          sustain: float = 0.7, release: float = 0.15,
          sr: int = _SAMPLE_RATE) -> "np.ndarray":
    import numpy as np
    env = np.zeros(n, dtype=np.float32)
    a = int(attack * sr)
    d = int(decay * sr)
    r = int(release * sr)
    s_end = max(a + d, n - r)
    if a > 0:
        env[:a] = np.linspace(0, 1, a)
    if d > 0 and a + d <= n:
        env[a:a + d] = np.linspace(1, sustain, d)
    env[a + d:s_end] = sustain
    if r > 0:
        env[s_end:s_end + r] = np.linspace(sustain, 0, min(r, n - s_end))
    return env


def _note(midi: int, duration: float, instrument: str = "piano",
          sr: int = _SAMPLE_RATE) -> "np.ndarray":
    """Synthesize a single note with instrument-specific timbre."""
    import numpy as np
    freq = _midi_to_hz(midi)
    n = int(sr * duration)

    if instrument == "piano":
        # Bright harmonic series
        wave = (
            _sine(freq, duration, sr) * 0.6 +
            _sine(freq * 2, duration, sr) * 0.25 +
            _sine(freq * 3, duration, sr) * 0.10 +
            _sine(freq * 4, duration, sr) * 0.05
        )
        env = _adsr(n, attack=0.01, decay=0.15, sustain=0.5, release=0.3)

    elif instrument == "strings":
        # Warm, slow attack
        wave = (
            _sine(freq, duration, sr) * 0.5 +
            _sine(freq * 2, duration, sr) * 0.3 +
            _sine(freq * 3, duration, sr) * 0.15 +
            _sine(freq * 0.5, duration, sr) * 0.05
        )
        env = _adsr(n, attack=0.12, decay=0.1, sustain=0.8, release=0.25)

    elif instrument == "pad":
        # Soft, slow attack, long sustain
        wave = (
            _sine(freq, duration, sr) * 0.45 +
            _sine(freq * 2, duration, sr) * 0.3 +
            _sine(freq * 0.5, duration, sr) * 0.15 +
            _sine(freq * 3, duration, sr) * 0.10
        )
        env = _adsr(n, attack=0.25, decay=0.05, sustain=0.9, release=0.35)

    elif instrument == "flute":
        # Breathy, pure tone
        wave = (
            _sine(freq, duration, sr) * 0.7 +
            _sine(freq * 2, duration, sr) * 0.2 +
            _sine(freq * 3, duration, sr) * 0.10
        )
        env = _adsr(n, attack=0.08, decay=0.05, sustain=0.85, release=0.20)

    elif instrument == "drone":
        # Tanpura-like sustained drone
        wave = (
            _sine(freq, duration, sr) * 0.4 +
            _sine(freq * 2, duration, sr) * 0.25 +
            _sine(freq * 3, duration, sr) * 0.20 +
            _sine(freq * 4, duration, sr) * 0.10 +
            _sine(freq * 0.5, duration, sr) * 0.05
        )
        env = _adsr(n, attack=0.3, decay=0.0, sustain=1.0, release=0.4)

    elif instrument == "brass":
        # Bright, punchy
        wave = (
            _sine(freq, duration, sr) * 0.5 +
            _sine(freq * 2, duration, sr) * 0.3 +
            _sine(freq * 3, duration, sr) * 0.15 +
            _sine(freq * 4, duration, sr) * 0.05
        )
        env = _adsr(n, attack=0.03, decay=0.08, sustain=0.75, release=0.15)

    elif instrument == "percussion":
        # Kick-like thump
        freq_sweep = freq * 2
        t = np.linspace(0, duration, n, endpoint=False)
        sweep = np.exp(-t * 8) * freq_sweep
        wave = np.sin(2 * math.pi * np.cumsum(sweep) / sr).astype(np.float32)
        env = _adsr(n, attack=0.005, decay=0.2, sustain=0.0, release=0.1)

    else:
        wave = _sine(freq, duration, sr)
        env = _adsr(n)

    return (wave[:n] * env[:n]).astype(np.float32)


def _chord(root_midi: int, chord_type: str, duration: float,
           instrument: str = "piano", sr: int = _SAMPLE_RATE) -> "np.ndarray":
    """Synthesize a chord (sum of notes)."""
    import numpy as np
    intervals = _CHORD_INTERVALS.get(chord_type, [0, 4, 7])
    waves = [_note(root_midi + iv, duration, instrument, sr) for iv in intervals]
    n = max(len(w) for w in waves)
    out = np.zeros(n, dtype=np.float32)
    for w in waves:
        out[:len(w)] += w
    return out / len(waves)


def _percussion_track(bpm: float, duration: float,
                      sr: int = _SAMPLE_RATE) -> "np.ndarray":
    """Simple kick + snare pattern."""
    import numpy as np
    beat = 60.0 / bpm
    n = int(sr * duration)
    out = np.zeros(n, dtype=np.float32)
    t = 0.0
    beat_idx = 0
    while t < duration:
        pos = int(t * sr)
        if pos >= n:
            break
        # Kick on beats 1 and 3
        if beat_idx % 4 in (0, 2):
            kick = _note(36, min(beat * 0.4, 0.3), "percussion", sr)
            end = min(pos + len(kick), n)
            out[pos:end] += kick[:end - pos] * 0.7
        # Snare on beats 2 and 4
        if beat_idx % 4 in (1, 3):
            snare = _note(40, min(beat * 0.3, 0.2), "percussion", sr)
            end = min(pos + len(snare), n)
            out[pos:end] += snare[:end - pos] * 0.5
        t += beat
        beat_idx += 1
    return out


def _melody_track(scale_notes: List[int], bpm: float, duration: float,
                  instrument: str = "flute", sr: int = _SAMPLE_RATE) -> "np.ndarray":
    """Generate a simple melodic phrase over the duration."""
    import numpy as np
    beat = 60.0 / bpm
    note_dur = beat * 0.9
    n = int(sr * duration)
    out = np.zeros(n, dtype=np.float32)
    t = 0.0
    rng = random.Random(42)
    while t < duration:
        pos = int(t * sr)
        if pos >= n:
            break
        midi = rng.choice(scale_notes)
        note_wave = _note(midi, min(note_dur, duration - t), instrument, sr)
        end = min(pos + len(note_wave), n)
        out[pos:end] += note_wave[:end - pos] * 0.6
        t += beat
    return out


# ── Main generation function ──────────────────────────────────────────────────

def generate_bgm(style: str, duration: float = 60.0) -> Optional[Path]:
    """
    Generate background music for the given style.

    Args:
        style: VisualStyle name string (e.g. "DYNAMIC_EPIC") or VisualStyle enum.
        duration: Target duration in seconds.

    Returns:
        Path to the generated WAV file, or None on failure.
    """
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as exc:
        logger.warning("procedural_bgm_engine: missing dependency (%s) — skipping", exc)
        return None

    # Normalise style key
    style_key = str(style).upper().replace(" ", "_").replace("VISUALSTYLE.", "")
    # Strip enum prefix if present (e.g. "VisualStyle.DYNAMIC_EPIC")
    if "." in style_key:
        style_key = style_key.split(".")[-1]

    profile = _STYLE_PROFILES.get(style_key)
    if not profile:
        # Fallback to PEACEFUL_NATURE
        logger.debug("Unknown style %r — using PEACEFUL_NATURE profile", style_key)
        profile = _STYLE_PROFILES["PEACEFUL_NATURE"]
        style_key = "PEACEFUL_NATURE"

    # Check cache
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _CACHE_DIR / f"style_{style_key.lower()}.wav"
    if cache_path.exists():
        logger.info("BGM cache hit: %s", cache_path)
        return cache_path

    logger.info("Generating procedural BGM: style=%s duration=%.1fs bpm=%d",
                style_key, duration, profile["bpm"])

    try:
        sr = _SAMPLE_RATE
        n_total = int(sr * duration)
        mix = np.zeros(n_total, dtype=np.float32)

        bpm = profile["bpm"]
        beat = 60.0 / bpm
        chord_prog = profile["chord_prog"]
        instruments = profile["instruments"]
        scale_name = profile["scale"]
        scale_intervals = _SCALES.get(scale_name, _SCALES["major"])
        scale_notes = [_ROOT_MIDI + iv for iv in scale_intervals]
        # Add octave above
        scale_notes += [n + 12 for n in scale_notes]

        # Chord duration = 4 beats
        chord_dur = beat * 4
        n_chords = max(1, int(math.ceil(duration / chord_dur)))

        # ── Chord/harmony layer ───────────────────────────────────────────
        harm_instrument = "strings" if "strings" in instruments else \
                          "pad"     if "pad"     in instruments else \
                          "piano"
        t = 0.0
        for i in range(n_chords):
            root_offset, chord_type = chord_prog[i % len(chord_prog)]
            root_midi = _ROOT_MIDI + root_offset
            seg_dur = min(chord_dur, duration - t)
            if seg_dur <= 0:
                break
            wave = _chord(root_midi, chord_type, seg_dur, harm_instrument, sr)
            pos = int(t * sr)
            end = min(pos + len(wave), n_total)
            mix[pos:end] += wave[:end - pos] * 0.5
            t += chord_dur

        # ── Melody layer ──────────────────────────────────────────────────
        if "flute" in instruments:
            mel = _melody_track(scale_notes, bpm, duration, "flute", sr)
            mix[:len(mel)] += mel[:n_total] * 0.55
        elif "piano" in instruments:
            mel = _melody_track(scale_notes, bpm, duration, "piano", sr)
            mix[:len(mel)] += mel[:n_total] * 0.45

        # ── Drone layer ───────────────────────────────────────────────────
        if "drone" in instruments:
            drone_wave = _note(_ROOT_MIDI, duration, "drone", sr)
            mix[:len(drone_wave)] += drone_wave[:n_total] * 0.3

        # ── Percussion layer ──────────────────────────────────────────────
        if "percussion" in instruments:
            perc = _percussion_track(bpm, duration, sr)
            mix[:len(perc)] += perc[:n_total] * 0.45

        # ── Brass stabs (adventure) ───────────────────────────────────────
        if "brass" in instruments:
            brass_mel = _melody_track(scale_notes, bpm * 0.5, duration, "brass", sr)
            mix[:len(brass_mel)] += brass_mel[:n_total] * 0.35

        # ── Fade in / out ─────────────────────────────────────────────────
        fade_samples = int(sr * 2.5)
        if n_total > fade_samples * 2:
            mix[:fade_samples] *= np.linspace(0, 1, fade_samples)
            mix[-fade_samples:] *= np.linspace(1, 0, fade_samples)

        # ── Normalise ─────────────────────────────────────────────────────
        peak = np.max(np.abs(mix))
        if peak > 0:
            mix = mix / peak * profile["volume"]

        # ── Write WAV ─────────────────────────────────────────────────────
        sf.write(str(cache_path), mix, sr, subtype="PCM_16")
        logger.info("Procedural BGM saved: %s (%.1fs)", cache_path, duration)
        return cache_path

    except Exception as exc:
        logger.warning("Procedural BGM generation failed: %s", exc)
        return None
