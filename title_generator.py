"""
title_generator.py - Viral YouTube title generator for RAGAI Editor V2.

Uses Groq LLM to generate click-worthy Hindi/English YouTube titles.
Falls back to templates when Groq is unavailable.
Saves generated title to compiled/title.txt.
"""
from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

_FALLBACK = [
    "{n} dil chhu lene wali kahaniyan | Hindi Kahani",
    "In kahaniyon ne sabko rula diya | Emotional Hindi Stories",
    "{n} Inspiring Stories That Will Change Your Life | Hindi",
    "Zindagi badal dene wali {n} kahaniyan | Motivational",
    "{n} Best Hindi Stories | Must Watch Compilation",
    "Aaj ki {n} sachi kahaniyan | True Stories Hindi",
    "{n} Emotional Stories | Dil ko chhu jayengi ye kahaniyan",
]

_PROMPT = """You are a viral YouTube title expert for Hindi emotional story compilations.

Generate ONE compelling YouTube title:
- Topics: {topics}
- Number of stories: {n}
- Max 70 characters, emotionally engaging, include Hindi text
- Format: [Emoji] [Hindi Title] | [English subtitle]

Reply with ONLY the title."""


class TitleGenerator:
    """Generates viral YouTube titles using Groq LLM with fallback templates."""

    def __init__(self, groq_api_key: str = ""):
        self._api_key = groq_api_key

    def generate(
        self,
        clip_topics: List[str],
        clip_count: int,
        output_path: Optional[Path] = None,
    ) -> str:
        title = self._from_groq(clip_topics, clip_count) or self._fallback(clip_count)
        logger.info("Generated title: %s", title)
        if output_path:
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(title, encoding="utf-8")
                logger.info("Title saved: %s", output_path)
            except Exception as exc:
                logger.warning("Could not save title.txt: %s", exc)
        return title

    def _from_groq(self, topics: List[str], n: int) -> Optional[str]:
        if not self._api_key:
            return None
        try:
            from groq import Groq
            client = Groq(api_key=self._api_key)
            prompt = _PROMPT.format(topics=", ".join(topics[:5]) or "Hindi stories", n=n)
            resp = client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=80,
                temperature=0.9,
            )
            raw = resp.choices[0].message.content.strip().splitlines()[0]
            title = raw.strip('"').strip("'")
            return title if len(title) > 5 else None
        except Exception as exc:
            logger.warning("Groq title generation failed: %s", exc)
            return None

    def _fallback(self, n: int) -> str:
        return random.choice(_FALLBACK).format(n=n)
