"""
models.py — Shared data models, enums, constants, and exceptions for RAGAI Video Factory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import uuid4


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Audience(str, Enum):
    FAMILY   = "family"
    CHILDREN = "children"
    ADULTS   = "adults"
    DEVOTEES = "devotees"


class Language(str, Enum):
    HI = "hi"   # Hindi
    TA = "ta"   # Tamil
    TE = "te"   # Telugu
    BN = "bn"   # Bengali
    GU = "gu"   # Gujarati
    MR = "mr"   # Marathi
    KN = "kn"   # Kannada
    ML = "ml"   # Malayalam
    PA = "pa"   # Punjabi
    UR = "ur"   # Urdu


class VideoFormat(str, Enum):
    LANDSCAPE = "landscape"   # 1920x1080
    SHORTS    = "shorts"      # 1080x1920


class VisualStyle(str, Enum):
    DYNAMIC_EPIC         = "DYNAMIC_EPIC"
    MYSTERY_DARK         = "MYSTERY_DARK"
    SPIRITUAL_DEVOTIONAL = "SPIRITUAL_DEVOTIONAL"
    PEACEFUL_NATURE      = "PEACEFUL_NATURE"
    ROMANTIC_DRAMA       = "ROMANTIC_DRAMA"
    ADVENTURE_ACTION     = "ADVENTURE_ACTION"
    AUTO                 = "AUTO"


class InputMode(str, Enum):
    TOPIC  = "topic"
    SCRIPT = "script"
    AUDIO  = "audio"
    IMAGE  = "image"


class QualityPreset(str, Enum):
    DRAFT    = "draft"     # 720p  — fast preview
    STANDARD = "standard"  # 1080p — social media
    HIGH     = "high"      # 1440p — YouTube
    CINEMA   = "cinema"    # 4K    — content creation


# ---------------------------------------------------------------------------
# Resolution constants
# ---------------------------------------------------------------------------

# Output resolutions per quality preset, per format (landscape, shorts)
QUALITY_CONFIGS: Dict[str, dict] = {
    QualityPreset.DRAFT: {
        "label":   "Draft 720p  (fast preview)",
        "landscape": (1280,  720),
        "shorts":    ( 720, 1280),
        "preset":  "fast",
        "crf":     23,
        "bitrate_landscape": "4000k",
        "bitrate_shorts":    "3000k",
    },
    QualityPreset.STANDARD: {
        "label":   "Standard 1080p  (social media)",
        "landscape": (1920, 1080),
        "shorts":    (1080, 1920),
        "preset":  "medium",
        "crf":     20,
        "bitrate_landscape": "8000k",
        "bitrate_shorts":    "6000k",
    },
    QualityPreset.HIGH: {
        "label":   "High 1440p  (YouTube)",
        "landscape": (2560, 1440),
        "shorts":    (1440, 2560),
        "preset":  "slow",
        "crf":     18,
        "bitrate_landscape": "12000k",
        "bitrate_shorts":    "9000k",
    },
    QualityPreset.CINEMA: {
        "label":   "4K Cinema  (content creation)",
        "landscape": (3840, 2160),
        "shorts":    (2160, 3840),
        "preset":  "slow",
        "crf":     16,
        "bitrate_landscape": "20000k",
        "bitrate_shorts":    "15000k",
    },
}

# Convenience: RESOLUTIONS still points to 4K (used as fallback)
RESOLUTIONS: Dict[VideoFormat, Tuple[int, int]] = {
    VideoFormat.LANDSCAPE: (3840, 2160),
    VideoFormat.SHORTS:    (2160, 3840),
}

# Leonardo AI max safe resolution (upscaled by FFmpeg)
IMAGE_RESOLUTIONS: Dict[VideoFormat, Tuple[int, int]] = {
    VideoFormat.LANDSCAPE: (1344, 768),
    VideoFormat.SHORTS:    (768, 1344),
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Scene:
    number: int
    narration: str                     # text in selected Language
    image_prompt: str                  # English prompt for Leonardo AI
    duration_seconds: float            # target scene duration
    image_path: Optional[Path] = None  # set after image generation
    audio_path: Optional[Path] = None  # set after voice synthesis
    clip_path: Optional[Path] = None   # set after Ken Burns encoding


@dataclass
class StyleConfig:
    style: VisualStyle
    prompt_modifiers: str    # appended to every image prompt
    color_grade_filter: str  # FFmpeg vf filter string
    music_filename: str      # filename in music/ dir
    color_palette: str       # human-readable descriptor


@dataclass
class PipelineConfig:
    topic: str
    script_file: Optional[str]
    audience: Audience
    language: Language
    style: VisualStyle
    format: VideoFormat
    character_names: Dict[str, str]
    output_dir: Path
    use_edge_tts: bool
    groq_api_key: str
    leonardo_api_key: str
    input_mode: InputMode = InputMode.TOPIC
    audio_file: Optional[str] = None
    image_files: List[str] = field(default_factory=list)
    image_context: str = ""
    scene_count: int = 8        # number of scenes to generate (5–15)
    quality: QualityPreset = QualityPreset.CINEMA
    target_duration_minutes: float = 0.0  # 0 = let LLM decide; >0 = target total length
    custom_music_path: Optional[str] = None  # override auto BGM selection
    hf_token: str = ""  # optional HuggingFace token for FLUX.1-schnell fallback


@dataclass
class PipelineResult:
    output_path: Path
    thumbnail_path: Path
    metadata_txt_path: Path
    scenes: List[Scene]
    elapsed_seconds: float


@dataclass
class PipelineContext:
    """Mutable state passed through pipeline stages."""
    config: PipelineConfig
    scenes: List[Scene] = field(default_factory=list)
    style_config: Optional[StyleConfig] = None
    work_dir: Path = field(default_factory=lambda: Path("tmp") / uuid4().hex)
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class RAGAIError(Exception):
    """Base exception for all RAGAI errors."""


class ConfigError(RAGAIError):
    """Raised when configuration is invalid or required keys are missing."""


class StoryGenerationError(RAGAIError):
    """Raised when the Groq LLM story generation stage fails."""


class ImageGenerationError(RAGAIError):
    """Raised when the Leonardo AI image generation stage fails."""


class VoiceSynthesisError(RAGAIError):
    """Raised when voice synthesis (Edge-TTS / gTTS) fails."""


class VideoAssemblyError(RAGAIError):
    """Raised when FFmpeg video assembly fails."""


class FFmpegNotFoundError(VideoAssemblyError):
    """Raised when FFmpeg is not found on the system PATH."""


class AudioTranscriptionError(RAGAIError):
    """Raised when Groq Whisper transcription fails."""


class ImageImportError(RAGAIError):
    """Raised when an uploaded image cannot be loaded or validated."""
