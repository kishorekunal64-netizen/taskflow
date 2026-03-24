"""
video_assembler.py — Cinematic 4K video assembly for RAGAI Video Factory.

Cinematic features:
  - 24 fps (film standard)
  - 4K UHD output (3840×2160 landscape / 2160×3840 shorts)
  - Ken Burns with quintic ease-in-out + random pan direction
  - Subtle film grain (intensity 6) for texture
  - 2.39:1 anamorphic letterbox on landscape (cinema widescreen)
  - H.264 High profile, slow preset, CRF 16 (~20 Mbps)
  - 320k AAC audio
  - xfade cross-dissolve transitions between scenes
  - Music fade-in/out with per-style volume
"""

from __future__ import annotations

import logging
import random
import re
import shutil
import subprocess
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image

from models import (
    FFmpegNotFoundError,
    Language,
    PipelineConfig,
    QualityPreset,
    QUALITY_CONFIGS,
    Scene,
    VideoAssemblyError,
    VideoFormat,
    VisualStyle,
    RESOLUTIONS,
)
from style_detector import STYLE_COLOR_GRADE, STYLE_MUSIC_MAP
from music_selector import MusicSelector

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cinematic constants (quality-independent)
# ---------------------------------------------------------------------------

FPS = 24
KEN_BURNS_ZOOM_MIN = 1.02
KEN_BURNS_ZOOM_MAX = 1.10
FILM_GRAIN_INTENSITY = 6
LETTERBOX_RATIO = 2.39
TRANSITION_DURATION = 0.8
MUSIC_FADE_IN = 2.5
MUSIC_FADE_OUT = 4.0
AUDIO_BITRATE = "320k"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[\s\-]+", "_", text)
    text = re.sub(r"[^\w]", "", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "video"


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _quintic(t: float) -> float:
    """Ease-in-out quintic — smoother than cubic, true cinematic feel."""
    return t * t * t * (t * (6.0 * t - 15.0) + 10.0)


def _run_ffmpeg(cmd: List[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("FFmpeg failed (exit %d):\n%s", result.returncode, result.stderr)
        raise VideoAssemblyError(
            f"FFmpeg exited with code {result.returncode}.\nstderr:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# Intel QSV detection
# ---------------------------------------------------------------------------

_qsv_available: Optional[bool] = None  # cached after first check


def _check_qsv() -> bool:
    """Return True if FFmpeg h264_qsv encoder is available on this system."""
    global _qsv_available
    if _qsv_available is not None:
        return _qsv_available
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        _qsv_available = "h264_qsv" in result.stdout
    except Exception:
        _qsv_available = False
    if _qsv_available:
        logger.info("Intel QSV detected — hardware encoding enabled (h264_qsv)")
    else:
        logger.info("Intel QSV not available — using software encoding (libx264)")
    return _qsv_available


def _build_video_encode_args(preset: str, crf: int, use_qsv: bool) -> List[str]:
    """Return FFmpeg video codec arguments for QSV or software encoding."""
    if use_qsv:
        # QSV uses -global_quality instead of CRF; map CRF range (16–23) → ICQ quality (18–26)
        icq = max(18, min(int(crf * 1.1), 51))
        return [
            "-c:v", "h264_qsv",
            "-preset", "medium",          # QSV preset: veryfast/faster/medium/slow
            "-global_quality", str(icq),
            "-look_ahead", "1",
        ]
    return [
        "-c:v", "libx264",
        "-profile:v", "high", "-level", "5.1",
        "-preset", preset,
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
    ]


def _probe_duration(path: Path) -> float:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(probe.stdout.strip())
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# VideoAssembler
# ---------------------------------------------------------------------------

class VideoAssembler:

    def __init__(
        self,
        work_dir: Path,
        music_dir: Path,
        output_dir: Path,
        quality: QualityPreset = QualityPreset.CINEMA,
    ) -> None:
        if shutil.which("ffmpeg") is None:
            raise FFmpegNotFoundError(
                "FFmpeg not found on PATH.\n"
                "  Windows: https://ffmpeg.org/download.html (add bin/ to PATH)\n"
                "  macOS  : brew install ffmpeg\n"
                "  Ubuntu : sudo apt install ffmpeg"
            )
        self.work_dir = Path(work_dir)
        self.music_dir = Path(music_dir)
        self.output_dir = Path(output_dir)
        self._quality = quality
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("VideoAssembler ready (work=%s out=%s quality=%s)", self.work_dir, self.output_dir, quality)

    # ------------------------------------------------------------------
    # Ken Burns — cinematic 4K frames
    # ------------------------------------------------------------------

    def _ken_burns_frames(
        self, scene: Scene, fmt: VideoFormat, W_out: int, H_out: int
    ) -> List[np.ndarray]:
        """Generate cinematic Ken Burns frames at the requested output resolution."""
        n_frames = max(1, round(scene.duration_seconds * FPS))

        img = Image.open(scene.image_path).convert("RGB")

        # Upscale source to at least 4K before cropping — preserves sharpness
        scale = max(W_out / img.width, H_out / img.height) * KEN_BURNS_ZOOM_MAX * 1.05
        src_w = int(img.width * scale)
        src_h = int(img.height * scale)
        img = img.resize((src_w, src_h), Image.LANCZOS)
        arr = np.array(img, dtype=np.uint8)

        zoom_start = random.uniform(KEN_BURNS_ZOOM_MIN, KEN_BURNS_ZOOM_MAX - 0.04)
        zoom_end = random.uniform(zoom_start + 0.02, KEN_BURNS_ZOOM_MAX)

        # 8 compass pan directions
        directions = [
            (0.0, 0.0, 1.0, 1.0),   # TL → BR
            (1.0, 0.0, 0.0, 1.0),   # TR → BL
            (0.0, 1.0, 1.0, 0.0),   # BL → TR
            (1.0, 1.0, 0.0, 0.0),   # BR → TL
            (0.5, 0.0, 0.5, 1.0),   # top → bottom
            (0.5, 1.0, 0.5, 0.0),   # bottom → top
            (0.0, 0.5, 1.0, 0.5),   # left → right
            (1.0, 0.5, 0.0, 0.5),   # right → left
        ]
        px0, py0, px1, py1 = random.choice(directions)

        # Letterbox bar height (landscape only)
        bar_h = 0
        if fmt == VideoFormat.LANDSCAPE:
            bar_h = max(0, int(H_out * (1.0 - (W_out / LETTERBOX_RATIO) / H_out) / 2))

        rng = np.random.default_rng(scene.number)
        frames: List[np.ndarray] = []

        for i in range(n_frames):
            t = i / max(n_frames - 1, 1)
            te = _quintic(t)

            zoom = _lerp(zoom_start, zoom_end, te)
            crop_w = int(src_w / zoom)
            crop_h = int(src_h / zoom)
            crop_w = min(crop_w, src_w)
            crop_h = min(crop_h, src_h)

            max_x = max(src_w - crop_w, 0)
            max_y = max(src_h - crop_h, 0)
            x = int(_lerp(px0, px1, te) * max_x)
            y = int(_lerp(py0, py1, te) * max_y)

            cropped = arr[y:y + crop_h, x:x + crop_w]
            frame = np.array(
                Image.fromarray(cropped).resize((W_out, H_out), Image.LANCZOS),
                dtype=np.uint8,
            )

            # Film grain
            if FILM_GRAIN_INTENSITY > 0:
                grain = rng.integers(
                    -FILM_GRAIN_INTENSITY, FILM_GRAIN_INTENSITY + 1,
                    size=frame.shape, dtype=np.int16,
                )
                frame = np.clip(frame.astype(np.int16) + grain, 0, 255).astype(np.uint8)

            # Letterbox
            if bar_h > 0:
                frame[:bar_h, :] = 0
                frame[H_out - bar_h:, :] = 0

            frames.append(frame)

        return frames

    # ------------------------------------------------------------------
    # Scene clip encoder
    # ------------------------------------------------------------------

    def _write_scene_clip(
        self, scene: Scene, frames: List[np.ndarray],
        preset: str, crf: int,
    ) -> Path:
        """Encode Ken Burns frames + scene audio → H.264 clip at given quality.

        Uses Intel QSV hardware encoding when available, falls back to libx264.
        """
        frame_dir = self.work_dir / f"scene_{scene.number:03d}_frames"
        frame_dir.mkdir(parents=True, exist_ok=True)

        for idx, frame in enumerate(frames):
            Image.fromarray(frame).save(str(frame_dir / f"frame_{idx:04d}.png"))

        clip_path = self.work_dir / f"clip_{scene.number:03d}.mp4"
        use_qsv = _check_qsv()
        video_args = _build_video_encode_args(preset, crf, use_qsv)

        cmd = (
            ["ffmpeg", "-y",
             "-framerate", str(FPS),
             "-i", str(frame_dir / "frame_%04d.png"),
             "-i", str(scene.audio_path)]
            + video_args
            + ["-c:a", "aac", "-b:a", AUDIO_BITRATE,
               "-shortest",
               str(clip_path)]
        )

        try:
            _run_ffmpeg(cmd)
        except VideoAssemblyError:
            if use_qsv:
                # QSV failed at runtime — fall back to software
                logger.warning("QSV encode failed for scene %d — retrying with libx264", int(scene.number))
                global _qsv_available
                _qsv_available = False
                sw_args = _build_video_encode_args(preset, crf, False)
                cmd = (
                    ["ffmpeg", "-y",
                     "-framerate", str(FPS),
                     "-i", str(frame_dir / "frame_%04d.png"),
                     "-i", str(scene.audio_path)]
                    + sw_args
                    + ["-c:a", "aac", "-b:a", AUDIO_BITRATE,
                       "-shortest",
                       str(clip_path)]
                )
                _run_ffmpeg(cmd)
            else:
                raise

        logger.debug("Scene clip (%s): %s", "QSV" if use_qsv else "SW", clip_path)
        return clip_path

    # ------------------------------------------------------------------
    # Concat with xfade cross-dissolve
    # ------------------------------------------------------------------

    def _concat_clips(self, clip_paths: List[Path], preset: str, crf: int) -> Path:
        """Concatenate clips with xfade cross-dissolve transitions."""
        if len(clip_paths) == 1:
            return clip_paths[0]

        output_path = self.work_dir / "concat.mp4"
        inputs: List[str] = []
        for p in clip_paths:
            inputs += ["-i", str(p)]

        durations = [_probe_duration(p) for p in clip_paths]

        # Build xfade video filter chain
        filter_parts: List[str] = []
        n = len(clip_paths)
        cumulative = 0.0
        prev_label = "0:v"

        for i in range(1, n):
            cumulative += durations[i - 1] - TRANSITION_DURATION
            out_label = f"xf{i}"
            filter_parts.append(
                f"[{prev_label}][{i}:v]xfade=transition=fade"
                f":duration={TRANSITION_DURATION}:offset={cumulative:.4f}[{out_label}]"
            )
            prev_label = out_label

        # Audio concat
        audio_inputs = "".join(f"[{i}:a]" for i in range(n))
        audio_filter = f"{audio_inputs}concat=n={n}:v=0:a=1[aout]"

        filter_complex = ";".join(filter_parts) + ";" + audio_filter

        use_qsv = _check_qsv()
        video_args = _build_video_encode_args(preset, crf, use_qsv)

        cmd = (
            ["ffmpeg", "-y"]
            + inputs
            + ["-filter_complex", filter_complex,
               "-map", f"[{prev_label}]",
               "-map", "[aout]"]
            + video_args
            + ["-c:a", "aac", "-b:a", AUDIO_BITRATE,
               str(output_path)]
        )

        try:
            _run_ffmpeg(cmd)
        except VideoAssemblyError:
            if use_qsv:
                logger.warning("QSV concat failed — retrying with libx264")
                global _qsv_available
                _qsv_available = False
                sw_args = _build_video_encode_args(preset, crf, False)
                cmd = (
                    ["ffmpeg", "-y"]
                    + inputs
                    + ["-filter_complex", filter_complex,
                       "-map", f"[{prev_label}]",
                       "-map", "[aout]"]
                    + sw_args
                    + ["-c:a", "aac", "-b:a", AUDIO_BITRATE,
                       str(output_path)]
                )
                _run_ffmpeg(cmd)
            else:
                raise

        logger.debug("Concat done (%s): %s", "QSV" if use_qsv else "SW", output_path)
        return output_path

    # ------------------------------------------------------------------
    # Music selection
    # ------------------------------------------------------------------

    def _select_music(self, style: VisualStyle, topic: str, custom_path: Optional[str] = None) -> Tuple[Optional[Path], str]:
        selector = MusicSelector(self.music_dir)
        return selector.select(topic, style, custom_path)

    def _mix_music(
        self,
        video_path: Path,
        music_path: Optional[Path],
        style: VisualStyle,
        topic: str,
        fmt: VideoFormat,
        timestamp: str,
        preset: str,
        bitrate: str,
    ) -> Path:
        """Apply color grade, mix music, final encode at selected quality bitrate."""
        slug = _slugify(topic)
        output_path = self.output_dir / f"{slug}_{timestamp}.mp4"
        color_grade = STYLE_COLOR_GRADE.get(style, "null")
        use_qsv = _check_qsv()

        # QSV uses -b:v (bitrate) rather than CRF for final output
        if use_qsv:
            video_encode = [
                "-c:v", "h264_qsv",
                "-preset", "medium",
                "-b:v", bitrate,
                "-look_ahead", "1",
            ]
        else:
            video_encode = [
                "-c:v", "libx264", "-profile:v", "high", "-level", "5.1",
                "-preset", preset, "-b:v", bitrate,
                "-pix_fmt", "yuv420p",
            ]

        if music_path and music_path.exists():
            video_duration = _probe_duration(video_path)
            fade_out_start = max(0.0, video_duration - MUSIC_FADE_OUT)

            filter_complex = (
                f"[0:v]{color_grade}[vout];"
                f"[1:a]aloop=loop=-1:size=2e+09,volume=0.10,"
                f"afade=t=in:d={MUSIC_FADE_IN},"
                f"afade=t=out:st={fade_out_start:.4f}:d={MUSIC_FADE_OUT}[amusic];"
                f"[0:a][amusic]amix=inputs=2:duration=first[aout]"
            )
            cmd = (
                ["ffmpeg", "-y",
                 "-i", str(video_path),
                 "-i", str(music_path),
                 "-filter_complex", filter_complex,
                 "-map", "[vout]", "-map", "[aout]"]
                + video_encode
                + ["-c:a", "aac", "-b:a", AUDIO_BITRATE,
                   "-movflags", "+faststart",
                   "-metadata", f"title={topic}",
                   "-metadata", f"comment=Generated by RAGAI at {timestamp}",
                   str(output_path)]
            )
        else:
            filter_complex = f"[0:v]{color_grade}[vout]"
            cmd = (
                ["ffmpeg", "-y",
                 "-i", str(video_path),
                 "-filter_complex", filter_complex,
                 "-map", "[vout]", "-map", "0:a"]
                + video_encode
                + ["-c:a", "aac", "-b:a", AUDIO_BITRATE,
                   "-movflags", "+faststart",
                   "-metadata", f"title={topic}",
                   str(output_path)]
            )

        try:
            _run_ffmpeg(cmd)
        except VideoAssemblyError:
            if use_qsv:
                logger.warning("QSV final encode failed — retrying with libx264")
                global _qsv_available
                _qsv_available = False
                return self._mix_music(
                    video_path, music_path, style, topic,
                    fmt, timestamp, preset, bitrate,
                )
            raise

        logger.info("Final video (%s, %s): %s", "QSV" if use_qsv else "SW", bitrate, output_path)
        return output_path

    # ------------------------------------------------------------------
    # Main assemble
    # ------------------------------------------------------------------

    def assemble(self, scenes: List[Scene], config: PipelineConfig) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        style = config.style if config.style != VisualStyle.AUTO else VisualStyle.DYNAMIC_EPIC

        # Resolve quality config
        quality = getattr(config, "quality", QualityPreset.CINEMA)
        qcfg = QUALITY_CONFIGS.get(quality, QUALITY_CONFIGS[QualityPreset.CINEMA])
        fmt_key = "landscape" if config.format == VideoFormat.LANDSCAPE else "shorts"
        W_out, H_out = qcfg[fmt_key]
        preset = qcfg["preset"]
        crf = qcfg["crf"]
        bitrate = qcfg[f"bitrate_{fmt_key}"]

        logger.info(
            "Quality: %s — %dx%d preset=%s crf=%d bitrate=%s",
            quality, W_out, H_out, preset, crf, bitrate,
        )

        clip_paths: List[Path] = []
        for scene in scenes:
            logger.info("Ken Burns frames — scene %d/%d", scene.number, len(scenes))
            frames = self._ken_burns_frames(scene, config.format, W_out, H_out)
            clip_path = self._write_scene_clip(scene, frames, preset, crf)
            scene.clip_path = clip_path
            clip_paths.append(clip_path)

        logger.info("Concatenating %d clips with xfade", len(clip_paths))
        concat_path = self._concat_clips(clip_paths, preset, crf)

        music_path, music_reason = self._select_music(
            style, config.topic, getattr(config, "custom_music_path", None)
        )
        logger.info("BGM: %s", music_reason)
        output_path = self._mix_music(
            concat_path, music_path, style, config.topic,
            config.format, timestamp, preset, bitrate,
        )

        self._generate_thumbnail(scenes, config.format, config.topic)
        self._write_metadata_txt(config.topic, config.language, scenes)
        return output_path

    # ------------------------------------------------------------------
    # Thumbnail + metadata
    # ------------------------------------------------------------------

    def _generate_thumbnail(
        self, scenes: List[Scene], fmt: VideoFormat, topic: str = "video"
    ) -> Path:
        slug = _slugify(topic)
        thumbnail_path = self.output_dir / f"{slug}_thumbnail.jpg"
        mid = scenes[len(scenes) // 2]
        img = Image.open(mid.image_path).convert("RGB")
        img = img.resize((1280, 720), Image.LANCZOS)
        img.save(str(thumbnail_path), "JPEG", quality=92)
        logger.info("Thumbnail: %s", thumbnail_path)
        return thumbnail_path

    def _write_metadata_txt(
        self, topic: str, language: Language, scenes: List[Scene]
    ) -> Path:
        slug = _slugify(topic)
        metadata_path = self.output_dir / f"{slug}_metadata.txt"
        title = f"Title: {topic}"
        snippets = [s.narration[:100] for s in scenes[:3] if s.narration]
        description = f"Watch this cinematic 4K video about '{topic}'. " + " ".join(snippets)

        topic_words = re.sub(r"[^\w\s]", "", topic).split()
        base_tags = [w.lower() for w in topic_words if len(w) > 2]
        fixed_tags = ["ragai", "aiVideo", "cinematic4K", "shorts", language.value]
        all_tags = base_tags + fixed_tags
        seen: set = set()
        unique: List[str] = []
        for t in all_tags:
            if t not in seen:
                seen.add(t)
                unique.append(t)
        while len(unique) < 10:
            unique.append(f"video{len(unique)}")
        hashtags = " ".join(f"#{t}" for t in unique[:10])

        metadata_path.write_text(f"{title}\n\n{description}\n\n{hashtags}\n", encoding="utf-8")
        logger.info("Metadata: %s", metadata_path)
        return metadata_path
