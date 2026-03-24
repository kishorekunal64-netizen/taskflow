# Requirements Document

## Introduction

This feature adds two new input modes to the RAGAI Video Factory, expanding beyond the existing "Generate from Topic" and "Use Script File" options:

1. **Audio Storytelling Input** — The user uploads an audio file containing a narration or story. RAGAI transcribes the audio, derives scenes from the transcript, and generates a video aligned to the spoken content. The original audio is used as the scene narration track instead of synthesizing new voice.

2. **Image Upload Input** — The user uploads one or more images and provides a text context/description. RAGAI uses the uploaded images as the visual source for scenes (bypassing Leonardo AI image generation) and generates a story/narration from the provided context, then assembles a video.

Both modes integrate into the existing five-stage pipeline (`pipeline.py`) and are exposed through the GUI (`gui.py`) and CLI (`ragai.py`).

---

## Glossary

- **Pipeline**: The five-stage RAGAI orchestrator defined in `pipeline.py` that produces a final MP4 video.
- **PipelineConfig**: The dataclass in `models.py` that carries all configuration for a single pipeline run.
- **InputMode**: An enumeration value representing how the user supplies the primary creative input (topic, script, audio, or image).
- **Audio_Transcriber**: The new component responsible for converting an uploaded audio file into a text transcript.
- **Transcript**: The plain-text output produced by Audio_Transcriber from an uploaded audio file.
- **Scene**: The existing `Scene` dataclass in `models.py` — one unit of narration + image + audio + clip.
- **Image_Importer**: The new component responsible for validating and loading user-supplied images into Scene objects.
- **Context_Text**: Free-form text the user provides alongside uploaded images to guide story/narration generation.
- **Story_Generator**: The existing `StoryGenerator` class in `story_generator.py`.
- **Voice_Synthesizer**: The existing `VoiceSynthesizer` class in `voice_synthesizer.py`.
- **GUI**: The tkinter application defined in `gui.py`.
- **CLI**: The command-line interface defined in `ragai.py`.
- **Supported_Audio_Formats**: MP3, WAV, M4A, OGG, FLAC — the audio file types accepted by the Audio_Transcriber.
- **Supported_Image_Formats**: JPEG, PNG, WEBP — the image file types accepted by the Image_Importer.

---

## Requirements

### Requirement 1: Audio Input Mode — File Acceptance

**User Story:** As a content creator, I want to upload an audio file containing my narration, so that RAGAI can generate a video that matches my spoken story.

#### Acceptance Criteria

1. THE GUI SHALL display an "Upload Audio Story" radio button option alongside the existing "Generate from Topic" and "Use Script File" options in the Story Source section.
2. WHEN the user selects the "Upload Audio Story" input mode in the GUI, THE GUI SHALL show a file-picker control and hide the topic entry and script file controls.
3. WHEN the user selects an audio file via the file-picker, THE GUI SHALL validate that the file extension is one of the Supported_Audio_Formats (.mp3, .wav, .m4a, .ogg, .flac).
4. IF the selected file extension is not in Supported_Audio_Formats, THEN THE GUI SHALL display an error message stating the accepted formats and prevent pipeline execution.
5. THE CLI SHALL accept a `--audio-file PATH` argument that specifies the path to an audio file for the Audio Storytelling Input mode.
6. IF the `--audio-file` path does not exist or is not a file, THEN THE CLI SHALL print an error message and exit with a non-zero status code.

---

### Requirement 2: Audio Transcription

**User Story:** As a content creator, I want my uploaded audio to be automatically transcribed, so that RAGAI can use the spoken words as the story script.

#### Acceptance Criteria

1. WHEN an audio file is provided as input, THE Audio_Transcriber SHALL transcribe the audio file into a Transcript string using the Groq Whisper API.
2. WHEN transcription succeeds, THE Audio_Transcriber SHALL return a non-empty Transcript string.
3. IF the Groq Whisper API returns an error response, THEN THE Audio_Transcriber SHALL raise an `AudioTranscriptionError` with a descriptive message including the HTTP status code.
4. IF the audio file cannot be read or is corrupt, THEN THE Audio_Transcriber SHALL raise an `AudioTranscriptionError` with a descriptive message.
5. THE Audio_Transcriber SHALL support all Supported_Audio_Formats as input.
6. WHEN transcription produces a Transcript, THE Pipeline SHALL pass the Transcript to the Story_Generator's `parse_script` method to derive scenes, preserving the existing scene-parsing logic.

---

### Requirement 3: Audio Input — Voice Track Handling

**User Story:** As a content creator, I want the original audio from my uploaded file to be used as the narration track in the video, so that my own voice is preserved in the output.

#### Acceptance Criteria

1. WHEN the input mode is Audio Storytelling Input, THE Pipeline SHALL skip the Voice_Synthesizer stage and use the original uploaded audio as the narration source.
2. WHEN the input mode is Audio Storytelling Input, THE Pipeline SHALL split the original audio into per-scene segments based on the scene durations derived from the Transcript.
3. WHEN audio splitting produces a segment for a scene, THE Pipeline SHALL assign the segment file path to `scene.audio_path` so the Video_Assembler can use it without modification.
4. IF the original audio duration is shorter than the total scene duration sum, THEN THE Pipeline SHALL pad the final scene's audio segment with silence to match the required duration.
5. THE Audio_Transcriber SHALL expose a `get_word_timestamps` method that returns word-level timing data when the Groq Whisper API provides it, to enable accurate audio splitting.

---

### Requirement 4: Image Upload Input Mode — File Acceptance

**User Story:** As a content creator, I want to upload my own images and provide context about them, so that RAGAI generates a video using my images as the visual content.

#### Acceptance Criteria

1. THE GUI SHALL display an "Upload Images" radio button option alongside the existing input mode options in the Story Source section.
2. WHEN the user selects the "Upload Images" input mode in the GUI, THE GUI SHALL show an image file-picker (supporting multi-select), a context text entry field, and hide the topic and script file controls.
3. WHEN the user selects image files via the file-picker, THE GUI SHALL validate that each file's extension is one of the Supported_Image_Formats (.jpg, .jpeg, .png, .webp).
4. IF any selected file extension is not in Supported_Image_Formats, THEN THE GUI SHALL display an error message listing the invalid files and prevent pipeline execution.
5. THE GUI SHALL require at least one image to be selected before allowing pipeline execution in Image Upload mode.
6. IF the user attempts to generate a video in Image Upload mode with no images selected, THEN THE GUI SHALL display a validation error message.
7. THE CLI SHALL accept a `--image-files PATH[,PATH,...]` argument (comma-separated list of image paths) and a `--image-context TEXT` argument for the Image Upload Input mode.
8. IF any path in `--image-files` does not exist or is not a file, THEN THE CLI SHALL print an error message listing the missing paths and exit with a non-zero status code.

---

### Requirement 5: Image Upload Input — Image Processing

**User Story:** As a content creator, I want my uploaded images to be used directly as scene visuals, so that the video reflects my own visual content.

#### Acceptance Criteria

1. WHEN image files are provided as input, THE Image_Importer SHALL load each image file and validate it can be opened as a valid image using PIL.
2. IF an image file cannot be opened by PIL, THEN THE Image_Importer SHALL raise an `ImageImportError` with the filename and a descriptive message.
3. WHEN loading images, THE Image_Importer SHALL resize each image to match the target `VideoFormat` resolution defined in `IMAGE_RESOLUTIONS` in `models.py`.
4. WHEN images are loaded and resized, THE Image_Importer SHALL save each resized image to the pipeline's working directory and return the saved file paths.
5. WHEN the input mode is Image Upload Input, THE Pipeline SHALL skip the Leonardo AI image generation stage and assign the Image_Importer output paths directly to `scene.image_path` for each scene.
6. WHEN the number of uploaded images is less than the number of generated scenes, THE Image_Importer SHALL cycle through the uploaded images (repeating from the first) to fill all scene image slots.
7. WHEN the number of uploaded images is greater than the number of generated scenes, THE Image_Importer SHALL use only the first N images where N equals the number of scenes.

---

### Requirement 6: Image Upload Input — Story Generation from Context

**User Story:** As a content creator, I want RAGAI to generate a narration based on my images and the context I provide, so that the video has a coherent story matching my visual content.

#### Acceptance Criteria

1. WHEN the input mode is Image Upload Input and Context_Text is provided, THE Story_Generator SHALL generate scenes using the Context_Text as the topic input to the existing `generate` method.
2. WHEN the input mode is Image Upload Input and Context_Text is empty, THE Story_Generator SHALL generate scenes using a default topic derived from the uploaded image filenames.
3. THE PipelineConfig SHALL include an `image_files` field (list of file paths, default empty) and an `image_context` field (string, default empty) to carry Image Upload Input parameters.
4. THE PipelineConfig SHALL include an `audio_file` field (optional file path, default None) to carry the Audio Storytelling Input parameter.
5. THE PipelineConfig SHALL include an `input_mode` field of type `InputMode` enum with values: `TOPIC`, `SCRIPT`, `AUDIO`, `IMAGE`.

---

### Requirement 7: Pipeline Routing by Input Mode

**User Story:** As a developer, I want the pipeline to correctly route execution based on the selected input mode, so that each mode produces a valid video without executing unnecessary stages.

#### Acceptance Criteria

1. WHEN `PipelineConfig.input_mode` is `InputMode.TOPIC`, THE Pipeline SHALL execute all five existing stages unchanged.
2. WHEN `PipelineConfig.input_mode` is `InputMode.SCRIPT`, THE Pipeline SHALL execute all five existing stages unchanged.
3. WHEN `PipelineConfig.input_mode` is `InputMode.AUDIO`, THE Pipeline SHALL execute: transcription → scene parsing → image generation → audio splitting → video assembly (skipping Voice_Synthesizer synthesis).
4. WHEN `PipelineConfig.input_mode` is `InputMode.IMAGE`, THE Pipeline SHALL execute: story generation → image import → voice synthesis → video assembly (skipping Leonardo AI image generation).
5. WHEN `PipelineConfig.input_mode` is `InputMode.AUDIO` and `InputMode.IMAGE` simultaneously (future combination), THE Pipeline SHALL raise a `ConfigError` indicating mutually exclusive modes. (Note: combined audio+image mode is out of scope for this feature but the guard must exist.)
6. THE Pipeline SHALL log the active input mode at the start of each run.

---

### Requirement 8: Error Handling and New Exception Types

**User Story:** As a developer, I want clear, typed exceptions for the new input modes, so that errors are easy to diagnose and handle.

#### Acceptance Criteria

1. THE `models.py` module SHALL define an `AudioTranscriptionError` exception class that inherits from `RAGAIError`.
2. THE `models.py` module SHALL define an `ImageImportError` exception class that inherits from `RAGAIError`.
3. IF the Audio_Transcriber raises `AudioTranscriptionError`, THEN THE Pipeline SHALL log the error, append it to the internal errors list, and re-raise it to the caller.
4. IF the Image_Importer raises `ImageImportError`, THEN THE Pipeline SHALL log the error, append it to the internal errors list, and re-raise it to the caller.
5. WHEN an `AudioTranscriptionError` or `ImageImportError` is raised during a GUI pipeline run, THE GUI SHALL display the error message in the error dialog and re-enable the Generate button.

---

### Requirement 9: Round-Trip Transcript Integrity

**User Story:** As a developer, I want to verify that transcription and scene parsing are consistent, so that no narration content is silently lost.

#### Acceptance Criteria

1. THE Audio_Transcriber SHALL expose a `transcribe` method that accepts a file path and returns a Transcript string.
2. WHEN `parse_script(transcribe(audio_file))` is called, THE Story_Generator SHALL return a non-empty list of Scene objects whose concatenated narration text contains all significant words from the Transcript (round-trip property).
3. THE Audio_Transcriber SHALL preserve the full Transcript text without truncation for audio files up to 25 MB in size.
