"""
auto_pipeline.py — Fully automated compilation pipeline for RAGAI Editor V2.

When enabled, watches for new clips, groups them by topic, and auto-exports
a compilation when the batch threshold is reached.

Workflow:
  collect clips → group by topic → generate hook → assemble → thumbnail → export
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from clip_manager import Clip, ClipManager, STATE_EXPORTED
from timeline import TimelineCanvas, TimelineEntry
from topic_engine import TopicEngine, CompilationGroup
from variation_engine import VariationEngine

logger = logging.getLogger(__name__)


class AutoPipeline:
    """
    Manages auto-mode: accumulates new clips and triggers a full
    compilation export when batch_size is reached.
    """

    def __init__(
        self,
        clip_manager: ClipManager,
        timeline: TimelineCanvas,
        compiled_dir: Path = Path("compiled"),
        music_dir: Path = Path("music"),
        batch_size: int = 3,
        groq_api_key: str = "",
        on_export_trigger: Optional[Callable] = None,
        on_status_update: Optional[Callable[[str], None]] = None,
    ):
        self._cm = clip_manager
        self._timeline = timeline
        self._compiled_dir = Path(compiled_dir)
        self._music_dir = Path(music_dir)
        self._batch_size = batch_size
        self._groq_api_key = groq_api_key
        self._on_export_trigger = on_export_trigger
        self._on_status = on_status_update
        self._enabled = False
        self._pending: List[Clip] = []
        self._lock = threading.Lock()
        self._topic_engine = TopicEngine()
        self._variation = VariationEngine()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool):
        self._enabled = value
        if value:
            self._update_status()
        else:
            self._post_status("Auto Mode: OFF")

    def set_batch_size(self, size: int):
        self._batch_size = max(1, size)
        self._update_status()

    def on_new_clip(self, clip: Clip):
        """Called when a new clip is imported. Only acts if auto mode is ON."""
        if not self._enabled:
            return
        with self._lock:
            self._pending.append(clip)
            count = len(self._pending)
            remaining = self._batch_size - count

        if remaining > 0:
            self._post_status(
                f"Auto Mode: {count}/{self._batch_size} clips — waiting for {remaining} more…"
            )
        else:
            threading.Thread(target=self._run_compilation, daemon=True).start()

    def clear_pending(self):
        with self._lock:
            self._pending.clear()
        self._update_status()

    # ------------------------------------------------------------------
    # Full compilation workflow
    # ------------------------------------------------------------------

    def _run_compilation(self):
        """Full auto-compilation: group → hook → assemble → thumbnail → export."""
        with self._lock:
            batch = list(self._pending[: self._batch_size])
            self._pending = self._pending[self._batch_size :]

        self._post_status(f"Auto Mode: starting compilation with {len(batch)} clips…")
        logger.info("Auto pipeline: %d clips", len(batch))

        # 1. Group clips by topic
        group = self._topic_engine.best_group(batch)
        if group:
            clips = self._variation.shuffle_clips(group.clips)
            title = group.title
            self._post_status(f"Auto Mode: group '{title}' ({len(clips)} clips)")
        else:
            clips = self._variation.shuffle_clips(batch)
            title = "RAGAI Compilation"
            self._post_status("Auto Mode: no topic group — using all clips")

        # 2. Build timeline entries with varied transitions
        transitions = self._variation.assign_transitions(len(clips))
        entries: List[TimelineEntry] = []
        for clip, trans in zip(clips, transitions):
            entries.append(TimelineEntry(clip=clip, transition=trans))

        # 3. Generate hook
        hook_path: Optional[Path] = None
        if self._groq_api_key:
            try:
                from hook_generator import HookGenerator
                self._post_status("Auto Mode: generating hook narration…")
                hg = HookGenerator(
                    groq_api_key=self._groq_api_key,
                    music_dir=self._music_dir,
                )
                hook_path = self._compiled_dir / f"hook_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
                self._compiled_dir.mkdir(parents=True, exist_ok=True)
                hg.generate(
                    compilation_title=title,
                    clip_count=len(clips),
                    output_path=hook_path,
                    hook_style=self._variation.pick_hook_style(),
                )
            except Exception as exc:
                logger.warning("Hook generation failed: %s — skipping", exc)
                hook_path = None

        # 4. Generate outro
        outro_path: Optional[Path] = None
        try:
            from outro_generator import OutroGenerator
            self._post_status("Auto Mode: generating outro clip…")
            og = OutroGenerator(music_dir=self._music_dir)
            outro_path = self._compiled_dir / f"outro_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            og.generate(outro_path, text_index=self._variation.pick_outro_variant())
        except Exception as exc:
            logger.warning("Outro generation failed: %s — skipping", exc)
            outro_path = None

        # 5. Assemble
        self._post_status("Auto Mode: assembling compilation video…")
        try:
            from assembler import Assembler
            asm = Assembler()

            def _progress(pct, msg):
                self._post_status(f"Auto Mode: {msg} ({int(pct * 100)}%)")

            def _done(out_path: Path):
                self._post_status(f"Auto Mode: export complete → {out_path.name}")
                self._generate_thumbnail(clips[0], title, out_path)
                # Mark clips as exported
                for clip in clips:
                    self._cm.set_state(clip.clip_id, STATE_EXPORTED)
                # Clear timeline
                self._timeline.clear()
                if self._on_export_trigger:
                    self._on_export_trigger()

            def _error(exc: Exception):
                self._post_status(f"Auto Mode: export failed — {exc}")
                logger.error("Auto pipeline export error: %s", exc)

            asm.export(
                entries=entries,
                topic=title,
                output_format="YouTube Long",
                quality="Standard 1080p",
                add_fade=True,
                hook_path=hook_path,
                outro_path=outro_path,
                on_progress=_progress,
                on_done=_done,
                on_error=_error,
            )
        except Exception as exc:
            logger.error("Assembler init failed: %s", exc)
            self._post_status(f"Auto Mode: assembler error — {exc}")

    def _generate_thumbnail(self, clip: Clip, title: str, video_path: Path):
        try:
            from thumbnail_generator import ThumbnailGenerator
            tg = ThumbnailGenerator()
            thumb_out = video_path.parent / (video_path.stem + "_thumbnail.jpg")
            tg.generate(Path(clip.filepath), title, thumb_out)
            logger.info("Auto thumbnail: %s", thumb_out)
        except Exception as exc:
            logger.warning("Auto thumbnail failed: %s", exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_status(self):
        if not self._enabled:
            return
        with self._lock:
            count = len(self._pending)
        remaining = self._batch_size - count
        self._post_status(
            f"Auto Mode: ON — {count}/{self._batch_size} clips ({remaining} more to export)"
        )

    def _post_status(self, msg: str):
        logger.info(msg)
        if self._on_status:
            self._on_status(msg)
