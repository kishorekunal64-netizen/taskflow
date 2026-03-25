"""
language_engine.py — Multi-language detection and configuration for RAGAI.

Detects language from topic metadata and provides per-language voice,
narration style, and prompt configuration. Integrates with story_generator,
voice_synthesizer, and title_generator.

All existing behaviour is preserved when language is explicitly set.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, Optional

from models import Language

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language detection — Unicode script ranges
# ---------------------------------------------------------------------------

_SCRIPT_RANGES: Dict[str, Language] = {
    # Devanagari (Hindi, Marathi)
    r"[\u0900-\u097F]": Language.HI,
    # Tamil
    r"[\u0B80-\u0BFF]": Language.TA,
    # Telugu
    r"[\u0C00-\u0C7F]": Language.TE,
    # Bengali
    r"[\u0980-\u09FF]": Language.BN,
    # Gujarati
    r"[\u0A80-\u0AFF]": Language.GU,
    # Kannada
    r"[\u0C80-\u0CFF]": Language.KN,
    # Malayalam
    r"[\u0D00-\u0D7F]": Language.ML,
    # Gurmukhi (Punjabi)
    r"[\u0A00-\u0A7F]": Language.PA,
    # Arabic (Urdu)
    r"[\u0600-\u06FF]": Language.UR,
}

# Keyword hints for English detection
_ENGLISH_KEYWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "who", "that",
    "and", "or", "but", "in", "on", "at", "to", "of", "for",
    "with", "his", "her", "their", "this", "from", "by",
}

# Per-language narration style hints injected into story prompts
NARRATION_STYLE: Dict[Language, str] = {
    Language.EN: "Write in clear, engaging English. Use vivid storytelling.",
    Language.HI: "हिंदी में लिखें। भावनात्मक और प्रेरणादायक शैली में।",
    Language.TA: "தமிழில் எழுதுங்கள். உணர்ச்சிமிக்க கதை சொல்லும் பாணியில்.",
    Language.TE: "తెలుగులో రాయండి. భావోద్వేగ కథన శైలిలో.",
    Language.BN: "বাংলায় লিখুন। আবেগময় গল্প বলার ধরনে।",
    Language.GU: "ગુજરાતીમાં લખો. ભાવનાત્મક વાર્તા કહેવાની શૈલીમાં.",
    Language.MR: "मराठीत लिहा. भावनिक कथाकथन शैलीत.",
    Language.KN: "ಕನ್ನಡದಲ್ಲಿ ಬರೆಯಿರಿ. ಭಾವನಾತ್ಮಕ ಕಥೆ ಹೇಳುವ ಶೈಲಿಯಲ್ಲಿ.",
    Language.ML: "മലയാളത്തിൽ എഴുതുക. വൈകാരിക കഥ പറയൽ ശൈലിയിൽ.",
    Language.PA: "ਪੰਜਾਬੀ ਵਿੱਚ ਲਿਖੋ। ਭਾਵਨਾਤਮਕ ਕਹਾਣੀ ਸੁਣਾਉਣ ਦੀ ਸ਼ੈਲੀ ਵਿੱਚ.",
    Language.UR: "اردو میں لکھیں۔ جذباتی کہانی سنانے کے انداز میں۔",
}

# Image prompt language — always English for Leonardo AI
IMAGE_PROMPT_LANGUAGE = "en"


# ---------------------------------------------------------------------------
# LanguageEngine
# ---------------------------------------------------------------------------

class LanguageEngine:
    """Detect language and provide per-language configuration."""

    def detect(self, topic: str, hint: Optional[str] = None) -> Language:
        """Detect language from topic text.

        Args:
            topic: The story topic string.
            hint:  Optional ISO code hint (e.g. "en", "hi"). If valid, used directly.

        Returns:
            Language enum value.
        """
        # 1. Explicit hint takes priority
        if hint:
            try:
                lang = Language(hint.lower().strip())
                logger.info("Language set from hint: %s", lang)
                return lang
            except ValueError:
                logger.warning("Unknown language hint %r — auto-detecting", hint)

        # 2. Script-based detection
        for pattern, lang in _SCRIPT_RANGES.items():
            if re.search(pattern, topic):
                logger.info("Language detected by script: %s", lang)
                return lang

        # 3. English keyword heuristic
        words = set(re.findall(r"\b[a-zA-Z]+\b", topic.lower()))
        overlap = words & _ENGLISH_KEYWORDS
        if len(overlap) >= 2 or (words and len(overlap) / len(words) > 0.3):
            logger.info("Language detected as English (keyword heuristic)")
            return Language.EN

        # 4. Default fallback
        logger.info("Language detection inconclusive — defaulting to Hindi")
        return Language.HI

    def narration_style(self, language: Language) -> str:
        """Return the narration style instruction for the given language."""
        return NARRATION_STYLE.get(language, NARRATION_STYLE[Language.EN])

    def voice_name(self, language: Language) -> str:
        """Return the Edge-TTS voice name for the given language."""
        from voice_synthesizer import VOICE_MAP
        return VOICE_MAP.get(language, "en-US-JennyNeural")

    def gtts_code(self, language: Language) -> str:
        """Return the gTTS language code for the given language."""
        from voice_synthesizer import GTTS_LANG_MAP
        return GTTS_LANG_MAP.get(language, "en")

    def is_rtl(self, language: Language) -> bool:
        """Return True for right-to-left languages (Urdu, Arabic)."""
        return language in {Language.UR}

    def display_name(self, language: Language) -> str:
        """Human-readable language name."""
        names = {
            Language.EN: "English",
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
        return names.get(language, language.value)
