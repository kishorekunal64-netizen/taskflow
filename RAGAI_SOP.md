# RAGAI Video Factory — Standard Operating Procedure (SOP)

> Version: 6.0 | Platform: Windows 10/11 | Last Updated: March 2026 | Author: Kunal
>
> Book & Story → Cinematic Hindi Video → YouTube

---

## Table of Contents

1. [RAGAI System Overview](#1-ragai-system-overview)
2. [System Requirements](#2-system-requirements)
3. [Tool Installations](#3-tool-installations)
4. [API Key Registration](#4-api-key-registration)
5. [Project Setup](#5-project-setup)
6. [Running the App](#6-running-the-app)
7. [Making a Video — Step by Step](#7-making-a-video--step-by-step)
8. [Input Modes](#8-input-modes)
9. [Visual Styles Guide](#9-visual-styles-guide)
10. [Quality Presets Reference](#10-quality-presets-reference)
11. [Image Provider Chain](#11-image-provider-chain)
12. [Intel QSV Hardware Encoding](#12-intel-qsv-hardware-encoding)
13. [Scene Re-Generate (Scenes Tab)](#13-scene-re-generate-scenes-tab)
14. [Voice Settings](#14-voice-settings)
15. [Groq Rate Limits & Solutions](#15-groq-rate-limits--solutions)
16. [API Costs & Free Limits](#16-api-costs--free-limits)
17. [Pipeline Overview](#17-pipeline-overview)
18. [Project Structure Reference](#18-project-structure-reference)
19. [Configuration Reference](#19-configuration-reference)
20. [YouTube Upload Workflow](#20-youtube-upload-workflow)
21. [YouTube Monetization Requirements](#21-youtube-monetization-requirements)
22. [Troubleshooting Guide](#22-troubleshooting-guide)
23. [Quick Rebuild Checklist](#23-quick-rebuild-checklist)
24. [Before Next Laptop Rebuild — Backup Checklist](#24-before-next-laptop-rebuild--backup-checklist)
25. [Pending Items & Future Upgrades](#25-pending-items--future-upgrades)
26. [Quick Reference Commands](#26-quick-reference-commands)

---

## 1. RAGAI System Overview

RAGAI is a fully automated AI video factory. You type a story topic, choose a language, and RAGAI creates a complete cinematic video with AI images, voiceover, smooth Ken Burns animations, and background music — ready for YouTube.

### Architecture (v6.0)

| Component | Technology |
|-----------|-----------|
| Story Generation | Groq llama-3.3-70b-versatile (free, cloud) |
| Audio Transcription | Groq Whisper (free, cloud) |
| AI Images — Primary | Leonardo Kino XL (modelId: b24e16ff-06e3-43eb-8d33-4416c2d75876) |
| AI Images — Fallback 1 | Pollinations.ai — FLUX-based, no key, unlimited free |
| AI Images — Fallback 2 | HuggingFace FLUX.1-schnell — free HF token |
| AI Images — Fallback 3 | OpenVINO local — Intel Arc GPU, fully offline |
| Voice (Natural) | Edge-TTS — hi-IN-SwaraNeural (needs internet) |
| Voice (Fallback) | gTTS — consistent, works on any network |
| Video Encoding | FFmpeg — H.264, Intel QSV hardware or libx264 software |
| Animation | PIL frames + FFmpeg, 24fps cinematic Ken Burns |
| Music | 7 tracks in RAGAI/music/ — auto-selected by style |
| Output | Up to 4K UHD (3840×2160) landscape / Shorts (2160×3840) |

### NEW in v6.0 vs v5.0

- **Intel QSV hardware encoding** — 5–10x faster encode on Intel Arc 140V GPU
- **4 image providers** with automatic fallback chain (Leonardo → Pollinations → HuggingFace → OpenVINO)
- **OpenVINO local provider** — generate images offline on Intel Arc GPU, zero API cost
- **4 quality presets** — Draft 720p / Standard 1080p / High 1440p / Cinema 4K
- **4 input modes** — Topic / Script / Audio transcription / Image upload
- **Scene Re-Generate tab** — swap any scene's image after a run without re-running everything
- **Video length control** — set target duration (1–10 min) or let AI decide
- **Custom BGM** — browse and use your own background music file
- **Scene count selector** — choose 5, 8, 10, 12, or 15 scenes
- **Modular codebase** — split into 12 focused Python modules (was single ragai.py)
- **Animated GUI header** — baby-face cards for Radha & Gauri with bobbing animation

---

## 2. System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Windows 10 64-bit | Windows 11 64-bit |
| RAM | 8 GB | 16 GB+ (shared with Intel Arc GPU) |
| Disk | 10 GB free | 50 GB+ (4K output files are large) |
| CPU | 4-core | Intel Core Ultra (Arc GPU for QSV) |
| GPU | Any | Intel Arc 140V+ (QSV encoding + OpenVINO) |
| Internet | Required | Required (Groq + Leonardo APIs) |

> Tested on: Acer Swift AI SF14-51, Intel Core Ultra 226V/258V, Intel Arc 140V, 16GB LPDDR5X, Windows 11

---

## 3. Tool Installations

### 3.1 Python 3.11 or 3.12

1. Download from: https://www.python.org/downloads/
   - Choose: **Windows installer (64-bit)**
2. Run the installer
   - ✅ Check **"Add Python to PATH"** before clicking Install
3. Verify:
   ```cmd
   python --version
   ```
4. Upgrade pip:
   ```cmd
   python -m pip install --upgrade pip
   ```

### 3.2 Git

1. Download from: https://git-scm.com/download/win
2. Run installer with default settings
3. Verify: `git --version`

### 3.3 FFmpeg 8.x

FFmpeg is the video encoding engine. RAGAI requires FFmpeg 8.x on the system PATH.

1. Download from: https://www.gyan.dev/ffmpeg/builds/
   - Choose: **ffmpeg-release-essentials.zip** (latest 8.x build)
2. Extract to: `C:\ffmpeg\`
3. Add to System PATH:
   - Win + S → "Environment Variables" → System variables → Path → New → `C:\ffmpeg\bin`
4. Open a **new** Command Prompt and verify:
   ```cmd
   ffmpeg -version
   ```

> The project ships with `ffmpeg-8.1-essentials_build/` locally. You can also add that to PATH:
> ```cmd
> set PATH=%PATH%;C:\path\to\ragai\ffmpeg-8.1-essentials_build\bin
> ```
> Note: the local ffmpeg folder is excluded from Git (too large). Re-download if rebuilding.

### 3.4 VS Code + Extensions (Recommended)

| Extension | Purpose |
|-----------|---------|
| Python (`ms-python.python`) | Python language support |
| Pylance (`ms-python.vscode-pylance`) | Type checking, IntelliSense |
| Python Debugger (`ms-python.debugpy`) | Breakpoint debugging |
| GitLens (`eamodio.gitlens`) | Git history |
| Dotenv (`mikestead.dotenv`) | .env syntax highlighting |

---

## 4. API Key Registration

### 4.1 Groq API Key

Groq powers **story generation** (LLaMA 3) and **audio transcription** (Whisper).

1. Go to: https://console.groq.com/
2. Sign up / Log in → **API Keys** → **Create API Key**
3. Copy the key — starts with `gsk_...`

Free tier limits:
- 30 requests/minute
- 6,000 tokens/minute
- 500,000 tokens/day (~8–10 videos/day)

### 4.2 Leonardo AI API Key

Leonardo AI generates the scene images (primary provider).

1. Go to: https://app.leonardo.ai/
2. Sign up / Log in → **Profile** → **API Access** → **Generate API Key**
3. Copy the key (UUID format)

Free tier: ~150 tokens/day (~1–2 videos/day).
Image resolution used: **1344×768** (landscape) / **768×1344** (shorts) — within Leonardo's 32–1536px safe range.

### 4.3 HuggingFace Token (Optional — for Fallback 2)

Only needed if you want HuggingFace FLUX.1-schnell as a fallback when Leonardo is exhausted.

1. Go to: https://huggingface.co/settings/tokens
2. Create a token with **read** access
3. Add to `.env` as `HF_TOKEN=hf_...`

> Without this token, HuggingFace still works but at lower rate limits.

---

## 5. Project Setup

### 5.1 Clone / Copy the Project

```cmd
git clone https://github.com/kishorekunal64-netizen/taskflow.git ragai
cd ragai
```

The project root should look like:
```
ragai/
├── ragai.py              ← entry point
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
├── music_selector.py
├── log_setup.py
├── ragai_diagnose.py
├── requirements.txt
├── START_RAGAI.bat
├── .env              ← you create this
├── music/            ← 7 background music tracks
└── output/           ← generated videos saved here
```

### 5.2 Create Virtual Environment

```cmd
python -m venv venv
venv\Scripts\activate
```

Your prompt shows `(venv)` when active. To deactivate: `deactivate`

### 5.3 Install Python Dependencies

```cmd
pip install -r requirements.txt
```

| Package | Min Version | Purpose |
|---------|-------------|---------|
| `groq` | 0.9.0 | Groq LLM + Whisper API |
| `python-dotenv` | 1.0.0 | Load .env config |
| `requests` | 2.31.0 | HTTP calls to Leonardo / Pollinations |
| `Pillow` | 10.0.0 | Image processing / thumbnails |
| `opencv-python` | 4.9.0 | Frame operations |
| `numpy` | 1.26.0 | Array operations for video frames |
| `edge-tts` | 6.1.9 | Microsoft Edge TTS (primary voice) |
| `gTTS` | 2.5.0 | Google TTS (fallback voice) |
| `pydub` | 0.25.1 | Audio file manipulation |

**Optional — OpenVINO local image generation (Intel Arc GPU):**
```cmd
pip install "optimum[openvino]" diffusers accelerate
```
Only needed if you want fully offline image generation. Model downloads ~1.5GB on first use.

### 5.4 Configure .env File

Create `.env` in the project root:

```env
# Required
GROQ_API_KEY=gsk_your_groq_key_here
LEONARDO_API_KEY=your_leonardo_uuid_key_here

# Optional
HF_TOKEN=hf_your_huggingface_token      # enables HF FLUX fallback
USE_EDGE_TTS=true                        # false = use gTTS
DEFAULT_LANGUAGE=hi
DEFAULT_FORMAT=landscape
LOG_LEVEL=INFO
```

> Never commit `.env` to Git — it is already in `.gitignore`.

---

## 6. Running the App

### 6.1 GUI Mode (Recommended)

**Option A — Double-click launcher (easiest):**

Double-click `START_RAGAI.bat` in the project folder. It activates the venv and launches the GUI.

**Option B — Manual launch:**
```cmd
venv\Scripts\activate
python ragai.py
```

The GUI opens with three tabs:
- **Settings tab** — all inputs: topic, language, style, format, scene count, quality, BGM, output dir
- **Scenes tab** — after a run, shows all scene images with Re-Generate buttons
- **Live Log tab** — real-time pipeline output with colour-coded log levels

### 6.2 CLI Mode

```cmd
venv\Scripts\activate

# Topic mode
python ragai.py --cli --topic "A girl from village comes to Mumbai" --language hi --style DYNAMIC_EPIC --format landscape

# Script file mode
python ragai.py --cli --script-file my_script.txt --language hi

# Audio transcription mode
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
| `--image-context` | text | "" | Context hint for image mode |
| `--audience` | family/children/adults/devotees | family | Target audience |
| `--language` | hi/ta/te/bn/gu/mr/kn/ml/pa/ur | hi | Narration language |
| `--style` | AUTO/DYNAMIC_EPIC/MYSTERY_DARK/SPIRITUAL_DEVOTIONAL/PEACEFUL_NATURE/ROMANTIC_DRAMA/ADVENTURE_ACTION | AUTO | Visual style |
| `--format` | landscape/shorts | landscape | Video format |
| `--quality` | draft/standard/high/cinema | cinema | Output quality preset |
| `--scenes` | 5/8/10/12/15 | 8 | Number of scenes |
| `--duration` | 0.0–10.0 | 0.0 (auto) | Target video length in minutes |
| `--output-dir` | directory path | ./output | Output directory |

### 6.3 Diagnostics

```cmd
python ragai.py --diagnose
```

Checks: Python version, all packages, FFmpeg on PATH, .env keys, music/ folder, output/ writable, Intel QSV availability.

---

## 7. Making a Video — Step by Step

| Step | What to Do |
|------|-----------|
| 1 — Open app | Double-click `START_RAGAI.bat` |
| 2 — Story Source | Choose: Topic / Script / Audio / Images |
| 3 — Topic | Type in English e.g. "A girl from village comes to Mumbai" |
| 4 — Audience | Select: Family / Children / Adults / Devotees |
| 5 — Language | Select from dropdown (Hindi, Tamil, Telugu, etc.) |
| 6 — Visual Style | Select AUTO or pick a specific style |
| 7 — Scene Count | Choose 5, 8, 10, 12, or 15 scenes |
| 8 — Video Length | Auto (AI decides) or set 1–10 minutes |
| 9 — Background Music | Auto-selected, or Browse to use your own file |
| 10 — Quality | Draft (fast) / Standard / High / Cinema 4K |
| 11 — Format | Landscape 4K (YouTube) or Shorts 4K (Reels/Shorts) |
| 12 — Character Names | Optional: "hero=Arjun, heroine=Priya" |
| 13 — Output Dir | Default: ./output — or Browse to change |
| 14 — Generate | Click GENERATE VIDEO — watch Live Log tab |
| 15 — Wait | 5–30 min depending on quality and scene count |
| 16 — Done | Video + thumbnail + metadata.txt saved in output/ |
| 17 — Scenes tab | Review scene images, re-generate any you don't like |

---

## 8. Input Modes

| Mode | How to Use | Best For |
|------|-----------|---------|
| **Topic** | Type a topic → AI writes the full story | Most common — zero prep needed |
| **Script** | Browse to a .txt file with your script | When you have pre-written content |
| **Audio** | Browse to an .mp3/.wav file → Groq Whisper transcribes it | Recorded narrations, interviews |
| **Images** | Browse to select your own images → AI writes story around them | When you have specific visuals |

---

## 9. Visual Styles Guide

| Style | Best For | Color Grade |
|-------|---------|-------------|
| AUTO | Let RAGAI detect from topic keywords (recommended) | Varies |
| Dynamic Epic | Mythology, history, war stories | High contrast, warm |
| Mystery Dark | Thriller, detective, horror | Desaturated, cool shadows |
| Spiritual Devotional | Religious, bhajan, devotional | Warm golden tones |
| Peaceful Nature | Children stories, nature, calm | Soft greens, bright |
| Romantic Drama | Love stories, family drama, emotional | Warm pinks, soft |
| Adventure Action | Action, fantasy, journey stories | Vivid, high saturation |

---

## 10. Quality Presets Reference

| Preset | Resolution | FPS | FFmpeg Preset | CRF | Bitrate | Use Case |
|--------|-----------|-----|---------------|-----|---------|---------|
| Draft | 1280×720 | 24 | fast | 23 | 4 Mbps | Quick preview |
| Standard | 1920×1080 | 24 | medium | 20 | 8 Mbps | Social media |
| High | 2560×1440 | 24 | slow | 18 | 12 Mbps | YouTube |
| Cinema | 3840×2160 (4K) | 24 | slow | 16 | 20 Mbps | Content creation |

> Cinema preset is intentionally slow — 4K H.264 at CRF 16 prioritizes quality over speed.
> With Intel QSV enabled, Cinema 4K encodes 5–10x faster than software libx264.

**Shorts format** uses the same presets but portrait resolution (e.g. 2160×3840 for Cinema).

---

## 11. Image Provider Chain

RAGAI automatically falls through a 4-provider chain. When one provider fails or hits its quota, it switches to the next — no manual action needed.

| Priority | Provider | Cost | Requires | Quality | Speed |
|----------|---------|------|---------|---------|-------|
| 1 | **Leonardo AI** (Kino XL) | 150 tokens/day free | API key | Best | ~30s/image |
| 2 | **Pollinations.ai** | Free, unlimited | Nothing | Good | ~20–90s/image |
| 3 | **HuggingFace FLUX.1-schnell** | Free | HF token (optional) | Good | ~30–120s/image |
| 4 | **OpenVINO local** | Free, offline | `optimum[openvino]` installed | Good | ~15s on Arc 140V |

### How fallback works

- Leonardo quota exhausted (429/402) → switches to Pollinations for rest of session
- Pollinations fails → switches to HuggingFace
- HuggingFace fails → switches to OpenVINO (if installed)
- All fail → uses a dark placeholder image (video still completes)

### Enabling OpenVINO (offline local generation)

```cmd
venv\Scripts\activate
pip install "optimum[openvino]" diffusers accelerate
```

First run downloads the model (~1.5GB) to `~/.cache/huggingface/`. Subsequent runs are instant.
Model used: `OpenVINO/LCM_Dreamshaper_v7-int8-ov` — runs on Intel Arc GPU, falls back to CPU.

---

## 12. Intel QSV Hardware Encoding

RAGAI automatically detects Intel Quick Sync Video (QSV) at startup and uses it for all three encode stages.

### What it does

- Replaces software `libx264` with hardware `h264_qsv` encoder
- Uses Intel Arc 140V GPU for encoding — frees CPU for other work
- **5–10x faster** encode speed vs software (Cinema 4K: ~3 min vs ~25 min)
- Automatic CPU fallback if QSV fails at runtime

### How it works

| Stage | With QSV | Without QSV |
|-------|---------|------------|
| Scene clips | `h264_qsv -global_quality 18` | `libx264 -crf 16` |
| Concat | `h264_qsv -global_quality 18` | `libx264 -crf 16` |
| Final mix | `h264_qsv -b:v 20000k` | `libx264 -b:v 20000k` |

### Checking QSV status

QSV detection is logged at startup. Look for in the Live Log:
```
Intel QSV detected — hardware encoding enabled (h264_qsv)
```
or:
```
Intel QSV not available — using software encoding (libx264)
```

### Requirements for QSV

- Intel Arc / Iris Xe / UHD Graphics GPU
- FFmpeg built with QSV support (the gyan.dev essentials build includes it)
- Intel Graphics driver up to date (Windows Update or Intel Arc Control)

---

## 13. Scene Re-Generate (Scenes Tab)

After a video is generated, the **Scenes tab** shows all scene images with individual Re-Generate buttons.

### How to use

1. Generate a video (Settings tab → GENERATE VIDEO)
2. Click the **Scenes tab** — all scene thumbnails appear
3. Find a scene image you don't like
4. Click **Re-generate Image** on that scene card
5. The image regenerates using the same provider chain
6. The scene clip is automatically re-encoded with the new image
7. The thumbnail updates live — no need to re-run the full pipeline

### What it shows per scene

- Scene number
- First 120 characters of narration text
- Thumbnail (160×90px preview)
- Provider used (e.g. "Done via LEONARDO")
- Re-generate button (disabled during generation)

> Note: Re-generating a scene image also re-encodes that scene's clip automatically. To rebuild the final video with all updated clips, run Generate again after you're happy with all scenes.

---

## 14. Voice Settings

### Two Voice Modes

| Mode | Quality | Network |
|------|---------|---------|
| Edge-TTS (Microsoft Neural) | Natural, human-sounding | Needs internet (may be blocked on some WiFi) |
| gTTS (Google) | Consistent but robotic | Works on any network |

Default is Edge-TTS. Set `USE_EDGE_TTS=false` in `.env` to switch to gTTS permanently.

### Switch to Natural Voice (Mobile Hotspot if needed)

Edge-TTS is blocked by some WiFi networks. Use mobile hotspot for best voice:

```cmd
python -c "content=open('ragai.py',encoding='utf-8').read(); open('ragai.py','w',encoding='utf-8').write(content.replace('USE_EDGE_TTS = False','USE_EDGE_TTS = True')); print('Natural voice ON!')"
```

Or simply set in `.env`:
```env
USE_EDGE_TTS=true
```

### Switch Back to gTTS (Any Network)

```env
USE_EDGE_TTS=false
```

### Indian Language Voice Map

| Language | Microsoft Neural Voice |
|----------|----------------------|
| Hindi | hi-IN-SwaraNeural |
| English | en-IN-NeerjaNeural |
| Tamil | ta-IN-PallaviNeural |
| Telugu | te-IN-ShrutiNeural |
| Bengali | bn-IN-TanishaaNeural |
| Gujarati | gu-IN-DhwaniNeural |
| Marathi | mr-IN-AarohiNeural |
| Kannada | kn-IN-SapnaNeural |
| Malayalam | ml-IN-SobhanaNeural |
| Punjabi | pa-IN-OjasNeural |
| Urdu | ur-PK-UzmaNeural |

---

## 15. Groq Rate Limits & Solutions

| Situation | Solution |
|-----------|---------|
| 429 error — daily limit hit | Wait 24 hours for automatic reset (free tier) |
| Need to keep working now | Switch model: replace `llama-3.3-70b-versatile` with `llama-3.1-8b-instant` |
| Switch back to best quality | Replace `llama-3.1-8b-instant` with `llama-3.3-70b-versatile` |
| Free daily limit | 500,000 tokens/day — enough for ~8–10 videos |

### Switch to Backup Model

```cmd
python -c "content=open('story_generator.py',encoding='utf-8').read(); content=content.replace('llama-3.3-70b-versatile','llama-3.1-8b-instant'); open('story_generator.py','w',encoding='utf-8').write(content); print('Backup model ON!')"
```

### Switch Back to Best Model

```cmd
python -c "content=open('story_generator.py',encoding='utf-8').read(); content=content.replace('llama-3.1-8b-instant','llama-3.3-70b-versatile'); open('story_generator.py','w',encoding='utf-8').write(content); print('Best model ON!')"
```

> Note: In v6.0 the model is defined in `story_generator.py`, not `ragai.py`.

---

## 16. API Costs & Free Limits

| Service | Cost & Limits |
|---------|--------------|
| Groq (Story + Transcription) | FREE — 500K tokens/day, ~8–10 videos/day |
| Leonardo (Images — primary) | FREE — 150 credits/day (~1–2 videos). Paid $24/month for 80+ videos/day |
| Pollinations.ai (Images — fallback 1) | FREE — unlimited, no key needed |
| HuggingFace FLUX (Images — fallback 2) | FREE — rate limited, HF token optional |
| OpenVINO local (Images — fallback 3) | FREE — offline, Intel Arc GPU, no internet |
| Edge-TTS (Voice) | FREE — Microsoft, unlimited |
| gTTS (Voice Fallback) | FREE — Google, unlimited |
| FFmpeg (Video) | FREE — open source, unlimited |
| **Total for 1–2 videos/day** | **$0/month** |
| **Total for 40 videos/day** | **~$24/month** (Leonardo paid only) |

---

## 17. Pipeline Overview

RAGAI runs a 5-stage pipeline for every video:

```
[Input] ──► Stage 1: Style Detection
              │  (auto-detect from topic keywords, or use user selection)
              ▼
           Stage 2: Story Generation (Groq LLaMA 3)
              │  or: Script parsing / Audio transcription (Groq Whisper)
              ▼
           Stage 3: Image Generation (Leonardo → Pollinations → HF → OpenVINO)
              │  or: User image import + resize
              ▼
           Stage 4: Voice Synthesis (Edge-TTS / gTTS)
              │  or: Audio file splitting (for audio input mode)
              ▼
           Stage 5: Video Assembly (FFmpeg)
              │  • Ken Burns motion (24fps, quintic ease, 8 pan directions)
              │  • Film grain (intensity 6)
              │  • Letterbox (2.39:1 anamorphic on landscape)
              │  • Color grading per style
              │  • Cross-dissolve transitions (0.8s xfade)
              │  • Background music mix (fade in/out)
              │  • H.264 encode (QSV or libx264)
              ▼
           [Output: .mp4 + thumbnail.jpg + metadata.txt]
```

### Stage Timing (Cinema 4K, 8 scenes, Intel Arc 140V)

| Stage | Time | Notes |
|-------|------|-------|
| Story | ~30s | Groq LLaMA 3.3 70B |
| Images | ~4 min | Leonardo AI (30s/image × 8) |
| Voice | ~1 min | Edge-TTS parallel synthesis |
| Assembly | ~3 min | QSV hardware encode |
| **Total** | **~8–9 min** | With QSV. Software: ~25 min |

---

## 18. Project Structure Reference

```
ragai/
│
├── ragai.py              Entry point — GUI/CLI dispatch
├── config.py             .env loading and AppConfig dataclass
├── models.py             All enums, dataclasses, constants, exceptions
├── pipeline.py           5-stage pipeline orchestrator + scene re-generate API
│
├── story_generator.py    Stage 2 — Groq LLaMA story/scene generation
├── image_generator.py    Stage 3 — 4-provider chain (Leonardo/Pollinations/HF/OpenVINO)
├── voice_synthesizer.py  Stage 4 — Edge-TTS / gTTS voice synthesis
├── video_assembler.py    Stage 5 — FFmpeg Ken Burns + QSV encode
│
├── style_detector.py     Auto-detect visual style from topic keywords
├── audio_transcriber.py  Groq Whisper transcription + audio splitting
├── image_importer.py     User image loading, validation, resize
├── music_selector.py     BGM selection by style + keyword scoring
├── log_setup.py          Logging configuration
├── gui.py                Tkinter GUI — animated header, 3 tabs, dark theme
├── ragai_diagnose.py     Diagnostics runner
├── create_music_v2.py    One-time music track generator (run once after fresh install)
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
├── logs/                 Application logs (ragai_YYYYMMDD_HHMMSS.log)
└── venv/                 Virtual environment (not committed)
```

---

## 19. Configuration Reference

### .env Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GROQ_API_KEY` | ✅ Yes | — | Groq API key (story + transcription) |
| `LEONARDO_API_KEY` | ✅ Yes | — | Leonardo AI key (image generation) |
| `HF_TOKEN` | No | "" | HuggingFace token (enables FLUX fallback) |
| `USE_EDGE_TTS` | No | `true` | Use Edge-TTS; `false` = gTTS fallback |
| `DEFAULT_LANGUAGE` | No | `hi` | Default narration language |
| `DEFAULT_FORMAT` | No | `landscape` | Default video format |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity (DEBUG/INFO/WARNING/ERROR) |

### Language Codes

| Code | Language | Code | Language |
|------|----------|------|----------|
| `hi` | Hindi | `kn` | Kannada |
| `ta` | Tamil | `ml` | Malayalam |
| `te` | Telugu | `pa` | Punjabi |
| `bn` | Bengali | `ur` | Urdu |
| `gu` | Gujarati | | |
| `mr` | Marathi | | |

---

## 20. YouTube Upload Workflow (Manual)

Manual upload is recommended for monetization — gives you control over quality before publishing.

| Step | Action |
|------|--------|
| 1 — Make video | Run RAGAI → video saved in `output/` folder |
| 2 — Review | Watch the video — check quality, voice, images |
| 3 — Open YouTube Studio | Go to studio.youtube.com |
| 4 — Upload | Click Upload → select your MP4 file |
| 5 — Title | Write SEO-optimized Hindi title e.g. "आंचल की कहानी \| प्रेरणादायक कहानी" |
| 6 — Description | Add story summary + hashtags from `metadata.txt` |
| 7 — Thumbnail | Use `*_thumbnail.jpg` from output folder or custom |
| 8 — Schedule | Post at 7–9 PM IST for best reach |
| 9 — Publish | Set Public when ready |

### Best Upload Times (IST)

- Weekdays: 7:00 PM – 9:00 PM
- Weekends: 10:00 AM – 12:00 PM or 7:00 PM – 9:00 PM
- Avoid posting at night or early morning

### Recommended Hashtags for Hindi Content

```
#HindiKahani #HindiStory #MotivationalStory #AIVideo #RAGAI 
#HindiContent #KahaniHindi #YoutubeHindi #PrernaDayakKahani #FamilyStory
```

---

## 21. YouTube Monetization Requirements

| Requirement | Target |
|-------------|--------|
| Subscribers | 1,000 minimum |
| Watch Hours | 4,000 hours in last 12 months |
| Content Policy | No copyright violations, original content |
| Consistency | Post regularly — aim for 1 video/day minimum |
| Estimated timeline | 3–6 months with daily posting |

### Content Strategy for Fast Growth

1. Post 1 video daily minimum — consistency is key
2. Use real Indian city/village names in topics (Delhi, Mumbai, Hapur etc.)
3. Family and motivational stories get highest watch time
4. Add custom thumbnail — increases click rate by 3x
5. Reply to all comments in first 24 hours
6. Share on WhatsApp groups and Facebook

---

## 22. Troubleshooting Guide

| Problem | Solution |
|---------|---------|
| **Virtual environment not found** | `python -m venv venv` → `venv\Scripts\activate` → `pip install -r requirements.txt` |
| **FFmpeg not found on PATH** | Verify: `ffmpeg -version`. Re-add `C:\ffmpeg\bin` to System PATH (see section 3.3) |
| **Missing required config key(s): GROQ_API_KEY** | Check `.env` file exists in project root. Verify key names exactly match. No spaces around `=` |
| **ModuleNotFoundError: No module named 'pydub'** | `venv\Scripts\activate` → `pip install pydub` |
| **ModuleNotFoundError: No module named 'edge_tts'** | `pip install edge-tts` |
| **Edge-TTS fails / no audio** | Set `USE_EDGE_TTS=false` in `.env` to fall back to gTTS. Check internet connection |
| **Leonardo AI returns 400 / image generation fails** | Verify `LEONARDO_API_KEY` is correct. Check daily token balance at https://app.leonardo.ai/. Resolution is fixed at 1344×768 (safe) |
| **Groq rate limit errors (429)** | Free tier: 30 req/min, 6000 tokens/min. Reduce scene count (5 instead of 10). Wait 60s and retry. Or switch to backup model (see section 15) |
| **Video output is black / corrupted** | Run diagnostics: `python ragai.py --diagnose`. Check `logs/` folder for latest log. Ensure `tmp/` directory is writable |
| **GUI doesn't open (Tkinter error)** | Tkinter is included with Python on Windows. Reinstall Python if missing. Ensure running from venv: `venv\Scripts\activate` |
| **App crashes on startup** | `python ragai.py --diagnose` — review output for missing packages or config issues |
| **Intel QSV not detected but I have Arc GPU** | Update Intel Graphics driver via Windows Update or Intel Arc Control. Verify FFmpeg build has QSV: `ffmpeg -encoders | findstr qsv` |
| **OpenVINO import error** | `pip install "optimum[openvino]" diffusers accelerate` |
| **Scene Re-Generate button does nothing** | Must run a full generation first. Pipeline object is stored after completion |
| **Baby face emoji not showing in GUI header** | This is a Windows tkinter limitation — the labels use system emoji renderer. Ensure Windows is up to date |
| **Mixed voices in video** | Set `USE_EDGE_TTS=false` for consistent gTTS voice across all scenes |
| **No sound in video** | Check `music/` folder has .mp3 files. Run `create_music_v2.py` if missing |
| **Video too slow to make** | Cinema 4K is intentionally slow for quality. Use Draft or Standard preset for faster preview. Enable QSV if you have Intel Arc GPU |
| **Groq model decommissioned** | Change model name in `story_generator.py` — check console.groq.com/docs for current models |
| **All image providers failed** | Check internet connection. Verify Leonardo API key. Install OpenVINO for offline fallback: `pip install "optimum[openvino]" diffusers` |

---

## 23. Quick Rebuild Checklist

Use this checklist when rebuilding on a new machine:

- [ ] Install Python 3.11 or 3.12 (add to PATH)
- [ ] Install Git
- [ ] Install FFmpeg 8.x (add `bin/` to PATH)
- [ ] Install VS Code + Python extension
- [ ] Clone/copy project to local folder
- [ ] `python -m venv venv`
- [ ] `venv\Scripts\activate`
- [ ] `pip install -r requirements.txt`
- [ ] Create `.env` with `GROQ_API_KEY` and `LEONARDO_API_KEY`
- [ ] (Optional) `pip install "optimum[openvino]" diffusers` for offline images
- [ ] Double-click `START_RAGAI.bat` to launch
- [ ] Run `python ragai.py --diagnose` to verify everything

---

## 24. Before Next Laptop Rebuild — Backup Checklist

**IMPORTANT: Back up these files to Google Drive or email them to yourself before rebuilding!**

| Priority | File / Folder | Why |
|----------|--------------|-----|
| 🔴 Critical | `.env` | Your API keys — cannot recover without this |
| 🔴 Critical | All `*.py` files in project root | The entire application |
| 🟡 Important | `music/` folder | 7 generated tracks (or re-run `create_music_v2.py`) |
| 🟡 Important | `requirements.txt` | Exact dependency versions |
| 🟡 Important | `START_RAGAI.bat` | Launcher script |
| 🟢 Optional | `output/` folder | Keep your best videos |
| 🟢 Optional | `logs/` folder | Useful for debugging history |

**Do NOT back up:**
- `venv/` — recreate with `python -m venv venv`
- `tmp/` — auto-generated working files
- `__pycache__/` — auto-generated bytecode
- `ffmpeg-8.1-essentials_build/` — re-download from gyan.dev

---

## 25. Pending Items & Future Upgrades

### Pending — To Complete

| Item | Details |
|------|---------|
| YouTube Auto-Upload | Google Cloud project 'RAGAI YOUTUBE' created, API enabled, OAuth client created. Stopped because ragai052018@gmail.com was disabled. Use main Gmail to complete setup when needed |
| Edge-TTS on WiFi | Blocked by current WiFi/router. Works on mobile hotspot. May work on home WiFi — test after rebuild. **Auto-detection added in v6.1** — RAGAI now probes `speech.platform.bing.com:443` at startup and silently switches to gTTS if blocked. No mid-generation failures. |
| OpenVINO end-to-end test | `_openvino()` method implemented and integrated. Run `python test_openvino.py` to verify on Arc 140V without running the full pipeline. |

### Future Upgrades (After Revenue)

| Upgrade | Benefit |
|---------|---------|
| Acer Predator Helios Neo 16S (RTX 5070) | Local AI — $0 API costs. Pays for itself in 18 months at 40 videos/day |
| Leonardo paid plan ($24/month) | 80+ videos/day instead of 1–2 |
| Groq Dev Tier | Higher daily token limits |
| AnimateDiff / Stable Video | Real AI video motion (requires RTX 5070) |
| YouTube auto-upload | Fully automated publish pipeline |
| Batch generation | Queue multiple topics, run overnight |

---

## 26. Quick Reference Commands

### Run RAGAI (GUI)
```cmd
venv\Scripts\activate
python ragai.py
```

### Run Diagnostics
```cmd
venv\Scripts\activate
python ragai.py --diagnose
```

### Regenerate Music Tracks
```cmd
venv\Scripts\activate
python create_music_v2.py
```

### Check Active Groq Model
```cmd
python -c "import re; content=open('story_generator.py',encoding='utf-8').read(); print(set(re.findall(r'llama[a-zA-Z0-9\-\.]+', content)))"
```

### Switch to Backup Groq Model (llama-3.1-8b-instant)
```cmd
python -c "content=open('story_generator.py',encoding='utf-8').read(); content=content.replace('llama-3.3-70b-versatile','llama-3.1-8b-instant'); open('story_generator.py','w',encoding='utf-8').write(content); print('Backup model ON!')"
```

### Switch Back to Best Groq Model
```cmd
python -c "content=open('story_generator.py',encoding='utf-8').read(); content=content.replace('llama-3.1-8b-instant','llama-3.3-70b-versatile'); open('story_generator.py','w',encoding='utf-8').write(content); print('Best model ON!')"
```

### Enable Natural Voice (Edge-TTS)
```cmd
python -c "content=open('.env',encoding='utf-8').read(); open('.env','w',encoding='utf-8').write(content.replace('USE_EDGE_TTS=false','USE_EDGE_TTS=true')); print('Natural voice ON!')"
```

### Enable Fallback Voice (gTTS)
```cmd
python -c "content=open('.env',encoding='utf-8').read(); open('.env','w',encoding='utf-8').write(content.replace('USE_EDGE_TTS=true','USE_EDGE_TTS=false')); print('gTTS voice ON!')"
```

### Install OpenVINO (offline image generation)
```cmd
venv\Scripts\activate
pip install "optimum[openvino]" diffusers accelerate
```

### Check Intel QSV availability
```cmd
ffmpeg -hide_banner -encoders 2>nul | findstr qsv
```

### Free Up RAM (if slow)
```cmd
taskkill /F /IM ollama.exe
```

### View Latest Log
```cmd
powershell "Get-ChildItem logs\ | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content"
```

---

*RAGAI Video Factory v6.0 — AI-powered cinematic video generation for Indian language content.*
*Built by Kunal with Kiro | March 2026*
