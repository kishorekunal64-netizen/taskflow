"""
visual_variation_engine.py - Prevent visual repetition in RAGAI video assembly.

Randomizes camera pan direction, zoom strength, scene duration, and transitions.
Every 3-4 scenes generates a hybrid motion scene (AnimateDiff if available,
otherwise enhanced Ken Burns with randomized parameters).

Integrates with video_assembler.py by providing per-scene motion configs.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

TRANSITIONS = ["cross_dissolve", "fade", "slide_left", "slide_right", "zoom_in", "cut"]

PAN_DIRECTIONS = [
    "left_to_right",
    "right_to_left",
    "top_to_bottom",
    "bottom_to_top",
    "diagonal_tl_br",
    "diagonal_tr_bl",
]

ZOOM_MODES = ["zoom_in", "zoom_out", "zoom_in_slow", "zoom_out_slow", "static"]


@dataclass
class SceneMotionConfig:
    """Per-scene visual motion parameters passed to the assembler."""
    scene_index: int
    pan_direction: str
    zoom_mode: str
    zoom_strength: float        # 1.0 = no zoom, 1.3 = 30% zoom
    duration_seconds: float
    transition_in: str
    is_hybrid_motion: bool = False
    motion_style: str = "ken_burns"   # "ken_burns" or "animatediff"


@dataclass
class VisualVariationPlan:
    """Full visual plan for a sequence of scenes."""
    scenes: List[SceneMotionConfig] = field(default_factory=list)

    @property
    def total_duration(self) -> float:
        return sum(s.duration_seconds for s in self.scenes)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class VisualVariationEngine:
    """
    Generates per-scene motion configs to maximize visual diversity.

    Rules:
    - No two consecutive scenes share the same pan direction
    - No two consecutive scenes share the same transition
    - Every 3-4 scenes: hybrid motion scene (AnimateDiff or enhanced Ken Burns)
    - Zoom strength varies between 1.05 and 1.35
    - Scene duration varies between 4.0 and 7.0 seconds
    """

    HYBRID_INTERVAL_MIN = 3
    HYBRID_INTERVAL_MAX = 4
    DURATION_MIN = 4.0
    DURATION_MAX = 7.0
    ZOOM_MIN = 1.05
    ZOOM_MAX = 1.35

    def __init__(self):
        self._animatediff_available = self._check_animatediff()

    def generate_plan(self, scene_count: int) -> VisualVariationPlan:
        """Generate a full visual variation plan for scene_count scenes."""
        plan = VisualVariationPlan()
        prev_pan = None
        prev_transition = None
        hybrid_countdown = random.randint(self.HYBRID_INTERVAL_MIN, self.HYBRID_INTERVAL_MAX)

        for i in range(scene_count):
            pan = self._pick_pan(exclude=prev_pan)
            zoom_mode = random.choice(ZOOM_MODES)
            zoom_strength = round(random.uniform(self.ZOOM_MIN, self.ZOOM_MAX), 2)
            duration = round(random.uniform(self.DURATION_MIN, self.DURATION_MAX), 1)
            transition = self._pick_transition(exclude=prev_transition)

            hybrid_countdown -= 1
            is_hybrid = hybrid_countdown <= 0
            if is_hybrid:
                hybrid_countdown = random.randint(self.HYBRID_INTERVAL_MIN, self.HYBRID_INTERVAL_MAX)
                motion_style = "animatediff" if self._animatediff_available else "ken_burns_enhanced"
                duration = 3.5  # hybrid clips are shorter
            else:
                motion_style = "ken_burns"

            cfg = SceneMotionConfig(
                scene_index=i,
                pan_direction=pan,
                zoom_mode=zoom_mode,
                zoom_strength=zoom_strength,
                duration_seconds=duration,
                transition_in=transition,
                is_hybrid_motion=is_hybrid,
                motion_style=motion_style,
            )
            plan.scenes.append(cfg)
            prev_pan = pan
            prev_transition = transition

            logger.debug(
                "Scene %d: pan=%s zoom=%s(%.2f) dur=%.1fs trans=%s hybrid=%s",
                i, pan, zoom_mode, zoom_strength, duration, transition, is_hybrid,
            )

        logger.info(
            "VisualVariationPlan: %d scenes, %.1fs total, %d hybrid",
            scene_count, plan.total_duration,
            sum(1 for s in plan.scenes if s.is_hybrid_motion),
        )
        return plan

    def get_ffmpeg_vf(self, cfg: SceneMotionConfig, w: int = 1920, h: int = 1080) -> str:
        """
        Build an FFmpeg -vf filter string for a scene config.
        Used by video_assembler.py when applying Ken Burns effect.
        """
        z = cfg.zoom_strength
        dur = cfg.duration_seconds
        fps = 25
        total_frames = int(dur * fps)

        pan_map = {
            "left_to_right":  (f"x='iw/2-(iw/zoom/2)+((iw-(iw/zoom))*on/{total_frames})'", "y='ih/2-(ih/zoom/2)'"),
            "right_to_left":  (f"x='iw/2-(iw/zoom/2)+((iw-(iw/zoom))*(1-on/{total_frames}))'", "y='ih/2-(ih/zoom/2)'"),
            "top_to_bottom":  ("x='iw/2-(iw/zoom/2)'", f"y='ih/2-(ih/zoom/2)+((ih-(ih/zoom))*on/{total_frames})'"),
            "bottom_to_top":  ("x='iw/2-(iw/zoom/2)'", f"y='ih/2-(ih/zoom/2)+((ih-(ih/zoom))*(1-on/{total_frames}))'"),
            "diagonal_tl_br": (f"x='iw/2-(iw/zoom/2)+((iw-(iw/zoom))*on/{total_frames})'", f"y='ih/2-(ih/zoom/2)+((ih-(ih/zoom))*on/{total_frames})'"),
            "diagonal_tr_bl": (f"x='iw/2-(iw/zoom/2)+((iw-(iw/zoom))*(1-on/{total_frames}))'", f"y='ih/2-(ih/zoom/2)+((ih-(ih/zoom))*on/{total_frames})'"),
        }

        if cfg.zoom_mode in ("zoom_in", "zoom_in_slow"):
            zoom_expr = f"zoom='min(zoom+{0.0015 if cfg.zoom_mode == 'zoom_in_slow' else 0.003},{z})'"
        elif cfg.zoom_mode in ("zoom_out", "zoom_out_slow"):
            zoom_expr = f"zoom='if(eq(on,1),{z},max(1,zoom-{0.0015 if cfg.zoom_mode == 'zoom_out_slow' else 0.003}))'"
        else:
            zoom_expr = f"zoom={z}"

        x_expr, y_expr = pan_map.get(cfg.pan_direction, pan_map["left_to_right"])
        vf = f"zoompan={zoom_expr}:{x_expr}:{y_expr}:d={total_frames}:s={w}x{h}:fps={fps}"
        return vf

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _pick_pan(self, exclude: Optional[str] = None) -> str:
        choices = [p for p in PAN_DIRECTIONS if p != exclude]
        return random.choice(choices or PAN_DIRECTIONS)

    def _pick_transition(self, exclude: Optional[str] = None) -> str:
        choices = [t for t in TRANSITIONS if t != exclude]
        return random.choice(choices or TRANSITIONS)

    @staticmethod
    def _check_animatediff() -> bool:
        try:
            import importlib
            return importlib.util.find_spec("animatediff") is not None
        except Exception:
            return False
