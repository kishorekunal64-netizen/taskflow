"""
auto_pipeline.py - Fully automated compilation pipeline for RAGAI Editor V3.

Upgraded: smart grouping by topic similarity + emotion arc + duration target.
Prevents same topic repeated (clip diversity). Supports 10/15/30 min targets.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from clip_manager import Clip, ClipManager, STATE_EXPORTED
from timeline import TimelineCanvas, TimelineEntry
from variation_engine import VariationEngine
from smart_compiler import SmartCompiler
from story_flow_optimizer import StoryFlowOptimizer
from clip_similarity import ClipSimilarityDetector

logger = logging.getLogger(__name__)


class AutoPipeline:
    """
    Manages auto-mode: accumulates new clips and triggers a full
    compilation export when enough clips are available for SmartCompiler.
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
        target_minutes: int = 10,
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
        self._variation = VariationEngine()
        self._smart = SmartCompiler()
        self._optimizer = StoryFlowOptimizer()
        self._similarity = ClipSimilarityDetector(threshold=0.6)
        self._target_seconds = target_minutes * 60
        self._seen_topics: set = set()   # diversity tracking

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool):
        self._enabled = value
        self._post_status("Auto Mode: ON" if value else "Auto Mode: OFF")
        if value:
            self._update_status()

    def set_batch_size(self, size: int):
        self._batch_size = max(1, size)
        self._smart.min_clips = self._batch_size
        self._update_status()

    def on_new_clip(self, clip: Clip):
        if not self._enabled:
            return
        with self._lock:
            self._pending.append(clip)
            count = len(self._pending)

        if count >= self._smart.min_clips:
            threading.Thread(target=self._run_compilation, daemon=True).start()
        else:
            remaining = self._smart.min_clips - count
            self._post_status(f"Auto Mode: {count} clips - waiting for {remaining} more...")

    def clear_pending(self):
        with self._lock:
            self._pending.clear()
        self._update_status()

    def set_target_minutes(self, minutes: int):
        """Set compilation target length (10/15/30 min)."""
        self._target_seconds = max(60, minutes * 60)
        self._post_status(f"Auto Mode: target set to {minutes} min")

    def _run_compilation(self):
        with self._lock:
            all_pending = list(self._pending)
            self._pending.clear()

        self._post_status(f"Auto Mode: {len(all_pending)} clips - running smart selection...")

        # 1. Deduplicate similar clips
        diverse = self._similarity.filter_diverse(all_pending)

        # 2. Clip diversity — prevent same topic repeated consecutively
        seen = set()
        deduped = []
        for c in diverse:
            key = (c.topic or c.filename)[:30].lower()
            if key not in seen:
                deduped.append(c)
                seen.add(key)
        diverse = deduped
        self._post_status(f"Auto Mode: {len(diverse)} diverse clips after dedup")

        # 3. Smart duration-based selection (respect target length)
        self._smart.target_duration = self._target_seconds
        selected, title = self._smart.select_clips(diverse)
        if not selected:
            self._post_status("Auto Mode: not enough clips - waiting")
            with self._lock:
                self._pending.extend(all_pending)
            return

        # 4. Story flow optimization (emotion arc)
        self._post_status("Auto Mode: optimizing story arc...")
        ordered = self._optimizer.optimize(selected)

        # 5. Variation + transitions
        clips = self._variation.shuffle_clips(ordered)
        transitions = self._variation.assign_transitions(len(clips))
        entries: List[TimelineEntry] = [
            TimelineEntry(clip=c, transition=t) for c, t in zip(clips, transitions)
        ]

        est = self._smart.estimate_duration(clips)
        self._post_status(
            f"Auto Mode: '{title}' - {len(clips)} clips, ~{int(est//60)}m{int(est%60):02d}s"
        )

        # 5. Generate viral title
        title_str = title
        if self._groq_api_key:
            try:
                from title_generator import TitleGenerator
                tg = TitleGenerator(self._groq_api_key)
                title_path = self._compiled_dir / "title.txt"
                self._compiled_dir.mkdir(parents=True, exist_ok=True)
                title_str = tg.generate(
                    clip_topics=[c.topic for c in clips],
                    clip_count=len(clips),
                    output_path=title_path,
                )
                self._post_status(f"Auto Mode: title generated")
            except Exception as exc:
                logger.warning("Title generation failed: %s", exc)

        # 6. Hook
        hook_path: Optional[Path] = None
        if self._groq_api_key:
            try:
                from hook_generator import HookGenerator
                self._post_status("Auto Mode: generating hook...")
                hg = HookGenerator(groq_api_key=self._groq_api_key, music_dir=self._music_dir)
                hook_path = self._compiled_dir / f"hook_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
                self._compiled_dir.mkdir(parents=True, exist_ok=True)
                hg.generate(title_str, len(clips), hook_path, self._variation.pick_hook_style())
            except Exception as exc:
                logger.warning("Hook failed: %s", exc)

        # 7. Outro
        outro_path: Optional[Path] = None
        try:
            from outro_generator import OutroGenerator
            self._post_status("Auto Mode: generating outro...")
            og = OutroGenerator(music_dir=self._music_dir)
            outro_path = self._compiled_dir / f"outro_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            og.generate(outro_path, text_index=self._variation.pick_outro_variant())
        except Exception as exc:
            logger.warning("Outro failed: %s", exc)

        # 8. Assemble
        self._post_status("Auto Mode: assembling...")
        try:
            from assembler import Assembler
            asm = Assembler()

            def _progress(pct, msg):
                self._post_status(f"Auto Mode: {msg} ({int(pct*100)}%)")

            def _done(out_path: Path):
                self._post_status(f"Auto Mode: export complete -> {out_path.name}")
                self._generate_thumbnail(clips[0], title_str, out_path)
                for clip in clips:
                    self._cm.set_state(clip.clip_id, STATE_EXPORTED)
                self._timeline.clear()
                if self._on_export_trigger:
                    self._on_export_trigger()

            def _error(exc: Exception):
                self._post_status(f"Auto Mode: export failed - {exc}")

            asm.export(
                entries=entries, topic=title_str,
                output_format="YouTube Long", quality="Standard 1080p",
                add_fade=True, hook_path=hook_path, outro_path=outro_path,
                on_progress=_progress, on_done=_done, on_error=_error,
            )
        except Exception as exc:
            logger.error("Assembler error: %s", exc)
            self._post_status(f"Auto Mode: assembler error - {exc}")

    def _generate_thumbnail(self, clip: Clip, title: str, video_path: Path):
        try:
            from thumbnail_generator import ThumbnailGenerator
            tg = ThumbnailGenerator()
            thumb_out = video_path.parent / (video_path.stem + "_thumbnail.jpg")
            tg.generate(Path(clip.filepath), title, thumb_out)
        except Exception as exc:
            logger.warning("Auto thumbnail failed: %s", exc)

    def _update_status(self):
        if not self._enabled:
            return
        with self._lock:
            count = len(self._pending)
        self._post_status(
            f"Auto Mode: ON - {count} clips pending (target {self._smart.target_seconds/60:.0f}min)"
        )

    def _post_status(self, msg: str):
        logger.info(msg)
        if self._on_status:
            self._on_status(msg)
