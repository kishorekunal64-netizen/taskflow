"""
audio_transcriber.py — Groq Whisper audio transcription and audio splitting for RAGAI.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List

import requests

from models import AudioTranscriptionError

logger = logging.getLogger(__name__)


@dataclass
class WordTimestamp:
    word: str
    start: float  # seconds from start of audio
    end: float    # seconds from start of audio


class AudioTranscriber:
    GROQ_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
    SUPPORTED_FORMATS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
    MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def _validate_audio_path(self, audio_path: Path) -> None:
        """Validate extension and readability; raise AudioTranscriptionError on failure."""
        if audio_path.suffix.lower() not in self.SUPPORTED_FORMATS:
            raise AudioTranscriptionError(
                f"Unsupported audio format '{audio_path.suffix}'. "
                f"Supported: {', '.join(sorted(self.SUPPORTED_FORMATS))}"
            )
        if not audio_path.exists():
            raise AudioTranscriptionError(f"Audio file not found: {audio_path}")
        if not audio_path.is_file():
            raise AudioTranscriptionError(f"Path is not a file: {audio_path}")
        try:
            audio_path.open("rb").close()
        except OSError as exc:
            raise AudioTranscriptionError(f"Audio file is not readable: {audio_path}") from exc

    def _post_to_whisper(self, audio_path: Path, extra_data: dict | None = None) -> dict:
        """POST audio to Groq Whisper API and return parsed JSON response."""
        data = {"model": "whisper-large-v3"}
        if extra_data:
            data.update(extra_data)

        headers = {"Authorization": f"Bearer {self.api_key}"}

        with audio_path.open("rb") as audio_file:
            files = {"file": (audio_path.name, audio_file, "application/octet-stream")}
            response = requests.post(
                self.GROQ_WHISPER_URL,
                headers=headers,
                data=data,
                files=files,
                timeout=120,
            )

        if not response.ok:
            raise AudioTranscriptionError(
                f"Groq Whisper API error {response.status_code}: {response.text}"
            )

        return response.json()

    def transcribe(self, audio_path: Path) -> str:
        """Submit audio to Groq Whisper; return full transcript string.

        Raises AudioTranscriptionError on API error or unreadable file.
        """
        self._validate_audio_path(audio_path)
        result = self._post_to_whisper(audio_path)
        return result.get("text", "")

    def get_word_timestamps(self, audio_path: Path) -> List[WordTimestamp]:
        """Return word-level timing data using verbose_json response format.

        Returns empty list if Whisper does not provide timestamps.
        """
        self._validate_audio_path(audio_path)
        result = self._post_to_whisper(audio_path, {"response_format": "verbose_json"})

        timestamps: List[WordTimestamp] = []
        for segment in result.get("segments", []):
            for word_data in segment.get("words", []):
                timestamps.append(
                    WordTimestamp(
                        word=word_data.get("word", ""),
                        start=float(word_data.get("start", 0.0)),
                        end=float(word_data.get("end", 0.0)),
                    )
                )

        return timestamps


from models import Scene


class AudioSplitter:
    def __init__(self) -> None:
        pass

    def split(self, audio_path: Path, scenes: List[Scene], work_dir: Path) -> List[Scene]:
        """Split audio_path into per-scene segments based on scene.duration_seconds.

        Assigns scene.audio_path for each scene. Pads the final segment with silence
        if the source audio is shorter than the total scene duration.
        Returns the mutated scenes list.
        """
        try:
            from pydub import AudioSegment
        except ImportError as exc:
            raise ImportError(
                "pydub is required for audio splitting. Run: pip install pydub"
            ) from exc

        audio = AudioSegment.from_file(str(audio_path))
        audio_duration_ms = len(audio)

        cursor_ms = 0
        for scene in scenes:
            segment_ms = int(scene.duration_seconds * 1000)
            start_ms = cursor_ms
            end_ms = cursor_ms + segment_ms

            if start_ms >= audio_duration_ms:
                # Source audio fully exhausted — entire segment is silence
                segment = AudioSegment.silent(duration=segment_ms)
            elif end_ms > audio_duration_ms:
                # Partial audio available — pad remainder with silence
                available = audio[start_ms:audio_duration_ms]
                padding = AudioSegment.silent(duration=end_ms - audio_duration_ms)
                segment = available + padding
            else:
                segment = audio[start_ms:end_ms]

            dest = work_dir / f"scene_{scene.number:03d}_audio.mp3"
            segment.export(str(dest), format="mp3")
            scene.audio_path = dest
            logger.info("Exported audio segment for scene %d: %s", scene.number, dest)

            cursor_ms = end_ms

        return scenes
