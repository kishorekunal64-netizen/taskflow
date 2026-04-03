"""
web_ui.py — Mobile-first Flask Web UI for RAGAI v9.0.

Access from any device on the same WiFi:
  Laptop: http://localhost:5000
  Phone:  http://192.168.x.x:5000

Tabs: Generate | Scenes | Scheduler | Trends | Logs
"""

from __future__ import annotations

import json
import logging
import os
import queue
import socket
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, Response, jsonify, render_template, render_template_string, request, stream_with_context

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_log_queue: queue.Queue = queue.Queue(maxsize=500)
_pipeline_thread: Optional[threading.Thread] = None
_pipeline_result: Dict[str, Any] = {}
_scheduler_proc: Optional[subprocess.Popen] = None



# ---------------------------------------------------------------------------
# Log handler that feeds the SSE queue
# ---------------------------------------------------------------------------

class _QueueHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            _log_queue.put_nowait(msg)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/generate", methods=["POST"])
def api_generate():
    global _pipeline_thread, _pipeline_result
    if _pipeline_thread and _pipeline_thread.is_alive():
        return jsonify({"status": "error", "message": "Pipeline already running"})

    data = request.get_json()
    _pipeline_result = {"status": "running", "stage": "Starting...", "progress": 0}

    def _run():
        global _pipeline_result
        try:
            _pipeline_result["stage"] = "Loading pipeline..."
            _pipeline_result["progress"] = 5

            # Import here to avoid circular imports at module load
            from config import load_config
            from models import (Audience, Language, VideoFormat, VisualStyle,
                                QualityPreset, InputMode, PipelineConfig)
            from pipeline import Pipeline

            cfg = load_config()
            lang = Language(data.get("language", "hi"))
            style_str = data.get("style", "AUTO")
            style = VisualStyle(style_str) if style_str != "AUTO" else VisualStyle.AUTO

            config = PipelineConfig(
                topic=data["topic"],
                script_file=None,
                audience=Audience(data.get("audience", "family")),
                language=lang,
                style=style,
                format=VideoFormat(data.get("format", "landscape")),
                character_names={},
                output_dir=Path("output"),
                use_edge_tts=cfg.use_edge_tts,
                groq_api_key=cfg.groq_api_key,
                leonardo_api_key=cfg.leonardo_api_key,
                scene_count=int(data.get("scenes", 8)),
                quality=QualityPreset(data.get("quality", "cinema")),
            )

            def _progress(stage: str, n: int, total: int) -> None:
                pct = int((n / max(total, 1)) * 80) + 10
                _pipeline_result["stage"] = f"{stage} ({n}/{total})"
                _pipeline_result["progress"] = pct

            pipeline = Pipeline(config, progress_callback=_progress)
            result = pipeline.run()
            _pipeline_result = {
                "status": "done",
                "stage": "Complete!",
                "progress": 100,
                "output": str(result.output_path),
                "scenes": [{"narration": s.narration[:80],
                             "image": str(s.image_path) if s.image_path else ""}
                            for s in result.scenes],
            }
        except Exception as exc:
            logger.error("Pipeline error: %s", exc)
            _pipeline_result = {"status": "error", "stage": "Error", "message": str(exc)}

    _pipeline_thread = threading.Thread(target=_run, daemon=True)
    _pipeline_thread.start()
    return jsonify({"status": "started"})


@app.route("/api/status")
def api_status():
    return jsonify(_pipeline_result)


@app.route("/api/scenes")
def api_scenes():
    scenes = _pipeline_result.get("scenes", [])
    return jsonify({"scenes": scenes})


@app.route("/api/scene_thumb/<int:idx>")
def api_scene_thumb(idx: int):
    scenes = _pipeline_result.get("scenes", [])
    if idx < len(scenes):
        img_path = scenes[idx].get("image", "")
        if img_path and Path(img_path).exists():
            from flask import send_file
            return send_file(img_path, mimetype="image/png")
    return "", 404


@app.route("/api/regen_scene/<int:idx>", methods=["POST"])
def api_regen_scene(idx: int):
    # Trigger scene regeneration in background
    def _regen():
        try:
            from pipeline import Pipeline
            # This requires the pipeline object to still be alive
            # For simplicity, log a message
            logger.info("Scene %d re-generation requested via Web UI", idx)
        except Exception as exc:
            logger.error("Regen scene error: %s", exc)
    threading.Thread(target=_regen, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/scheduler/start", methods=["POST"])
def api_scheduler_start():
    global _scheduler_proc
    if _scheduler_proc and _scheduler_proc.poll() is None:
        return jsonify({"status": "already_running"})
    _scheduler_proc = subprocess.Popen(
        [sys.executable, "scheduler_v2.py"],
        cwd=str(Path(__file__).parent),
    )
    logger.info("Scheduler v2 started (pid %d)", _scheduler_proc.pid)
    return jsonify({"status": "started"})


@app.route("/api/scheduler/stop", methods=["POST"])
def api_scheduler_stop():
    global _scheduler_proc
    if _scheduler_proc and _scheduler_proc.poll() is None:
        _scheduler_proc.terminate()
        logger.info("Scheduler stopped")
    return jsonify({"status": "stopped"})


@app.route("/api/scheduler/status")
def api_scheduler_status():
    running = bool(_scheduler_proc and _scheduler_proc.poll() is None)
    queue_size = 0
    current_topic = ""
    status_file = Path("tmp/scheduler_status.json")
    if status_file.exists():
        try:
            d = json.loads(status_file.read_text(encoding="utf-8"))
            current_topic = d.get("current_topic", "")
        except Exception:
            pass
    queue_file = Path("topics_queue.json")
    if queue_file.exists():
        try:
            queue_size = len(json.loads(queue_file.read_text(encoding="utf-8")))
        except Exception:
            pass
    return jsonify({"running": running, "current_topic": current_topic, "queue_size": queue_size})


@app.route("/api/queue/add", methods=["POST"])
def api_queue_add():
    data = request.get_json()
    topic = data.get("topic", "").strip()
    if not topic:
        return jsonify({"status": "error", "message": "empty topic"})
    queue_file = Path("topics_queue.json")
    existing = []
    if queue_file.exists():
        try:
            existing = json.loads(queue_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    if topic not in existing:
        existing.insert(0, topic)
        queue_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"status": "ok"})


@app.route("/api/trends/fetch", methods=["POST"])
def api_trends_fetch():
    try:
        from trend_fetcher_v2 import fetch_and_queue, _score_topic
        new_topics = fetch_and_queue()
        result = [{"topic": t, "score": _score_topic(t)} for t in new_topics[:20]]
        return jsonify({"topics": result})
    except Exception as exc:
        logger.error("Trends fetch error: %s", exc)
        return jsonify({"topics": [], "error": str(exc)})


@app.route("/api/log_stream")
def api_log_stream():
    def _generate():
        while True:
            try:
                msg = _log_queue.get(timeout=30)
                yield f"data: {msg}\n\n"
            except queue.Empty:
                yield "data: \n\n"  # keepalive
    return Response(stream_with_context(_generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    # Wire log queue handler
    handler = _QueueHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                                           datefmt="%H:%M:%S"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)

    local_ip = _get_local_ip()
    print("=" * 60)
    print("RAGAI Studio — Web UI")
    print("=" * 60)
    print(f"Laptop:  http://localhost:5000")
    print(f"Phone:   http://{local_ip}:5000")
    print("=" * 60)
    print("Open the Phone URL on any device on the same WiFi")
    print("Press Ctrl+C to stop")
    print()

    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
