"""
prompt_optimizer.py — Adaptive prompt evolution for RAGAI story generation.

Analyzes analytics_data.json and retention_optimizer feedback to improve
story prompts over time. Outputs updated prompt templates used by
story_generator.py.

Operates fully offline — no external API required.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_ANALYTICS_PATH = Path("analytics_data.json")
_TEMPLATES_PATH = Path("prompt_templates.json")

# ---------------------------------------------------------------------------
# Default prompt templates (baseline)
# ---------------------------------------------------------------------------

_DEFAULT_TEMPLATES: Dict[str, str] = {
    "hook_instruction": (
        "Start with a powerful emotional hook in the first scene that immediately "
        "grabs attention. Use a surprising fact, question, or dramatic moment."
    ),
    "pacing_instruction": (
        "Vary scene pacing: start fast, build tension in the middle, "
        "resolve emotionally at the end."
    ),
    "emotion_instruction": (
        "Each scene must carry a distinct emotion: curiosity, tension, hope, "
        "or inspiration. Avoid flat narration."
    ),
    "retention_instruction": (
        "Keep narration concise — 2-3 sentences per scene. "
        "End each scene with a micro-cliffhanger to maintain watch time."
    ),
    "visual_instruction": (
        "Describe vivid, cinematic visuals in each image prompt. "
        "Include lighting, mood, and character expression."
    ),
}


class PromptOptimizer:
    """Improve story prompts based on analytics and retention data."""

    def __init__(
        self,
        analytics_path: Path = _ANALYTICS_PATH,
        templates_path: Path = _TEMPLATES_PATH,
    ) -> None:
        self.analytics_path = Path(analytics_path)
        self.templates_path = Path(templates_path)
        self._templates: Dict[str, str] = dict(_DEFAULT_TEMPLATES)
        self._load_templates()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_template(self, key: str) -> str:
        """Return the current prompt template for the given key."""
        return self._templates.get(key, _DEFAULT_TEMPLATES.get(key, ""))

    def build_system_prompt_suffix(self) -> str:
        """Build a combined prompt suffix from all active templates."""
        parts = [
            self._templates.get("hook_instruction", ""),
            self._templates.get("pacing_instruction", ""),
            self._templates.get("emotion_instruction", ""),
            self._templates.get("retention_instruction", ""),
            self._templates.get("visual_instruction", ""),
        ]
        return "\n\n".join(p for p in parts if p)

    def optimize(self) -> Dict[str, str]:
        """Analyze analytics data and update prompt templates.

        Returns the updated templates dict.
        """
        analytics = self._load_analytics()
        if not analytics:
            logger.info("PromptOptimizer: no analytics data — using defaults")
            return self._templates

        changes = []

        # Rule 1: Low early retention → strengthen hook
        avg_retention_30s = self._avg_metric(analytics, "retention_30s_pct")
        if avg_retention_30s is not None and avg_retention_30s < 60.0:
            self._templates["hook_instruction"] = (
                "CRITICAL: The first scene must open with an extremely powerful hook — "
                "a shocking revelation, dramatic question, or intense emotional moment. "
                "Retention at 30 seconds is low. Make the opening unmissable."
            )
            changes.append(f"hook strengthened (avg_retention_30s={avg_retention_30s:.1f}%)")

        # Rule 2: Low average watch time → tighten pacing
        avg_watch = self._avg_metric(analytics, "watch_time_minutes")
        if avg_watch is not None and avg_watch < 2.0:
            self._templates["retention_instruction"] = (
                "Keep each scene to 1-2 sentences maximum. "
                "Every sentence must advance the story. Cut all filler. "
                "End each scene on a tension point."
            )
            changes.append(f"retention tightened (avg_watch={avg_watch:.1f}min)")

        # Rule 3: Low CTR → improve emotional intensity
        avg_ctr = self._avg_metric(analytics, "ctr_pct")
        if avg_ctr is not None and avg_ctr < 5.0:
            self._templates["emotion_instruction"] = (
                "Every scene must be emotionally charged. Use words that evoke "
                "strong feelings: sacrifice, betrayal, triumph, love, loss. "
                "CTR is low — the story must feel urgent and compelling."
            )
            changes.append(f"emotion intensified (avg_ctr={avg_ctr:.1f}%)")

        if changes:
            logger.info("PromptOptimizer: applied %d improvements: %s", len(changes), changes)
        else:
            logger.info("PromptOptimizer: metrics healthy — no changes needed")

        self._save_templates()
        return self._templates

    def reset_to_defaults(self) -> None:
        """Reset all templates to built-in defaults."""
        self._templates = dict(_DEFAULT_TEMPLATES)
        self._save_templates()
        logger.info("PromptOptimizer: reset to defaults")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_templates(self) -> None:
        if self.templates_path.exists():
            try:
                data = json.loads(self.templates_path.read_text(encoding="utf-8"))
                self._templates.update(data)
                logger.info("PromptOptimizer: loaded templates from %s", self.templates_path)
            except Exception as exc:
                logger.warning("PromptOptimizer: failed to load templates — %s", exc)

    def _save_templates(self) -> None:
        try:
            self.templates_path.write_text(
                json.dumps(self._templates, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("PromptOptimizer: failed to save templates — %s", exc)

    def _load_analytics(self) -> Optional[List[Dict[str, Any]]]:
        if not self.analytics_path.exists():
            return None
        try:
            data = json.loads(self.analytics_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return [data]
        except Exception as exc:
            logger.warning("PromptOptimizer: failed to load analytics — %s", exc)
        return None

    def _avg_metric(self, records: List[Dict], key: str) -> Optional[float]:
        values = [r[key] for r in records if key in r and isinstance(r[key], (int, float))]
        if not values:
            return None
        return sum(values) / len(values)
