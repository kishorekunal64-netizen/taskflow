"""
ragai.py — Entry point for RAGAI Video Factory.
"""

import argparse
import sys
from pathlib import Path

from log_setup import configure_logging
from config import load_config
from models import (
    Audience,
    ConfigError,
    InputMode,
    Language,
    PipelineConfig,
    VideoFormat,
    VisualStyle,
)
from pipeline import Pipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_char_names(raw: str) -> dict:
    result = {}
    for pair in raw.split(","):
        if "=" in pair:
            k, _, v = pair.partition("=")
            k, v = k.strip(), v.strip()
            if k and v:
                result[k] = v
    return result


def gui_main(app_config):
    from gui import RAGAIApp
    app = RAGAIApp(app_config)
    app.mainloop()


# ---------------------------------------------------------------------------
# CLI mode
# ---------------------------------------------------------------------------

def cli_main(args, app_config):
    # Determine input mode from new flags first
    input_mode = InputMode.TOPIC
    audio_file = None
    image_files = []
    image_context = getattr(args, "image_context", "") or ""

    if getattr(args, "audio_file", None):
        audio_path = Path(args.audio_file)
        if not audio_path.exists() or not audio_path.is_file():
            print(f"❌ Error: audio file not found or is not a file: {args.audio_file}")
            sys.exit(1)
        input_mode = InputMode.AUDIO
        audio_file = str(audio_path)

    elif getattr(args, "image_files", None):
        raw_paths = [p.strip() for p in args.image_files.split(",") if p.strip()]
        missing = [p for p in raw_paths if not Path(p).exists() or not Path(p).is_file()]
        if missing:
            print(f"❌ Error: the following image files were not found or are not files: {', '.join(missing)}")
            sys.exit(1)
        input_mode = InputMode.IMAGE
        image_files = raw_paths

    # Interactive prompt fallback when neither --topic nor --script-file given
    # (only applies to TOPIC/SCRIPT modes)
    topic = args.topic
    script_file = args.script_file

    if input_mode in (InputMode.TOPIC, InputMode.SCRIPT) and not topic and not script_file:
        while not topic:
            topic = input("Enter topic: ").strip()

        raw_audience = input("Audience [family/children/adults/devotees] (default: family): ").strip()
        raw_language = input("Language [hi/ta/te/bn/gu/mr/kn/ml/pa/ur] (default: hi): ").strip()
        raw_style = input(
            "Style [AUTO/DYNAMIC_EPIC/MYSTERY_DARK/SPIRITUAL_DEVOTIONAL/PEACEFUL_NATURE/"
            "ROMANTIC_DRAMA/ADVENTURE_ACTION] (default: AUTO): "
        ).strip()
        raw_format = input("Format [landscape/shorts] (default: landscape): ").strip()
        raw_output = input("Output directory (default: ./output): ").strip()

        args.audience = raw_audience or "family"
        args.language = raw_language or "hi"
        args.style = raw_style or "AUTO"
        args.format = raw_format or "landscape"
        args.output_dir = raw_output or "./output"

    output_dir = Path(args.output_dir or "./output")
    output_dir.mkdir(parents=True, exist_ok=True)

    char_names = _parse_char_names(args.character_names) if args.character_names else {}

    config = PipelineConfig(
        topic=topic or "",
        script_file=script_file,
        audience=Audience(args.audience or "family"),
        language=Language(args.language or "hi"),
        style=VisualStyle(args.style or "AUTO"),
        format=VideoFormat(args.format or "landscape"),
        character_names=char_names,
        output_dir=output_dir,
        use_edge_tts=app_config.use_edge_tts,
        groq_api_key=app_config.groq_api_key,
        leonardo_api_key=app_config.leonardo_api_key,
        input_mode=input_mode,
        audio_file=audio_file,
        image_files=image_files,
        image_context=image_context,
        hf_token=app_config.hf_token,
    )

    def progress_callback(stage: str, scene: int, total: int) -> None:
        print(f"\r[RAGAI] Stage: {stage}  Scene: {scene}/{total}", end="", flush=True)

    try:
        result = Pipeline(config, progress_callback).run()
        print(f"\n\n✅ Video saved to: {result.output_path.resolve()}\n")
        print(f"   Thumbnail : {result.thumbnail_path.resolve()}")
        print(f"   Metadata  : {result.metadata_txt_path.resolve()}\n")
    except Exception as exc:
        print(f"\n❌ Error: {exc}\n")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="ragai",
        description="RAGAI Video Factory — AI-powered video generation",
    )

    # Mode flags (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--cli", action="store_true", help="Run in CLI mode")
    mode_group.add_argument("--gui", action="store_true", help="Run in GUI mode (default)")
    mode_group.add_argument("--web", action="store_true", help="Run in web mode")

    # Content flags
    parser.add_argument("--topic", metavar="TEXT", help="Video topic")
    parser.add_argument("--script-file", metavar="PATH", help="Path to script file")
    parser.add_argument(
        "--audience",
        choices=["family", "children", "adults", "devotees"],
        default="family",
    )
    parser.add_argument(
        "--language",
        choices=["hi", "ta", "te", "bn", "gu", "mr", "kn", "ml", "pa", "ur"],
        default="hi",
    )
    parser.add_argument(
        "--style",
        choices=["AUTO", "DYNAMIC_EPIC", "MYSTERY_DARK", "SPIRITUAL_DEVOTIONAL",
                 "PEACEFUL_NATURE", "ROMANTIC_DRAMA", "ADVENTURE_ACTION"],
        default="AUTO",
    )
    parser.add_argument(
        "--format",
        choices=["landscape", "shorts"],
        default="landscape",
    )
    parser.add_argument(
        "--character-names",
        metavar="TEXT",
        help='Comma-separated "placeholder=name" pairs',
    )
    parser.add_argument("--output-dir", metavar="PATH", default="./output")

    # New input mode flags
    parser.add_argument("--audio-file", metavar="PATH", help="Path to an audio file for Audio Storytelling Input mode")
    parser.add_argument("--image-files", metavar="PATHS", help="Comma-separated list of image file paths for Image Upload mode")
    parser.add_argument("--image-context", metavar="TEXT", default="", help="Context/description text for Image Upload mode")

    # Utility flags
    parser.add_argument("--diagnose", action="store_true", help="Run diagnostics and exit")

    args = parser.parse_args()

    # Configure logging as early as possible
    configure_logging(level="INFO")

    # Diagnostics
    if args.diagnose:
        from ragai_diagnose import run_diagnostics
        run_diagnostics()
        sys.exit(0)

    # Load config
    try:
        app_config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}")
        sys.exit(1)

    # Dispatch
    if args.web:
        print("Web mode not yet implemented.")
        sys.exit(1)
    elif args.cli:
        cli_main(args, app_config)
    else:
        # GUI is the default (covers --gui and no mode flag)
        gui_main(app_config)


if __name__ == "__main__":
    main()
