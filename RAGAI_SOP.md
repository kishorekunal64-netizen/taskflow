# RAGAI Video Factory — Standard Operating Procedure (SOP)

> Version: 7.4 | Platform: Windows 10/11 | Last Updated: March 2026 | Author: Kunal
>
> Book & Story → Cinematic Hindi/English Video → YouTube

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
27. [RAGAI Editor V2](#27-ragai-editor-v2)
28. [RAGAI Editor V2 — Module Reference](#28-ragai-editor-v2--module-reference)
29. [Global Config — ragai_config.json](#29-global-config--ragai_configjson)
30. [Job Manager & Crash Recovery System](#30-job-manager--crash-recovery-system)
31. [Scheduler — Automated Topic Queue](#31-scheduler--automated-topic-queue)
32. [Complete Project Structure Reference (v6.0 + Editor V2)](#32-complete-project-structure-reference-v60--editor-v2)
33. [Rebuild on New System — Complete Checklist](#33-rebuild-on-new-system--complete-checklist)
34. [How to Ask Kiro to Rebuild RAGAI on a New System](#34-how-to-ask-kiro-to-rebuild-ragai-on-a-new-system)
35. [Content Intelligence Layer (v7.0)](#35-content-intelligence-layer-v70)
36. [Thumbnail A/B Testing](#36-thumbnail-ab-testing)
37. [Performance Layer](#37-performance-layer)
38. [Intelligence Layer (v7.1)](#38-intelligence-layer-v71)
39. [Flexible Input Modes (v7.2)](#39-flexible-input-modes-v72)
40. [Cinematic Prompt Engine (v7.3)](#40-cinematic-prompt-engine-v73)
41. [Character Reference System (v7.4)](#41-character-reference-system-v74)
42. [Advanced Configuration Reference](#42-advanced-configuration-reference--ragai_advanced_configjson)
43. [Complete Project Structure Reference (v7.4)](#43-complete-project-structure-reference-v74)

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


---

## 27. RAGAI Editor V2

RAGAI Editor V2 is a standalone Tkinter desktop application that automatically collects videos produced by RAGAI and compiles them into long-form YouTube compilation videos.

### Purpose

- Watch `./output/` for new RAGAI-generated videos
- Group clips by topic/hashtag
- Auto-generate hook intro + outro clips
- Compile into a single long-form video (12–20 min)
- Generate viral thumbnails
- Save final compilation to `./compiled/`

### Entry Point

```cmd
venv\Scripts\activate
python editor.py
```

Or double-click `START_EDITOR.bat`.

### GUI Layout

| Panel | Location | Contents |
|-------|----------|----------|
| Clip Library | Left | Thumbnail grid, search/filter, clip metadata |
| Timeline Editor | Center | Visual drag-and-drop canvas, trim controls, transitions |
| Export Settings | Right | Format, quality, output folder, EXPORT VIDEO button, AUTO MODE toggle |

### Auto Mode

Toggle **AUTO MODE** in the right panel. When enabled:

1. Watcher detects new video folders in `./output/`
2. Clips are imported and metadata extracted
3. When 3+ clips share related hashtags, a compilation group is formed
4. Hook intro is generated via Groq LLM + Edge-TTS
5. Compilation is assembled via FFmpeg (hook + clips + outro)
6. Thumbnail is generated
7. Final video saved to `./compiled/`
8. Clips marked as `Exported`

### Manual Mode

1. Open editor — clip library auto-populates from `./output/`
2. Drag clips onto the timeline
3. Adjust trim points and transitions
4. Click **EXPORT VIDEO**

---

## 28. RAGAI Editor V2 — Module Reference

| Module | File | Responsibility |
|--------|------|---------------|
| Entry point | `editor.py` | Init clip manager, start watcher, launch GUI, init auto pipeline |
| GUI | `editor_gui.py` | 3-panel Tkinter interface (ClipLibraryPanel, TimelinePanel, ExportPanel) |
| Config | `editor_config.py` | Load/save `ragai_config.json` |
| Clip Manager | `clip_manager.py` | Maintain clip library in `editor_clips.json` |
| Watcher | `watcher.py` | watchdog monitor on `./output/`, skips locked folders |
| Topic Engine | `topic_engine.py` | Group clips by hashtag similarity |
| Hook Generator | `hook_generator.py` | Groq LLM hook text → Edge-TTS voice → FFmpeg intro clip |
| Outro Generator | `outro_generator.py` | Subscribe outro clip via FFmpeg |
| Variation Engine | `variation_engine.py` | Rotate voices, randomize music/order/transitions |
| Thumbnail Generator | `thumbnail_generator.py` | Extract frame, darken, overlay Hindi text, glow effect |
| Timeline | `timeline.py` | Tkinter Canvas drag-and-drop timeline |
| Assembler | `assembler.py` | FFmpeg compile: hook + clips + outro → final MP4 |
| Auto Pipeline | `auto_pipeline.py` | Fully automated batch compilation workflow |

### Clip States

| State | Meaning |
|-------|---------|
| `Available` | In library, not yet on timeline |
| `InTimeline` | Added to current timeline |
| `Exported` | Already compiled into a video |

### Clip Library Persistence

Clip metadata is stored in `editor_clips.json` (runtime file, not committed to Git).

Each entry contains: `filename`, `path`, `duration`, `resolution`, `topic`, `hashtags`, `thumbnail`, `created_at`, `state`.

### Output Folder Structure (v6.0+)

Each RAGAI generation saves into its own folder:

```
output/
├── video_20260324_001/
│   ├── video.mp4
│   ├── thumbnail.jpg
│   └── metadata.txt
├── video_20260324_002/
│   ├── video.mp4
│   ├── thumbnail.jpg
│   └── metadata.txt
```

The watcher reads `metadata.txt` for title, description, and hashtags.

### Compiled Output

```
compiled/
├── RAGAI_Compilation_VillageStory_20260324.mp4
├── RAGAI_Compilation_VillageStory_20260324_thumb.jpg
└── .thumbs/   ← cached thumbnail previews
```

---

## 29. Global Config — ragai_config.json

Both RAGAI and RAGAI Editor read from `ragai_config.json` in the project root.

```json
{
  "output_dir":       "./output",
  "compiled_dir":     "./compiled",
  "default_quality":  "cinema",
  "default_language": "hi",
  "enable_qsv":       true,
  "hook_enabled":     true,
  "outro_enabled":    true,
  "auto_thumbnail":   true,
  "auto_titles":      true
}
```

| Key | Default | Description |
|-----|---------|-------------|
| `output_dir` | `./output` | Where RAGAI saves generated videos |
| `compiled_dir` | `./compiled` | Where Editor saves compilations |
| `default_quality` | `cinema` | Quality preset for compilations |
| `default_language` | `hi` | Default narration language |
| `enable_qsv` | `true` | Use Intel QSV hardware encoding |
| `hook_enabled` | `true` | Generate hook intro for compilations |
| `outro_enabled` | `true` | Append subscribe outro |
| `auto_thumbnail` | `true` | Auto-generate viral thumbnail |
| `auto_titles` | `true` | Auto-generate title from hashtags |

Loaded via `editor_config.py` → `load_editor_config()`. Falls back to safe defaults if file is missing.

---

## 30. Job Manager & Crash Recovery System

`job_manager.py` ensures the pipeline runs reliably for long periods without manual supervision.

### Purpose

- Track every generation job with full lifecycle state
- Detect and recover from crashes or interrupted generations
- File-lock mechanism prevents watcher from importing incomplete videos
- Health monitor alerts if any component stops

### Job State File

All job state is persisted in `jobs_state.json` (runtime file, not committed to Git).

```json
{
  "abc123": {
    "job_id":        "abc123...",
    "topic":         "Village girl becomes IAS officer",
    "status":        "completed",
    "started_at":    "2026-03-24T10:00:00+00:00",
    "completed_at":  "2026-03-24T10:08:30+00:00",
    "output_folder": "video_20260324_001",
    "error":         null,
    "retries":       0
  }
}
```

### Job Statuses

| Status | Meaning |
|--------|---------|
| `pending` | Queued, not yet started |
| `processing` | Generation actively running |
| `completed` | Video verified and saved |
| `failed` | Generation failed or output invalid |

### Job Lifecycle

```
create_job(topic)          → status: pending
mark_processing(job_id)    → status: processing  +  write generation.lock
  ... RAGAI runs ...
mark_completed(job_id)     → verify video.mp4 exists + size stable
                           → status: completed   +  remove generation.lock
                           → OR status: failed if verification fails
```

### File Lock Mechanism

During generation, a `generation.lock` file is written inside the output folder:

```
output/video_20260324_001/
├── generation.lock   ← watcher ignores this folder while lock exists
├── video.mp4
├── thumbnail.jpg
└── metadata.txt
```

The watcher (`watcher.py`) skips any folder containing `generation.lock`. The lock is removed after generation completes successfully.

### Crash Recovery

On scheduler startup, `job_manager.startup_recovery()` runs automatically:

1. Scans `jobs_state.json` for any job with `status: processing`
2. For each interrupted job:
   - If `video.mp4` exists and is valid → marks `completed`, removes stale lock
   - If output is missing/incomplete → marks `failed`, prepends topic back to `topics_queue.json`
3. Max retries: **2** — after that, job is abandoned with error logged

### Health Monitor

Runs every 60 seconds in a background thread. Checks:

- Scheduler heartbeat (warns if scheduler stopped)
- Watcher heartbeat (warns if folder watcher stopped)
- Topic queue size (warns if queue is empty)
- Stuck jobs (warns if any job has been `processing` for > 30 minutes)

All warnings logged to `logs/job_manager.log`.

### Log File

```
logs/job_manager.log
```

Format: `YYYY-MM-DDTHH:MM:SS  LEVEL     message`

---

## 31. Scheduler — Automated Topic Queue

`scheduler.py` reads topics from `topics_queue.json` and runs RAGAI generation for each topic automatically.

### Topics Queue File

```json
[
  "Village girl becomes IAS officer",
  "A soldier saves his village",
  "Radha doing pooja in Shiva temple",
  "..."
]
```

Topics are consumed from the top. Recovered/failed topics are prepended back to the front.

### Running the Scheduler

```cmd
venv\Scripts\activate

# Run continuously (default 5-min interval between jobs)
python scheduler.py

# Run once (process one topic and exit)
python scheduler.py --once

# Custom interval
python scheduler.py --interval 300

# Crash recovery only (no new jobs)
python scheduler.py --recover-only
```

Or double-click `START_SCHEDULER.bat`.

### Scheduler Flags

| Flag | Description |
|------|-------------|
| `--once` | Process one topic then exit |
| `--interval N` | Seconds to wait between jobs (default: 300) |
| `--recover-only` | Run crash recovery and exit, no new generation |

### Full Automation Flow

```
START_SCHEDULER.bat
      │
      ▼
scheduler.py starts
      │
      ├─► job_manager.startup_recovery()   ← fix any crashed jobs
      │
      └─► loop:
            read topics_queue.json
            pop next topic
            job_manager.create_job(topic)
            job_manager.mark_processing(job_id, folder)
            job_manager.write_lock(folder)
            run: python ragai.py --cli --topic "..." 
            job_manager.mark_completed(job_id, folder)
            job_manager.remove_lock(folder)
            wait interval
            repeat
```

Meanwhile, `watcher.py` monitors `./output/` and imports completed (unlocked) videos into the Editor clip library automatically.

---

## 32. Complete Project Structure Reference (v6.0 + Editor V2)

```
ragai/
│
├── ragai.py                Entry point — GUI/CLI dispatch
├── config.py               .env loading and AppConfig dataclass
├── models.py               All enums, dataclasses, constants, exceptions
├── pipeline.py             5-stage pipeline orchestrator
│
├── story_generator.py      Stage 2 — Groq LLaMA story/scene generation
├── image_generator.py      Stage 3 — 4-provider image chain
├── voice_synthesizer.py    Stage 4 — Edge-TTS / gTTS voice synthesis
├── video_assembler.py      Stage 5 — FFmpeg Ken Burns + QSV encode
│
├── style_detector.py       Auto-detect visual style from topic keywords
├── audio_transcriber.py    Groq Whisper transcription + audio splitting
├── image_importer.py       User image loading, validation, resize
├── music_selector.py       BGM selection by style + keyword scoring
├── log_setup.py            Logging configuration
├── gui.py                  Tkinter GUI — animated header, 3 tabs, dark theme
├── ragai_diagnose.py       Diagnostics runner
├── create_music_v2.py      One-time music track generator
│
├── editor.py               RAGAI Editor V2 — entry point
├── editor_gui.py           3-panel Tkinter GUI (Library/Timeline/Export)
├── editor_config.py        ragai_config.json loader
├── clip_manager.py         Clip library manager (editor_clips.json)
├── watcher.py              watchdog folder monitor (skips locked folders)
├── timeline.py             Tkinter Canvas drag-and-drop timeline
├── assembler.py            FFmpeg compilation assembler
├── auto_pipeline.py        Fully automated batch compilation
├── topic_engine.py         Hashtag-based clip grouping
├── hook_generator.py       AI hook intro video generator
├── outro_generator.py      Subscribe outro clip generator
├── variation_engine.py     Content variation (voices, music, order)
├── thumbnail_generator.py  Viral thumbnail composer
│
├── job_manager.py          Job state tracker + crash recovery
├── scheduler.py            Automated topic queue runner
│
├── viral_scorer.py         Viral potential scoring
├── trend_fetcher.py        Trending topic fetcher
│
├── ragai_config.json       Global config (output_dir, quality, QSV, etc.)
├── topics_queue.json       Topic queue for scheduler
├── jobs_state.json         Runtime job state (not committed)
├── editor_clips.json       Runtime clip library (not committed)
│
├── START_RAGAI.bat         Launch RAGAI GUI
├── START_EDITOR.bat        Launch RAGAI Editor V2
├── START_SCHEDULER.bat     Launch automated scheduler
├── requirements.txt        Python dependencies
├── .env                    API keys (not committed)
│
├── music/                  7 background music tracks
├── output/                 Generated videos (folder-per-video structure)
├── compiled/               Editor compilation outputs
├── logs/                   Application logs
└── venv/                   Virtual environment (not committed)
```

---

## 33. Rebuild on New System — Complete Checklist

Use this when setting up RAGAI on a new machine from scratch.

### Step 1 — Install Tools

- [ ] Python 3.11 or 3.12 — https://python.org/downloads — check "Add to PATH"
- [ ] Git — https://git-scm.com/download/win
- [ ] FFmpeg 8.x — https://www.gyan.dev/ffmpeg/builds/ → extract to `C:\ffmpeg\` → add `C:\ffmpeg\bin` to System PATH
- [ ] VS Code + Python extension (`ms-python.python`)

### Step 2 — Get the Project

```cmd
git clone https://github.com/kishorekunal64-netizen/taskflow.git ragai
cd ragai
```

### Step 3 — Virtual Environment

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Step 4 — Configure .env

Create `.env` in project root:

```env
GROQ_API_KEY=gsk_your_key_here
LEONARDO_API_KEY=your_leonardo_uuid_here
HF_TOKEN=hf_optional
USE_EDGE_TTS=true
DEFAULT_LANGUAGE=hi
DEFAULT_FORMAT=landscape
LOG_LEVEL=INFO
```

### Step 5 — Generate Music Tracks

```cmd
python create_music_v2.py
```

### Step 6 — Verify Everything

```cmd
python ragai.py --diagnose
```

### Step 7 — Launch

| App | Command |
|-----|---------|
| RAGAI Video Factory | Double-click `START_RAGAI.bat` |
| RAGAI Editor V2 | Double-click `START_EDITOR.bat` |
| Automated Scheduler | Double-click `START_SCHEDULER.bat` |

### Step 8 — Optional: Intel Arc Offline Images

```cmd
pip install "optimum[openvino]" diffusers accelerate
```

---

## 34. How to Ask Kiro to Rebuild RAGAI on a New System

If you need to rebuild the entire RAGAI system using Kiro AI on a new machine, use this prompt:

```
You are rebuilding the RAGAI Video Factory system on a new Windows machine.

The full system consists of:
1. RAGAI Video Factory (ragai.py) — AI video generation pipeline
2. RAGAI Editor V2 (editor.py) — compilation editor
3. Job Manager (job_manager.py) — crash recovery system
4. Scheduler (scheduler.py) — automated topic queue

Tech stack:
- Python 3.11+, Windows 11, Intel Arc 140V GPU (QSV + OpenVINO)
- FFmpeg 8.x with QSV support
- Groq API (story + transcription), Leonardo AI (images), Edge-TTS (voice)
- Tkinter GUI, watchdog, plyer, Pillow, OpenCV, pydub

Please:
1. Read RAGAI_SOP.md completely
2. Recreate all Python modules as documented in Section 32
3. Recreate all .bat launchers
4. Recreate requirements.txt
5. Do NOT recreate .env (user will fill in API keys)
6. Verify with: python ragai.py --diagnose
```

---

*RAGAI Video Factory v6.0 + Editor V2 — AI-powered cinematic video generation and compilation.*
*Built by Kunal with Kiro | March 2026*

---

## 35. Content Intelligence Layer (v7.0)

Added in March 2026. All modules are optional and controlled via `ragai_advanced_config.json`.

### 35.1 Topic Quality Engine — `topic_quality_engine.py`

Scores every topic before spending any API credits. Topics scoring below threshold are filtered out automatically.

| Dimension | Weight | Description |
|-----------|--------|-------------|
| Emotion | 30% | Emotional resonance keywords |
| Curiosity | 20% | Mystery/surprise triggers |
| Relatability | 30% | Family/village/struggle themes |
| Popularity | 20% | Trending keyword match |

Composite score range: 0–10. Topics below 2.0 are skipped.

### 35.2 Engagement Predictor — `engagement_predictor.py`

Predicts CTR and watch time before generation. Blocks low-engagement topics.

Output example:
```json
{ "predicted_ctr": 7.87, "predicted_watch_minutes": 5.31, "should_generate": true }
```

### 35.3 Narrative Variation Engine — `narrative_variation_engine.py`

Rotates through 5 narrative structures so every video tells a story differently:

| Code | Structure |
|------|-----------|
| A | Hero's Journey |
| B | Mystery Reveal |
| C | Conflict Resolution |
| D | Character Twist |
| E | Investigation |

### 35.4 Visual Variation Engine — `visual_variation_engine.py`

Per-scene Ken Burns motion configs with hybrid patterns every 3–4 scenes. Prevents repetitive visual pacing.

### 35.5 Content Variation Engine — `content_variation_engine.py`

Rotates voice styles (SSML prosody), music moods, and scene pacing profiles automatically per topic.

Pacing profiles: Balanced, Slow Burn, Dynamic, Fast Paced.

### 35.6 Story Archive — `story_archive.py`

SQLite database (`story_archive.db`) tracking all generated stories. Uses Jaccard similarity to detect duplicate topics and suggest variants.

Functions: `save_story()`, `check_duplicate_topic()`, `retrieve_similar_topics()`, `suggest_variant()`, `stats()`

---

## 36. Thumbnail A/B Testing — `thumbnail_ab_tester.py`

Generates 3 thumbnail layout variants (A, B, C) per video. Tracks CTR via Wilson lower-bound scoring. Auto-selects winner after 50+ impressions.

Variants are saved alongside the video:
```
output/video_YYYYMMDD_HHMMSS/
├── video.mp4
├── thumbnail_A.jpg
├── thumbnail_B.jpg
├── thumbnail_C.jpg
└── metadata.txt
```

Update CTR data from `analytics_data.json`:
```python
from thumbnail_ab_tester import ThumbnailABTester
tester = ThumbnailABTester()
tester.bulk_update_from_analytics("analytics_data.json")
winner = tester.select_winner("video_id")
```

---

## 37. Performance Layer

### 37.1 Parallel Scene Executor — `scene_parallel_executor.py`

Processes image generation, voice synthesis, and clip encoding concurrently using `ThreadPoolExecutor` with 4 workers. Reduces generation time by ~50–70%.

### 37.2 Video Assembler Fixes — `video_assembler.py`

- Pipe-based Ken Burns (no PNG frame dump) — ~60–70% faster scene encoding
- Intel QSV hardware encoding with automatic fallback to libx264
- `OSError`/`BrokenPipeError` catch for Windows QSV pipe failures — auto-retries with libx264
- `tempfile.TemporaryFile()` for stderr (eliminates pipe deadlock on long encodes)

---

## 38. Intelligence Layer (v7.1)

### 38.1 Language Engine — `language_engine.py`

Detects language from Unicode script ranges + English keyword heuristics. Supports 11 languages.

**English is now fully supported** — `Language.EN` added to models.py. Voice: `en-US-JennyNeural`.

| Language | Code | Edge-TTS Voice |
|----------|------|----------------|
| English | en | en-US-JennyNeural |
| Hindi | hi | hi-IN-SwaraNeural |
| Tamil | ta | ta-IN-PallaviNeural |
| Telugu | te | te-IN-ShrutiNeural |
| Bengali | bn | bn-IN-TanishaaNeural |
| Gujarati | gu | gu-IN-DhwaniNeural |
| Marathi | mr | mr-IN-AarohiNeural |
| Kannada | kn | kn-IN-SapnaNeural |
| Malayalam | ml | ml-IN-SobhanaNeural |
| Punjabi | pa | pa-IN-VaaniNeural |
| Urdu | ur | ur-PK-UzmaNeural |

### 38.2 Story Knowledge Graph — `story_knowledge_graph.py`

SQLite database (`story_graph.db`) storing topic, characters, locations, themes, and emotion arc per story. Semantic similarity search prevents story repetition across videos.

Functions: `add_story()`, `search_similar_story()`, `suggest_story_variant()`

### 38.3 Scene Composer — `scene_composer.py`

PIL-based layer compositor combining:
- Background image
- Character overlays (RGBA)
- Foreground layer
- Lighting presets: golden_hour, blue_hour, dramatic, soft_natural, night
- Motion effects: vignette, film_grain, soft_blur_edges

Used optionally before video assembly.

### 38.4 Style Engine — `style_engine.py`

Channel branding via `channel_styles.json`. Per-channel music style, voice style, color grade, and thumbnail colors.

```json
{
  "devotional_channel": {
    "music_style": "devotional",
    "color_palette": "warm",
    "voice_style": "calm"
  }
}
```

### 38.5 Emotion Detector — `emotion_detector.py`

Keyword-based emotion scoring across Hindi + English. Detects: joy, sadness, tension, hope, inspiration, calm, conflict, resolution. Outputs per-scene arc map for `story_flow_optimizer.py`.

### 38.6 Render Optimizer — `render_optimizer.py`

Probes FFmpeg for NVENC/QSV/VAAPI GPU encoders. Returns optimal encode args per hardware. Recommends parallel worker count based on CPU/GPU availability.

Encoder priority: NVENC → QSV → VAAPI → libx264 (CPU)

### 38.7 QA Engine — `qa_engine.py`

ffprobe-based validation of scene clips and final output. Checks:
- Scene duration (1–120 seconds)
- Audio stream presence
- File size (minimum 100KB)

Returns `regenerate_scenes` list for failed clips.

### 38.8 Prompt Optimizer — `prompt_optimizer.py`

Reads `analytics_data.json`, applies rules to strengthen hook/pacing/emotion prompt templates when metrics drop. Persists improvements to `prompt_templates.json`.

Rules:
- `retention_30s_pct < 60%` → strengthen hook instruction
- `watch_time_minutes < 2.0` → tighten pacing instruction
- `ctr_pct < 5.0%` → intensify emotion instruction

---

## 39. Flexible Input Modes (v7.2)

### 39.1 Manual Topic Loader — `manual_topic_loader.py`

Load topics from `topics_manual.txt` (one per line) or `topics_queue.json` with priority over auto-discovered topics.

**Priority order:** topics_manual.txt → topics_queue.json → automated discovery

```
topics_manual.txt example:
A poor farmer who saves his village
A mysterious temple miracle
A young girl who becomes a doctor
```

Consumed topics are removed from the file automatically. GUI integration: `add_manual_topic(topic)`.

### 39.2 Script Loader — `script_loader.py`

Load `.txt` scripts from `scripts/` directory. Bypasses `story_generator.py` entirely.

Supported formats:
- Explicit markers: `[SCENE 1]`, `[SCENE 2]`, etc.
- Paragraph-based: blank lines separate scenes

Processed scripts are renamed to `.done`.

### 39.3 Microphone Narration Recorder — `mic_narration_recorder.py`

Records microphone input via `sounddevice`, saves normalized WAV to `narrations/`. When a narration file exists, `voice_synthesizer.py` is bypassed.

```cmd
pip install sounddevice scipy
```

Usage:
```python
from mic_narration_recorder import MicNarrationRecorder
recorder = MicNarrationRecorder()
path = recorder.record("story_001", duration_seconds=120)
```

### 39.4 Audio Sync Engine — `audio_sync_engine.py`

Maps a single narration WAV to multiple scenes using word-count-weighted or equal time distribution. Splits audio via FFmpeg and assigns `scene.audio_path` per scene.

---

## 40. Cinematic Prompt Engine (v7.3)

Transforms plain scene descriptions into rich cinematic prompts. Zero additional API calls — only the prompt text changes.

### 40.1 Cinematic Prompt Engine — `cinematic_prompt_engine.py`

Wraps every prompt with rotating shot type and lighting style.

**Shot types:** cinematic wide shot, dramatic close-up, low-angle cinematic shot, over-the-shoulder shot, cinematic aerial view, tracking shot perspective

**Lighting styles:** golden hour lighting, soft morning light, dramatic sunset lighting, warm cinematic lighting, diffused cloudy daylight, moody night lighting

**Quality suffix appended:** `cinematic storytelling, ultra realistic, film still, shallow depth of field, 4k`

### 40.2 Character Anchor Engine — `character_anchor_engine.py`

10 default character profiles (farmer, girl, teacher, mother, officer, doctor, soldier, child, elder, woman). Detects character keywords in Hindi and English, injects the full physical description so the same character looks identical across all scenes.

### 40.3 Location Anchor Engine — `location_anchor_engine.py`

12 default location profiles (village, temple, farm, school, city, forest, river, home, office, hospital, mountain, market). Appends consistent environment context to every matching scene.

### 40.4 Prompt Template Builder — `prompt_template_builder.py`

Single assembly point. Pipeline:
```
character inject → location inject → cinematic wrap → style modifier
```

Used by `image_generator._build_prompt()`.

### Config Flags

```json
{
  "enable_cinematic_prompt_engine": true,
  "enable_character_anchor": true,
  "enable_location_anchor": true
}
```

---

## 41. Character Reference System (v7.4)

Generates one portrait image per character and reuses it across all scenes for visual consistency. Scene image count is unchanged — portraits are pre-generated before the main scene loop.

### 41.1 Character Profile Generator — `character_profile_generator.py`

Scans story scenes to detect main characters. Builds structured profiles stored in `characters.json`.

```json
[
  {
    "id": "farmer_story001",
    "role": "farmer",
    "description": "young Indian farmer, mid-30s, brown skin, short black hair, thin mustache, wearing white kurta and dhoti",
    "reference_image": "characters/farmer_story001_reference.png"
  }
]
```

### 41.2 Character Reference Manager — `character_reference_manager.py`

Generates portrait images for each character using the existing image generation API (full provider chain). Saves to `characters/<char_id>_reference.png`. Skips generation if file already exists.

Portrait prompt template:
```
portrait photo of {description}, studio lighting, ultra realistic, neutral background, sharp focus, professional headshot, 4k
```

### 41.3 Reference Prompt Engine — `reference_prompt_engine.py`

When a reference image exists, injects `"the same farmer as shown in the reference image"` into scene prompts. Falls back to text description anchor if no reference exists.

### Pipeline Flow

```
story_generator
      ↓
character_profile_generator   ← detects characters from scenes
      ↓
character_reference_manager   ← generates portrait images (once per story)
      ↓
prompt_template_builder.activate_reference_engine()
      ↓
image_generator               ← scene images (count unchanged)
```

### Config Flags

```json
{
  "enable_character_reference_system": true,
  "enable_reference_conditioning": true
}
```

---

## 42. Advanced Configuration Reference — ragai_advanced_config.json

All new modules are controlled by `ragai_advanced_config.json` in the project root. Set any flag to `false` to disable that feature — the system reverts to original behaviour.

```json
{
  "enable_language_engine": true,
  "enable_story_knowledge_graph": true,
  "enable_scene_composer": true,
  "enable_style_engine": true,
  "enable_emotion_detection": true,
  "enable_render_optimizer": true,
  "enable_qa_engine": true,
  "enable_prompt_optimizer": true,
  "enable_manual_topic_mode": true,
  "enable_manual_script_mode": true,
  "enable_mic_narration_mode": true,
  "enable_cinematic_prompt_engine": true,
  "enable_character_anchor": true,
  "enable_location_anchor": true,
  "enable_character_reference_system": true,
  "enable_reference_conditioning": true
}
```

---

## 43. Complete Project Structure Reference (v7.4)

```
ragai/
│
├── Core Pipeline
│   ├── ragai.py                    Entry point — GUI/CLI dispatch
│   ├── config.py                   .env loading and AppConfig dataclass
│   ├── models.py                   All enums, dataclasses, constants, exceptions
│   ├── pipeline.py                 5-stage pipeline orchestrator
│   ├── story_generator.py          Stage 2 — Groq LLaMA story/scene generation
│   ├── image_generator.py          Stage 3 — 4-provider image chain + cinematic prompts
│   ├── voice_synthesizer.py        Stage 4 — Edge-TTS / gTTS (11 languages)
│   ├── video_assembler.py          Stage 5 — FFmpeg Ken Burns + QSV encode
│   ├── style_detector.py           Auto-detect visual style from topic keywords
│   ├── audio_transcriber.py        Groq Whisper transcription + audio splitting
│   ├── image_importer.py           User image loading, validation, resize
│   ├── music_selector.py           BGM selection by style + keyword scoring
│
├── Content Intelligence
│   ├── topic_quality_engine.py     Topic scoring (emotion/curiosity/relatability)
│   ├── engagement_predictor.py     CTR + watch time prediction
│   ├── narrative_variation_engine.py  5 narrative structures rotation
│   ├── visual_variation_engine.py  Per-scene Ken Burns motion variation
│   ├── content_variation_engine.py Voice/music/pacing profile rotation
│   ├── story_archive.py            SQLite story memory + duplicate detection
│   ├── thumbnail_ab_tester.py      3-variant A/B testing with Wilson CTR scoring
│
├── Intelligence Layer
│   ├── language_engine.py          11-language detection + voice/style config
│   ├── story_knowledge_graph.py    SQLite semantic story graph
│   ├── scene_composer.py           PIL layer compositor (lighting + effects)
│   ├── style_engine.py             Channel branding via channel_styles.json
│   ├── emotion_detector.py         Per-scene emotion arc detection
│   ├── render_optimizer.py         GPU encoder detection (NVENC/QSV/VAAPI)
│   ├── qa_engine.py                ffprobe-based video/clip validation
│   ├── prompt_optimizer.py         Analytics-driven prompt template evolution
│
├── Flexible Input Modes
│   ├── manual_topic_loader.py      topics_manual.txt + queue priority injection
│   ├── script_loader.py            User script files bypass story_generator
│   ├── mic_narration_recorder.py   Microphone recording → normalized WAV
│   ├── audio_sync_engine.py        Narration-to-scene audio splitting
│
├── Cinematic Prompt Engine
│   ├── cinematic_prompt_engine.py  Shot type + lighting style rotation
│   ├── character_anchor_engine.py  Text-based character consistency
│   ├── location_anchor_engine.py   Location environment consistency
│   ├── prompt_template_builder.py  Single prompt assembly entry point
│
├── Character Reference System
│   ├── character_profile_generator.py  Detect + profile story characters
│   ├── character_reference_manager.py  Generate + cache portrait images
│   ├── reference_prompt_engine.py      Reference-based prompt injection
│
├── Performance
│   ├── scene_parallel_executor.py  ThreadPoolExecutor (4 workers) for scenes
│
├── Editor V2
│   ├── editor.py                   RAGAI Editor V2 entry point
│   ├── editor_gui.py               3-panel Tkinter GUI
│   ├── editor_config.py            ragai_config.json loader
│   ├── clip_manager.py             Clip library manager
│   ├── watcher.py                  watchdog folder monitor
│   ├── timeline.py                 Drag-and-drop timeline
│   ├── assembler.py                FFmpeg compilation assembler
│   ├── auto_pipeline.py            Automated batch compilation
│   ├── topic_engine.py             Hashtag-based clip grouping
│   ├── hook_generator.py           AI hook intro generator
│   ├── outro_generator.py          Subscribe outro generator
│   ├── variation_engine.py         Content variation engine
│   ├── thumbnail_generator.py      Viral thumbnail composer
│
├── Automation
│   ├── job_manager.py              Job state + crash recovery
│   ├── scheduler.py                Automated topic queue runner
│
├── Analytics
│   ├── analytics_engine.py         Video performance analytics
│   ├── retention_optimizer.py      Watch time optimization
│   ├── channel_manager.py          Multi-channel management
│   ├── shorts_generator.py         YouTube Shorts generation
│   ├── title_generator.py          SEO title generation
│   ├── viral_scorer.py             Viral potential scoring
│   ├── trend_fetcher.py            Trending topic fetcher
│
├── Config Files
│   ├── ragai_advanced_config.json  Feature flags for all new modules
│   ├── ragai_config.json           Global config (output_dir, quality, QSV)
│   ├── channel_styles.json         Per-channel branding config
│   ├── characters.json             Character profiles (generated per story)
│   ├── topics_queue.json           Scheduler topic queue
│   ├── topics_manual.txt           Manual topic input file
│
├── Data Files (runtime, not committed)
│   ├── jobs_state.json             Job lifecycle state
│   ├── editor_clips.json           Clip library state
│   ├── story_archive.db            Story memory database
│   ├── story_graph.db              Story knowledge graph
│   ├── prompt_templates.json       Evolved prompt templates
│   ├── analytics_data.json         Video performance data
│
├── Folders
│   ├── output/                     Generated videos (folder-per-video)
│   ├── compiled/                   Editor compilation outputs
│   ├── characters/                 Character reference portrait images
│   ├── narrations/                 Microphone narration WAV files
│   ├── scripts/                    User-provided script .txt files
│   ├── music/                      7 background music tracks
│   ├── logs/                       Application logs
│   └── tmp/                        Temporary working files (auto-cleaned)
```

---

*RAGAI Video Factory v7.4 — AI-powered cinematic video generation with character consistency, multi-language support, and adaptive intelligence.*
*Built by Kunal with Kiro | March 2026*
