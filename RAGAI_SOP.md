# RAGAI Video Factory — Standard Operating Procedure (SOP)

> Version: 8.0 | Platform: Windows 10/11 | Last Updated: April 2026 | Author: Kunal
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
7. [Making a Video — Step by Step (Operational Guide)](#7-making-a-video--step-by-step-operational-guide)
8. [Input Modes](#8-input-modes)
9. [Visual Styles Guide](#9-visual-styles-guide)
10. [Quality Presets Reference](#10-quality-presets-reference)
11. [Image Provider Chain](#11-image-provider-chain)
12. [Intel QSV Hardware Encoding](#12-intel-qsv-hardware-encoding)
13. [Scene Re-Generate (Scenes Tab)](#13-scene-re-generate-scenes-tab)
14. [Voice Settings](#14-voice-settings)
15. [Background Music System](#15-background-music-system)
16. [Image Quality & Ken Burns System](#16-image-quality--ken-burns-system)
17. [Groq Rate Limits & Solutions](#17-groq-rate-limits--solutions)
18. [API Costs & Free Limits](#18-api-costs--free-limits)
19. [Pipeline Overview](#19-pipeline-overview)
20. [Project Structure Reference](#20-project-structure-reference)
21. [Configuration Reference](#21-configuration-reference)
22. [YouTube Upload Workflow](#22-youtube-upload-workflow)
23. [YouTube Monetization Requirements](#23-youtube-monetization-requirements)
24. [Troubleshooting Guide](#24-troubleshooting-guide)
25. [Quick Rebuild Checklist](#25-quick-rebuild-checklist)
26. [Before Next Laptop Rebuild — Backup Checklist](#26-before-next-laptop-rebuild--backup-checklist)
27. [Pending Items & Future Upgrades](#27-pending-items--future-upgrades)
28. [Quick Reference Commands](#28-quick-reference-commands)
29. [RAGAI Editor V2](#29-ragai-editor-v2)
30. [RAGAI Editor V2 — Module Reference](#30-ragai-editor-v2--module-reference)
31. [Global Config — ragai_config.json](#31-global-config--ragai_configjson)
32. [Job Manager & Crash Recovery System](#32-job-manager--crash-recovery-system)
33. [Scheduler — Automated Topic Queue](#33-scheduler--automated-topic-queue)
34. [Complete Project Structure Reference (v7.4)](#34-complete-project-structure-reference-v74)
35. [Rebuild on New System — Complete Checklist](#35-rebuild-on-new-system--complete-checklist)
36. [How to Ask Kiro to Rebuild RAGAI on a New System](#36-how-to-ask-kiro-to-rebuild-ragai-on-a-new-system)
37. [Content Intelligence Layer (v7.0)](#37-content-intelligence-layer-v70)
38. [Thumbnail A/B Testing](#38-thumbnail-ab-testing)
39. [Performance Layer](#39-performance-layer)
40. [Intelligence Layer (v7.1)](#40-intelligence-layer-v71)
41. [Flexible Input Modes (v7.2)](#41-flexible-input-modes-v72)
42. [Cinematic Prompt Engine (v7.3)](#42-cinematic-prompt-engine-v73)
43. [Character Reference System (v7.4)](#43-character-reference-system-v74)
44. [Advanced Configuration Reference](#44-advanced-configuration-reference--ragai_advanced_configjson)
45. [Complete Project Structure Reference (v8.0)](#45-complete-project-structure-reference-v80)
46. [v8.0 Bug Fixes & Technical Changes](#46-v80-bug-fixes--technical-changes)

---

## 1. RAGAI System Overview

RAGAI is a fully automated AI video factory. You type a story topic, choose a language, and RAGAI creates a complete cinematic video with AI images, voiceover, smooth Ken Burns animations, and background music — ready for YouTube.

### Architecture (v8.0)

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
| Video Encoding | FFmpeg 8.x — H.264, Intel QSV hardware or libx264 software |
| Animation | PIL frames + FFmpeg, 24fps cinematic Ken Burns (contain+blur bg) |
| Music | 7 tracks in music/ — auto-selected by style, stereo 44.1kHz mix |
| Output | Up to 4K UHD (3840×2160) landscape / Shorts (2160×3840) |

### What's New in v8.0

- **BGM audio fix** — background music now audible at proper volume (stereo 44.1kHz, loudnorm -16 LUFS)
- **Image distortion fix** — Ken Burns uses contain+blur-background, no squish or crop of portrait images
- **Aspect ratio fix** — crop always matches output ratio exactly, no stretch distortion
- **colorbalance fix** — FFmpeg 8.x compatible parameter names (rs/gs/bs instead of ss/sm/sh)
- **Safe pan zones** — Ken Burns pan stays within image content, never pans into blurred background

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
| FFmpeg | 8.x required | 8.1-essentials from gyan.dev |

> Tested on: Acer Swift AI SF14-51, Intel Core Ultra 226V/258V, Intel Arc 140V, 16GB LPDDR5X, Windows 11

---

## 3. Tool Installations

### 3.1 Python 3.11 or 3.12

1. Download from: https://www.python.org/downloads/
2. Run installer — ✅ Check **"Add Python to PATH"**
3. Verify: `python --version`
4. Upgrade pip: `python -m pip install --upgrade pip`

### 3.2 Git

1. Download from: https://git-scm.com/download/win
2. Run installer with default settings
3. Verify: `git --version`

### 3.3 FFmpeg 8.x (REQUIRED — must be 8.x)

FFmpeg is the video encoding engine. RAGAI requires FFmpeg **8.x** specifically — older versions have different colorbalance filter parameter names.

1. Download from: https://www.gyan.dev/ffmpeg/builds/
   - Choose: **ffmpeg-release-essentials.zip** (latest 8.x build)
2. Extract to: `C:\ffmpeg\`
3. Add to System PATH: Win + S → "Environment Variables" → System variables → Path → New → `C:\ffmpeg\bin`
4. Open a **new** Command Prompt and verify:
   ```cmd
   ffmpeg -version
   ```
   Output should show: `ffmpeg version 8.x`

> IMPORTANT: FFmpeg 7.x or older will cause colorbalance filter errors. Always use 8.x from gyan.dev.

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

Free tier: 30 req/min, 6,000 tokens/min, 500,000 tokens/day (~8–10 videos/day)

### 4.2 Leonardo AI API Key

Leonardo AI generates the scene images (primary provider).

1. Go to: https://app.leonardo.ai/
2. Sign up / Log in → **Profile** → **API Access** → **Generate API Key**
3. Copy the key (UUID format)

Free tier: ~150 tokens/day (~1–2 videos/day).

### 4.3 HuggingFace Token (Optional — for Fallback 2)

1. Go to: https://huggingface.co/settings/tokens
2. Create a token with **read** access
3. Add to `.env` as `HF_TOKEN=hf_...`

---

## 5. Project Setup

### 5.1 Clone the Project

```cmd
git clone https://github.com/kishorekunal64-netizen/taskflow.git ragai
cd ragai
```

### 5.2 Create Virtual Environment

```cmd
python -m venv venv
venv\Scripts\activate
```

### 5.3 Install Python Dependencies

```cmd
pip install -r requirements.txt
```

### 5.4 Configure .env File

Create `.env` in the project root:

```env
GROQ_API_KEY=gsk_your_groq_key_here
LEONARDO_API_KEY=your_leonardo_uuid_key_here
HF_TOKEN=hf_your_huggingface_token
USE_EDGE_TTS=true
DEFAULT_LANGUAGE=hi
DEFAULT_FORMAT=landscape
LOG_LEVEL=INFO
```

---

## 6. Running the App

### 6.1 GUI Mode (Recommended)

**Option A — Double-click launcher:**
Double-click `START_RAGAI.bat` in the project folder.

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

### 6.3 Diagnostics

```cmd
python ragai.py --diagnose
```

Checks: Python version, all packages, FFmpeg on PATH, .env keys, music/ folder, output/ writable, Intel QSV availability.

---

## 7. Making a Video — Step by Step (Operational Guide)

This is the complete user workflow from opening the app to getting a finished video.

### Step 1 — Launch the App

Double-click `START_RAGAI.bat` or run:
```cmd
venv\Scripts\activate
python ragai.py
```

Wait for the GUI to open (5–10 seconds). The animated header with Radha & Gauri cards will appear.

### Step 2 — Choose Story Source

In the **Settings tab**, select your input mode:

| Mode | When to Use |
|------|-------------|
| **Topic** | You have a story idea — AI writes everything |
| **Script** | You have a pre-written script file (.txt) |
| **Audio** | You have a recorded narration (.mp3/.wav) |
| **Images** | You have your own photos/images to use |

### Step 3 — Enter Your Topic (Topic Mode)

Type your topic in English in the Topic field. Examples:
- `A poor farmer who saves his village from drought`
- `A girl from Hapur who becomes an IAS officer`
- `Radha doing pooja in Shiva temple`
- `A soldier fighting to protect his family`

> Tip: Include location names (Delhi, Mumbai, village) and emotion words for better stories.

### Step 4 — Select Audience

Choose who the video is for:
- **Family** — suitable for all ages (recommended for most topics)
- **Children** — simpler language, gentle themes
- **Adults** — mature themes, complex stories
- **Devotees** — religious/spiritual content

### Step 5 — Select Language

Choose the narration language from the dropdown:
- **Hindi (hi)** — most popular for Indian YouTube
- **English (en)** — for international audience
- **Tamil, Telugu, Bengali, Gujarati, Marathi, Kannada, Malayalam, Punjabi, Urdu**

### Step 6 — Select Visual Style

| Style | Best For |
|-------|---------|
| **AUTO** | Let RAGAI detect from topic (recommended) |
| Dynamic Epic | Mythology, history, war, kingdom stories |
| Mystery Dark | Thriller, detective, horror, crime |
| Spiritual Devotional | Religious, bhajan, temple, devotional |
| Peaceful Nature | Children stories, nature, village, calm |
| Romantic Drama | Love stories, family drama, emotional |
| Adventure Action | Action, fantasy, journey, quest |

### Step 7 — Set Scene Count

Choose how many scenes (images) the video will have:
- **5 scenes** — ~2–3 min video, fastest generation
- **8 scenes** — ~4–5 min video (recommended)
- **10 scenes** — ~5–7 min video
- **12 scenes** — ~7–9 min video
- **15 scenes** — ~10–12 min video, slowest

### Step 8 — Set Video Length (Optional)

- Leave at **0 (Auto)** — AI decides the best length
- Or set **1–10 minutes** to target a specific duration

### Step 9 — Background Music

- **Auto mode** (default) — RAGAI automatically picks the best music track based on your topic and style
- **Custom music** — click **Browse…** to use your own .mp3 file
- **Clear** — removes custom music, returns to auto

> The 7 built-in tracks: epic, mystery, devotional, nature, romantic, adventure, neutral
> Music is mixed at proper volume — voice is clear, music is audible in background.

### Step 10 — Select Quality Preset

| Preset | Resolution | Speed | Use For |
|--------|-----------|-------|---------|
| **Draft** | 720p | Fastest | Quick preview |
| **Standard** | 1080p | Fast | Social media |
| **High** | 1440p | Medium | YouTube |
| **Cinema** | 4K UHD | Slow | Best quality |

> With Intel QSV (Arc GPU): Cinema 4K takes ~3 min. Without QSV: ~25 min.

### Step 11 — Select Format

- **Landscape** — 16:9 widescreen (YouTube standard)
- **Shorts** — 9:16 portrait (YouTube Shorts, Instagram Reels)

### Step 12 — Character Names (Optional)

If your story has named characters, enter them:
```
hero=Arjun, heroine=Priya, villain=Rajan
```
This helps the AI use consistent names throughout the story.

### Step 13 — Output Directory

Default is `./output` — leave as-is or click Browse to change.

### Step 14 — Click GENERATE VIDEO

Click the **GENERATE VIDEO** button. The progress bar starts and the **Live Log tab** shows real-time output.

### Step 15 — Monitor Progress

Switch to the **Live Log tab** to watch the pipeline:
```
Stage 1: Style detection...
Stage 2: Story generation...
Stage 3: Image generation (scene 1/8)...
Stage 4: Voice synthesis (scene 1/8)...
Stage 5: Video assembly...
BGM: Auto-matched: epic.mp3 (score 2.0)
Final video (QSV, 20000k): output\video_20260403_...\video.mp4
Pipeline complete in 487.23s
```

### Step 16 — Wait for Completion

Typical times (Cinema 4K, 8 scenes):
- With Intel QSV: **8–10 minutes**
- Without QSV (software): **20–30 minutes**
- Draft 720p: **2–4 minutes**

### Step 17 — Review Output

When complete, go to your output folder:
```
output/
└── video_20260403_HHMMSS/
    ├── video.mp4        ← your finished video
    ├── thumbnail.jpg    ← auto-generated thumbnail
    └── metadata.txt     ← title, description, hashtags for YouTube
```

### Step 18 — Review Scene Images (Optional)

Click the **Scenes tab** to see all scene images. If any image looks wrong:
1. Click **Re-generate Image** on that scene card
2. A new image is generated and the clip is re-encoded
3. No need to re-run the full pipeline

### Step 19 — Upload to YouTube

1. Open `metadata.txt` — copy the title, description, and hashtags
2. Go to studio.youtube.com → Upload
3. Select `video.mp4`
4. Paste title and description
5. Upload `thumbnail.jpg` as custom thumbnail
6. Schedule for 7–9 PM IST for best reach
7. Publish

---

## 8. Input Modes

| Mode | How to Use | Best For |
|------|-----------|---------|
| **Topic** | Type a topic → AI writes the full story | Most common — zero prep needed |
| **Script** | Browse to a .txt file with your script | When you have pre-written content |
| **Audio** | Browse to an .mp3/.wav file → Groq Whisper transcribes it | Recorded narrations, interviews |
| **Images** | Browse to select your own images → AI writes story around them | When you have specific visuals |

### Using Image Mode with Portrait Photos

When you upload portrait photos (phone camera photos, tall images):
- RAGAI preserves the full image — no cropping, no squishing
- The image is centered with a blurred background filling the sides (cinematic look)
- Ken Burns zoom stays within the image content area
- The person/subject is always fully visible

---

## 9. Visual Styles Guide

| Style | Best For | Color Grade | BGM Track |
|-------|---------|-------------|-----------|
| AUTO | Let RAGAI detect from topic keywords | Varies | Auto-matched |
| Dynamic Epic | Mythology, history, war stories | High contrast, warm orange-teal | epic.mp3 |
| Mystery Dark | Thriller, detective, horror | Desaturated, cool teal shadows | mystery.mp3 |
| Spiritual Devotional | Religious, bhajan, devotional | Warm saffron-gold, soft glow | devotional.mp3 |
| Peaceful Nature | Children stories, nature, calm | Soft greens, airy, bright | nature.mp3 |
| Romantic Drama | Love stories, family drama | Warm rose-gold, soft contrast | romantic.mp3 |
| Adventure Action | Action, fantasy, journey | Vivid, punchy, teal-orange | adventure.mp3 |

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

---

## 11. Image Provider Chain

RAGAI automatically falls through a 4-provider chain when one fails or hits quota.

| Priority | Provider | Cost | Requires | Quality | Speed |
|----------|---------|------|---------|---------|-------|
| 1 | **Leonardo AI** (Kino XL) | 150 tokens/day free | API key | Best | ~30s/image |
| 2 | **Pollinations.ai** | Free, unlimited | Nothing | Good | ~20–90s/image |
| 3 | **HuggingFace FLUX.1-schnell** | Free | HF token (optional) | Good | ~30–120s/image |
| 4 | **OpenVINO local** | Free, offline | `optimum[openvino]` installed | Good | ~15s on Arc 140V |

### Enabling OpenVINO (offline local generation)

```cmd
venv\Scripts\activate
pip install "optimum[openvino]" diffusers accelerate
```

First run downloads the model (~1.5GB). Subsequent runs are instant.

---

## 12. Intel QSV Hardware Encoding

RAGAI automatically detects Intel Quick Sync Video (QSV) at startup.

### What it does

- Replaces software `libx264` with hardware `h264_qsv` encoder
- **5–10x faster** encode speed vs software
- Automatic CPU fallback if QSV fails at runtime

### Checking QSV status

Look in the Live Log at startup:
```
Intel QSV detected — hardware encoding enabled (h264_qsv)
```
or:
```
Intel QSV not available — using software encoding (libx264)
```

### Requirements for QSV

- Intel Arc / Iris Xe / UHD Graphics GPU
- FFmpeg 8.x from gyan.dev (includes QSV support)
- Intel Graphics driver up to date

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

---

## 14. Voice Settings

### Two Voice Modes

| Mode | Quality | Network |
|------|---------|---------|
| Edge-TTS (Microsoft Neural) | Natural, human-sounding | Needs internet |
| gTTS (Google) | Consistent but robotic | Works on any network |

Set in `.env`:
```env
USE_EDGE_TTS=true   # natural voice
USE_EDGE_TTS=false  # gTTS fallback
```

### Indian Language Voice Map

| Language | Microsoft Neural Voice |
|----------|----------------------|
| Hindi | hi-IN-SwaraNeural |
| English | en-US-JennyNeural |
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

## 15. Background Music System

### How BGM Works (v8.0)

RAGAI automatically selects and mixes background music into every video.

**Selection logic:**
1. If you set a custom BGM file → uses that file
2. Scores all 7 tracks against your topic keywords (keyword match scoring)
3. Adds style bonus (+2 points) for the preferred track of your visual style
4. Picks the highest-scoring track that exists on disk
5. Falls back to style default → neutral.mp3 if nothing matches

**Audio mix (v8.0 fixed):**
- Voice is normalized to -16 LUFS (broadcast standard, clear and loud)
- Music is set to -8 dB relative to voice (clearly audible background)
- Both streams resampled to 44.1kHz stereo before mixing
- `amix normalize=0` preserves set levels (no automatic halving)
- Output: stereo AAC 320kbps at 44.1kHz — plays on all devices

### BGM Track → Style Mapping

| Track | Style | Topic Keywords |
|-------|-------|---------------|
| epic.mp3 | Dynamic Epic | war, battle, warrior, kingdom, mythology, history, hero |
| mystery.mp3 | Mystery Dark | mystery, thriller, detective, crime, ghost, horror, dark |
| devotional.mp3 | Spiritual Devotional | god, goddess, temple, prayer, krishna, shiva, bhakti |
| nature.mp3 | Peaceful Nature | nature, forest, river, village, children, peaceful, calm |
| romantic.mp3 | Romantic Drama | love, romance, wedding, family, drama, emotional |
| adventure.mp3 | Adventure Action | adventure, journey, quest, magic, fantasy, action |
| neutral.mp3 | Fallback | story, life, people, world, documentary |

### Using Custom BGM

1. In the Settings tab, find the **Background Music** section
2. Click **Browse…** → select any .mp3 file
3. The label shows your file name in green
4. Click **✕ Clear** to return to auto mode

### Troubleshooting BGM

| Problem | Solution |
|---------|---------|
| No music heard | Check output video is from a run AFTER April 2026 (v8.0 fix) |
| Music too quiet | This was the old bug — v8.0 fixes it. Re-run the pipeline |
| Wrong music style | Set style manually instead of AUTO, or use custom BGM |
| music/ folder empty | Run `python create_music_v2.py` to regenerate tracks |

---

## 16. Image Quality & Ken Burns System

### How Images Are Processed (v8.0)

**Image import (user-supplied images):**
- Images are saved as-is (original resolution, RGB PNG)
- No forced resize at import — original quality preserved
- Ken Burns stage handles all scaling

**Ken Burns processing:**
1. Image is loaded at original resolution
2. **Contain scale** — image is scaled to fit entirely within the output frame (no cropping of content)
3. Blurred version of the image fills letterbox/pillarbox bars (cinematic look)
4. Canvas is scaled up by 1.12x for Ken Burns zoom headroom
5. **Safe pan zones** — pan stays within the image content area, never into blurred background
6. Crop always matches output aspect ratio exactly (no stretch distortion)

### Portrait Photos in Landscape Videos

When you use portrait photos (phone camera, tall images) in landscape format:
- The full person is visible (head to toe)
- Blurred background fills the sides
- Ken Burns zooms into the person, not the background
- No squishing, no cropping of the subject

### Image Quality Tips

| Tip | Why |
|-----|-----|
| Use high-res originals (2MP+) | Better quality after upscaling to 4K |
| Portrait photos work fine | v8.0 handles them correctly |
| Landscape photos fill frame | No bars needed |
| Square photos get side bars | Blurred background fills sides |

---

## 17. Groq Rate Limits & Solutions

| Situation | Solution |
|-----------|---------|
| 429 error — daily limit hit | Wait 24 hours for automatic reset |
| Need to keep working now | Switch to backup model (see below) |
| Free daily limit | 500,000 tokens/day — enough for ~8–10 videos |

### Switch to Backup Model

```cmd
python -c "content=open('story_generator.py',encoding='utf-8').read(); content=content.replace('llama-3.3-70b-versatile','llama-3.1-8b-instant'); open('story_generator.py','w',encoding='utf-8').write(content); print('Backup model ON!')"
```

### Switch Back to Best Model

```cmd
python -c "content=open('story_generator.py',encoding='utf-8').read(); content=content.replace('llama-3.1-8b-instant','llama-3.3-70b-versatile'); open('story_generator.py','w',encoding='utf-8').write(content); print('Best model ON!')"
```

---

## 18. API Costs & Free Limits

| Service | Cost & Limits |
|---------|--------------|
| Groq (Story + Transcription) | FREE — 500K tokens/day, ~8–10 videos/day |
| Leonardo (Images — primary) | FREE — 150 credits/day (~1–2 videos). Paid $24/month for 80+ videos/day |
| Pollinations.ai (Images — fallback 1) | FREE — unlimited, no key needed |
| HuggingFace FLUX (Images — fallback 2) | FREE — rate limited |
| OpenVINO local (Images — fallback 3) | FREE — offline, Intel Arc GPU |
| Edge-TTS (Voice) | FREE — Microsoft, unlimited |
| gTTS (Voice Fallback) | FREE — Google, unlimited |
| FFmpeg (Video) | FREE — open source |
| **Total for 1–2 videos/day** | **$0/month** |
| **Total for 40 videos/day** | **~$24/month** (Leonardo paid only) |

---

## 19. Pipeline Overview

```
[Input] ──► Stage 1: Style Detection
              │  (auto-detect from topic keywords, or use user selection)
              ▼
           Stage 2: Story Generation (Groq LLaMA 3)
              │  or: Script parsing / Audio transcription (Groq Whisper)
              ▼
           Stage 3: Image Generation (Leonardo → Pollinations → HF → OpenVINO)
              │  or: User image import (original quality preserved)
              ▼
           Stage 4: Voice Synthesis (Edge-TTS / gTTS)
              │  or: Audio file splitting (for audio input mode)
              ▼
           Stage 5: Video Assembly (FFmpeg)
              │  • Contain+blur Ken Burns (portrait-safe, no distortion)
              │  • Safe pan zones (stays within image content)
              │  • Film grain (intensity 6)
              │  • Letterbox (2.39:1 anamorphic on landscape)
              │  • Color grading per style (FFmpeg 8.x compatible)
              │  • Cross-dissolve transitions (0.8s xfade)
              │  • BGM mix: loudnorm -16 LUFS voice + -8dB music, 44.1kHz stereo
              │  • H.264 encode (QSV or libx264)
              ▼
           [Output: video.mp4 + thumbnail.jpg + metadata.txt]
```

### Stage Timing (Cinema 4K, 8 scenes, Intel Arc 140V)

| Stage | Time | Notes |
|-------|------|-------|
| Story | ~30s | Groq LLaMA 3.3 70B |
| Images | ~4 min | Leonardo AI (30s/image × 8) |
| Voice | ~1 min | Edge-TTS |
| Assembly | ~3 min | QSV hardware encode |
| **Total** | **~8–9 min** | With QSV. Software: ~25 min |

---

## 20. Project Structure Reference

```
ragai/
├── ragai.py              Entry point — GUI/CLI dispatch
├── config.py             .env loading and AppConfig dataclass
├── models.py             All enums, dataclasses, constants, exceptions
├── pipeline.py           5-stage pipeline orchestrator
├── story_generator.py    Stage 2 — Groq LLaMA story/scene generation
├── image_generator.py    Stage 3 — 4-provider chain
├── voice_synthesizer.py  Stage 4 — Edge-TTS / gTTS voice synthesis
├── video_assembler.py    Stage 5 — FFmpeg Ken Burns + QSV encode (v8.0)
├── style_detector.py     Auto-detect visual style (FFmpeg 8.x colorbalance)
├── audio_transcriber.py  Groq Whisper transcription + audio splitting
├── image_importer.py     User image loading (original quality, no forced resize)
├── music_selector.py     BGM selection by style + keyword scoring
├── log_setup.py          Logging configuration
├── gui.py                Tkinter GUI — animated header, 3 tabs, dark theme
├── ragai_diagnose.py     Diagnostics runner
├── create_music_v2.py    One-time music track generator
├── START_RAGAI.bat       Windows one-click launcher
├── requirements.txt      Python dependencies
├── .env                  API keys and config (not committed)
├── music/                7 background music tracks
├── output/               Generated videos (folder-per-video structure)
├── tmp/                  Temporary working files (auto-cleaned)
└── logs/                 Application logs
```

---

## 21. Configuration Reference

### .env Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GROQ_API_KEY` | Yes | — | Groq API key |
| `LEONARDO_API_KEY` | Yes | — | Leonardo AI key |
| `HF_TOKEN` | No | "" | HuggingFace token |
| `USE_EDGE_TTS` | No | `true` | `false` = gTTS fallback |
| `DEFAULT_LANGUAGE` | No | `hi` | Default narration language |
| `DEFAULT_FORMAT` | No | `landscape` | Default video format |
| `LOG_LEVEL` | No | `INFO` | DEBUG/INFO/WARNING/ERROR |

---

## 22. YouTube Upload Workflow

| Step | Action |
|------|--------|
| 1 | Run RAGAI → video saved in `output/video_YYYYMMDD_HHMMSS/` |
| 2 | Watch the video — check quality, voice, images, music |
| 3 | Open `metadata.txt` — copy title, description, hashtags |
| 4 | Go to studio.youtube.com → Upload |
| 5 | Select `video.mp4` |
| 6 | Paste title and description from metadata.txt |
| 7 | Upload `thumbnail.jpg` as custom thumbnail |
| 8 | Schedule for 7–9 PM IST |
| 9 | Publish |

### Best Upload Times (IST)

- Weekdays: 7:00 PM – 9:00 PM
- Weekends: 10:00 AM – 12:00 PM or 7:00 PM – 9:00 PM

---

## 23. YouTube Monetization Requirements

| Requirement | Target |
|-------------|--------|
| Subscribers | 1,000 minimum |
| Watch Hours | 4,000 hours in last 12 months |
| Consistency | 1 video/day minimum |
| Estimated timeline | 3–6 months with daily posting |

---

## 24. Troubleshooting Guide

| Problem | Solution |
|---------|---------|
| **FFmpeg colorbalance error** | Must use FFmpeg 8.x from gyan.dev. Older versions use different parameter names |
| **No background music / music inaudible** | Must run pipeline after April 2026 (v8.0 fix). Old videos need re-generation |
| **Image squished/distorted** | Fixed in v8.0. Re-run pipeline — new videos use contain+blur approach |
| **Image cropped (head/feet cut off)** | Fixed in v8.0. Safe pan zones keep Ken Burns within image content |
| **Virtual environment not found** | `python -m venv venv` → `venv\Scripts\activate` → `pip install -r requirements.txt` |
| **FFmpeg not found on PATH** | Verify: `ffmpeg -version`. Re-add `C:\ffmpeg\bin` to System PATH |
| **Missing GROQ_API_KEY** | Check `.env` file exists in project root. No spaces around `=` |
| **Edge-TTS fails / no audio** | Set `USE_EDGE_TTS=false` in `.env`. Check internet connection |
| **Leonardo AI returns 400** | Check API key in `.env`. Free quota may be exhausted — Pollinations fallback activates |
| **Groq rate limit (429)** | Free tier: 30 req/min. Reduce scene count or switch to backup model |
| **Video output is black** | Run `python ragai.py --diagnose`. Check `logs/` folder |
| **Intel QSV not detected** | Update Intel Graphics driver. Verify: `ffmpeg -encoders | findstr qsv` |
| **No sound in video** | Check `music/` folder has .mp3 files. Run `python create_music_v2.py` |
| **Video too slow to make** | Use Draft or Standard preset. Enable QSV if you have Intel Arc GPU |
| **All image providers failed** | Check internet. Verify Leonardo API key. Install OpenVINO for offline fallback |
| **music/ folder empty** | Run `python create_music_v2.py` to regenerate all 7 tracks |
| **sample_rate=96000 in output** | Old bug — fixed in v8.0. Re-run pipeline for 44.1kHz output |

---

## 25. Quick Rebuild Checklist

- [ ] Install Python 3.11 or 3.12 (add to PATH)
- [ ] Install Git
- [ ] Install FFmpeg **8.x** from gyan.dev (add `bin/` to PATH)
- [ ] Install VS Code + Python extension
- [ ] Clone project: `git clone https://github.com/kishorekunal64-netizen/taskflow.git`
- [ ] `python -m venv venv`
- [ ] `venv\Scripts\activate`
- [ ] `pip install -r requirements.txt`
- [ ] Create `.env` with `GROQ_API_KEY` and `LEONARDO_API_KEY`
- [ ] `python create_music_v2.py` (generate music tracks)
- [ ] `python ragai.py --diagnose` (verify everything)
- [ ] Double-click `START_RAGAI.bat` to launch

---

## 26. Before Next Laptop Rebuild — Backup Checklist

| Priority | File / Folder | Why |
|----------|--------------|-----|
| Critical | `.env` | Your API keys |
| Critical | All `*.py` files in project root | The entire application |
| Important | `music/` folder | 7 generated tracks |
| Important | `requirements.txt` | Exact dependency versions |
| Important | `START_RAGAI.bat` | Launcher script |
| Optional | `output/` folder | Keep your best videos |

**Do NOT back up:** `venv/`, `tmp/`, `__pycache__/`, `ffmpeg-8.1-essentials_build/`

---

## 27. Pending Items & Future Upgrades

### Pending

| Item | Details |
|------|---------|
| YouTube Auto-Upload | OAuth setup pending — use manual upload for now |
| Edge-TTS on WiFi | Blocked by some routers. Works on mobile hotspot. Auto-detection added in v6.1 |

### Future Upgrades

| Upgrade | Benefit |
|---------|---------|
| Acer Predator Helios Neo 16S (RTX 5070) | Local AI — $0 API costs |
| Leonardo paid plan ($24/month) | 80+ videos/day |
| AnimateDiff / Stable Video | Real AI video motion |
| YouTube auto-upload | Fully automated publish pipeline |
| Batch generation | Queue multiple topics, run overnight |

---

## 28. Quick Reference Commands

```cmd
# Launch GUI
venv\Scripts\activate
python ragai.py

# Run diagnostics
python ragai.py --diagnose

# Regenerate music tracks
python create_music_v2.py

# Switch to backup Groq model
python -c "content=open('story_generator.py',encoding='utf-8').read(); content=content.replace('llama-3.3-70b-versatile','llama-3.1-8b-instant'); open('story_generator.py','w',encoding='utf-8').write(content); print('Backup model ON!')"

# Switch back to best Groq model
python -c "content=open('story_generator.py',encoding='utf-8').read(); content=content.replace('llama-3.1-8b-instant','llama-3.3-70b-versatile'); open('story_generator.py','w',encoding='utf-8').write(content); print('Best model ON!')"

# Enable natural voice (Edge-TTS)
python -c "content=open('.env',encoding='utf-8').read(); open('.env','w',encoding='utf-8').write(content.replace('USE_EDGE_TTS=false','USE_EDGE_TTS=true')); print('Natural voice ON!')"

# Enable fallback voice (gTTS)
python -c "content=open('.env',encoding='utf-8').read(); open('.env','w',encoding='utf-8').write(content.replace('USE_EDGE_TTS=true','USE_EDGE_TTS=false')); print('gTTS voice ON!')"

# Check Intel QSV availability
ffmpeg -hide_banner -encoders 2>nul | findstr qsv

# View latest log
powershell "Get-ChildItem logs\ | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content"

# Install OpenVINO (offline image generation)
pip install "optimum[openvino]" diffusers accelerate

# Test BGM audio levels on an existing video
ffmpeg -i output\video_FOLDER\video.mp4 -af volumedetect -vn -f null - 2>&1 | findstr volume
```

---

## 29. RAGAI Editor V2

RAGAI Editor V2 is a standalone Tkinter desktop application that automatically collects videos produced by RAGAI and compiles them into long-form YouTube compilation videos.

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
2. When 3+ clips share related hashtags, a compilation group is formed
3. Hook intro is generated via Groq LLM + Edge-TTS
4. Compilation is assembled via FFmpeg (hook + clips + outro)
5. Thumbnail is generated
6. Final video saved to `./compiled/`

---

## 30. RAGAI Editor V2 — Module Reference

| Module | File | Responsibility |
|--------|------|---------------|
| Entry point | `editor.py` | Init clip manager, start watcher, launch GUI |
| GUI | `editor_gui.py` | 3-panel Tkinter interface |
| Config | `editor_config.py` | Load/save `ragai_config.json` |
| Clip Manager | `clip_manager.py` | Maintain clip library in `editor_clips.json` |
| Watcher | `watcher.py` | watchdog monitor on `./output/` |
| Topic Engine | `topic_engine.py` | Group clips by hashtag similarity |
| Hook Generator | `hook_generator.py` | Groq LLM hook text → Edge-TTS → FFmpeg intro |
| Outro Generator | `outro_generator.py` | Subscribe outro clip |
| Variation Engine | `variation_engine.py` | Rotate voices, music, order |
| Thumbnail Generator | `thumbnail_generator.py` | Extract frame, overlay Hindi text |
| Timeline | `timeline.py` | Tkinter Canvas drag-and-drop |
| Assembler | `assembler.py` | FFmpeg compile: hook + clips + outro |
| Auto Pipeline | `auto_pipeline.py` | Fully automated batch compilation |

---

## 31. Global Config — ragai_config.json

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

---

## 32. Job Manager & Crash Recovery System

`job_manager.py` ensures the pipeline runs reliably for long periods without manual supervision.

### Job Statuses

| Status | Meaning |
|--------|---------|
| `pending` | Queued, not yet started |
| `processing` | Generation actively running |
| `completed` | Video verified and saved |
| `failed` | Generation failed |

### File Lock Mechanism

During generation, a `generation.lock` file is written inside the output folder. The watcher skips any folder containing this lock. Lock is removed after successful completion.

### Crash Recovery

On scheduler startup, `job_manager.startup_recovery()` runs automatically:
- Scans for any job with `status: processing`
- If `video.mp4` exists and is valid → marks `completed`
- If output is missing → marks `failed`, prepends topic back to queue
- Max retries: 2

---

## 33. Scheduler — Automated Topic Queue

`scheduler.py` reads topics from `topics_queue.json` and runs RAGAI generation automatically.

```cmd
# Run continuously (default 5-min interval)
python scheduler.py

# Run once (process one topic and exit)
python scheduler.py --once

# Custom interval
python scheduler.py --interval 300

# Crash recovery only
python scheduler.py --recover-only
```

Or double-click `START_SCHEDULER.bat`.

---

## 34. Complete Project Structure Reference (v7.4)

```
ragai/
├── Core Pipeline
│   ├── ragai.py, config.py, models.py, pipeline.py
│   ├── story_generator.py, image_generator.py
│   ├── voice_synthesizer.py, video_assembler.py (v8.0)
│   ├── style_detector.py (FFmpeg 8.x), audio_transcriber.py
│   ├── image_importer.py (original quality), music_selector.py
├── Content Intelligence
│   ├── topic_quality_engine.py, engagement_predictor.py
│   ├── narrative_variation_engine.py, visual_variation_engine.py
│   ├── content_variation_engine.py, story_archive.py
│   ├── thumbnail_ab_tester.py
├── Intelligence Layer
│   ├── language_engine.py, story_knowledge_graph.py
│   ├── scene_composer.py, style_engine.py
│   ├── emotion_detector.py, render_optimizer.py
│   ├── qa_engine.py, prompt_optimizer.py
├── Flexible Input Modes
│   ├── manual_topic_loader.py, script_loader.py
│   ├── mic_narration_recorder.py, audio_sync_engine.py
├── Cinematic Prompt Engine
│   ├── cinematic_prompt_engine.py, character_anchor_engine.py
│   ├── location_anchor_engine.py, prompt_template_builder.py
├── Character Reference System
│   ├── character_profile_generator.py
│   ├── character_reference_manager.py, reference_prompt_engine.py
├── Editor V2
│   ├── editor.py, editor_gui.py, editor_config.py
│   ├── clip_manager.py, watcher.py, timeline.py
│   ├── assembler.py, auto_pipeline.py, topic_engine.py
│   ├── hook_generator.py, outro_generator.py
│   ├── variation_engine.py, thumbnail_generator.py
├── Automation
│   ├── job_manager.py, scheduler.py
├── Analytics
│   ├── analytics_engine.py, retention_optimizer.py
│   ├── channel_manager.py, shorts_generator.py
│   ├── title_generator.py, viral_scorer.py, trend_fetcher.py
├── Folders
│   ├── output/    compiled/    characters/
│   ├── narrations/    scripts/    music/
│   ├── logs/    tmp/
```

---

## 35. Rebuild on New System — Complete Checklist

### Step 1 — Install Tools
- [ ] Python 3.11 or 3.12 — check "Add to PATH"
- [ ] Git
- [ ] FFmpeg **8.x** from gyan.dev → extract to `C:\ffmpeg\` → add `C:\ffmpeg\bin` to PATH
- [ ] VS Code + Python extension

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
```cmd
# RAGAI Video Factory
START_RAGAI.bat

# RAGAI Editor V2
START_EDITOR.bat

# Automated Scheduler
START_SCHEDULER.bat
```

---

## 36. How to Ask Kiro to Rebuild RAGAI on a New System

```
You are rebuilding the RAGAI Video Factory system on a new Windows machine.

The full system consists of:
1. RAGAI Video Factory (ragai.py) — AI video generation pipeline
2. RAGAI Editor V2 (editor.py) — compilation editor
3. Job Manager (job_manager.py) — crash recovery system
4. Scheduler (scheduler.py) — automated topic queue

Tech stack:
- Python 3.11+, Windows 11, Intel Arc 140V GPU (QSV + OpenVINO)
- FFmpeg 8.x with QSV support (REQUIRED — 8.x only)
- Groq API (story + transcription), Leonardo AI (images), Edge-TTS (voice)
- Tkinter GUI, watchdog, Pillow, numpy, pydub

Please:
1. Read RAGAI_SOP.md completely
2. Recreate all Python modules as documented in Section 34
3. Recreate all .bat launchers
4. Recreate requirements.txt
5. Do NOT recreate .env (user will fill in API keys)
6. Verify with: python ragai.py --diagnose

IMPORTANT v8.0 requirements:
- video_assembler.py must use contain+blur Ken Burns (not cover scale)
- style_detector.py must use rs/gs/bs/rm/gm/bm for colorbalance (not ss/sm/sh)
- BGM mix must use loudnorm + amix normalize=0 + aresample=44100
- image_importer.py must NOT force-resize images (preserve original quality)
```

---

## 37. Content Intelligence Layer (v7.0)

### 37.1 Topic Quality Engine — `topic_quality_engine.py`

Scores every topic before spending any API credits.

| Dimension | Weight | Description |
|-----------|--------|-------------|
| Emotion | 30% | Emotional resonance keywords |
| Curiosity | 20% | Mystery/surprise triggers |
| Relatability | 30% | Family/village/struggle themes |
| Popularity | 20% | Trending keyword match |

Topics below score 2.0 are skipped automatically.

### 37.2 Engagement Predictor — `engagement_predictor.py`

Predicts CTR and watch time before generation. Output:
```json
{ "predicted_ctr": 7.87, "predicted_watch_minutes": 5.31, "should_generate": true }
```

### 37.3 Narrative Variation Engine — `narrative_variation_engine.py`

Rotates through 5 narrative structures: Hero's Journey, Mystery Reveal, Conflict Resolution, Character Twist, Investigation.

### 37.4 Story Archive — `story_archive.py`

SQLite database tracking all generated stories. Uses Jaccard similarity to detect duplicate topics.

---

## 38. Thumbnail A/B Testing — `thumbnail_ab_tester.py`

Generates 3 thumbnail variants (A, B, C) per video. Tracks CTR via Wilson lower-bound scoring. Auto-selects winner after 50+ impressions.

```
output/video_YYYYMMDD_HHMMSS/
├── video.mp4
├── thumbnail_A.jpg
├── thumbnail_B.jpg
├── thumbnail_C.jpg
└── metadata.txt
```

---

## 39. Performance Layer

### Parallel Scene Executor — `scene_parallel_executor.py`

Processes image generation, voice synthesis, and clip encoding concurrently using `ThreadPoolExecutor` with 4 workers. Reduces generation time by ~50–70%.

### Video Assembler (v8.0) — `video_assembler.py`

- Pipe-based Ken Burns (no PNG frame dump) — ~60–70% faster scene encoding
- Intel QSV hardware encoding with automatic fallback to libx264
- Contain+blur approach — full image visible, no distortion
- Safe pan zones — Ken Burns stays within image content
- BGM: loudnorm + stereo 44.1kHz mix

---

## 40. Intelligence Layer (v7.1)

### Language Engine — `language_engine.py`

Detects language from Unicode script ranges. Supports 11 languages including English.

### Story Knowledge Graph — `story_knowledge_graph.py`

SQLite database storing topic, characters, locations, themes per story. Semantic similarity search prevents story repetition.

### Render Optimizer — `render_optimizer.py`

Probes FFmpeg for NVENC/QSV/VAAPI GPU encoders. Encoder priority: NVENC → QSV → VAAPI → libx264.

### QA Engine — `qa_engine.py`

ffprobe-based validation of scene clips and final output. Checks duration, audio stream, file size.

---

## 41. Flexible Input Modes (v7.2)

### Manual Topic Loader — `manual_topic_loader.py`

Load topics from `topics_manual.txt` (one per line). Priority over auto-discovered topics.

### Microphone Narration Recorder — `mic_narration_recorder.py`

Records microphone input, saves normalized WAV to `narrations/`. Bypasses voice synthesizer when narration exists.

```cmd
pip install sounddevice scipy
```

### Audio Sync Engine — `audio_sync_engine.py`

Maps a single narration WAV to multiple scenes using word-count-weighted distribution.

---

## 42. Cinematic Prompt Engine (v7.3)

Transforms plain scene descriptions into rich cinematic prompts. Zero additional API calls.

**Shot types:** cinematic wide shot, dramatic close-up, low-angle cinematic shot, over-the-shoulder shot, cinematic aerial view, tracking shot perspective

**Lighting styles:** golden hour, soft morning light, dramatic sunset, warm cinematic, diffused cloudy daylight, moody night

**Quality suffix:** `cinematic storytelling, ultra realistic, film still, shallow depth of field, 4k`

---

## 43. Character Reference System (v7.4)

Generates one portrait image per character and reuses it across all scenes for visual consistency.

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
image_generator               ← scene images with character consistency
```

---

## 44. Advanced Configuration Reference — ragai_advanced_config.json

```json
{
  "enable_language_engine": true,
  "enable_story_knowledge_graph": true,
  "enable_scene_composer": true,
  "enable_emotion_detection": true,
  "enable_render_optimizer": true,
  "enable_qa_engine": true,
  "enable_prompt_optimizer": true,
  "enable_manual_topic_mode": true,
  "enable_cinematic_prompt_engine": true,
  "enable_character_anchor": true,
  "enable_location_anchor": true,
  "enable_character_reference_system": true,
  "enable_reference_conditioning": true
}
```

Set any flag to `false` to disable that feature — system reverts to original behaviour.

---

## 45. Complete Project Structure Reference (v8.0)

```
ragai/
│
├── Core Pipeline (v8.0 updated)
│   ├── ragai.py                    Entry point — GUI/CLI dispatch
│   ├── config.py                   .env loading and AppConfig dataclass
│   ├── models.py                   All enums, dataclasses, constants, exceptions
│   ├── pipeline.py                 5-stage pipeline orchestrator
│   ├── story_generator.py          Stage 2 — Groq LLaMA story/scene generation
│   ├── image_generator.py          Stage 3 — 4-provider image chain
│   ├── voice_synthesizer.py        Stage 4 — Edge-TTS / gTTS (11 languages)
│   ├── video_assembler.py          Stage 5 — v8.0: contain+blur KB, safe pan, BGM fix
│   ├── style_detector.py           v8.0: FFmpeg 8.x colorbalance (rs/gs/bs)
│   ├── audio_transcriber.py        Groq Whisper transcription + audio splitting
│   ├── image_importer.py           v8.0: original quality preserved, no forced resize
│   ├── music_selector.py           BGM selection by style + keyword scoring
│
├── Content Intelligence
│   ├── topic_quality_engine.py, engagement_predictor.py
│   ├── narrative_variation_engine.py, visual_variation_engine.py
│   ├── content_variation_engine.py, story_archive.py
│   ├── thumbnail_ab_tester.py
│
├── Intelligence Layer
│   ├── language_engine.py, story_knowledge_graph.py
│   ├── scene_composer.py, style_engine.py
│   ├── emotion_detector.py, render_optimizer.py
│   ├── qa_engine.py, prompt_optimizer.py
│
├── Flexible Input Modes
│   ├── manual_topic_loader.py, script_loader.py
│   ├── mic_narration_recorder.py, audio_sync_engine.py
│
├── Cinematic Prompt Engine
│   ├── cinematic_prompt_engine.py, character_anchor_engine.py
│   ├── location_anchor_engine.py, prompt_template_builder.py
│
├── Character Reference System
│   ├── character_profile_generator.py
│   ├── character_reference_manager.py, reference_prompt_engine.py
│
├── Performance
│   ├── scene_parallel_executor.py
│
├── Editor V2
│   ├── editor.py, editor_gui.py, editor_config.py
│   ├── clip_manager.py, watcher.py, timeline.py
│   ├── assembler.py, auto_pipeline.py, topic_engine.py
│   ├── hook_generator.py, outro_generator.py
│   ├── variation_engine.py, thumbnail_generator.py
│
├── Automation
│   ├── job_manager.py, scheduler.py
│
├── Analytics
│   ├── analytics_engine.py, retention_optimizer.py
│   ├── channel_manager.py, shorts_generator.py
│   ├── title_generator.py, viral_scorer.py, trend_fetcher.py
│
├── Config Files
│   ├── ragai_advanced_config.json, ragai_config.json
│   ├── channel_styles.json, characters.json
│   ├── topics_queue.json, topics_manual.txt
│
├── Folders
│   ├── output/        compiled/      characters/
│   ├── narrations/    scripts/       music/
│   ├── logs/          tmp/
```

---

## 46. v8.0 Bug Fixes & Technical Changes

This section documents all fixes applied in v8.0 (April 2026).

### Fix 1 — FFmpeg 8.x colorbalance Parameter Names

**File:** `style_detector.py`

**Problem:** FFmpeg 8.x removed the old short parameter names (`ss`, `sm`, `sh`, `ms`, `mm`, `mh`) from the `colorbalance` filter. Any video using `MYSTERY_DARK` or `ROMANTIC_DRAMA` style would fail with:
```
Error applying option 'ss' to filter 'colorbalance': Option not found
```

**Fix:** Replaced with correct FFmpeg 8.x parameter names:
- `ss` (shadows) → `rs`, `gs`, `bs` (per channel)
- `sm` (midtones) → `rm`, `gm`, `bm`
- `sh` (highlights) → `rh`, `gh`, `bh`

**Affected styles:** MYSTERY_DARK, ROMANTIC_DRAMA

---

### Fix 2 — Background Music Inaudible

**File:** `video_assembler.py` → `_mix_music()`

**Problem:** The TTS voice is mono 24kHz. The music is stereo 44.1kHz. Without explicit resampling, `amix` used the first input's format (mono 24kHz), downmixing the music to near-inaudible levels. Additionally, `amix` with default `normalize=1` halved the output volume.

**Root cause chain:**
1. Voice: mono 24kHz (Edge-TTS output)
2. Music: stereo 44.1kHz (mp3 files)
3. Old `amix` without resampling → music downsampled to mono 24kHz at 0.25 volume
4. `amix normalize=1` (default) → divides output by 2 → -6dB quieter
5. `loudnorm` filter outputs at 96kHz by default → some players can't decode

**Fix:**
```python
# Voice: normalize to -16 LUFS broadcast standard
[0:a]aresample=44100,aformat=channel_layouts=stereo,loudnorm=I=-16:TP=-1.5:LRA=11[avoice]
# Music: resample to 44.1kHz stereo, set -8dB below voice
[1:a]aloop=loop=-1:size=2e+09,aresample=44100,aformat=channel_layouts=stereo,volume=-8dB,...[amusic]
# Mix: normalize=0 preserves set levels, force 44100 output
[avoice][amusic]amix=inputs=2:duration=first:normalize=0,aresample=44100[aout]
```

**Result:** Voice at -16 LUFS (clear), music at -24 LUFS (audible background), output stereo 44.1kHz AAC.

---

### Fix 3 — Image Distortion (Squish/Stretch)

**Files:** `image_importer.py`, `video_assembler.py`

**Problem 1 — image_importer.py:** `img.resize((width, height))` forced every image to the target dimensions regardless of original aspect ratio. A portrait photo (0.75 ratio) got squashed into landscape (1.75 ratio) — 2.3x horizontal squish.

**Fix:** Images are now saved as-is (original resolution, RGB PNG). No forced resize at import.

**Problem 2 — video_assembler.py Ken Burns:** The scale factor was `max(W_out/img.width, H_out/img.height) * KEN_BURNS_ZOOM_MAX * 1.05` — the extra 1.05 caused over-scaling. The crop used `src_w/zoom × src_h/zoom` which inherited the source's aspect ratio instead of the output's, causing stretch when resizing to `(W_out, H_out)`.

**Fix:** 
- Scale: `max(W_out/img.width, H_out/img.height) * KEN_BURNS_ZOOM_MAX * 1.02` (minimal safety margin)
- Crop: `W_out/zoom × H_out/zoom` — always matches output aspect ratio exactly

---

### Fix 4 — Portrait Image Cropping (Head/Feet Cut Off)

**File:** `video_assembler.py`

**Problem:** The Ken Burns `cover` scale (`max`) crops portrait images when placed in landscape output. A 3024×4032 portrait in 1920×1080 landscape would have the top and bottom cut off.

**Fix:** Switched to `contain` scale (`min`) with blurred background:
1. `contain_scale = min(W_out/img.width, H_out/img.height)` — fits entire image
2. Blurred version of image fills letterbox/pillarbox bars
3. Canvas scaled up by `KEN_BURNS_ZOOM_MAX * 1.02` for zoom headroom
4. `_safe_center()` function ensures Ken Burns pan stays within image content area

**Result:** Full person visible (head to toe), blurred background on sides, Ken Burns zooms into the subject.

---

### Fix 5 — Ken Burns Panning Into Blurred Background

**File:** `video_assembler.py`

**Problem:** After the contain+blur fix, the Ken Burns pan directions (8 fixed directions) could pan to the edges of the scaled canvas, which showed the blurred background instead of the image content.

**Fix:** `_safe_center()` function computes safe pan range:
- Calculates content bounds in the scaled canvas
- If content is narrower than crop window (portrait in landscape) → centers crop on content, no horizontal pan
- If content is taller than crop window → allows vertical pan within content bounds
- Pan start/end positions are constrained to the safe range

---

*RAGAI Video Factory v8.0 — AI-powered cinematic video generation with full image quality preservation and proper BGM mixing.*
*Built by Kunal with Kiro | April 2026*
