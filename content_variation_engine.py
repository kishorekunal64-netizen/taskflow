"""
content_variation_engine.py - Reduce content repetition across voice, music, and pacing.

Three variation axes:
  1. Voice style    — pitch/rate/volume modifiers applied on top of Edge-TTS voice
  2. Music mood     — selects BGM mood profile independent of topic keywords
  3. Scene pacing   — controls clip duration distribution (fast / balanced / slow-burn)

All axes rotate to avoid back-to-back repetition.
Integrates with voice_synthesizer.py, music_selector.py, and assembler.py.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Voice Style Variation
# ---------------------------------------------------------------------------

@dataclass
class VoiceStyle:
    name: str
    rate: str    # Edge-TTS SSML rate  e.g. "+0%", "+15%", "-10%"
    pitch: str   # Edge-TTS SSML pitch e.g. "+0Hz", "+5Hz", "-3Hz"
    volume: str  # Edge-TTS SSML volume e.g. "+0%", "+10%", "-5%"
    description: str


VOICE_STYLES: List[VoiceStyle] = [
    VoiceStyle("Neutral",      rate="+0%",   pitch="+0Hz",  volume="+0%",   description="Default natural voice"),
    VoiceStyle("Energetic",    rate="+15%",  pitch="+5Hz",  volume="+10%",  description="Fast, high-energy narration"),
    VoiceStyle("Calm",         rate="-10%",  pitch="-3Hz",  volume="-5%",   description="Slow, soothing narration"),
    VoiceStyle("Dramatic",     rate="-5%",   pitch="+8Hz",  volume="+5%",   description="Intense, emotional delivery"),
    VoiceStyle("Storyteller",  rate="+5%",   pitch="-2Hz",  volume="+0%",   description="Warm, narrative tone"),
]

_last_voice_style: Optional[str] = None


# ---------------------------------------------------------------------------
# 2. Music Mood Variation
# ---------------------------------------------------------------------------

@dataclass
class MusicMoodProfile:
    name: str
    preferred_tracks: List[str]   # filenames from music_selector track bank
    volume_db: float              # relative volume adjustment in dB
    fade_in_sec: float
    fade_out_sec: float
    description: str


MUSIC_MOODS: List[MusicMoodProfile] = [
    MusicMoodProfile(
        name="Epic",
        preferred_tracks=["epic.mp3"],
        volume_db=-3.0, fade_in_sec=2.0, fade_out_sec=4.0,
        description="Grand, cinematic feel",
    ),
    MusicMoodProfile(
        name="Emotional",
        preferred_tracks=["romantic.mp3", "nature.mp3"],
        volume_db=-6.0, fade_in_sec=3.0, fade_out_sec=5.0,
        description="Soft, heartfelt background",
    ),
    MusicMoodProfile(
        name="Mysterious",
        preferred_tracks=["mystery.mp3"],
        volume_db=-4.0, fade_in_sec=1.5, fade_out_sec=3.0,
        description="Tense, suspenseful atmosphere",
    ),
    MusicMoodProfile(
        name="Devotional",
        preferred_tracks=["devotional.mp3"],
        volume_db=-5.0, fade_in_sec=2.0, fade_out_sec=4.0,
        description="Spiritual, peaceful tone",
    ),
    MusicMoodProfile(
        name="Adventure",
        preferred_tracks=["adventure.mp3"],
        volume_db=-3.0, fade_in_sec=1.0, fade_out_sec=3.0,
        description="Upbeat, action-driven energy",
    ),
]

_last_music_mood: Optional[str] = None


# ---------------------------------------------------------------------------
# 3. Scene Pacing Profiles
# ---------------------------------------------------------------------------

@dataclass
class PacingProfile:
    name: str
    min_duration: float   # seconds per scene
    max_duration: float
    hook_duration: float  # first scene duration (hooks are shorter)
    transition_speed: str # "fast" | "normal" | "slow"
    description: str


PACING_PROFILES: List[PacingProfile] = [
    PacingProfile(
        name="Fast Cut",
        min_duration=3.0, max_duration=5.0, hook_duration=2.5,
        transition_speed="fast",
        description="High energy, short clips — good for action/trending topics",
    ),
    PacingProfile(
        name="Balanced",
        min_duration=4.5, max_duration=7.0, hook_duration=3.5,
        transition_speed="normal",
        description="Standard pacing — works for most story types",
    ),
    PacingProfile(
        name="Slow Burn",
        min_duration=6.0, max_duration=9.0, hook_duration=5.0,
        transition_speed="slow",
        description="Deliberate, emotional pacing — good for drama/devotional",
    ),
    PacingProfile(
        name="Dynamic",
        min_duration=3.5, max_duration=8.0, hook_duration=3.0,
        transition_speed="normal",
        description="Variable pacing — alternates fast and slow scenes",
    ),
]

_last_pacing: Optional[str] = None


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

@dataclass
class ContentVariationPlan:
    voice_style: VoiceStyle
    music_mood: MusicMoodProfile
    pacing: PacingProfile

    def summary(self) -> str:
        return (
            f"Voice={self.voice_style.name} | "
            f"Music={self.music_mood.name} | "
            f"Pacing={self.pacing.name}"
        )


class ContentVariationEngine:
    """
    Selects voice style, music mood, and scene pacing for each video
    to maximise content diversity across the channel.

    Avoids repeating the same combination back-to-back.

    Usage::

        engine = ContentVariationEngine()
        plan = engine.pick_plan()
        # plan.voice_style, plan.music_mood, plan.pacing

        # Or force specific axes:
        plan = engine.pick_plan(force_voice="Dramatic", force_pacing="Fast Cut")
    """

    def pick_plan(
        self,
        force_voice: Optional[str] = None,
        force_music: Optional[str] = None,
        force_pacing: Optional[str] = None,
    ) -> ContentVariationPlan:
        """Return a varied ContentVariationPlan, avoiding last-used values."""
        global _last_voice_style, _last_music_mood, _last_pacing

        voice  = self._pick_voice(force_voice)
        music  = self._pick_music(force_music)
        pacing = self._pick_pacing(force_pacing)

        _last_voice_style = voice.name
        _last_music_mood  = music.name
        _last_pacing      = pacing.name

        plan = ContentVariationPlan(voice_style=voice, music_mood=music, pacing=pacing)
        logger.info("ContentVariationPlan: %s", plan.summary())
        return plan

    def pick_plan_for_topic(self, topic: str, narrative_code: str = "") -> ContentVariationPlan:
        """
        Pick a plan that complements the topic and narrative structure.
        Applies heuristic rules before falling back to random rotation.
        """
        topic_lower = topic.lower()

        # Voice heuristics
        force_voice = None
        if any(w in topic_lower for w in ["war", "battle", "fight", "hero", "victory"]):
            force_voice = "Dramatic"
        elif any(w in topic_lower for w in ["god", "temple", "prayer", "bhakti", "devotional"]):
            force_voice = "Calm"
        elif any(w in topic_lower for w in ["mystery", "secret", "hidden", "ghost"]):
            force_voice = "Storyteller"

        # Music heuristics
        force_music = None
        if any(w in topic_lower for w in ["devotional", "bhakti", "krishna", "shiva", "ram"]):
            force_music = "Devotional"
        elif any(w in topic_lower for w in ["mystery", "thriller", "crime", "ghost"]):
            force_music = "Mysterious"
        elif any(w in topic_lower for w in ["war", "battle", "kingdom", "empire"]):
            force_music = "Epic"

        # Pacing heuristics — narrative code D/E tend to be faster
        force_pacing = None
        if narrative_code in ("D", "E"):
            force_pacing = "Fast Cut"
        elif narrative_code in ("B",):
            force_pacing = "Slow Burn"

        return self.pick_plan(
            force_voice=force_voice,
            force_music=force_music,
            force_pacing=force_pacing,
        )

    def build_ssml_wrapper(self, text: str, voice_style: VoiceStyle) -> str:
        """
        Wrap narration text in Edge-TTS compatible SSML prosody tags.
        Pass the result to edge_tts.Communicate() instead of plain text.
        """
        return (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="hi-IN">'
            f'<prosody rate="{voice_style.rate}" pitch="{voice_style.pitch}" '
            f'volume="{voice_style.volume}">{text}</prosody>'
            f'</speak>'
        )

    def scene_durations(self, scene_count: int, pacing: PacingProfile) -> List[float]:
        """
        Generate per-scene duration list based on pacing profile.
        First scene uses hook_duration; rest vary within min/max.
        Dynamic pacing alternates short/long.
        """
        durations: List[float] = []
        for i in range(scene_count):
            if i == 0:
                durations.append(pacing.hook_duration)
            elif pacing.name == "Dynamic":
                # Alternate fast and slow
                if i % 2 == 0:
                    d = round(random.uniform(pacing.min_duration, (pacing.min_duration + pacing.max_duration) / 2), 1)
                else:
                    d = round(random.uniform((pacing.min_duration + pacing.max_duration) / 2, pacing.max_duration), 1)
                durations.append(d)
            else:
                durations.append(round(random.uniform(pacing.min_duration, pacing.max_duration), 1))
        return durations

    def music_ffmpeg_args(self, mood: MusicMoodProfile, music_path: str) -> List[str]:
        """
        Return FFmpeg audio filter args for mixing BGM at the mood's volume
        with fade-in and fade-out applied.
        """
        vol_factor = 10 ** (mood.volume_db / 20.0)
        return [
            "-i", music_path,
            "-filter_complex",
            (
                f"[1:a]volume={vol_factor:.4f},"
                f"afade=t=in:st=0:d={mood.fade_in_sec},"
                f"afade=t=out:st=0:d={mood.fade_out_sec}[bgm];"
                "[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            ),
            "-map", "0:v", "-map", "[aout]",
        ]

    # ------------------------------------------------------------------
    # Internal pickers
    # ------------------------------------------------------------------

    def _pick_voice(self, force: Optional[str]) -> VoiceStyle:
        global _last_voice_style
        if force:
            match = next((v for v in VOICE_STYLES if v.name == force), None)
            if match:
                return match
        choices = [v for v in VOICE_STYLES if v.name != _last_voice_style]
        return random.choice(choices or VOICE_STYLES)

    def _pick_music(self, force: Optional[str]) -> MusicMoodProfile:
        global _last_music_mood
        if force:
            match = next((m for m in MUSIC_MOODS if m.name == force), None)
            if match:
                return match
        choices = [m for m in MUSIC_MOODS if m.name != _last_music_mood]
        return random.choice(choices or MUSIC_MOODS)

    def _pick_pacing(self, force: Optional[str]) -> PacingProfile:
        global _last_pacing
        if force:
            match = next((p for p in PACING_PROFILES if p.name == force), None)
            if match:
                return match
        choices = [p for p in PACING_PROFILES if p.name != _last_pacing]
        return random.choice(choices or PACING_PROFILES)
