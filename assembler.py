"""
assembler.py — Video Builder for RAGAI Editor V2.

Joins hook + timeline clips + outro into a final compiled video using FFmpeg.
Supports transitions, QSV hardware encoding, multiple output qualities.
Output saved to ./compiled/RAGAI_Compilation_{topic}_{date}.mp4
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from clip_manager import Clip
from timeline import TimelineEntry

logger = logging.getLogger(__name__)

COMPILED_DIR = Path("compiled")

FORMAT_PRESETS = {
    "YouTube Long":    {"vf": "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2", "ar": "44100"},
    "YouTube Shorts":  {"vf": "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2", "ar": "44100"},
    "Instagram Reels": {"vf": "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2", "ar": "44100"},
}

QUALITY_PRESETS = {
    "Standard 1080p": {"crf": "20", "preset": "medium", "maxrate": "8M"},
    "High 1440p":     {"crf": "18", "preset": "slow",   "maxrate": "12M"},
    "Cinema 4K":      {"crf": "16", "preset": "slow",   "maxrate": "20M"},
}


def _ffmpeg_path() -> str:
    p = shutil.which("ffmpeg")
    if p:
        return p
    local = Path("ffmpeg-8.1-essentials_build") / "bin" / "ffmpeg.exe"
    return str(local) if local.exists() else "ffmpeg"


def check_qsv() -> bool:
    ffmpeg = _ffmpeg_path()
    try:
        r = subprocess.run([ffmpeg, "-encoders"], capture_output=True, text=True, timeout=10)
        return "h264_qsv" in r.stdout
    except Exception:
        return False


def _probe_duration(path: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _parse_transition(name: str):
    mapping = {
        "Dissolve 0.5s": (0.5, "dissolve"),
        "Dissolve 1s":   (1.0, "dissolve"),
        "Dissolve 2s":   (2.0, "dissolve"),
        "Fade Black 1s": (1.0, "fade"),
    }
    return mapping.get(name, (0.0, "fade"))


class Assembler:
    """Builds compiled video: hook + timeline clips + outro."""

    def __init__(self):
        self._ffmpeg = _ffmpeg_path()
        self._qsv = check_qsv()
        COMPILED_DIR.mkdir(parents=True, exist_ok=True)

    def is_ready(self) -> bool:
        return shutil.which("ffmpeg") is not None or Path(self._ffmpeg).exists()

    def export(
        self,
        entries: List[TimelineEntry],
        topic: str = "Compilation",
        output_format: str = "YouTube Long",
        quality: str = "Standard 1080p",
        add_fade: bool = True,
        hook_path: Optional[Path] = None,
        outro_path: Optional[Path] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
        on_done: Optional[Callable[[Path], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ):
        """Start export in a background thread."""
        if not self.is_ready():
            if on_error:
                on_error(RuntimeError("FFmpeg not found. Install FFmpeg and add it to PATH."))
            return
        if not entries:
            if on_error:
                on_error(ValueError("Timeline is empty."))
            return

        def _run():
            try:
                out = self._do_export(entries, topic, output_format, quality,
                                      add_fade, hook_path, outro_path, on_progress)
                if on_done:
                    on_done(out)
            except Exception as exc:
                logger.exception("Export failed: %s", exc)
                if on_error:
                    on_error(exc)

        threading.Thread(target=_run, daemon=True).start()

    def _do_export(self, entries, topic, output_format, quality,
                   add_fade, hook_path, outro_path, on_progress) -> Path:
        fmt  = FORMAT_PRESETS.get(output_format, FORMAT_PRESETS["YouTube Long"])
        qual = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["Standard 1080p"])
        total = len(entries)

        with tempfile.TemporaryDirectory(prefix="ragai_editor_") as tmp:
            tmp_path = Path(tmp)
            processed: List[Path] = []

            # Normalise hook
            if hook_path and hook_path.exists():
                if on_progress:
                    on_progress(0.02, "Processing hook clip…")
                hook_norm = tmp_path / "hook_norm.mp4"
                self._normalise_clip(hook_path, hook_norm, fmt, qual)
                processed.append(hook_norm)

            # Normalise timeline clips
            for i, entry in enumerate(entries):
                if on_progress:
                    on_progress((i + 1) / (total + 3), f"Processing clip {i + 1}/{total}…")
                out_clip = tmp_path / f"clip_{i:03d}.mp4"
                self._process_clip(entry, out_clip, fmt, qual)
                processed.append(out_clip)

            # Normalise outro
            if outro_path and outro_path.exists():
                if on_progress:
                    on_progress((total + 1) / (total + 3), "Processing outro clip…")
                outro_norm = tmp_path / "outro_norm.mp4"
                self._normalise_clip(outro_path, outro_norm, fmt, qual)
                processed.append(outro_norm)

            if on_progress:
                on_progress((total + 2) / (total + 3), "Joining clips…")

            joined = self._join_clips(processed, entries, tmp_path, fmt, qual, add_fade,
                                      has_hook=hook_path is not None,
                                      has_outro=outro_path is not None)

            # Move to compiled/
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_topic = "".join(c if c.isalnum() or c in "_- " else "" for c in topic)[:30].strip().replace(" ", "_")
            final = COMPILED_DIR / f"RAGAI_Compilation_{safe_topic}_{ts}.mp4"
            shutil.move(str(joined), str(final))

        if on_progress:
            on_progress(1.0, "Done")
        logger.info("Export complete: %s", final)
        return final

    def _normalise_clip(self, src: Path, out: Path, fmt: dict, qual: dict):
        """Scale/pad a clip to target format without trim."""
        cmd = [self._ffmpeg, "-y", "-i", str(src),
               "-vf", fmt["vf"], "-ar", fmt["ar"], "-ac", "2"]
        cmd += self._encoder_args(qual)
        cmd += ["-c:a", "aac", "-b:a", "192k", str(out)]
        subprocess.run(cmd, capture_output=True, check=True, timeout=300)

    def _process_clip(self, entry: TimelineEntry, out: Path, fmt: dict, qual: dict):
        clip = entry.clip
        cmd = [self._ffmpeg, "-y"]
        t_in  = clip.trim_in  if clip.trim_in  >= 0 else 0.0
        t_out = clip.trim_out if clip.trim_out >= 0 else clip.duration
        if t_in > 0:
            cmd += ["-ss", str(t_in)]
        cmd += ["-i", clip.filepath]
        if t_out < clip.duration:
            cmd += ["-t", str(t_out - t_in)]
        cmd += ["-vf", fmt["vf"], "-ar", fmt["ar"], "-ac", "2"]
        cmd += self._encoder_args(qual)
        cmd += ["-c:a", "aac", "-b:a", "192k", str(out)]
        subprocess.run(cmd, capture_output=True, check=True, timeout=600)

    def _encoder_args(self, qual: dict) -> List[str]:
        if self._qsv:
            return ["-c:v", "h264_qsv", "-global_quality", qual["crf"]]
        return ["-c:v", "libx264", "-crf", qual["crf"],
                "-preset", qual["preset"], "-maxrate", qual["maxrate"],
                "-bufsize", "16M", "-pix_fmt", "yuv420p"]

    def _join_clips(self, clips, entries, tmp, fmt, qual, add_fade,
                    has_hook=False, has_outro=False) -> Path:
        out = tmp / "joined.mp4"
        # Determine which entries have transitions (skip hook/outro indices)
        offset = 1 if has_hook else 0
        entry_slice = entries  # transitions come from timeline entries

        has_transitions = any(e.transition != "Cut" for e in entry_slice[1:])

        if not has_transitions:
            list_file = tmp / "concat.txt"
            list_file.write_text("\n".join(f"file '{p}'" for p in clips), encoding="utf-8")
            cmd = [self._ffmpeg, "-y", "-f", "concat", "-safe", "0",
                   "-i", str(list_file), "-c", "copy", str(out)]
            subprocess.run(cmd, capture_output=True, check=True, timeout=3600)
        else:
            inputs = []
            for p in clips:
                inputs += ["-i", str(p)]
            filter_parts = []
            prev_v, prev_a = "[0:v]", "[0:a]"
            cumulative = 0.0
            for i in range(1, len(clips)):
                dur_prev = _probe_duration(clips[i - 1])
                cumulative += dur_prev
                # Get transition from entry if available
                entry_idx = i - offset
                if 0 <= entry_idx < len(entry_slice):
                    xfade_dur, xfade_type = _parse_transition(entry_slice[entry_idx].transition)
                else:
                    xfade_dur, xfade_type = 0.5, "dissolve"
                if xfade_dur > 0:
                    cumulative -= xfade_dur
                    cur_v, cur_a = f"[v{i}]", f"[a{i}]"
                    filter_parts.append(
                        f"{prev_v}[{i}:v]xfade=transition={xfade_type}:duration={xfade_dur}:offset={cumulative:.3f}{cur_v}"
                    )
                    filter_parts.append(f"{prev_a}[{i}:a]acrossfade=d={xfade_dur}{cur_a}")
                    prev_v, prev_a = cur_v, cur_a
            filter_str = ";".join(filter_parts) if filter_parts else f"[0:v]{prev_v};[0:a]{prev_a}"
            cmd = ([self._ffmpeg, "-y"] + inputs +
                   ["-filter_complex", filter_str,
                    "-map", prev_v, "-map", prev_a,
                    "-c:v", "libx264", "-crf", qual["crf"], "-preset", qual["preset"],
                    "-c:a", "aac", "-b:a", "192k", str(out)])
            subprocess.run(cmd, capture_output=True, check=True, timeout=3600)

        if add_fade:
            faded = tmp / "faded.mp4"
            dur = _probe_duration(out)
            cmd = [self._ffmpeg, "-y", "-i", str(out),
                   "-vf", f"fade=t=in:st=0:d=1,fade=t=out:st={max(0, dur-1):.2f}:d=1",
                   "-af", f"afade=t=in:st=0:d=1,afade=t=out:st={max(0, dur-1):.2f}:d=1",
                   "-c:v", "libx264", "-crf", qual["crf"], "-preset", "fast",
                   "-c:a", "aac", "-b:a", "192k", str(faded)]
            subprocess.run(cmd, capture_output=True, check=True, timeout=600)
            return faded
        return out
