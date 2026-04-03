"""
pipeline.py — Pipeline orchestrator for RAGAI Video Factory.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, List, Optional
from uuid import uuid4

from models import (
    ConfigError,
    InputMode,
    AudioTranscriptionError,
    ImageImportError,
    PipelineConfig,
    PipelineResult,
    Scene,
    VisualStyle,
)
from story_generator import StoryGenerator
from image_generator import ImageGenerator
from voice_synthesizer import VoiceSynthesizer
try:
    from voice_synthesizer_v2 import MultiSpeakerVoiceSynthesizer
    _MULTI_SPEAKER_AVAILABLE = True
except ImportError:
    _MULTI_SPEAKER_AVAILABLE = False
from video_assembler import VideoAssembler
from style_detector import StyleDetector
from audio_transcriber import AudioTranscriber, AudioSplitter
from image_importer import ImageImporter

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates the five-stage RAGAI video generation pipeline."""

    def __init__(
        self,
        config: PipelineConfig,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> None:
        self.config = config
        self.progress_callback = progress_callback

        # Unique working directory under tmp/
        self.work_dir = Path("tmp") / uuid4().hex
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Instantiate all pipeline components
        self.story_generator = StoryGenerator(api_key=config.groq_api_key)
        self.image_generator = ImageGenerator(
            api_key=config.leonardo_api_key,
            work_dir=self.work_dir / "images",
            hf_token=getattr(config, "hf_token", ""),
        )
        self.voice_synthesizer = VoiceSynthesizer(
            use_edge_tts=config.use_edge_tts,
            work_dir=self.work_dir / "audio",
        )
        # Use multi-speaker synthesizer if available and character names are set
        if _MULTI_SPEAKER_AVAILABLE:
            self._multi_speaker = MultiSpeakerVoiceSynthesizer(
                use_edge_tts=config.use_edge_tts,
                work_dir=self.work_dir / "audio",
                known_characters=list(config.character_names.values()) if config.character_names else [],
            )
        else:
            self._multi_speaker = None
        self.video_assembler = VideoAssembler(
            work_dir=self.work_dir / "video",
            music_dir=Path("music"),
            output_dir=config.output_dir,
            quality=config.quality,
        )
        self.style_detector = StyleDetector()

        # Conditionally instantiate new-mode components
        if config.input_mode == InputMode.AUDIO:
            self._audio_transcriber = AudioTranscriber(api_key=config.groq_api_key)
            self._audio_splitter = AudioSplitter()
        if config.input_mode == InputMode.IMAGE:
            self._image_importer = ImageImporter(work_dir=self.work_dir / "images")

        self._errors: List[str] = []

    # ------------------------------------------------------------------
    # Progress helper
    # ------------------------------------------------------------------

    def _update_progress(self, stage: str, scene_num: int, total: int) -> None:
        """Log progress and invoke the optional progress callback."""
        logger.info("Pipeline progress — stage=%s scene=%d/%d", stage, int(scene_num), int(total))
        if self.progress_callback is not None:
            self.progress_callback(stage, int(scene_num), int(total))

    # ------------------------------------------------------------------
    # Scene re-generate (public API for GUI)
    # ------------------------------------------------------------------

    def regenerate_scene_image(
        self,
        scene: Scene,
        style: VisualStyle,
    ) -> Path:
        """Re-generate the image for a single scene and re-encode its clip.

        Called from the GUI after a full pipeline run when the user wants to
        swap out one scene's image without re-running everything.

        Args:
            scene: The Scene object whose image_path and clip_path will be updated.
            style: The resolved VisualStyle used for the original run.

        Returns:
            The new image Path (also set on scene.image_path).
        """
        logger.info("Re-generating image for scene %d", int(scene.number))
        new_path = self.image_generator.generate_one(scene, style, self.config.format)
        scene.image_path = new_path
        logger.info("Scene %d image replaced: %s [provider: %s]",
                    int(scene.number), new_path, self.image_generator.active_provider)

        # Re-encode the scene clip so the new image appears in the final video
        logger.info("Re-encoding scene %d clip with new image", int(scene.number))
        self.video_assembler.regenerate_scene_clip(scene, self.config)

        return new_path

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(self) -> PipelineResult:
        """Execute all pipeline stages and return a PipelineResult.

        Raises:
            Any exception raised by a pipeline stage is propagated to the caller
            after being logged and appended to the internal errors list.
        """
        start_time = time.monotonic()
        logger.info("Input mode: %s", self.config.input_mode)

        # ----------------------------------------------------------------
        # Stage 1: Style detection
        # ----------------------------------------------------------------
        try:
            if self.config.style == VisualStyle.AUTO:
                logger.info("Stage 1: Auto-detecting visual style for topic=%r", self.config.topic)
                style = self.style_detector.detect(self.config.topic)
                logger.info("Style detected: %s", style)
            else:
                style = self.config.style
                logger.info("Stage 1: Using user-selected style=%s", style)
        except Exception as exc:
            self._errors.append(f"Style detection error: {exc}")
            logger.error("Stage 1 (style detection) failed: %s", exc)
            raise

        # ----------------------------------------------------------------
        # Stage 2: Story generation / transcript
        # ----------------------------------------------------------------
        # Guard: conflicting modes should never reach here, but be explicit.
        if self.config.audio_file and self.config.image_files:
            raise ConfigError(
                "Both audio_file and image_files are set — only one input mode may be active."
            )

        if self.config.input_mode == InputMode.AUDIO:
            try:
                logger.info("Stage 2: Transcribing audio file %r", self.config.audio_file)
                transcript = self._audio_transcriber.transcribe(Path(self.config.audio_file))
                logger.info("Transcription complete (%d chars)", len(transcript))
                scenes: List[Scene] = self.story_generator.parse_script(
                    transcript, self.config.language
                )
                logger.info("Parsed transcript into %d scenes", len(scenes))
            except AudioTranscriptionError as exc:
                self._errors.append(f"Transcription error: {exc}")
                logger.error("Stage 2 (transcription) failed: %s", exc)
                raise
            except Exception as exc:
                self._errors.append(f"Story generation error: {exc}")
                logger.error("Stage 2 (story generation) failed: %s", exc)
                raise

        elif self.config.input_mode == InputMode.IMAGE:
            try:
                logger.info("Stage 2: Generating story from image context")
                # Derive a topic from image filenames if no context provided
                topic = self.config.image_context or ", ".join(
                    Path(p).stem for p in self.config.image_files
                )
                scenes = self.story_generator.generate(
                    topic=topic,
                    audience=self.config.audience,
                    style=style,
                    language=self.config.language,
                    character_names=self.config.character_names,
                    scene_count=self.config.scene_count,
                    target_duration_minutes=getattr(self.config, "target_duration_minutes", 0.0),
                )
                logger.info("Generated %d scenes from image context", len(scenes))
            except Exception as exc:
                self._errors.append(f"Story generation error: {exc}")
                logger.error("Stage 2 (story generation) failed: %s", exc)
                raise

        else:
            # TOPIC / SCRIPT — existing logic unchanged
            try:
                logger.info("Stage 2: Story generation")
                if self.config.script_file:
                    script_text = Path(self.config.script_file).read_text(encoding="utf-8")
                    scenes = self.story_generator.parse_script(
                        script_text, self.config.language
                    )
                    logger.info("Parsed script into %d scenes", len(scenes))
                else:
                    scenes = self.story_generator.generate(
                        topic=self.config.topic,
                        audience=self.config.audience,
                        style=style,
                        language=self.config.language,
                        character_names=self.config.character_names,
                        scene_count=self.config.scene_count,
                        target_duration_minutes=getattr(self.config, "target_duration_minutes", 0.0),
                        trend_context=getattr(self.config, "trend_context", ""),
                    )
                    logger.info("Generated %d scenes from topic", len(scenes))
            except Exception as exc:
                self._errors.append(f"Story generation error: {exc}")
                logger.error("Stage 2 (story generation) failed: %s", exc)
                raise

        total_scenes = len(scenes)
        self._update_progress("story", 0, total_scenes)

        # ----------------------------------------------------------------
        # Stage 3: Image generation / import
        # ----------------------------------------------------------------
        if self.config.input_mode == InputMode.IMAGE:
            try:
                logger.info("Stage 3: Importing %d user images for %d scenes",
                            len(self.config.image_files), total_scenes)
                image_paths = [Path(p) for p in self.config.image_files]
                resized_paths = self._image_importer.load_and_resize(
                    image_paths, self.config.format, total_scenes
                )
                for scene, img_path in zip(scenes, resized_paths):
                    scene.image_path = img_path
                    self._update_progress("images", scene.number, total_scenes)
            except ImageImportError as exc:
                self._errors.append(f"Image import error: {exc}")
                logger.error("Stage 3 (image import) failed: %s", exc)
                raise
            except Exception as exc:
                self._errors.append(f"Image generation error: {exc}")
                logger.error("Stage 3 (image generation) failed: %s", exc)
                raise
        else:
            # TOPIC / SCRIPT / AUDIO — existing Leonardo AI logic unchanged
            try:
                logger.info("Stage 3: Image generation for %d scenes", total_scenes)
                for i, scene in enumerate(scenes, start=1):
                    scene.image_path = self.image_generator.generate_one(
                        scene, style, self.config.format
                    )
                    provider = self.image_generator.active_provider
                    logger.info("Scene %d/%d image ready [provider: %s]",
                                i, total_scenes, provider)
                    self._update_progress("images", i, total_scenes)
            except Exception as exc:
                self._errors.append(f"Image generation error: {exc}")
                logger.error("Stage 3 (image generation) failed: %s", exc)
                raise

        # ----------------------------------------------------------------
        # Stage 4: Voice synthesis / audio splitting
        # ----------------------------------------------------------------
        if self.config.input_mode == InputMode.AUDIO:
            try:
                logger.info("Stage 4: Splitting source audio into %d scene segments", total_scenes)
                self._audio_splitter.split(
                    Path(self.config.audio_file), scenes, self.work_dir / "audio"
                )
                self._update_progress("voice", total_scenes, total_scenes)
            except Exception as exc:
                self._errors.append(f"Audio splitting error: {exc}")
                logger.error("Stage 4 (audio splitting) failed: %s", exc)
                raise
        else:
            # TOPIC / SCRIPT / IMAGE — use multi-speaker if available, else standard
            try:
                logger.info("Stage 4: Voice synthesis for %d scenes", total_scenes)
                synth = self._multi_speaker if self._multi_speaker else self.voice_synthesizer
                for i, scene in enumerate(scenes, start=1):
                    scene.audio_path = synth.synthesize_one(
                        scene, self.config.language
                    )
                    self._update_progress("voice", i, total_scenes)
            except Exception as exc:
                self._errors.append(f"Voice synthesis error: {exc}")
                logger.error("Stage 4 (voice synthesis) failed: %s", exc)
                raise

        # ----------------------------------------------------------------
        # Stage 5: Video assembly
        # ----------------------------------------------------------------
        try:
            logger.info("Stage 5: Video assembly")
            self._update_progress("assembly", 0, 1)
            output_path = self.video_assembler.assemble(scenes, self.config)
        except Exception as exc:
            self._errors.append(f"Video assembly error: {exc}")
            logger.error("Stage 5 (video assembly) failed: %s", exc)
            raise

        elapsed = time.monotonic() - start_time
        logger.info("Pipeline complete in %.2fs — output: %s", elapsed, output_path)

        # Derive thumbnail and metadata paths from the output filename slug.
        slug = "_".join(output_path.stem.split("_")[:-2])
        output_dir = self.config.output_dir
        thumbnail_path = output_dir / f"{slug}_thumbnail.jpg"
        metadata_txt_path = output_dir / f"{slug}_metadata.txt"

        result = PipelineResult(
            output_path=output_path,
            thumbnail_path=thumbnail_path,
            metadata_txt_path=metadata_txt_path,
            scenes=scenes,
            elapsed_seconds=elapsed,
        )
        # Store for post-run scene regeneration
        self.last_result = result
        self.last_style = style
        return result
