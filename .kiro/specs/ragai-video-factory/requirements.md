# Requirements Document

## Introduction

RAGAI (Reel AI Generator for Automated Intelligence) is a Python application that transforms a story topic or script into a complete cinematic Hindi video ready for YouTube. The system orchestrates a multi-stage AI pipeline: story generation via Groq LLM, scene-by-scene image generation via Leonardo AI, Hindi voiceover synthesis via Edge-TTS, Ken Burns animated video assembly via PIL and FFmpeg, and background music mixing — producing a final 1920x1080 (landscape) or 1080x1920 (Shorts) MP4 file. RAGAI exposes both a CLI interface and a GUI interface (tkinter-based desktop or web-based).

## Glossary

- **RAGAI**: The application system described in this document.
- **Pipeline**: The end-to-end sequence of stages that converts a topic or script into a final video.
- **Scene**: A single narrative unit consisting of a script segment, a generated image, and a voiceover audio clip.
- **Story_Generator**: The component that calls the Groq API to produce a structured story or expand a topic into a full script.
- **Image_Generator**: The component that calls the Leonardo AI API to produce one image per scene.
- **Voice_Synthesizer**: The component that converts scene narration text to audio using Edge-TTS or gTTS fallback.
- **Video_Assembler**: The component that applies Ken Burns animation to images, overlays voiceover audio, mixes background music, and encodes the final MP4 via FFmpeg.
- **Style_Detector**: The component that analyses a topic or script and selects the most appropriate Visual Style.
- **Visual_Style**: One of six predefined cinematic styles that govern image generation prompts and color grading.
- **Ken_Burns_Effect**: A pan-and-zoom animation applied to still images to create motion in video.
- **Edge_TTS**: Microsoft Azure Neural TTS accessed via the `edge-tts` Python library (offline-capable, no API key required).
- **gTTS**: Google Text-to-Speech, used as fallback when Edge-TTS is unavailable.
- **Groq_API**: The LLM inference API used for story and prompt generation (model: llama-3.3-70b-versatile).
- **Leonardo_API**: The image generation API used for scene visuals (model: Kino XL, id: aa77f04e-3eec-4034-9c07-d0f619684628).
- **Config**: The `.env` file and runtime configuration that stores API keys and feature flags.
- **Output_Directory**: The `output/` folder where final MP4 files are saved.
- **Music_Library**: The `music/` folder containing 7 local `.mp3` background tracks.
- **Log**: Structured diagnostic output written to the `logs/` directory.
- **CLI**: Command-line interface mode of RAGAI.
- **GUI**: Graphical user interface mode of RAGAI (tkinter desktop or web-based).
- **Audience**: The intended viewer demographic — one of: FAMILY, children, adults, devotees.
- **Language**: The narration language — Hindi (primary) with support for Tamil, Telugu, Bengali, Gujarati, Marathi, Kannada, Malayalam, Punjabi, Urdu.
- **Format**: The output video aspect ratio — Landscape (1920x1080) or Shorts (1080x1920).

---

## Requirements

### Requirement 1: Story Generation

**User Story:** As a content creator, I want RAGAI to generate a structured cinematic story from a topic or accept my own script, so that I have a scene-by-scene narrative ready for video production.

#### Acceptance Criteria

1. WHEN the user provides a topic in English, THE Story_Generator SHALL call the Groq API (model: llama-3.3-70b-versatile) and return a structured story containing between 5 and 12 scenes.
2. WHEN the user provides a manual script, THE Story_Generator SHALL parse the script into scenes without calling the Groq API.
3. THE Story_Generator SHALL produce each scene as a structured object containing: scene number, Hindi narration text, English image prompt, and scene duration in seconds.
4. WHEN the Groq API returns HTTP 429 (rate limit), THE Story_Generator SHALL automatically retry using model llama-3.1-8b-instant and notify the user of the fallback.
5. IF the Groq API returns an error other than 429, THEN THE Story_Generator SHALL log the error with full response details and raise a descriptive exception to the Pipeline.
6. THE Story_Generator SHALL incorporate the selected Audience and Visual_Style into the LLM prompt to ensure age-appropriate and tonally consistent output.
7. WHEN character name customization is enabled by the user, THE Story_Generator SHALL substitute placeholder character names in the generated story with the user-supplied names.
8. THE Story_Generator SHALL generate scene narration text in the Language selected by the user.

---

### Requirement 2: Image Generation

**User Story:** As a content creator, I want a high-quality cinematic image generated for each scene, so that the video has visually compelling frames that match the story.

#### Acceptance Criteria

1. WHEN a scene is ready for image generation, THE Image_Generator SHALL call the Leonardo AI API using model Kino XL (id: aa77f04e-3eec-4034-9c07-d0f619684628) and return one image per scene.
2. THE Image_Generator SHALL construct image prompts by combining the scene's English image prompt with style-specific cinematic keywords derived from the selected Visual_Style.
3. THE Image_Generator SHALL request images at resolution 1792x1024 for Landscape format and 1024x1792 for Shorts format.
4. WHEN the Leonardo API returns a non-200 response, THE Image_Generator SHALL retry the request up to 3 times with exponential backoff before raising an exception.
5. IF all retry attempts fail, THEN THE Image_Generator SHALL log the failure and substitute a solid-color placeholder image so the Pipeline can continue.
6. THE Image_Generator SHALL respect the Leonardo AI daily credit limit by tracking estimated credit usage per session and warning the user when fewer than 20 credits remain.
7. WHEN all scene images are generated, THE Image_Generator SHALL save each image to a temporary working directory with a filename that encodes the scene number.

---

### Requirement 3: Visual Style System

**User Story:** As a content creator, I want RAGAI to apply a consistent cinematic visual style across all scenes, so that the video has a coherent aesthetic that matches the story genre.

#### Acceptance Criteria

1. THE Style_Detector SHALL support exactly six named Visual Styles: DYNAMIC_EPIC, MYSTERY_DARK, SPIRITUAL_DEVOTIONAL, PEACEFUL_NATURE, ROMANTIC_DRAMA, ADVENTURE_ACTION.
2. WHEN the user selects "auto", THE Style_Detector SHALL analyse the topic or script and select the most appropriate Visual_Style using keyword and semantic matching.
3. THE Style_Detector SHALL map each Visual_Style to a set of image prompt modifiers, color palette descriptors, and FFmpeg color-grading filter parameters.
4. WHEN a Visual_Style is selected, THE Image_Generator SHALL apply the corresponding prompt modifiers to every scene image request.
5. WHEN a Visual_Style is selected, THE Video_Assembler SHALL apply the corresponding color-grading filter during FFmpeg encoding.

---

### Requirement 4: Voice Synthesis

**User Story:** As a content creator, I want natural-sounding Hindi voiceover for each scene, so that the video narration is clear and engaging for Indian audiences.

#### Acceptance Criteria

1. WHEN a scene narration text is available, THE Voice_Synthesizer SHALL generate an audio clip using Edge-TTS with voice hi-IN-SwaraNeural for Hindi.
2. THE Voice_Synthesizer SHALL select the appropriate Edge-TTS neural voice for each supported Language as defined in the language-to-voice mapping configuration.
3. WHEN Edge-TTS is unavailable or raises an exception, THE Voice_Synthesizer SHALL fall back to gTTS for the same text and log the fallback event.
4. THE Voice_Synthesizer SHALL save each scene audio clip as a WAV or MP3 file in the temporary working directory with a filename encoding the scene number.
5. THE Voice_Synthesizer SHALL expose a USE_EDGE_TTS configuration flag in Config; WHEN the flag is set to false, THE Voice_Synthesizer SHALL use gTTS directly without attempting Edge-TTS.
6. WHEN narration text exceeds 500 characters for a single scene, THE Voice_Synthesizer SHALL split the text into segments, synthesize each segment, and concatenate the audio clips before saving.

---

### Requirement 5: Ken Burns Animation and Video Assembly

**User Story:** As a content creator, I want each scene image to be animated with a Ken Burns pan-and-zoom effect and assembled into a single video with voiceover and music, so that the final output looks cinematic rather than a static slideshow.

#### Acceptance Criteria

1. THE Video_Assembler SHALL apply a Ken Burns effect to each scene image by generating a sequence of PIL frames at 30 fps with smooth pan and zoom interpolation over the scene duration.
2. THE Video_Assembler SHALL synchronise each scene's frame sequence with its corresponding voiceover audio clip so that narration and visuals are aligned.
3. THE Video_Assembler SHALL select one background music track from the Music_Library based on the selected Visual_Style and mix it at a volume level that does not exceed -18 dBFS relative to the voiceover.
4. THE Video_Assembler SHALL encode the final video using FFmpeg with H.264 video codec and AAC audio codec.
5. THE Video_Assembler SHALL produce Landscape output at 1920x1080 resolution and Shorts output at 1080x1920 resolution.
6. THE Video_Assembler SHALL save the final MP4 to the Output_Directory with a filename that includes the topic slug and a UTC timestamp.
7. WHEN FFmpeg is not found on the system PATH, THE Video_Assembler SHALL raise a descriptive exception with installation instructions before starting the pipeline.
8. THE Video_Assembler SHALL add a subtle scene-transition effect (crossfade or fade-to-black) between consecutive scenes with a duration of 0.5 seconds.

---

### Requirement 6: Multi-Language Support

**User Story:** As a content creator targeting regional Indian audiences, I want to produce videos in languages other than Hindi, so that I can reach Tamil, Telugu, Bengali, and other regional viewers.

#### Acceptance Criteria

1. THE Voice_Synthesizer SHALL support the following languages with their corresponding Edge-TTS neural voices: Hindi (hi-IN-SwaraNeural), Tamil (ta-IN-PallaviNeural), Telugu (te-IN-ShrutiNeural), Bengali (bn-IN-TanishaaNeural), Gujarati (gu-IN-DhwaniNeural), Marathi (mr-IN-AarohiNeural), Kannada (kn-IN-SapnaNeural), Malayalam (ml-IN-SobhanaNeural), Punjabi (pa-IN-VaaniNeural), Urdu (ur-PK-UzmaNeural).
2. WHEN a non-Hindi language is selected, THE Story_Generator SHALL instruct the LLM to produce scene narration text in the selected Language while keeping image prompts in English.
3. THE RAGAI SHALL store the language-to-voice mapping in a configuration file so that new languages can be added without modifying application code.

---

### Requirement 7: CLI Interface

**User Story:** As a developer or power user, I want a command-line interface, so that I can run RAGAI in automated scripts or headless environments.

#### Acceptance Criteria

1. THE CLI SHALL accept the following arguments: `--topic`, `--script-file`, `--audience`, `--language`, `--style`, `--format`, `--character-names`, `--output-dir`.
2. WHEN `--topic` and `--script-file` are both omitted, THE CLI SHALL enter interactive prompt mode and ask the user for each required input in sequence.
3. THE CLI SHALL display a real-time progress indicator showing the current pipeline stage and scene number being processed.
4. WHEN the pipeline completes successfully, THE CLI SHALL print the absolute path of the generated MP4 file.
5. IF any pipeline stage raises an exception, THEN THE CLI SHALL print a human-readable error message and exit with a non-zero status code.
6. THE CLI SHALL support a `--diagnose` flag that runs the diagnostic checker and exits without producing a video.

---

### Requirement 8: GUI Interface

**User Story:** As a non-technical content creator, I want a graphical interface, so that I can configure and run RAGAI without using the command line.

#### Acceptance Criteria

1. THE GUI SHALL provide input fields or controls for all user-configurable options: story source (topic or script), topic text, audience, language, visual style, format, and character name customization.
2. THE GUI SHALL display a progress bar and stage label that update in real time as the pipeline executes.
3. WHEN the pipeline completes, THE GUI SHALL display the output file path and offer a button to open the Output_Directory in the system file explorer.
4. WHEN a pipeline error occurs, THE GUI SHALL display the error message in a visible dialog or status area without crashing the application.
5. THE GUI SHALL run the pipeline in a background thread so that the interface remains responsive during processing.
6. THE GUI SHALL be implemented using tkinter as the primary option, with a web-based (Flask + HTML) alternative selectable via a Config flag.

---

### Requirement 9: Configuration and Environment

**User Story:** As a developer setting up RAGAI, I want all API keys and feature flags managed through a single `.env` file, so that secrets are never hard-coded and the app is easy to configure.

#### Acceptance Criteria

1. THE RAGAI SHALL load configuration from a `.env` file at startup using `python-dotenv`.
2. THE Config SHALL require the following keys: `GROQ_API_KEY`, `LEONARDO_API_KEY`.
3. THE Config SHALL support the following optional flags with documented defaults: `USE_EDGE_TTS` (default: true), `DEFAULT_LANGUAGE` (default: hi), `DEFAULT_FORMAT` (default: landscape), `LOG_LEVEL` (default: INFO).
4. WHEN a required API key is missing from Config at startup, THE RAGAI SHALL print a descriptive error message identifying the missing key and exit before starting the pipeline.
5. THE RAGAI SHALL never write API keys or secrets to Log files or standard output.

---

### Requirement 10: Logging and Diagnostics

**User Story:** As a developer troubleshooting a failed video generation, I want structured logs and a diagnostic tool, so that I can quickly identify which pipeline stage failed and why.

#### Acceptance Criteria

1. THE RAGAI SHALL write structured log entries to a timestamped file in the `logs/` directory for every pipeline run.
2. THE Log SHALL include: timestamp, log level, pipeline stage, scene number (where applicable), and message.
3. THE RAGAI SHALL provide a `ragai_diagnose.py` script that checks: Python version, required package installation, FFmpeg availability, `.env` file presence, API key validity (via lightweight test calls), and Music_Library file count.
4. WHEN the diagnostic script runs, THE RAGAI SHALL display each check result with a green checkmark (✅) for pass or red cross (❌) for fail.
5. IF any diagnostic check fails, THEN THE RAGAI SHALL print a remediation hint for that specific check.

---

### Requirement 11: Music Library and Audio Mixing

**User Story:** As a content creator, I want background music automatically selected and mixed into the video, so that the final output has professional audio production quality.

#### Acceptance Criteria

1. THE Music_Library SHALL contain exactly 7 background music tracks as `.mp3` files in the `music/` directory.
2. THE RAGAI SHALL provide a `create_music_v2.py` script that programmatically generates all 7 tracks so that the Music_Library can be recreated without external downloads.
3. THE Video_Assembler SHALL select the background track whose genre best matches the selected Visual_Style.
4. THE Video_Assembler SHALL loop the selected track if its duration is shorter than the total video duration.
5. THE Video_Assembler SHALL fade the background music in over the first 2 seconds and fade it out over the last 3 seconds of the video.

---

### Requirement 12: Output Quality and Metadata

**User Story:** As a YouTube content creator, I want the generated video to meet YouTube's technical requirements and include useful metadata, so that I can upload it directly without post-processing.

#### Acceptance Criteria

1. THE Video_Assembler SHALL encode the final MP4 at a minimum video bitrate of 8 Mbps for Landscape and 6 Mbps for Shorts.
2. THE Video_Assembler SHALL encode audio at 192 kbps AAC stereo.
3. THE RAGAI SHALL generate a companion `.txt` file alongside the MP4 containing a suggested YouTube title, description, and 10 hashtags derived from the topic and language.
4. THE Video_Assembler SHALL embed the topic string and generation timestamp as MP4 metadata tags (title, comment).
5. THE RAGAI SHALL produce a thumbnail image (1280x720 JPEG) from the most visually prominent scene image for use as a YouTube thumbnail.

---

### Requirement 13: Windows Launcher

**User Story:** As a non-technical Windows user, I want a one-click launcher on my Desktop, so that I can start RAGAI without opening a terminal.

#### Acceptance Criteria

1. THE RAGAI SHALL include a `START_RAGAI.bat` file that activates the Python virtual environment and launches the GUI interface.
2. WHEN the `.bat` file is executed, THE RAGAI SHALL open the GUI window within 5 seconds on a standard Windows 10/11 machine with all dependencies installed.
3. THE `START_RAGAI.bat` SHALL display a user-friendly error message if the virtual environment or `ragai.py` is not found at the expected path.
