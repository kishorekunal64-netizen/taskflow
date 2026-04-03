"""
editor.py — Entry point for RAGAI Editor V2.

Responsibilities:
  1. Load ragai_config.json
  2. Load .env for Groq API key (needed for hook generation)
  3. Initialise ClipManager
  4. Start OutputWatcher
  5. Launch RAGAIEditorApp GUI
  6. Initialise AutoPipeline
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from log_setup import configure_logging
from editor_config import load_editor_config


def main():
    # ------------------------------------------------------------------ logging
    configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("RAGAI Editor V3 starting…")

    # ------------------------------------------------------------------ CLI args
    load_folder = ""
    if len(sys.argv) >= 3 and sys.argv[1] == "--load":
        load_folder = sys.argv[2]
        logger.info("Load folder: %s", load_folder)

    # ------------------------------------------------------------------ config
    cfg = load_editor_config()
    output_dir   = Path(cfg["output_dir"])
    compiled_dir = Path(cfg["compiled_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    compiled_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ API key (optional — for hook)
    groq_api_key = ""
    try:
        from dotenv import dotenv_values
        env = dotenv_values(".env")
        groq_api_key = env.get("GROQ_API_KEY", "")
        if groq_api_key:
            logger.info("Groq API key loaded — hook generation enabled")
        else:
            logger.info("No GROQ_API_KEY in .env — hook generation will use fallback text")
    except Exception as exc:
        logger.warning("Could not load .env: %s", exc)

    # ------------------------------------------------------------------ FFmpeg check
    import shutil
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    if not ffmpeg_ok:
        local = Path("ffmpeg-8.1-essentials_build") / "bin" / "ffmpeg.exe"
        ffmpeg_ok = local.exists()
    if not ffmpeg_ok:
        logger.warning(
            "FFmpeg not found on PATH. Export will be disabled.\n"
            "Install FFmpeg: https://ffmpeg.org/download.html"
        )

    # ------------------------------------------------------------------ ClipManager
    from clip_manager import ClipManager
    ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
    clip_manager = ClipManager(ffmpeg_path=ffmpeg_bin)
    logger.info("ClipManager ready — %d clips in library", len(clip_manager.get_all()))

    # ------------------------------------------------------------------ GUI
    try:
        from editor_gui import RAGAIEditorApp
        app = RAGAIEditorApp(
            clip_manager=clip_manager,
            output_dir=output_dir,
            compiled_dir=compiled_dir,
            groq_api_key=groq_api_key,
            cfg=cfg,
            load_folder=load_folder,
        )
        app.protocol("WM_DELETE_WINDOW", app.on_close)
        logger.info("GUI launched")
        app.mainloop()
    except KeyboardInterrupt:
        logger.info("Editor closed by user")
    except Exception as exc:
        logger.exception("Fatal error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
