"""
mic_narration_recorder.py — Microphone narration recording for RAGAI.

Records user narration via microphone, saves as WAV, and normalizes
audio for use in the pipeline. When a narration file exists, the
pipeline bypasses voice_synthesizer.py entirely.

Dependencies (optional — graceful fallback if not installed):
  pip install sounddevice scipy

Output: narrations/story_NNN.wav

When enable_mic_narration_mode is False, this module is a no-op.
"""

from __future__ import annotations

import logging
import wave
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_NARRATIONS_DIR = Path("narrations")

# Recording defaults
DEFAULT_SAMPLE_RATE = 44100
DEFAULT_CHANNELS    = 1        # mono
DEFAULT_DTYPE       = "int16"


class MicNarrationRecorder:
    """Record microphone narration and save as normalized WAV."""

    def __init__(self, narrations_dir: Path = _NARRATIONS_DIR) -> None:
        self.narrations_dir = Path(narrations_dir)
        self.narrations_dir.mkdir(parents=True, exist_ok=True)
        self._sd = None   # sounddevice — lazy import

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        story_id: str,
        duration_seconds: float,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
    ) -> Path:
        """Record microphone input for `duration_seconds` and save as WAV.

        Args:
            story_id:         Identifier used in filename (e.g. "story_001").
            duration_seconds: How long to record.
            sample_rate:      Audio sample rate (default 44100 Hz).

        Returns:
            Path to the saved WAV file.

        Raises:
            RuntimeError if sounddevice is not installed.
        """
        sd = self._get_sounddevice()
        out_path = self.narrations_dir / f"{story_id}.wav"

        logger.info("MicRecorder: recording %.1fs at %dHz → %s",
                    duration_seconds, sample_rate, out_path)
        print(f"\n🎙  Recording {duration_seconds:.0f}s — speak now...")

        audio = sd.rec(
            int(duration_seconds * sample_rate),
            samplerate=sample_rate,
            channels=DEFAULT_CHANNELS,
            dtype=DEFAULT_DTYPE,
        )
        sd.wait()
        print("✅  Recording complete.")

        self._save_wav(audio, out_path, sample_rate)
        self._normalize(out_path)
        logger.info("MicRecorder: saved %s", out_path)
        return out_path

    def record_scenes(
        self,
        story_id: str,
        scene_count: int,
        seconds_per_scene: float = 15.0,
    ) -> list:
        """Record narration for each scene individually.

        Returns list of Paths, one per scene.
        """
        paths = []
        for i in range(1, scene_count + 1):
            input(f"\n▶  Press ENTER to record scene {i}/{scene_count}...")
            scene_id = f"{story_id}_scene_{i:03d}"
            path = self.record(scene_id, seconds_per_scene)
            paths.append(path)
        return paths

    def has_narration(self, story_id: str) -> bool:
        """Return True if a narration file already exists for this story."""
        return (self.narrations_dir / f"{story_id}.wav").exists()

    def get_narration_path(self, story_id: str) -> Optional[Path]:
        """Return path to existing narration WAV, or None."""
        p = self.narrations_dir / f"{story_id}.wav"
        return p if p.exists() else None

    def list_narrations(self) -> list:
        """Return all WAV files in narrations/."""
        return sorted(self.narrations_dir.glob("*.wav"))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_sounddevice(self):
        if self._sd is not None:
            return self._sd
        try:
            import sounddevice as sd
            self._sd = sd
            return sd
        except ImportError:
            raise RuntimeError(
                "sounddevice is not installed.\n"
                "Install it with: pip install sounddevice scipy\n"
                "Then retry mic recording."
            )

    def _save_wav(self, audio, path: Path, sample_rate: int) -> None:
        """Save numpy int16 array as WAV file."""
        try:
            import scipy.io.wavfile as wavfile
            wavfile.write(str(path), sample_rate, audio)
        except ImportError:
            # Fallback: use stdlib wave module
            import numpy as np
            with wave.open(str(path), "w") as wf:
                wf.setnchannels(DEFAULT_CHANNELS)
                wf.setsampwidth(2)  # int16 = 2 bytes
                wf.setframerate(sample_rate)
                wf.writeframes(audio.tobytes())

    def _normalize(self, wav_path: Path) -> None:
        """Normalize WAV audio to -3dBFS peak using scipy if available."""
        try:
            import numpy as np
            import scipy.io.wavfile as wavfile

            rate, data = wavfile.read(str(wav_path))
            peak = np.abs(data).max()
            if peak == 0:
                return
            # Target peak: 0.7 of int16 max (~-3dBFS)
            target = int(32767 * 0.7)
            normalized = (data.astype(np.float32) * (target / peak)).astype(np.int16)
            wavfile.write(str(wav_path), rate, normalized)
            logger.debug("MicRecorder: normalized %s (peak=%d → %d)", wav_path.name, peak, target)
        except Exception as exc:
            logger.warning("MicRecorder: normalization skipped — %s", exc)
