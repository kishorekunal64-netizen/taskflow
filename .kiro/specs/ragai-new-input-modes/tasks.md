# Implementation Plan: ragai-new-input-modes

## Overview

Extend the RAGAI Video Factory with two new input modes — Audio Storytelling (`AUDIO`) and Image Upload (`IMAGE`) — by adding new models, two new modules (`audio_transcriber.py`, `image_importer.py`), routing logic in the pipeline, and UI/CLI entry points.

## Tasks

- [x] 1. Extend models.py with new types
  - Add `InputMode` enum with values `TOPIC`, `SCRIPT`, `AUDIO`, `IMAGE`
  - Add `AudioTranscriptionError` and `ImageImportError` exception classes inheriting from `RAGAIError`
  - Add `input_mode`, `audio_file`, `image_files`, and `image_context` fields to `PipelineConfig` with appropriate defaults
  - _Requirements: 6.3, 6.4, 6.5, 8.1, 8.2_

- [ ] 2. Implement AudioTranscriber and AudioSplitter in audio_transcriber.py
  - [x] 2.1 Implement `WordTimestamp` dataclass and `AudioTranscriber` class
    - Define `SUPPORTED_FORMATS`, `MAX_FILE_SIZE_BYTES`, and `GROQ_WHISPER_URL` constants
    - Implement `transcribe(audio_path)` — validate extension, POST to Groq Whisper API, return transcript string; raise `AudioTranscriptionError` on API error or unreadable file
    - Implement `get_word_timestamps(audio_path)` — use `verbose_json` response format, return `List[WordTimestamp]` (empty list if not provided)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.5, 9.1, 9.3_

  - [~] 2.2 Write property test for audio extension validation (Property 1)
    - **Property 1: Audio file extension validation accepts only supported formats**
    - **Validates: Requirements 1.3, 1.4**

  - [~] 2.3 Write property test for Groq error codes raising AudioTranscriptionError (Property 3)
    - **Property 3: Groq Whisper API error codes produce AudioTranscriptionError**
    - **Validates: Requirements 2.3**

  - [~] 2.4 Write property test for supported format acceptance (Property 4)
    - **Property 4: AudioTranscriber accepts all supported audio formats without format rejection**
    - **Validates: Requirements 2.5**

  - [x] 2.5 Implement `AudioSplitter` class in audio_transcriber.py
    - Implement `split(audio_path, scenes, work_dir)` using pydub — split audio into per-scene segments based on `scene.duration_seconds`, assign `scene.audio_path`, pad final segment with silence if source is shorter than total duration
    - _Requirements: 3.2, 3.3, 3.4_

  - [~] 2.6 Write property test for audio splitting producing N segments (Property 5)
    - **Property 5: Audio splitting produces exactly N segments with audio_path assigned**
    - **Validates: Requirements 3.2, 3.3**

  - [~] 2.7 Write unit tests for AudioTranscriber and AudioSplitter
    - Test `transcribe()` with mocked Groq API responses (success, 4xx, 5xx, network error)
    - Test `get_word_timestamps()` with mocked verbose_json response
    - Test `split()` with a real short WAV file — verify segment count and file existence
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.2, 3.3_

- [x] 3. Checkpoint — Ensure all audio_transcriber tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Implement ImageImporter in image_importer.py
  - [x] 4.1 Implement `ImageImporter` class
    - Define `SUPPORTED_FORMATS` constant `{".jpg", ".jpeg", ".png", ".webp"}`
    - Implement `load_and_resize(image_paths, fmt, n_scenes)` — validate each file can be opened by PIL, resize to `IMAGE_RESOLUTIONS[fmt]`, save to `work_dir`, cycle if fewer than `n_scenes`, truncate if more; raise `ImageImportError` on PIL failure
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.6, 5.7_

  - [ ] 4.2 Write property test for image extension validation (Property 2)
    - **Property 2: Image file extension validation accepts only supported formats**
    - **Validates: Requirements 4.3, 4.4**

  - [ ] 4.3 Write property test for resized image dimensions (Property 7)
    - **Property 7: Resized images match target VideoFormat dimensions**
    - **Validates: Requirements 5.3, 5.4**

  - [ ] 4.4 Write property test for ImageImporter output length (Property 8)
    - **Property 8: ImageImporter output length always equals n_scenes**
    - **Validates: Requirements 5.6, 5.7**

  - [ ] 4.5 Write unit tests for ImageImporter
    - Test `load_and_resize()` with real PIL images — verify dimensions and file existence
    - Test with a corrupt file — verify `ImageImportError` is raised
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 5. Checkpoint — Ensure all image_importer tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Update pipeline.py with input_mode routing
  - [x] 6.1 Add imports and instantiate new components in `Pipeline.__init__`
    - Import `InputMode`, `AudioTranscriptionError`, `ImageImportError` from `models`
    - Import `AudioTranscriber`, `AudioSplitter` from `audio_transcriber`
    - Import `ImageImporter` from `image_importer`
    - Conditionally instantiate `AudioTranscriber` and `AudioSplitter` (AUDIO mode) and `ImageImporter` (IMAGE mode) inside `__init__`
    - Log the active `input_mode` at the start of `run()`
    - _Requirements: 7.6_

  - [x] 6.2 Route Stage 2 (story/transcript) by input_mode
    - `AUDIO` → call `AudioTranscriber.transcribe()` then `StoryGenerator.parse_script()`; wrap in try/except for `AudioTranscriptionError` (log + append + re-raise)
    - `IMAGE` → call `StoryGenerator.generate(topic=image_context or derived_topic)`
    - `TOPIC` / `SCRIPT` → existing logic unchanged
    - Add guard: if both AUDIO and IMAGE somehow set, raise `ConfigError`
    - _Requirements: 2.6, 6.1, 6.2, 7.1, 7.2, 7.3, 7.4, 7.5, 8.3_

  - [x] 6.3 Route Stage 3 (image generation) by input_mode
    - `IMAGE` → call `ImageImporter.load_and_resize()` and assign paths to `scene.image_path`; wrap in try/except for `ImageImportError` (log + append + re-raise)
    - All other modes → existing `ImageGenerator.generate_one()` logic unchanged
    - _Requirements: 5.5, 7.4, 8.4_

  - [x] 6.4 Route Stage 4 (voice synthesis) by input_mode
    - `AUDIO` → call `AudioSplitter.split()` instead of `VoiceSynthesizer.synthesize_one()`
    - All other modes → existing `VoiceSynthesizer.synthesize_one()` logic unchanged
    - _Requirements: 3.1, 3.2, 3.3, 7.3_

  - [ ] 6.5 Write property test for AUDIO mode skipping VoiceSynthesizer (Property 6)
    - **Property 6: AUDIO mode pipeline skips VoiceSynthesizer**
    - **Validates: Requirements 3.1, 7.3**

  - [ ] 6.6 Write property test for IMAGE mode skipping ImageGenerator (Property 9)
    - **Property 9: IMAGE mode pipeline skips Leonardo AI image generation**
    - **Validates: Requirements 5.5, 7.4**

  - [ ] 6.7 Write property test for new-mode errors re-raised by pipeline (Property 10)
    - **Property 10: New-mode errors are re-raised by the pipeline**
    - **Validates: Requirements 8.3, 8.4**

  - [ ] 6.8 Write unit tests for pipeline routing
    - Test `run()` with `input_mode=AUDIO` — mock all components, verify `VoiceSynthesizer.synthesize_one` not called
    - Test `run()` with `input_mode=IMAGE` — mock all components, verify `ImageGenerator.generate_one` not called
    - Test `run()` with conflicting modes — verify `ConfigError` raised
    - _Requirements: 7.3, 7.4, 7.5_

- [x] 7. Checkpoint — Ensure all pipeline routing tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Update gui.py with new input mode controls
  - [x] 8.1 Add "Upload Audio Story" and "Upload Images" radio buttons to the Story Source LabelFrame
    - Add radio buttons with values `"audio"` and `"image"` alongside existing `"topic"` and `"script"` buttons
    - _Requirements: 1.1, 4.1_

  - [x] 8.2 Implement `_audio_frame` and `_image_frame` widgets and `_on_source_change` extension
    - `_audio_frame`: file-picker button + selected path label; filter to Supported_Audio_Formats
    - `_image_frame`: multi-select file-picker button + selected paths label + context text entry
    - Extend `_on_source_change()` to show/hide the correct frame for all four modes
    - _Requirements: 1.2, 4.2_

  - [x] 8.3 Add GUI validation for audio and image modes in `_on_generate`
    - AUDIO: validate file is selected and extension is in Supported_Audio_Formats; show inline error if not
    - IMAGE: validate at least one image selected and all extensions are in Supported_Image_Formats; show inline error if not
    - _Requirements: 1.3, 1.4, 4.3, 4.4, 4.5, 4.6_

  - [x] 8.4 Build `PipelineConfig` with new fields for audio and image modes in `_on_generate`
    - Set `input_mode`, `audio_file`, `image_files`, `image_context` on `PipelineConfig` based on selected source
    - _Requirements: 6.3, 6.4, 6.5_

  - [ ] 8.5 Write unit tests for GUI widget visibility toggling
    - Test that selecting each radio button shows/hides the correct frames
    - Test validation error messages for missing audio file and missing image files
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [ ] 9. Update ragai.py CLI with new arguments
  - [x] 9.1 Add `--audio-file`, `--image-files`, and `--image-context` arguments to the argument parser
    - `--audio-file PATH`
    - `--image-files PATH[,PATH,...]` (comma-separated)
    - `--image-context TEXT`
    - _Requirements: 1.5, 4.7_

  - [x] 9.2 Extend `cli_main()` to set `input_mode` and validate new arguments
    - Detect which new argument is present and set `input_mode` accordingly on `PipelineConfig`
    - Validate `--audio-file` path exists; print error and `sys.exit(1)` if not
    - Validate each path in `--image-files` exists; print error listing missing paths and `sys.exit(1)` if any missing
    - _Requirements: 1.6, 4.8_

  - [ ] 9.3 Write unit tests for CLI argument parsing
    - Test `--audio-file` sets `input_mode=AUDIO` and correct `audio_file` value
    - Test `--image-files` sets `input_mode=IMAGE` and correct `image_files` list
    - Test missing file path triggers `sys.exit(1)`
    - _Requirements: 1.5, 1.6, 4.7, 4.8_

- [ ] 10. Write transcript round-trip property test (Property 11)
  - [ ] 10.1 Write property test for transcript round-trip preserving significant words
    - **Property 11: Transcript round-trip — parse_script preserves significant words**
    - **Validates: Requirements 9.2**

- [x] 11. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Property tests use `hypothesis` with `@settings(max_examples=100)`; each must include the comment tag `# Feature: ragai-new-input-modes, Property N: <property_text>`
- Test files live in `tests/` at the project root: `test_audio_transcriber.py`, `test_image_importer.py`, `test_pipeline_routing.py`, `test_gui_input_modes.py`, `test_cli_input_modes.py`
- `pydub` is used for audio splitting (already a project dependency via `voice_synthesizer.py`)
- `TOPIC` and `SCRIPT` pipeline paths remain completely unchanged
