# Implementation Plan: RAGAI Video Factory

## Overview

Implement the RAGAI pure-Python pipeline in dependency order: shared models and config first, then each pipeline stage (story → image → voice → video), then the interfaces (GUI, CLI), then supporting tools (music generator, diagnostics, launcher), and finally the test suite.

## Tasks

- [x] 1. Implement shared data models and enums
  - Create `models.py` (or inline in `pipeline.py`) with `Audience`, `Language`, `VideoFormat`, `VisualStyle`, `Scene`, `StyleConfig`, `PipelineConfig`, `PipelineResult`, `PipelineContext` dataclasses and enums
  - Define `RESOLUTIONS` and `IMAGE_RESOLUTIONS` constants
  - Define the `RAGAIError` exception hierarchy: `ConfigError`, `StoryGenerationError`, `ImageGenerationError`, `VoiceSynthesisError`, `VideoAssemblyError`, `FFmpegNotFoundError`
  - _Requirements: 1.3, 2.3, 3.1, 5.5, 9.2_

- [x] 2. Implement `config.py` — environment loading and validation
  - [x] 2.1 Implement `load_config()` using `python-dotenv` to read `.env`
    - Validate presence of `GROQ_API_KEY` and `LEONARDO_API_KEY`; raise `ConfigError` naming the missing key(s) on failure
    - Load optional flags `USE_EDGE_TTS`, `DEFAULT_LANGUAGE`, `DEFAULT_FORMAT`, `LOG_LEVEL` with documented defaults
    - Ensure no API key value is ever written to stdout or logs
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 2.2 Write property test for config validation (Property 17)
    - **Property 17: Config raises error for any missing required key**
    - **Validates: Requirements 9.2, 9.4**

  - [ ]* 2.3 Write unit tests for `config.py`
    - Test valid `.env` loads all fields with correct types and defaults
    - Test missing `GROQ_API_KEY`, missing `LEONARDO_API_KEY`, missing both — each raises `ConfigError` with the key name in the message
    - _Requirements: 9.1–9.4_

- [x] 3. Implement `style_detector.py` — visual style system
  - [x] 3.1 Define `STYLE_PROMPT_MODIFIERS`, `STYLE_COLOR_GRADE`, `STYLE_MUSIC_MAP` dicts for all 6 named styles
    - Each dict must have a non-empty entry for every `VisualStyle` member except AUTO
    - _Requirements: 3.1, 3.3_

  - [x] 3.2 Implement `StyleDetector.detect()` with `_keyword_match()` for AUTO resolution
    - Map topic keywords to the most appropriate `VisualStyle`
    - _Requirements: 3.2_

  - [ ]* 3.3 Write property test for style config completeness (Property 8)
    - **Property 8: Every VisualStyle has complete style config entries**
    - **Validates: Requirements 3.3**

- [x] 4. Implement `story_generator.py` — Groq LLM story generation
  - [x] 4.1 Implement `StoryGenerator.__init__`, `_call_groq()`, `_build_prompt()`, `_parse_llm_response()`
    - `_build_prompt` must embed audience, style, language, and character name instructions
    - `_call_groq` must handle HTTP 429 by retrying with `llama-3.1-8b-instant` and notifying the user; raise `StoryGenerationError` for all other errors
    - _Requirements: 1.1, 1.4, 1.5, 1.6, 1.8_

  - [x] 4.2 Implement `StoryGenerator.generate()` and `parse_script()`
    - `generate` returns 5–12 `Scene` objects with non-empty `narration`, `image_prompt`, positive `duration_seconds`, and unique `number`
    - `parse_script` parses a user-supplied script into scenes without calling the API
    - Apply character name substitution when `character_names` is non-empty
    - _Requirements: 1.1, 1.2, 1.3, 1.7_

  - [ ]* 4.3 Write property test for scene count invariant (Property 1)
    - **Property 1: Story scene count invariant**
    - **Validates: Requirements 1.1, 1.3**

  - [ ]* 4.4 Write property test for LLM prompt audience+style inclusion (Property 2)
    - **Property 2: LLM prompt contains audience and style**
    - **Validates: Requirements 1.6**

  - [ ]* 4.5 Write property test for character name substitution completeness (Property 3)
    - **Property 3: Character name substitution completeness**
    - **Validates: Requirements 1.7**

  - [ ]* 4.6 Write property test for language instruction in LLM prompt (Property 4)
    - **Property 4: Language instruction in LLM prompt**
    - **Validates: Requirements 1.8, 6.2**

  - [ ]* 4.7 Write unit tests for `story_generator.py`
    - Test Groq 429 triggers fallback model and user notification
    - Test non-429 Groq error raises `StoryGenerationError` with logged details
    - _Requirements: 1.4, 1.5_

- [x] 5. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement `image_generator.py` — Leonardo AI image generation
  - [x] 6.1 Implement `ImageGenerator.__init__`, `_build_prompt()`, `_poll_generation()`, `_download_image()`, `_placeholder_image()`, `_estimate_credits()`
    - `_build_prompt` must concatenate `scene.image_prompt` with `STYLE_PROMPT_MODIFIERS[style]`
    - Request resolution must match `IMAGE_RESOLUTIONS[fmt]` exactly
    - `_estimate_credits` warns when fewer than 20 credits remain
    - _Requirements: 2.1, 2.2, 2.3, 2.6_

  - [x] 6.2 Implement `ImageGenerator.generate_one()` and `generate_all()`
    - Retry non-200 responses up to 3 times with exponential backoff via `retry_with_backoff`
    - On total failure substitute `_placeholder_image` so the pipeline continues
    - Save each image to `work_dir` with filename encoding zero-padded scene number
    - _Requirements: 2.4, 2.5, 2.7_

  - [ ]* 6.3 Write property test for image prompt composition (Property 5)
    - **Property 5: Image prompt combines scene prompt and style modifiers**
    - **Validates: Requirements 2.2, 3.4**

  - [ ]* 6.4 Write property test for image request resolution (Property 6)
    - **Property 6: Image request resolution matches format**
    - **Validates: Requirements 2.3**

  - [ ]* 6.5 Write property test for output filename scene number encoding (Property 7)
    - **Property 7: Output files encode scene number**
    - **Validates: Requirements 2.7, 4.4**

  - [ ]* 6.6 Write unit tests for `image_generator.py`
    - Test Leonardo non-200 retries 3 times then uses placeholder
    - Test credit warning logged when estimate < 20
    - _Requirements: 2.4, 2.5, 2.6_

- [x] 7. Implement `voice_synthesizer.py` — Edge-TTS and gTTS synthesis
  - [x] 7.1 Define `VOICE_MAP` for all 10 supported languages
    - Store mapping in config-accessible structure so new languages require no code change
    - _Requirements: 4.2, 6.1, 6.3_

  - [x] 7.2 Implement `VoiceSynthesizer.__init__`, `_split_text()`, `_concat_audio()`, `_edge_tts()`, `_gtts_fallback()`
    - `_split_text` must split text > 500 chars into segments each ≤ 500 chars with round-trip fidelity
    - `_edge_tts` uses `VOICE_MAP[language]` as the voice name
    - `_gtts_fallback` is called when Edge-TTS raises any exception; log the fallback event
    - _Requirements: 4.1, 4.2, 4.3, 4.6_

  - [x] 7.3 Implement `VoiceSynthesizer.synthesize_one()` and `synthesize_all()`
    - Respect `USE_EDGE_TTS` flag — when false, skip Edge-TTS and call gTTS directly
    - Save each clip to `work_dir` with filename encoding zero-padded scene number
    - _Requirements: 4.4, 4.5_

  - [ ]* 7.4 Write property test for correct voice per language (Property 10)
    - **Property 10: Voice synthesizer uses correct voice for every language**
    - **Validates: Requirements 4.2, 6.1**

  - [ ]* 7.5 Write property test for long narration splitting (Property 11)
    - **Property 11: Long narration is split into segments ≤ 500 characters**
    - **Validates: Requirements 4.6**

  - [ ]* 7.6 Write unit tests for `voice_synthesizer.py`
    - Test Edge-TTS failure triggers gTTS fallback and logs the event
    - Test `USE_EDGE_TTS=false` calls gTTS directly without attempting Edge-TTS
    - _Requirements: 4.3, 4.5_

- [x] 8. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement `video_assembler.py` — Ken Burns animation and FFmpeg encoding
  - [x] 9.1 Implement `VideoAssembler.__init__` and FFmpeg pre-flight check
    - On init, verify FFmpeg is on PATH via `shutil.which`; raise `FFmpegNotFoundError` with install instructions if absent
    - _Requirements: 5.7_

  - [x] 9.2 Implement `_ken_burns_frames()` — PIL frame generation
    - Generate exactly `round(duration_seconds * FPS)` frames per scene
    - Interpolate zoom in `[1.0, 1.25]` and pan using smoothstep easing
    - Each frame must be a numpy array of shape `(H_out, W_out, 3)` uint8
    - _Requirements: 5.1_

  - [ ]* 9.3 Write property test for Ken Burns frame count (Property 12)
    - **Property 12: Ken Burns frame count matches duration × FPS**
    - **Validates: Requirements 5.1**

  - [ ]* 9.4 Write property test for Ken Burns zoom range (Property 13)
    - **Property 13: Ken Burns zoom values stay within safe range**
    - **Validates: Requirements 5.1**

  - [x] 9.5 Implement `_write_scene_clip()`, `_concat_clips()` with xfade crossfade
    - Per-scene clip: frames → PNG sequence → FFmpeg H.264 + AAC 192k, `-shortest` for audio sync
    - Concatenation: build xfade filter chain with `duration=0.5` between every consecutive clip pair
    - _Requirements: 5.2, 5.4, 5.8_

  - [ ]* 9.6 Write property test for crossfade transition duration (Property 16)
    - **Property 16: Crossfade transition duration is 0.5 seconds**
    - **Validates: Requirements 5.8**

  - [x] 9.7 Implement `_select_music()`, `_mix_music()`, and final FFmpeg encode
    - `_select_music` returns path matching `STYLE_MUSIC_MAP[style]` from `music/` dir
    - Music mixed at ≤ -18 dBFS relative to voiceover; loop track if shorter than video
    - Apply `afade=t=in:d=2` and `afade=t=out:d=3` filters
    - Apply `STYLE_COLOR_GRADE[style]` filter in `-filter_complex`
    - Encode at `8000k` for LANDSCAPE, `6000k` for SHORTS; audio at `192k` AAC stereo
    - _Requirements: 5.3, 5.4, 5.5, 11.3, 11.4, 11.5, 12.1, 12.2_

  - [ ]* 9.8 Write property test for FFmpeg encoding spec (Property 14)
    - **Property 14: FFmpeg encoding spec correctness**
    - **Validates: Requirements 5.4, 5.5, 12.1, 12.2**

  - [ ]* 9.9 Write property test for color grade filter in FFmpeg command (Property 9)
    - **Property 9: FFmpeg command contains color grade filter for selected style**
    - **Validates: Requirements 3.5**

  - [ ]* 9.10 Write property test for music fade filters (Property 21)
    - **Property 21: Music fade filters present in FFmpeg command**
    - **Validates: Requirements 11.5**

  - [ ]* 9.11 Write property test for music selection matching style (Property 20)
    - **Property 20: Music selection matches Visual Style**
    - **Validates: Requirements 11.3**

  - [x] 9.12 Implement `_generate_thumbnail()`, `_write_metadata_txt()`, output filename, and MP4 metadata tags
    - Thumbnail: 1280×720 JPEG from most visually prominent scene image
    - Metadata `.txt`: non-empty title, description, exactly 10 hashtags derived from topic and language
    - Output filename: URL-safe topic slug + UTC timestamp + `.mp4`
    - FFmpeg command must include `-metadata title=<topic>` and `-metadata comment=<timestamp>`
    - _Requirements: 5.6, 12.3, 12.4, 12.5_

  - [ ]* 9.13 Write property test for output filename slug and timestamp (Property 15)
    - **Property 15: Output filename contains topic slug and timestamp**
    - **Validates: Requirements 5.6**

  - [ ]* 9.14 Write property test for metadata .txt content (Property 22)
    - **Property 22: Metadata .txt contains title, description, and exactly 10 hashtags**
    - **Validates: Requirements 12.3**

  - [ ]* 9.15 Write property test for MP4 metadata tags in FFmpeg command (Property 23)
    - **Property 23: MP4 metadata tags present in FFmpeg command**
    - **Validates: Requirements 12.4**

  - [ ]* 9.16 Write property test for thumbnail dimensions (Property 24)
    - **Property 24: Thumbnail is 1280×720 JPEG**
    - **Validates: Requirements 12.5**

  - [ ]* 9.17 Write unit tests for `video_assembler.py`
    - Test `FFmpegNotFoundError` raised when `shutil.which("ffmpeg")` returns None
    - Test FFmpeg non-zero exit raises `VideoAssemblyError` with stderr logged
    - _Requirements: 5.7_

- [x] 10. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement `pipeline.py` — pipeline orchestrator
  - [x] 11.1 Implement `Pipeline.__init__`, `_update_progress()`, and `run()`
    - `run()` executes stages in order: style detection → story → images → voices → assembly
    - Call `progress_callback` after each scene and each stage transition
    - Collect errors in `PipelineContext.errors`; propagate stage exceptions to caller
    - Return `PipelineResult` with `output_path`, `thumbnail_path`, `metadata_txt_path`, `scenes`, `elapsed_seconds`
    - _Requirements: 1.1–1.8, 2.1–2.7, 4.1–4.6, 5.1–5.8_

  - [ ]* 11.2 Write unit tests for `pipeline.py`
    - Test full pipeline run with all external calls mocked returns a valid `PipelineResult`
    - Test that a stage exception propagates correctly to the caller
    - _Requirements: 5.1–5.8_

- [x] 12. Implement `gui.py` — tkinter GUI
  - [x] 12.1 Implement `RAGAIApp._build_ui()` with all input controls
    - Controls for: story source toggle (topic / script file), topic text entry, audience dropdown, language dropdown, visual style dropdown, format toggle, character name fields
    - Progress bar and stage label updated in real time
    - _Requirements: 8.1, 8.2_

  - [x] 12.2 Implement `_on_generate()`, `_start_pipeline_thread()`, `_poll_queue()` thread-safety pattern
    - Pipeline runs on a daemon `threading.Thread`; progress marshalled to main thread via `queue.Queue` + `root.after(100, _poll_queue)`
    - _Requirements: 8.5_

  - [x] 12.3 Implement `_on_complete()`, `_on_error()`, `_open_output_dir()`
    - On complete: display output path, enable "Open Folder" button that calls `os.startfile` (Windows)
    - On error: display message in status label or `messagebox.showerror` without crashing
    - _Requirements: 8.3, 8.4_

  - [ ]* 12.4 Write unit tests for `gui.py`
    - Test pipeline runs on a non-main thread (verify `threading.current_thread() != threading.main_thread()`)
    - Test error from pipeline is displayed without raising in the GUI
    - _Requirements: 8.4, 8.5_

- [x] 13. Implement `ragai.py` — entry point, CLI, and mode routing
  - [x] 13.1 Implement `main()` argument parsing and mode dispatch
    - Accept `--cli`, `--gui`, `--web` flags; default to GUI when no mode flag given
    - Parse all CLI arguments: `--topic`, `--script-file`, `--audience`, `--language`, `--style`, `--format`, `--character-names`, `--output-dir`, `--diagnose`
    - _Requirements: 7.1, 7.6_

  - [x] 13.2 Implement `cli_main()` — interactive prompt fallback and progress display
    - When `--topic` and `--script-file` are both absent, enter interactive prompt mode asking for each required input
    - Display real-time progress indicator showing current stage and scene number
    - On success print absolute path of generated MP4; on any exception print human-readable message and `sys.exit(1)`
    - When `--diagnose` is passed, call `ragai_diagnose` and exit without running the pipeline
    - _Requirements: 7.2, 7.3, 7.4, 7.5, 7.6_

  - [ ]* 13.3 Write unit tests for `ragai.py`
    - Test all CLI flags are accepted and mapped to correct `PipelineConfig` fields
    - Test interactive mode is triggered when both `--topic` and `--script-file` are omitted
    - Test `--diagnose` flag runs diagnostics and exits without pipeline execution
    - _Requirements: 7.1, 7.2, 7.6_

- [x] 14. Implement `create_music_v2.py` — programmatic music library generation
  - Implement script that generates exactly 7 `.mp3` background tracks in `music/`, one per non-AUTO `VisualStyle`
  - Each track filename must match the corresponding entry in `STYLE_MUSIC_MAP`
  - _Requirements: 11.1, 11.2_

  - [ ]* 14.1 Write unit test for music library file count
    - Verify exactly 7 `.mp3` files exist in `music/` after running `create_music_v2.py`
    - _Requirements: 11.1_

- [x] 15. Implement `ragai_diagnose.py` — diagnostic checker
  - Check and report with ✅/❌: Python version, required package installation, FFmpeg availability, `.env` file presence, API key validity (lightweight test calls), Music_Library file count
  - Print a remediation hint for every failed check
  - Wire `--diagnose` flag in `ragai.py` to invoke this script
  - _Requirements: 10.3, 10.4, 10.5, 7.6_

  - [ ]* 15.1 Write unit tests for `ragai_diagnose.py`
    - Mock each dependency (Python version, packages, FFmpeg, `.env`, API, music files) and verify correct ✅/❌ output and remediation hints
    - _Requirements: 10.3, 10.4, 10.5_

- [x] 16. Implement structured logging across all modules
  - Configure a `logging.Logger` in each module that writes to a timestamped file in `logs/`
  - Every log entry must include: ISO-8601 timestamp, log level, pipeline stage, scene number (where applicable), message
  - Add a log filter that strips patterns `sk-[A-Za-z0-9]+` and `Bearer [A-Za-z0-9]{20,}` before any write
  - _Requirements: 10.1, 10.2, 9.5_

  - [ ]* 16.1 Write property test for log entry fields (Property 19)
    - **Property 19: Log entries contain all required fields**
    - **Validates: Requirements 10.2**

  - [ ]* 16.2 Write property test for API key sanitisation in logs (Property 18)
    - **Property 18: Log entries never contain API key patterns**
    - **Validates: Requirements 9.5**

- [x] 17. Implement `START_RAGAI.bat` — Windows launcher
  - Activate the Python virtual environment (`venv\Scripts\activate.bat`)
  - Launch `python ragai.py --gui`
  - Display a user-friendly error message if the venv or `ragai.py` is not found at the expected path
  - _Requirements: 13.1, 13.2, 13.3_

- [x] 18. Final checkpoint — Ensure all tests pass
  - Run `python -m pytest tests/ -v` and confirm all tests pass.
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests use Hypothesis with `@settings(max_examples=100)` minimum; increase to 200 for critical properties (P1, P11, P12, P17)
- Unit tests use `pytest` with `unittest.mock` for external API calls
- Run tests with: `python -m pytest tests/ -v`
