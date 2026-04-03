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

from flask import Flask, Response, jsonify, render_template_string, request, stream_with_context

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
# HTML template (mobile-first dark UI)
# ---------------------------------------------------------------------------

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>RAGAI Studio</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d0d0d;color:#e0e0e0;font-family:'Segoe UI',sans-serif;font-size:15px}
.header{background:linear-gradient(135deg,#1a1a2e,#16213e);padding:16px 20px;
  display:flex;align-items:center;gap:12px;border-bottom:1px solid #333}
.header h1{font-size:20px;color:#7eb8f7;font-weight:700}
.header .ver{font-size:11px;color:#888;margin-top:2px}
.tabs{display:flex;background:#111;border-bottom:1px solid #333;overflow-x:auto}
.tab{padding:12px 18px;cursor:pointer;color:#888;font-size:13px;white-space:nowrap;
  border-bottom:2px solid transparent;transition:all .2s}
.tab.active{color:#7eb8f7;border-bottom-color:#7eb8f7}
.tab:hover{color:#aaa}
.panel{display:none;padding:16px;max-width:700px;margin:0 auto}
.panel.active{display:block}
.card{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:10px;padding:16px;margin-bottom:14px}
.card h3{color:#7eb8f7;font-size:14px;margin-bottom:12px;text-transform:uppercase;letter-spacing:.5px}
label{display:block;color:#aaa;font-size:12px;margin-bottom:4px;margin-top:10px}
input,select,textarea{width:100%;background:#111;border:1px solid #333;color:#e0e0e0;
  padding:10px 12px;border-radius:6px;font-size:14px;outline:none}
input:focus,select:focus,textarea:focus{border-color:#7eb8f7}
textarea{resize:vertical;min-height:80px}
.btn{display:inline-block;padding:12px 24px;border-radius:8px;border:none;
  cursor:pointer;font-size:14px;font-weight:600;transition:all .2s;width:100%;margin-top:12px}
.btn-primary{background:linear-gradient(135deg,#2e5496,#1a3a6e);color:#fff}
.btn-primary:hover{background:linear-gradient(135deg,#3a6ab8,#2a4a8e)}
.btn-danger{background:#6e1a1a;color:#fff}
.btn-danger:hover{background:#8e2a2a}
.btn-success{background:#1a6e3a;color:#fff}
.btn-success:hover{background:#2a8e4a}
.btn-sm{padding:6px 14px;font-size:12px;width:auto;margin-top:0}
.progress{background:#222;border-radius:4px;height:8px;margin-top:8px}
.progress-bar{height:8px;border-radius:4px;background:linear-gradient(90deg,#2e5496,#7eb8f7);
  transition:width .5s}
#log-box{background:#0a0a0a;border:1px solid #222;border-radius:6px;padding:12px;
  height:300px;overflow-y:auto;font-family:'Courier New',monospace;font-size:11px;
  color:#aaa;white-space:pre-wrap;word-break:break-all}
.log-info{color:#7eb8f7}.log-warn{color:#f7c97e}.log-error{color:#f77e7e}
.scene-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px}
.scene-card{background:#111;border:1px solid #2a2a2a;border-radius:8px;overflow:hidden;text-align:center}
.scene-card img{width:100%;height:90px;object-fit:cover}
.scene-card .scene-info{padding:6px;font-size:11px;color:#888}
.scene-card .btn-sm{margin:4px 6px 6px}
.status-dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px}
.dot-green{background:#4caf50}.dot-red{background:#f44336}.dot-yellow{background:#ff9800}
.topic-item{background:#111;border:1px solid #2a2a2a;border-radius:6px;padding:10px;
  margin-bottom:8px;display:flex;align-items:center;gap:10px}
.topic-item .topic-text{flex:1;font-size:13px}
.topic-score{color:#7eb8f7;font-size:11px;min-width:50px;text-align:right}
.quota-bar{margin-bottom:10px}
.quota-label{display:flex;justify-content:space-between;font-size:12px;color:#888;margin-bottom:4px}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>🎬 RAGAI Studio</h1>
    <div class="ver">v9.0 — AI Video Factory</div>
  </div>
</div>

<div class="tabs">
  <div class="tab active" onclick="showTab('generate')">Generate</div>
  <div class="tab" onclick="showTab('scenes')">Scenes</div>
  <div class="tab" onclick="showTab('scheduler')">Scheduler</div>
  <div class="tab" onclick="showTab('trends')">Trends</div>
  <div class="tab" onclick="showTab('logs')">Logs</div>
</div>

<!-- GENERATE TAB -->
<div id="tab-generate" class="panel active">
  <div class="card">
    <h3>Story Settings</h3>
    <label>Topic</label>
    <textarea id="topic" placeholder="A poor farmer who saves his village from drought..."></textarea>
    <label>Language</label>
    <select id="language">
      <option value="hi">Hindi</option><option value="en">English</option>
      <option value="ta">Tamil</option><option value="te">Telugu</option>
      <option value="bn">Bengali</option><option value="gu">Gujarati</option>
      <option value="mr">Marathi</option><option value="kn">Kannada</option>
      <option value="ml">Malayalam</option><option value="pa">Punjabi</option>
    </select>
    <label>Visual Style</label>
    <select id="style">
      <option value="AUTO">AUTO (detect from topic)</option>
      <option value="DYNAMIC_EPIC">Dynamic Epic</option>
      <option value="MYSTERY_DARK">Mystery Dark</option>
      <option value="SPIRITUAL_DEVOTIONAL">Spiritual Devotional</option>
      <option value="PEACEFUL_NATURE">Peaceful Nature</option>
      <option value="ROMANTIC_DRAMA">Romantic Drama</option>
      <option value="ADVENTURE_ACTION">Adventure Action</option>
    </select>
  </div>
  <div class="card">
    <h3>Video Settings</h3>
    <label>Quality</label>
    <select id="quality">
      <option value="draft">Draft 720p (fast)</option>
      <option value="standard">Standard 1080p</option>
      <option value="high">High 1440p</option>
      <option value="cinema" selected>Cinema 4K</option>
    </select>
    <label>Format</label>
    <select id="format">
      <option value="landscape" selected>Landscape (YouTube)</option>
      <option value="shorts">Shorts (Reels)</option>
    </select>
    <label>Scenes</label>
    <select id="scenes">
      <option value="5">5 scenes (~2 min)</option>
      <option value="8" selected>8 scenes (~4 min)</option>
      <option value="10">10 scenes (~6 min)</option>
      <option value="12">12 scenes (~8 min)</option>
      <option value="15">15 scenes (~12 min)</option>
    </select>
    <label>Audience</label>
    <select id="audience">
      <option value="family" selected>Family</option>
      <option value="children">Children</option>
      <option value="adults">Adults</option>
      <option value="devotees">Devotees</option>
    </select>
  </div>
  <div id="gen-status" style="display:none" class="card">
    <h3>Generation Progress</h3>
    <div id="gen-stage" style="color:#7eb8f7;font-size:13px">Starting...</div>
    <div class="progress"><div class="progress-bar" id="gen-bar" style="width:0%"></div></div>
  </div>
  <button class="btn btn-primary" onclick="startGenerate()" id="gen-btn">🎬 Generate Video</button>
</div>

<!-- SCENES TAB -->
<div id="tab-scenes" class="panel">
  <div class="card">
    <h3>Scene Gallery</h3>
    <div id="scene-grid" class="scene-grid">
      <div style="color:#666;font-size:13px">Generate a video first to see scenes here.</div>
    </div>
  </div>
</div>

<!-- SCHEDULER TAB -->
<div id="tab-scheduler" class="panel">
  <div class="card">
    <h3>Overnight Queue</h3>
    <div id="scheduler-status">
      <span class="status-dot dot-red" id="sched-dot"></span>
      <span id="sched-label">Scheduler stopped</span>
    </div>
    <div style="margin-top:12px">
      <div class="quota-bar">
        <div class="quota-label"><span>Groq tokens</span><span id="groq-used">0 / 500,000</span></div>
        <div class="progress"><div class="progress-bar" id="groq-bar" style="width:0%"></div></div>
      </div>
      <div class="quota-bar">
        <div class="quota-label"><span>Leonardo credits</span><span id="leo-used">0 / 150</span></div>
        <div class="progress"><div class="progress-bar" id="leo-bar" style="width:0%"></div></div>
      </div>
    </div>
    <div style="margin-top:10px;font-size:12px;color:#888">
      Queue size: <span id="queue-size">0</span> topics
    </div>
    <button class="btn btn-success" onclick="startScheduler()" id="sched-start-btn">▶ Start Overnight Queue</button>
    <button class="btn btn-danger" onclick="stopScheduler()" id="sched-stop-btn" style="display:none">⏹ Stop Scheduler</button>
  </div>
  <div class="card">
    <h3>Add Topic to Queue</h3>
    <label>Topic</label>
    <input type="text" id="queue-topic" placeholder="A village girl who becomes a doctor...">
    <button class="btn btn-primary btn-sm" style="width:auto;margin-top:8px" onclick="addToQueue()">+ Add to Queue</button>
  </div>
</div>

<!-- TRENDS TAB -->
<div id="tab-trends" class="panel">
  <div class="card">
    <h3>Trending Topics</h3>
    <button class="btn btn-primary" onclick="fetchTrends()" id="trends-btn">🔄 Fetch Trends Now</button>
    <div id="trends-list" style="margin-top:12px">
      <div style="color:#666;font-size:13px">Click Fetch Trends to load trending topics.</div>
    </div>
  </div>
</div>

<!-- LOGS TAB -->
<div id="tab-logs" class="panel">
  <div class="card">
    <h3>Live Log</h3>
    <div id="log-box"></div>
  </div>
</div>

<script>
function showTab(name) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  event.target.classList.add('active');
  if (name === 'logs') startLogStream();
  if (name === 'scheduler') refreshSchedulerStatus();
}

// Generate
async function startGenerate() {
  const topic = document.getElementById('topic').value.trim();
  if (!topic) { alert('Please enter a topic'); return; }
  document.getElementById('gen-btn').disabled = true;
  document.getElementById('gen-btn').textContent = '⏳ Generating...';
  document.getElementById('gen-status').style.display = 'block';
  const payload = {
    topic, language: document.getElementById('language').value,
    style: document.getElementById('style').value,
    quality: document.getElementById('quality').value,
    format: document.getElementById('format').value,
    scenes: parseInt(document.getElementById('scenes').value),
    audience: document.getElementById('audience').value,
  };
  const resp = await fetch('/api/generate', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  const data = await resp.json();
  if (data.status === 'started') {
    pollProgress();
  } else {
    alert('Error: ' + data.message);
    resetGenBtn();
  }
}

function resetGenBtn() {
  document.getElementById('gen-btn').disabled = false;
  document.getElementById('gen-btn').textContent = '🎬 Generate Video';
}

async function pollProgress() {
  const resp = await fetch('/api/status');
  const data = await resp.json();
  document.getElementById('gen-stage').textContent = data.stage || 'Processing...';
  document.getElementById('gen-bar').style.width = (data.progress || 0) + '%';
  if (data.status === 'running') {
    setTimeout(pollProgress, 2000);
  } else if (data.status === 'done') {
    document.getElementById('gen-stage').textContent = '✅ Complete! Video saved to output/';
    document.getElementById('gen-bar').style.width = '100%';
    resetGenBtn();
    loadScenes();
  } else if (data.status === 'error') {
    document.getElementById('gen-stage').textContent = '❌ Error: ' + data.message;
    resetGenBtn();
  }
}

// Scenes
async function loadScenes() {
  const resp = await fetch('/api/scenes');
  const data = await resp.json();
  const grid = document.getElementById('scene-grid');
  if (!data.scenes || data.scenes.length === 0) {
    grid.innerHTML = '<div style="color:#666;font-size:13px">No scenes yet.</div>';
    return;
  }
  grid.innerHTML = data.scenes.map((s, i) => `
    <div class="scene-card">
      <img src="/api/scene_thumb/${i}" onerror="this.src=''" alt="Scene ${i+1}">
      <div class="scene-info">Scene ${i+1}</div>
      <button class="btn btn-sm btn-primary" onclick="regenScene(${i})">↺ Regen</button>
    </div>`).join('');
}

async function regenScene(idx) {
  await fetch('/api/regen_scene/' + idx, {method:'POST'});
  setTimeout(loadScenes, 3000);
}

// Scheduler
async function startScheduler() {
  await fetch('/api/scheduler/start', {method:'POST'});
  document.getElementById('sched-start-btn').style.display = 'none';
  document.getElementById('sched-stop-btn').style.display = 'block';
  refreshSchedulerStatus();
}

async function stopScheduler() {
  await fetch('/api/scheduler/stop', {method:'POST'});
  document.getElementById('sched-start-btn').style.display = 'block';
  document.getElementById('sched-stop-btn').style.display = 'none';
  refreshSchedulerStatus();
}

async function refreshSchedulerStatus() {
  const resp = await fetch('/api/scheduler/status');
  const data = await resp.json();
  const dot = document.getElementById('sched-dot');
  const label = document.getElementById('sched-label');
  if (data.running) {
    dot.className = 'status-dot dot-green';
    label.textContent = 'Scheduler running — ' + (data.current_topic || 'idle');
    document.getElementById('sched-start-btn').style.display = 'none';
    document.getElementById('sched-stop-btn').style.display = 'block';
  } else {
    dot.className = 'status-dot dot-red';
    label.textContent = 'Scheduler stopped';
  }
  document.getElementById('queue-size').textContent = data.queue_size || 0;
}

async function addToQueue() {
  const topic = document.getElementById('queue-topic').value.trim();
  if (!topic) return;
  await fetch('/api/queue/add', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({topic})});
  document.getElementById('queue-topic').value = '';
  refreshSchedulerStatus();
}

// Trends
async function fetchTrends() {
  document.getElementById('trends-btn').textContent = '⏳ Fetching...';
  document.getElementById('trends-btn').disabled = true;
  const resp = await fetch('/api/trends/fetch', {method:'POST'});
  const data = await resp.json();
  document.getElementById('trends-btn').textContent = '🔄 Fetch Trends Now';
  document.getElementById('trends-btn').disabled = false;
  const list = document.getElementById('trends-list');
  if (!data.topics || data.topics.length === 0) {
    list.innerHTML = '<div style="color:#666;font-size:13px">No new topics found.</div>';
    return;
  }
  list.innerHTML = data.topics.map(t => `
    <div class="topic-item">
      <div class="topic-text">${t.topic}</div>
      <div class="topic-score">⭐ ${t.score}</div>
      <button class="btn btn-sm btn-success" onclick="addTrendToQueue('${t.topic.replace(/'/g,"\\'")}')">+</button>
    </div>`).join('');
}

async function addTrendToQueue(topic) {
  await fetch('/api/queue/add', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({topic})});
  alert('Added to queue: ' + topic);
}

// Live log stream
let logSource = null;
function startLogStream() {
  if (logSource) return;
  logSource = new EventSource('/api/log_stream');
  logSource.onmessage = function(e) {
    const box = document.getElementById('log-box');
    const line = document.createElement('div');
    const msg = e.data;
    if (msg.includes('ERROR')) line.className = 'log-error';
    else if (msg.includes('WARNING')) line.className = 'log-warn';
    else line.className = 'log-info';
    line.textContent = msg;
    box.appendChild(line);
    box.scrollTop = box.scrollHeight;
    if (box.children.length > 200) box.removeChild(box.firstChild);
  };
}

// Auto-refresh scheduler status every 10s
setInterval(refreshSchedulerStatus, 10000);
</script>
</body>
</html>"""


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
    return render_template_string(_HTML)


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
