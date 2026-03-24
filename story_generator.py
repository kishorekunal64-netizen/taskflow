"""
story_generator.py — Groq LLM story generation for RAGAI Video Factory.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional

import requests

from models import (
    Audience,
    Language,
    Scene,
    StoryGenerationError,
    VisualStyle,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language display names for prompt instructions
# ---------------------------------------------------------------------------

_LANGUAGE_NAMES: Dict[Language, str] = {
    Language.HI: "Hindi",
    Language.TA: "Tamil",
    Language.TE: "Telugu",
    Language.BN: "Bengali",
    Language.GU: "Gujarati",
    Language.MR: "Marathi",
    Language.KN: "Kannada",
    Language.ML: "Malayalam",
    Language.PA: "Punjabi",
    Language.UR: "Urdu",
}

_AUDIENCE_INSTRUCTIONS: Dict[Audience, str] = {
    Audience.FAMILY:   "suitable for all ages, family-friendly, wholesome content",
    Audience.CHILDREN: "simple language, fun and engaging, appropriate for children aged 5-12",
    Audience.ADULTS:   "mature themes allowed, sophisticated storytelling for adult viewers",
    Audience.DEVOTEES: "devotional and spiritual tone, reverent language, suitable for religious audiences",
}

_GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
_FALLBACK_MODEL = "llama-3.1-8b-instant"


class StoryGenerator:
    """Generates structured scene lists from a topic using the Groq LLM API."""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile") -> None:
        self.api_key = api_key
        self.model = model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        topic: str,
        audience: Audience,
        style: VisualStyle,
        language: Language,
        character_names: Dict[str, str],
        scene_count: int = 8,
        target_duration_minutes: float = 0.0,
    ) -> List[Scene]:
        """Call Groq to generate 5-12 scenes for *topic*.

        Applies character name substitution when *character_names* is non-empty.
        """
        prompt = self._build_prompt(topic, audience, style, language, character_names, scene_count, target_duration_minutes)
        raw = self._call_groq(prompt, self.model)
        scenes = self._parse_llm_response(raw, scene_count)

        if character_names:
            scenes = self._substitute_character_names(scenes, character_names)

        return scenes

    def parse_script(self, script_text: str, language: Language) -> List[Scene]:
        """Parse a user-supplied script into scenes without calling the API.

        Splits on blank lines or '---' / '===' delimiters.  Each paragraph
        becomes one scene with a default duration of 5.0 seconds.
        """
        # Split on blank lines or explicit delimiters
        raw_blocks = re.split(r"\n\s*\n|^---+$|^===+$", script_text, flags=re.MULTILINE)
        scenes: List[Scene] = []
        number = 1
        for block in raw_blocks:
            text = block.strip()
            if not text:
                continue
            # First sentence (up to 120 chars) becomes a simple English image prompt
            first_sentence = re.split(r"[।.!?]", text)[0].strip()
            image_prompt = first_sentence[:120] if first_sentence else text[:120]
            scenes.append(
                Scene(
                    number=number,
                    narration=text,
                    image_prompt=image_prompt,
                    duration_seconds=5.0,
                )
            )
            number += 1
        return scenes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        topic: str,
        audience: Audience,
        style: VisualStyle,
        language: Language,
        character_names: Optional[Dict[str, str]] = None,
        scene_count: int = 8,
        target_duration_minutes: float = 0.0,
    ) -> str:
        """Build the system+user prompt sent to Groq."""
        lang_name = _LANGUAGE_NAMES.get(language, language.value)
        audience_instruction = _AUDIENCE_INSTRUCTIONS.get(audience, audience.value)
        style_name = style.value.replace("_", " ").title()

        char_instruction = ""
        if character_names:
            pairs = ", ".join(f'"{k}" → "{v}"' for k, v in character_names.items())
            char_instruction = (
                f"\nCharacter name substitutions to apply: {pairs}."
            )

        # Compute per-scene duration hint when a target length is requested
        if target_duration_minutes > 0:
            secs_per_scene = (target_duration_minutes * 60) / scene_count
            secs_per_scene = max(4.0, min(secs_per_scene, 30.0))
            duration_instruction = (
                f"Target total video length: {target_duration_minutes} minute(s). "
                f"Each scene duration should be approximately {secs_per_scene:.0f} seconds "
                f"(integer, between {max(4, int(secs_per_scene)-4)} and {min(30, int(secs_per_scene)+4)})."
            )
        else:
            duration_instruction = (
                f'  "duration": scene duration in seconds (integer, between 4 and 10)'
            )

        prompt = (
            f"You are a professional cinematic scriptwriter.\n\n"
            f"Create a structured video story for the following topic: \"{topic}\"\n\n"
            f"Audience: {audience.value} — {audience_instruction}\n"
            f"Visual Style: {style_name}\n"
            f"Narration Language: {lang_name} — IMPORTANT: write ALL narration text in {lang_name}. "
            f"Do NOT write narration in English.\n"
            f"Image Prompts Language: English — IMPORTANT: write ALL image_prompt fields in English only.\n"
            f"{char_instruction}\n\n"
            f"Return ONLY a valid JSON array of EXACTLY {scene_count} scene objects. "
            f"Each object must have exactly these keys:\n"
            f'  "scene": integer scene number starting at 1\n'
            f'  "narration": narration text in {lang_name}\n'
            f'  "image_prompt": cinematic English description for image generation\n'
            f"{duration_instruction}\n\n"
            f"Example format:\n"
            f'[{{"scene": 1, "narration": "...", "image_prompt": "...", "duration": 6}}]\n\n'
            f"Output ONLY the JSON array. No markdown, no explanation, no extra text."
        )
        return prompt

    def _call_groq(self, prompt: str, model: str) -> str:
        """POST to Groq chat completions endpoint and return the assistant message text.

        On HTTP 429 retries once with the fallback model and notifies the user.
        On any other error logs and raises StoryGenerationError.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
        }

        try:
            response = requests.post(_GROQ_API_URL, headers=headers, json=payload, timeout=60)
        except requests.RequestException as exc:
            logger.error("Groq API request failed: %s", exc)
            raise StoryGenerationError(f"Network error calling Groq API: {exc}") from exc

        if response.status_code == 429:
            print(
                f"[RAGAI] Groq rate limit hit on model '{model}'. "
                f"Retrying with fallback model '{_FALLBACK_MODEL}'..."
            )
            logger.warning("Groq 429 rate limit; retrying with %s", _FALLBACK_MODEL)
            return self._call_groq(prompt, _FALLBACK_MODEL)

        if not response.ok:
            logger.error(
                "Groq API error %s: %s", response.status_code, response.text
            )
            raise StoryGenerationError(
                f"Groq API returned HTTP {response.status_code}: {response.text}"
            )

        try:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            logger.error("Unexpected Groq response structure: %s", response.text)
            raise StoryGenerationError(
                f"Could not parse Groq response: {exc}"
            ) from exc

    def _parse_llm_response(self, raw: str, scene_count: int = 8) -> List[Scene]:
        """Parse the raw LLM text into a list of Scene objects.

        Extracts the first JSON array found in *raw* to tolerate minor
        preamble/postamble from the model.
        """
        # Strip markdown code fences if present
        cleaned = re.sub(r"```(?:json)?", "", raw).strip()

        # Find the outermost JSON array
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if not match:
            logger.error("No JSON array found in LLM response: %s", raw[:500])
            raise StoryGenerationError(
                "LLM response did not contain a JSON array of scenes."
            )

        try:
            items = json.loads(match.group())
        except json.JSONDecodeError as exc:
            logger.error("JSON parse error in LLM response: %s", exc)
            raise StoryGenerationError(
                f"Failed to parse JSON from LLM response: {exc}"
            ) from exc

        if not isinstance(items, list) or len(items) == 0:
            raise StoryGenerationError("LLM returned an empty scene list.")

        scenes: List[Scene] = []
        for item in items:
            try:
                number = int(item.get("scene", len(scenes) + 1))
                narration = str(item.get("narration", "")).strip()
                image_prompt = str(item.get("image_prompt", "")).strip()
                duration = float(item.get("duration", 6))

                if not narration:
                    raise StoryGenerationError(
                        f"Scene {number} has empty narration."
                    )
                if not image_prompt:
                    raise StoryGenerationError(
                        f"Scene {number} has empty image_prompt."
                    )
                if duration <= 0:
                    raise StoryGenerationError(
                        f"Scene {number} has non-positive duration: {duration}"
                    )

                scenes.append(
                    Scene(
                        number=number,
                        narration=narration,
                        image_prompt=image_prompt,
                        duration_seconds=duration,
                    )
                )
            except (TypeError, ValueError) as exc:
                logger.error("Malformed scene item %s: %s", item, exc)
                raise StoryGenerationError(
                    f"Malformed scene data: {exc}"
                ) from exc

        if not (3 <= len(scenes) <= 20):
            raise StoryGenerationError(
                f"Expected {scene_count} scenes, got {len(scenes)}."
            )

        return scenes

    # ------------------------------------------------------------------
    # Character name substitution
    # ------------------------------------------------------------------

    @staticmethod
    def _substitute_character_names(
        scenes: List[Scene], character_names: Dict[str, str]
    ) -> List[Scene]:
        """Replace placeholder names in narration fields with user-supplied names."""
        for scene in scenes:
            for placeholder, replacement in character_names.items():
                scene.narration = scene.narration.replace(placeholder, replacement)
        return scenes
