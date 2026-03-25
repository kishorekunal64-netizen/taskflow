"""
script_loader.py — Manual script input for RAGAI.

Loads user-provided script files from the scripts/ directory and splits
them into scenes, bypassing story_generator.py entirely.

Script format (plain text):
  - One scene per paragraph (blank line separator), OR
  - Explicit scene markers: [SCENE 1], [SCENE 2], etc.
  - Lines starting with # are comments and ignored

Pipeline when script is detected:
  script_loader → scene_splitter → image_generator → voice_synthesizer

When enable_manual_script_mode is False, this module is a no-op.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional

from models import Language, Scene

logger = logging.getLogger(__name__)

_SCRIPTS_DIR = Path("scripts")

# Regex for explicit scene markers like [SCENE 1] or [Scene 3]
_SCENE_MARKER = re.compile(r"^\[scene\s*\d+\]", re.IGNORECASE)


class ScriptLoader:
    """Load and parse user-provided script files into Scene objects."""

    def __init__(self, scripts_dir: Path = _SCRIPTS_DIR) -> None:
        self.scripts_dir = Path(scripts_dir)
        self.scripts_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def list_scripts(self) -> List[Path]:
        """Return all .txt script files in scripts/ sorted by name."""
        return sorted(self.scripts_dir.glob("*.txt"))

    def has_scripts(self) -> bool:
        return bool(self.list_scripts())

    def next_script(self) -> Optional[Path]:
        """Return the next unprocessed script file, or None."""
        scripts = self.list_scripts()
        return scripts[0] if scripts else None

    # ------------------------------------------------------------------
    # Loading + parsing
    # ------------------------------------------------------------------

    def load(self, script_path: Path) -> List[str]:
        """Load a script file and return a list of scene narration strings.

        Supports two formats:
          1. Explicit markers: [SCENE 1] ... [SCENE 2] ...
          2. Paragraph-based: blank lines separate scenes
        """
        text = Path(script_path).read_text(encoding="utf-8")

        # Strip comment lines
        lines = [l for l in text.splitlines() if not l.strip().startswith("#")]
        cleaned = "\n".join(lines)

        # Try explicit scene markers first
        if _SCENE_MARKER.search(cleaned):
            scenes = self._split_by_markers(cleaned)
        else:
            scenes = self._split_by_paragraphs(cleaned)

        scenes = [s.strip() for s in scenes if s.strip()]
        logger.info("ScriptLoader: loaded %d scenes from %s", len(scenes), script_path)
        return scenes

    def to_scenes(
        self,
        script_path: Path,
        language: Language = Language.HI,
        default_duration: float = 8.0,
    ) -> List[Scene]:
        """Parse script into Scene objects ready for the pipeline.

        image_prompt is left as a generic placeholder — image_generator
        will use the narration text to build a real prompt if needed.
        """
        narrations = self.load(script_path)
        scenes: List[Scene] = []
        for i, narration in enumerate(narrations, start=1):
            # Build a simple English image prompt from the narration
            prompt = self._narration_to_image_prompt(narration)
            scenes.append(Scene(
                number=i,
                narration=narration,
                image_prompt=prompt,
                duration_seconds=default_duration,
            ))
        return scenes

    def mark_processed(self, script_path: Path) -> None:
        """Rename script to .done so it won't be picked up again."""
        done_path = script_path.with_suffix(".done")
        script_path.rename(done_path)
        logger.info("ScriptLoader: marked processed: %s → %s", script_path.name, done_path.name)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _split_by_markers(self, text: str) -> List[str]:
        """Split on [SCENE N] markers."""
        parts = _SCENE_MARKER.split(text)
        return [p.strip() for p in parts if p.strip()]

    def _split_by_paragraphs(self, text: str) -> List[str]:
        """Split on blank lines."""
        return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    def _narration_to_image_prompt(self, narration: str) -> str:
        """Generate a basic English image prompt from narration text.

        Strips non-ASCII (Hindi/regional) characters and builds a
        cinematic description. The image_generator can override this.
        """
        # Keep only ASCII words as a rough English extraction
        ascii_words = re.findall(r"[a-zA-Z]{3,}", narration)
        if ascii_words:
            base = " ".join(ascii_words[:12])
        else:
            # Fallback: use character count as scene descriptor
            base = f"cinematic scene with emotional storytelling"
        return f"Cinematic 4K scene: {base}, dramatic lighting, photorealistic"
