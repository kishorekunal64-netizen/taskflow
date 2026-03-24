"""
scene_parallel_executor.py - Parallel scene processing for RAGAI Video Factory.

Processes image generation, voice synthesis, and scene clip assembly
concurrently using ThreadPoolExecutor.

Expected improvement: 50-70% reduction in video generation time.

Integration:
    Called by pipeline.py instead of sequential scene processing.
    After all scenes complete, assembler.py merges the clips as usual.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_MAX_WORKERS = 4


@dataclass
class SceneTask:
    """Represents one scene's processing unit."""
    scene_index: int
    scene_data: object          # Scene dataclass from models.py
    image_path: Optional[Path] = None
    audio_path: Optional[Path] = None
    clip_path:  Optional[Path] = None
    error:      Optional[str]  = None
    duration_sec: float = 0.0


@dataclass
class ParallelExecutionResult:
    """Result of a full parallel scene execution run."""
    tasks: List[SceneTask] = field(default_factory=list)
    total_time_sec: float = 0.0
    success_count: int = 0
    failure_count: int = 0

    @property
    def all_succeeded(self) -> bool:
        return self.failure_count == 0

    @property
    def ordered_clips(self) -> List[Path]:
        """Return clip paths sorted by scene_index, skipping failed scenes."""
        return [
            t.clip_path for t in sorted(self.tasks, key=lambda t: t.scene_index)
            if t.clip_path and t.clip_path.exists()
        ]


# ---------------------------------------------------------------------------
# Core executor
# ---------------------------------------------------------------------------

class SceneParallelExecutor:
    """
    Executes per-scene generation tasks concurrently.

    Each scene goes through three stages:
      1. generate_image  — calls image_generator
      2. synthesize_voice — calls voice_synthesizer
      3. assemble_clip   — calls video_assembler for this single scene

    Stages within a scene are sequential (voice needs image for timing),
    but scenes run in parallel across workers.

    Usage::

        executor = SceneParallelExecutor(max_workers=4)
        result = executor.run(
            scenes=story.scenes,
            image_fn=image_gen.generate,
            voice_fn=voice_synth.synthesize_one,
            clip_fn=video_assembler.build_scene_clip,
        )
        # result.ordered_clips → list of Path objects ready for assembler.py
    """

    def __init__(self, max_workers: int = DEFAULT_MAX_WORKERS):
        self.max_workers = max_workers
        logger.info("SceneParallelExecutor initialised (workers=%d)", max_workers)

    def run(
        self,
        scenes: list,
        image_fn: Callable,
        voice_fn: Callable,
        clip_fn: Callable,
        work_dir: Optional[Path] = None,
    ) -> ParallelExecutionResult:
        """
        Process all scenes in parallel.

        Args:
            scenes   : list of Scene objects from models.py
            image_fn : callable(scene) → Path  (image file)
            voice_fn : callable(scene) → Path  (audio file)
            clip_fn  : callable(scene, image_path, audio_path) → Path  (video clip)
            work_dir : optional working directory for temp files

        Returns:
            ParallelExecutionResult with ordered clip paths
        """
        tasks = [SceneTask(scene_index=i, scene_data=s) for i, s in enumerate(scenes)]
        start = time.time()

        logger.info("Starting parallel scene processing: %d scenes, %d workers",
                    len(tasks), self.max_workers)

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            future_map: Dict[Future, SceneTask] = {
                pool.submit(self._process_scene, task, image_fn, voice_fn, clip_fn, work_dir): task
                for task in tasks
            }

            for future in as_completed(future_map):
                task = future_map[future]
                try:
                    completed_task = future.result()
                    # Merge results back into original task
                    task.image_path   = completed_task.image_path
                    task.audio_path   = completed_task.audio_path
                    task.clip_path    = completed_task.clip_path
                    task.duration_sec = completed_task.duration_sec
                    task.error        = completed_task.error
                    if task.error:
                        logger.error("Scene %d failed: %s", task.scene_index, task.error)
                    else:
                        logger.info("Scene %d complete (%.1fs)", task.scene_index, task.duration_sec)
                except Exception as exc:
                    task.error = str(exc)
                    logger.error("Scene %d raised exception: %s", task.scene_index, exc)

        elapsed = time.time() - start
        success = sum(1 for t in tasks if not t.error)
        failure = len(tasks) - success

        result = ParallelExecutionResult(
            tasks=tasks,
            total_time_sec=round(elapsed, 2),
            success_count=success,
            failure_count=failure,
        )

        logger.info(
            "Parallel execution complete: %d/%d scenes OK in %.1fs",
            success, len(tasks), elapsed,
        )
        return result

    def run_stage(
        self,
        scenes: list,
        stage_fn: Callable,
        stage_name: str = "stage",
    ) -> Dict[int, object]:
        """
        Run a single stage (e.g. image generation only) across all scenes in parallel.
        Returns {scene_index: result}.
        """
        results: Dict[int, object] = {}
        errors:  Dict[int, str]    = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            future_map = {
                pool.submit(stage_fn, scene): i
                for i, scene in enumerate(scenes)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    errors[idx] = str(exc)
                    logger.error("%s failed for scene %d: %s", stage_name, idx, exc)

        if errors:
            logger.warning("%s: %d/%d scenes failed", stage_name, len(errors), len(scenes))
        else:
            logger.info("%s: all %d scenes completed", stage_name, len(scenes))

        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _process_scene(
        self,
        task: SceneTask,
        image_fn: Callable,
        voice_fn: Callable,
        clip_fn: Callable,
        work_dir: Optional[Path],
    ) -> SceneTask:
        """Process a single scene through all three stages."""
        t0 = time.time()
        scene = task.scene_data

        try:
            # Stage 1: Image
            task.image_path = image_fn(scene)
            logger.debug("Scene %d: image done (%s)", task.scene_index, task.image_path)

            # Stage 2: Voice
            task.audio_path = voice_fn(scene)
            logger.debug("Scene %d: voice done (%s)", task.scene_index, task.audio_path)

            # Stage 3: Clip assembly
            task.clip_path = clip_fn(scene, task.image_path, task.audio_path)
            logger.debug("Scene %d: clip done (%s)", task.scene_index, task.clip_path)

        except Exception as exc:
            task.error = str(exc)
            logger.error("Scene %d processing error: %s", task.scene_index, exc)

        task.duration_sec = round(time.time() - t0, 2)
        return task
