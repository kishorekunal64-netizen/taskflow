# RAGAI Video Factory — Standard Operating Procedure (SOP)

> Version: 1.0 | Platform: Windows 10/11 | Last Updated: March 2026

This document covers everything needed to rebuild and run RAGAI Video Factory from scratch on a fresh Windows machine.

---

## Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Tool Installations](#2-tool-installations)
   - 2.1 Python 3.11
   - 2.2 Git
   - 2.3 FFmpeg 8.x
   - 2.4 VS Code + Extensions
3. [API Key Registration](#3-api-key-registration)
   - 3.1 Groq API Key
   - 3.2 Leonardo AI API Key
4. [Project Setup](#4-project-setup)
   - 4.1 Clone / Copy the Project
   - 4.2 Create Virtual Environment
   - 4.3 Install Python Dependencies
   - 4.4 Configure .env File
5. [Running the App](#5-running-the-app)
   - 5.1 GUI Mode (Recommended)
   - 5.2 CLI Mode
   - 5.3 Diagnostics
6. [Project Structure Reference](#6-project-structure-reference)
7. [Configuration Reference](#7-configuration-reference)
8. [Pipeline Overview](#8-pipeline-overview)
9. [Quality Presets Reference](#9-quality-presets-reference)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Windows 10 64-bit | Windows 11 64-bit |
| RAM | 8 GB | 16 GB+ |
| Disk | 10 GB free | 50 GB+ (4K output files are large) |
| CPU | 4-core | 8-core+ (FFmpeg encoding is CPU-intensive) |
| Internet | Required | Required (Groq + Leonardo AI APIs) |

---

## 2. Tool Installations

### 2.1 Python 3.11

RAGAI requires Python 3.11.x. Do **not** use 3.12+ (some dependencies may break).

1. Download from: https://www.python.org/downloads/release/python-3119/
   - Choose: **Windows installer (64-bit)**
2. Run the installer
   - ✅ Check **"Add Python to PATH"** before clicking Install
   - ✅ Check **"Install for all users"** (optional but recommended)
3. Verify installation:
   ```cmd
   python --version
   ```
   Expected output: `Python 3.11.x`

4. Upgrade pip:
   ```cmd
   python -m pip install --upgrade pip
   ```

---

### 2.2 Git

Required to clone the repository.

1. Download from: https://git-scm.com/download/win
   - Choose: **64-bit Git for Windows Setup**
2. Run installer with default settings
3. Verify:
   ```cmd
   git --version
   ```

---

### 2.3 FFmpeg 8.x

FFmpeg is the video encoding engine. RAGAI requires FFmpeg 8.x on the system PATH.

1. Download from: https://www.gyan.dev/ffmpeg/builds/
   - Choose: **ffmpeg-release-essentials.zip** (latest 8.x build)
   - Direct link pattern: `ffmpeg-8.x-essentials_build.zip`

2. Extract the zip to a permanent location, e.g.:
   ```
   C:\ffmpeg\
   ```
   After extraction you should have:
   ```
   C:\ffmpeg\bin\ffmpeg.exe
   C:\ffmpeg\bin\ffprobe.exe
   ```

3. Add FFmpeg to System PATH:
   - Press `Win + S` → search **"Environment Variables"**
   - Click **"Edit the system environment variables"**
   - Click **"Environment Variables..."**
   - Under **System variables**, find `Path` → click **Edit**
   - Click **New** → enter: `C:\ffmpeg\bin`
   - Click OK on all dialogs

4. Open a **new** Command Prompt and verify:
   ```cmd
   ffmpeg -version
   ```
   Expected: `ffmpeg version 8.x ...`

> Note: The project ships with a local `ffmpeg-8.1-essentials_build/` folder. You can also add that to PATH instead of installing system-wide:
> ```cmd
> set PATH=%PATH%;C:\path\to\project\ffmpeg-8.1-essentials_build\bin
> ```

---

### 2.4 VS Code + Extensions

Recommended editor for development and debugging.

1. Download from: https://code.visualstudio.com/
2. Install the following extensions (search in Extensions panel `Ctrl+Shift+X`):

| Extension | ID | Purpose |
|-----------|-----|---------|
| Python | `ms-python.python` | Python language support |
| Pylance | `ms-python.vscode-pylance` | Type checking, IntelliSense |
| Python Debugger | `ms-python.debugpy` | Breakpoint debugging |
| GitLens | `eamodio.gitlens` | Git history and blame |
| Dotenv | `mikestead.dotenv` | .env file syntax highlighting |
| indent-rainbow | `oderwat.indent-rainbow` | Visual indentation guide |

---

## 3. API Key Registration

### 3.1 Groq API Key

Groq powers two features: **story generation** (LLaMA 3) and **audio transcription** (Whisper).

1. Go to: https://console.groq.com/
2. Sign up / Log in
3. Navigate to: **API Keys** → **Create API Key**
4. Copy the key — it starts with `gsk_...`
5. Store it safely (you'll add it to `.env` in step 4.4)

Free tier limits (as of 2026):
- 30 requests/minute
- 6,000 tokens/minute
- 500,000 tokens/day

---

### 3.2 Leonardo AI API Key

Leonardo AI generates the scene images.

1. Go to: https://app.leonardo.ai/
2. Sign up / Log in
3. Navigate to: **Profile icon** → **API Access**
4. Click **Generate API Key**
5. Copy the key (UUID format)
6. Store it safely

Free tier: ~150 tokens/day (each image costs tokens based on resolution).

> Image resolution used by RAGAI: **1344×768** (landscape) / **768×1344** (shorts) — within Leonardo's 32–1536px safe range.

---

## 4. Project Setup

### 4.1 Clone / Copy the Project

If you have the project as a zip, extract it. If using Git:

```cmd
git clone <your-repo-url> ragai
cd ragai
```

The project root should look like:
```
ragai/
├── ragai.py
├── config.py
├── models.py
├── pipeline.py
├── gui.py
├── story_generator.py
├── image_generator.py
├── voice_synthesizer.py
├── video_assembler.py
├── style_detector.py
├── audio_transcriber.py
├── image_importer.py
├── log_setup.py
├── requirements.txt
├── START_RAGAI.bat
├── .env              ← you create this
├── music/            ← background music files
└── output/           ← generated videos go here
```

---

### 4.2 Create Virtual Environment

Always use a virtual environment to isolate dependencies.

```cmd
cd ragai
python -m venv venv
```

Activate it:
```cmd
venv\Scripts\activate
```

Your prompt should now show `(venv)` prefix.

> To deactivate later: `deactivate`

---

### 4.3 Install Python Dependencies

With the venv activated:

```cmd
pip install -r requirements.txt
```

Full dependency list with minimum versions:

| Package | Min Version | Purpose |
|---------|-------------|---------|
| `groq` | 0.9.0 | Groq LLM + Whisper API client |
| `python-dotenv` | 1.0.0 | Load `.env` config file |
| `requests` | 2.31.0 | HTTP calls to Leonardo AI |
| `Pillow` | 10.0.0 | Image processing / thumbnails |
| `opencv-python` | 4.9.0 | Frame extraction and Ken Burns |
| `numpy` | 1.26.0 | Array operations for video frames |
| `edge-tts` | 6.1.9 | Microsoft Edge TTS (primary voice) |
| `gTTS` | 2.5.0 | Google TTS (fallback voice) |
| `pydub` | 0.25.1 | Audio file manipulation |

Install individually if needed:
```cmd
pip install groq python-dotenv requests Pillow opencv-python numpy edge-tts gTTS pydub
```

---

### 4.4 Configure .env File

Create a file named `.env` in the project root (same folder as `ragai.py`):

```env
# Required — API Keys
GROQ_API_KEY=gsk_your_groq_key_here
LEONARDO_API_KEY=your_leonardo_uuid_key_here

# Optional — Voice synthesis (default: true)
# Set to false to use gTTS (Google TTS) instead of Edge-TTS
USE_EDGE_TTS=true

# Optional — Defaults (can be overridden in GUI)
DEFAULT_LANGUAGE=hi
DEFAULT_FORMAT=landscape

# Optional — Logging level (DEBUG / INFO / WARNING / ERROR)
LOG_LEVEL=INFO
```

> Never commit `.env` to Git. It is already in `.gitignore`.

---

## 5. Running the App

### 5.1 GUI Mode (Recommended)

**Option A — Double-click launcher (easiest):**

Double-click `START_RAGAI.bat` in the project folder.

This batch file:
1. Checks the virtual environment exists
2. Activates `venv\Scripts\activate`
3. Runs `pip install` to verify/update dependencies
4. Launches `python ragai.py --gui`

**Option B — Manual launch:**

```cmd
venv\Scripts\activate
python ragai.py
```

The GUI opens with:
- Animated header with color cycling
- Settings tab: topic, language, style, format, scene count, quality preset
- Live Log tab: real-time pipeline output
- Generate button → runs the full pipeline
- Cancel button → stops generation mid-run
- Thumbnail preview after completion

---

### 5.2 CLI Mode

For automation or headless servers:

```cmd
venv\Scripts\activate

# Basic usage
python ragai.py --cli --topic "A brave warrior saves the kingdom" --language hi --style DYNAMIC_EPIC --format landscape --output-dir ./output

# With script file
python ragai.py --cli --script-file my_script.txt --language hi

# Audio transcription mode (Groq Whisper)
python ragai.py --cli --audio-file recording.mp3 --language hi

# Image upload mode
python ragai.py --cli --image-files "img1.jpg,img2.jpg" --image-context "A family trip to the mountains"
```

**All CLI flags:**

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--topic` | any text | — | Video topic |
| `--script-file` | file path | — | Pre-written script |
| `--audio-file` | file path | — | Audio for transcription mode |
| `--image-files` | comma-separated paths | — | Images for image mode |
| `--image-context` | text | "" | Context for image mode |
| `--audience` | family/children/adults/devotees | family | Target audience |
| `--language` | hi/ta/te/bn/gu/mr/kn/ml/pa/ur | hi | Narration language |
| `--style` | AUTO/DYNAMIC_EPIC/MYSTERY_DARK/SPIRITUAL_DEVOTIONAL/PEACEFUL_NATURE/ROMANTIC_DRAMA/ADVENTURE_ACTION | AUTO | Visual style |
| `--format` | landscape/shorts | landscape | Video format |
| `--output-dir` | directory path | ./output | Output directory |

---

### 5.3 Diagnostics

Run the built-in diagnostics to check your environment:

```cmd
python ragai.py --diagnose
```

This checks:
- Python version
- All required packages installed
- FFmpeg on PATH
- `.env` file present and keys loaded
- `music/` directory and files present
- `output/` directory writable

---

## 6. Project Structure Reference

```
ragai/
│
├── ragai.py              Entry point — GUI/CLI/Web dispatch
├── config.py             .env loading and AppConfig dataclass
├── models.py             All enums, dataclasses, constants, exceptions
├── pipeline.py           5-stage pipeline orchestrator
│
├── story_generator.py    Stage 2 — Groq LLaMA story/scene generation
├── image_generator.py    Stage 3 — Leonardo AI image generation
├── voice_synthesizer.py  Stage 4 — Edge-TTS / gTTS voice synthesis
├── video_assembler.py    Stage 5 — FFmpeg Ken Burns + color grade + encode
│
├── style_detector.py     Auto-detect visual style from topic keywords
├── audio_transcriber.py  Groq Whisper transcription + audio splitting
├── image_importer.py     User image loading, validation, resize
├── log_setup.py          Logging configuration
├── gui.py                Tkinter GUI — animated, dark cinematic theme
├── ragai_diagnose.py     Diagnostics runner
│
├── START_RAGAI.bat       Windows one-click launcher
├── requirements.txt      Python dependencies
├── .env                  API keys and config (not committed)
│
├── music/                Background music per style
│   ├── adventure.mp3
│   ├── devotional.mp3
│   ├── epic.mp3
│   ├── mystery.mp3
│   ├── nature.mp3
│   ├── neutral.mp3
│   └── romantic.mp3
│
├── output/               Generated videos, thumbnails, metadata
├── tmp/                  Temporary working files (auto-cleaned)
└── logs/                 Application logs (ragai_YYYYMMDD_HHMMSS.log)
```

---

## 7. Configuration Reference

### .env Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GROQ_API_KEY` | ✅ Yes | — | Groq API key (story + transcription) |
| `LEONARDO_API_KEY` | ✅ Yes | — | Leonardo AI key (image generation) |
| `USE_EDGE_TTS` | No | `true` | Use Edge-TTS; `false` = gTTS fallback |
| `DEFAULT_LANGUAGE` | No | `hi` | Default narration language |
| `DEFAULT_FORMAT` | No | `landscape` | Default video format |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity |

### Language Codes

| Code | Language |
|------|----------|
| `hi` | Hindi |
| `ta` | Tamil |
| `te` | Telugu |
| `bn` | Bengali |
| `gu` | Gujarati |
| `mr` | Marathi |
| `kn` | Kannada |
| `ml` | Malayalam |
| `pa` | Punjabi |
| `ur` | Urdu |

---

## 8. Pipeline Overview

RAGAI runs a 5-stage pipeline for every video:

```
[Input] ──► Stage 1: Style Detection
              │
              ▼
           Stage 2: Story Generation (Groq LLaMA 3)
              │  or: Script parsing / Audio transcription
              ▼
           Stage 3: Image Generation (Leonardo AI)
              │  or: User image import + resize
              ▼
           Stage 4: Voice Synthesis (Edge-TTS / gTTS)
              │  or: Audio file splitting
              ▼
           Stage 5: Video Assembly (FFmpeg)
              │  Ken Burns motion, color grading, music mix,
              │  cross-dissolve transitions, H.264 encode
              ▼
           [Output: .mp4 + thumbnail + metadata.txt]
```

### Input Modes

| Mode | How to trigger | Description |
|------|---------------|-------------|
| Topic | Default | Enter a topic → AI generates story |
| Script | `--script-file` | Provide pre-written script |
| Audio | `--audio-file` | Transcribe audio → generate video |
| Image | `--image-files` | Use your own images + AI story |

---

## 9. Quality Presets Reference

| Preset | Resolution | FFmpeg Preset | CRF | Bitrate | Use Case |
|--------|-----------|---------------|-----|---------|----------|
| Draft | 1280×720 | fast | 23 | 4 Mbps | Quick preview |
| Standard | 1920×1080 | medium | 20 | 8 Mbps | Social media |
| High | 2560×1440 | slow | 18 | 12 Mbps | YouTube |
| Cinema | 3840×2160 (4K) | slow | 16 | 20 Mbps | Content creation |

> Cinema preset is slow by design — 4K H.264 encoding at CRF 16 prioritizes quality over speed.

---

## 10. Troubleshooting

### "Virtual environment not found"
```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### "FFmpeg not found on PATH"
- Verify FFmpeg is installed: `ffmpeg -version`
- If not found, re-add `C:\ffmpeg\bin` to System PATH (see section 2.3)
- Or set it temporarily: `set PATH=%PATH%;C:\ffmpeg\bin`

### "Missing required config key(s): GROQ_API_KEY"
- Check `.env` file exists in the project root
- Verify the key names are exactly `GROQ_API_KEY` and `LEONARDO_API_KEY`
- No spaces around the `=` sign

### "ModuleNotFoundError: No module named 'pydub'"
```cmd
venv\Scripts\activate
pip install pydub
```

### "ModuleNotFoundError: No module named 'edge_tts'"
```cmd
pip install edge-tts
```

### Edge-TTS fails / no audio
- Set `USE_EDGE_TTS=false` in `.env` to fall back to gTTS
- Check internet connection (Edge-TTS requires network access)

### Leonardo AI returns 400 / image generation fails
- Verify `LEONARDO_API_KEY` is correct
- Check your daily token balance at https://app.leonardo.ai/
- Image resolution is fixed at 1344×768 (landscape) / 768×1344 (shorts) — within safe limits

### Groq rate limit errors
- Free tier: 30 req/min, 6000 tokens/min
- Reduce scene count (5 scenes instead of 10)
- Wait 60 seconds and retry

### Video output is black / corrupted
- Run diagnostics: `python ragai.py --diagnose`
- Check `logs/` folder for the latest log file
- Ensure `tmp/` directory is writable

### GUI doesn't open (Tkinter error)
- Tkinter is included with Python on Windows — reinstall Python if missing
- Ensure you're running from the venv: `venv\Scripts\activate`

### App crashes on startup
```cmd
python ragai.py --diagnose
```
Review the output for missing packages or config issues.

---

## Quick Rebuild Checklist

Use this checklist when rebuilding on a new machine:

- [ ] Install Python 3.11.x (add to PATH)
- [ ] Install Git
- [ ] Install FFmpeg 8.x (add `bin/` to PATH)
- [ ] Install VS Code + Python extension
- [ ] Clone/copy project to local folder
- [ ] `python -m venv venv`
- [ ] `venv\Scripts\activate`
- [ ] `pip install -r requirements.txt`
- [ ] Create `.env` with `GROQ_API_KEY` and `LEONARDO_API_KEY`
- [ ] Double-click `START_RAGAI.bat` to launch
- [ ] Run `python ragai.py --diagnose` to verify everything

---

*RAGAI Video Factory — AI-powered cinematic video generation for Indian language content.*
