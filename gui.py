"""
gui.py — RAGAI Video Factory — premium dark UI (v9).

Design:
  - Charcoal / near-black surfaces with subtle borders (no harsh wireframe lines)
  - Static hero header — white logotype, orange accent, calm typography
  - Generous padding, rounded progress tracks, soft elevation on cards
"""

from __future__ import annotations

import json
import logging
import math
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

RAGAI_VERSION = "9.0.0"

# Daily quota estimates (free tier) — aligned with scheduler_v2.py
_GROQ_DAILY = 500_000
_LEONARDO_DAILY = 150
_YT_UNITS_DAILY = 10_000
_GROQ_EST_PER_VIDEO = 50_000
_LEO_EST_PER_VIDEO = 16
_QUOTA_FILE = Path("tmp/ragai_quota.json")

from config import AppConfig
from models import (
    Audience, InputMode, Language, PipelineConfig, PipelineResult,
    QualityPreset, QUALITY_CONFIGS, VideoFormat, VisualStyle,
)
from pipeline import Pipeline

# Trend Booster — lazy imports (graceful if not installed)
try:
    from trend_fetcher import fetch_trends, generate_hashtags
    from viral_scorer import score_topic
    _TREND_BOOSTER_AVAILABLE = True
except ImportError:
    _TREND_BOOSTER_AVAILABLE = False

# ---------------------------------------------------------------------------
# Colour system — premium dark (charcoal + orange)
# ---------------------------------------------------------------------------
BG          = "#0d0d10"       # app background
BG_HEADER   = "#121214"       # hero bar (flat, no grain)
BG_ELEV     = "#16161c"       # raised cards / sidebar
BG2         = BG_ELEV
BG3         = "#1e1e26"       # inputs
BORDER      = "#2a2a34"       # hairline
BORDER_SOFT = "#25252e"
LINE        = "#1f1f28"       # separators

ACCENT      = "#ff5722"
ACCENT_DIM  = "#c43e1a"
CYAN        = "#26c6da"
MAGENTA     = "#e040fb"
ORANGE      = "#ff5722"
GREEN_N     = "#66bb6a"
PURPLE      = "#ab47bc"
YELLOW_N    = "#ffca28"

FG          = "#f0f2f5"
FG_MUTED    = "#9ca3af"
FG2         = "#a8b0bc"
FG3         = "#6b7280"

FONT_HERO   = ("Segoe UI", 24, "bold")
FONT_TITLE  = ("Segoe UI", 12, "bold")
FONT_LABEL  = ("Segoe UI", 10)
FONT_SMALL  = ("Segoe UI", 9)
FONT_MONO   = ("Consolas", 9)
FONT_BTN    = ("Segoe UI", 10, "bold")

# Quality card themes  (bg, border_glow, text)
_Q_THEME = {
    QualityPreset.DRAFT:    ("#0a1a2a", CYAN,     "⚡ Draft 720p"),
    QualityPreset.STANDARD: ("#0a2a1a", GREEN_N,  "📱 Standard 1080p"),
    QualityPreset.HIGH:     ("#1a1a0a", YELLOW_N, "🎬 High 1440p"),
    QualityPreset.CINEMA:   ("#2a0a1a", MAGENTA,  "🎥 4K Cinema"),
}
_Q_SPEC = {
    QualityPreset.DRAFT:    "fast · CRF 23 · 4 Mbps",
    QualityPreset.STANDARD: "medium · CRF 20 · 8 Mbps",
    QualityPreset.HIGH:     "slow · CRF 18 · 12 Mbps",
    QualityPreset.CINEMA:   "slow · CRF 16 · 20 Mbps",
}

_AUDIENCE_LABELS = {
    "Family": Audience.FAMILY, "Children": Audience.CHILDREN,
    "Adults": Audience.ADULTS, "Devotees": Audience.DEVOTEES,
}
_LANGUAGE_LABELS = {
    "Hindi": Language.HI, "Tamil": Language.TA, "Telugu": Language.TE,
    "Bengali": Language.BN, "Gujarati": Language.GU, "Marathi": Language.MR,
    "Kannada": Language.KN, "Malayalam": Language.ML,
    "Punjabi": Language.PA, "Urdu": Language.UR,
}
_STYLE_LABELS = {
    "✨ AUTO":                  VisualStyle.AUTO,
    "⚡ Dynamic Epic":          VisualStyle.DYNAMIC_EPIC,
    "🌑 Mystery Dark":          VisualStyle.MYSTERY_DARK,
    "🕉  Spiritual Devotional": VisualStyle.SPIRITUAL_DEVOTIONAL,
    "🌿 Peaceful Nature":       VisualStyle.PEACEFUL_NATURE,
    "💕 Romantic Drama":        VisualStyle.ROMANTIC_DRAMA,
    "🏔  Adventure Action":     VisualStyle.ADVENTURE_ACTION,
}
_SCENE_COUNT_OPTIONS = [5, 8, 10, 12, 15]

# Video length options: (display label, float minutes)  0.0 = auto
_DURATION_OPTIONS = [
    ("⚡ Auto",  0.0),
    ("1 min",   1.0),
    ("2 min",   2.0),
    ("3 min",   3.0),
    ("5 min",   5.0),
    ("10 min", 10.0),
]

# Pipeline — horizontal step tracker (legacy compact)
_STAGES = ["Story", "Images", "Voice", "Assembly", "Done"]

# Vertical pipeline (wireframe) — title + subtitle per row
_PIPELINE_ROWS = [
    ("Story", "Groq LLaMA 3.3"),
    ("Images", "Leonardo → Pollinations"),
    ("Voice", "Edge-TTS · multi-speaker"),
    ("Assembly", "FFmpeg 8.x · Ken Burns"),
    ("Output", "4K H.264 · QSV"),
]


def _load_quota_state() -> dict:
    """Persisted Groq/Leonardo usage for UI bars (resets daily)."""
    today = time.strftime("%Y-%m-%d")
    if not _QUOTA_FILE.exists():
        return {"date": today, "groq_used": 0, "leonardo_used": 0, "yt_used": 0}
    try:
        data = json.loads(_QUOTA_FILE.read_text(encoding="utf-8"))
        if data.get("date") != today:
            return {"date": today, "groq_used": 0, "leonardo_used": 0, "yt_used": 0}
        return data
    except Exception:
        return {"date": today, "groq_used": 0, "leonardo_used": 0, "yt_used": 0}


def _save_quota_state(data: dict) -> None:
    try:
        _QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
        _QUOTA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _record_quota_after_video() -> dict:
    st = _load_quota_state()
    st["groq_used"] = min(_GROQ_DAILY, int(st.get("groq_used", 0)) + _GROQ_EST_PER_VIDEO)
    st["leonardo_used"] = min(_LEONARDO_DAILY, int(st.get("leonardo_used", 0)) + _LEO_EST_PER_VIDEO)
    _save_quota_state(st)
    return st


# ---------------------------------------------------------------------------
# Log handler
# ---------------------------------------------------------------------------
class _QueueLogHandler(logging.Handler):
    def __init__(self, q: queue.Queue) -> None:
        super().__init__()
        self._q = q

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._q.put(("log", self.format(record)))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Canvas helpers — rounded / pill bars (premium feel)
# ---------------------------------------------------------------------------
def _canvas_round_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
                       r: float, **kwargs) -> int:
    """Rounded rectangle via smooth polygon (Tk 8.6+)."""
    if r <= 0:
        return canvas.create_rectangle(x1, y1, x2, y2, **kwargs)
    return canvas.create_polygon(
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
        smooth=True,
        **kwargs,
    )


def _canvas_pill_bar(canvas: tk.Canvas, x0: int, y0: int, w: int, h: int,
                     pct: float, fill: str, track: str = None) -> None:
    """Draw a horizontal pill-shaped progress bar (0–100)."""
    canvas.delete("all")
    track = track or BG3
    r = h / 2
    _canvas_round_rect(canvas, x0, y0, x0 + w, y0 + h, r, fill=track, outline="")
    fill_w = max(h, int(w * min(100, max(0, pct)) / 100))
    _canvas_round_rect(canvas, x0, y0, x0 + fill_w, y0 + h, r, fill=fill, outline="")


# ---------------------------------------------------------------------------
# Cinematic premium header  (v2 — ember particles + film strip + scan line)
# ---------------------------------------------------------------------------
class _PremiumHeader(tk.Frame):
    """
    Full-canvas animated header:
      • Ember particle field + subtle dot-grid background
      • Scrolling film-strip along the bottom edge
      • Periodic scan-line sweep (broadcast monitor feel)
      • Logo fade-up entrance with 'AI' in orange accent
      • Orange-to-gold gradient accent separator
    """

    _HEADER_H   = 110   # total canvas height
    _STRIP_H    = 18    # film-strip row height
    _FRAME_W    = 22    # one film frame width
    _FRAME_GAP  = 4     # gap between frames
    _N_EMBERS   = 38    # particle count
    _SCAN_CYCLE = 4000  # ms between scan sweeps

    def __init__(self, parent, **kw):
        import random
        super().__init__(parent, bg=BG_HEADER, **kw)

        # ── single full-width canvas ────────────────────────────────────────
        self._c = tk.Canvas(
            self, bg=BG_HEADER, highlightthickness=0,
            height=self._HEADER_H,
        )
        self._c.pack(fill=tk.X)

        # ── accent separator (orange→gold gradient, 3 px) ───────────────────
        self._sep = tk.Canvas(
            self, height=3, bg=BG_HEADER, highlightthickness=0,
        )
        self._sep.pack(fill=tk.X)

        # ── state ────────────────────────────────────────────────────────────
        rng = random.Random()
        W = 1200  # initial guess; corrected on first draw
        H = self._HEADER_H
        self._embers = [
            [rng.uniform(0, W), rng.uniform(0, H - self._STRIP_H - 4),
             rng.uniform(1.0, 2.8),          # radius
             rng.uniform(0.25, 1.1),         # drift speed px/frame
             rng.uniform(0, math.pi * 2),    # alpha phase
             rng.uniform(-0.15, 0.15)]       # vertical drift
            for _ in range(self._N_EMBERS)
        ]
        self._strip_x   = 0.0          # film-strip scroll offset
        self._scan_x    = -1           # -1 = idle
        self._scan_tick = 0
        self._logo_y_off = 18          # entrance animation offset (px down)
        self._logo_alpha = 0           # 0..255 entrance fade
        self._sep_alpha  = 0           # separator fade-in

        # kick off after layout
        self.after(80,  self._start_entrance)
        self.after(100, self._loop)
        self.after(self._SCAN_CYCLE, self._trigger_scan)

    # ── entrance ─────────────────────────────────────────────────────────────
    def _start_entrance(self):
        self._logo_y_off = 18
        self._logo_alpha = 0
        self._sep_alpha  = 0
        self._entrance_step()

    def _entrance_step(self):
        # spring-ease: move 22% of remaining distance each frame
        self._logo_y_off  = max(0.0, self._logo_y_off  * 0.78)
        self._logo_alpha  = min(255, self._logo_alpha + 14)
        self._sep_alpha   = min(255, self._sep_alpha   + 10)
        if self._logo_y_off > 0.3 or self._logo_alpha < 255:
            self.after(16, self._entrance_step)

    # ── scan-line trigger ─────────────────────────────────────────────────────
    def _trigger_scan(self):
        self._scan_x = 0
        self.after(self._SCAN_CYCLE, self._trigger_scan)

    # ── main render loop (~60 fps) ────────────────────────────────────────────
    def _loop(self):
        c = self._c
        c.delete("all")
        W = max(800, c.winfo_width() or 1200)
        H = self._HEADER_H

        # 1. dot-grid background
        grid_step = 28
        for gx in range(0, W, grid_step):
            for gy in range(0, H - self._STRIP_H, grid_step):
                c.create_oval(gx-1, gy-1, gx+1, gy+1, fill="#1c1c22", outline="")

        # 2. ember particles
        for e in self._embers:
            e[0] = (e[0] + e[1]) % W
            e[1] += e[5] * 0.02          # gentle vertical drift
            e[1] = max(0.2, min(1.2, e[1]))
            e[4] += 0.045
            alpha = int(22 + 20 * (math.sin(e[4]) + 1) / 2)
            r = e[2]
            # outer glow
            ga = max(6, alpha // 3)
            gc = f"#{ga:02x}{int(ga*0.22):02x}00"
            c.create_oval(e[0]-r*2, e[1]-r*2, e[0]+r*2, e[1]+r*2,
                          fill=gc, outline="")
            # core ember
            ec = f"#{alpha:02x}{int(alpha*0.34):02x}00"
            c.create_oval(e[0]-r, e[1]-r, e[0]+r, e[1]+r,
                          fill=ec, outline="")

        # 3. film strip (bottom edge of canvas, above separator)
        sy = H - self._STRIP_H
        c.create_rectangle(0, sy, W, H, fill="#1a0a00", outline="")
        self._strip_x = (self._strip_x + 0.8) % (self._FRAME_W + self._FRAME_GAP)
        fx = -self._strip_x
        while fx < W + self._FRAME_W:
            # frame border
            c.create_rectangle(fx, sy+2, fx+self._FRAME_W, H-2,
                                fill="#2a1200", outline="#5a2800", width=1)
            # sprocket holes top & bottom
            for hx in (fx+4, fx+self._FRAME_W-8):
                c.create_rectangle(hx, sy+3, hx+4, sy+7,
                                   fill="#0d0600", outline="#3a1800")
                c.create_rectangle(hx, H-8, hx+4, H-3,
                                   fill="#0d0600", outline="#3a1800")
            fx += self._FRAME_W + self._FRAME_GAP

        # 4. scan line
        if self._scan_x >= 0:
            sw = 60
            sx0 = self._scan_x - sw
            for i in range(sw):
                dist = abs(i - sw // 2)
                alpha = max(0, 1.0 - dist / (sw / 2))
                sa = int(alpha * 55)
                sc = f"#{sa:02x}{int(sa*0.34):02x}00"
                xp = sx0 + i
                if 0 <= xp <= W:
                    c.create_line(xp, 0, xp, H - self._STRIP_H,
                                  fill=sc, width=1)
            self._scan_x += 9
            if self._scan_x > W + sw:
                self._scan_x = -1

        # 5. logo (fade-up entrance)
        cy = (H - self._STRIP_H) // 2 + int(self._logo_y_off)
        a = self._logo_alpha
        # icon
        icon_col = f"#{min(255,int(a)):02x}{int(min(255,a)*0.34):02x}{int(min(255,a)*0.13):02x}"
        c.create_text(W//2 - 90, cy - 4, text="🎬",
                      font=("Segoe UI", 26), fill=icon_col, anchor="e")
        # "RAG" in white, "AI" in orange
        fg_w = f"#{min(255,a):02x}{min(255,a):02x}{min(255,a):02x}"
        c.create_text(W//2 - 82, cy - 6, text="RAG",
                      font=("Segoe UI", 24, "bold"), fill=fg_w, anchor="w")
        ai_a = min(255, a)
        ai_col = f"#{ai_a:02x}{int(ai_a*0.34):02x}{int(ai_a*0.13):02x}"
        c.create_text(W//2 - 82 + 58, cy - 6, text="AI",
                      font=("Segoe UI", 24, "bold"), fill=ai_col, anchor="w")
        # tagline
        tg_a = max(0, a - 60)
        tg_col = f"#{int(tg_a*0.61):02x}{int(tg_a*0.64):02x}{int(tg_a*0.69):02x}"
        c.create_text(W//2 - 82 + 2, cy + 18,
                      text="AI VIDEO FACTORY  ·  CINEMATIC 4K",
                      font=("Segoe UI", 9, "bold"), fill=tg_col, anchor="w")

        # 6. separator gradient
        self._draw_sep(W)

        self.after(16, self._loop)   # ~60 fps

    # ── accent separator ──────────────────────────────────────────────────────
    def _draw_sep(self, W: int):
        s = self._sep
        s.delete("all")
        a = self._sep_alpha
        # orange → gold gradient
        for i in range(W):
            t = i / max(1, W - 1)
            r = int((0xff * (1 - t) + 0xff * t) * a / 255)
            g = int((0x57 * (1 - t) + 0xca * t) * a / 255)
            b = int((0x22 * (1 - t) + 0x28 * t) * a / 255)
            col = f"#{min(255,r):02x}{min(255,g):02x}{min(255,b):02x}"
            s.create_line(i, 0, i, 3, fill=col)


# ---------------------------------------------------------------------------
# Animated shimmer progress bar
# ---------------------------------------------------------------------------
class _ShimmerBar(tk.Canvas):
    """Animated pill track with soft shimmer (no harsh border)."""

    def __init__(self, parent, **kw):
        super().__init__(parent, height=10, bg=BG_ELEV, highlightthickness=0, **kw)
        self._active = False
        self._shimmer_x = 0
        self._color = ACCENT

    def start(self, color=ACCENT):
        self._active = True
        self._color = color
        self._shimmer_x = 0
        self._animate()

    def stop(self, success=True):
        self._active = False
        self.delete("all")
        w = max(40, self.winfo_width() or 360)
        h = 10
        fill = GREEN_N if success else "#e57373"
        _canvas_round_rect(self, 0, 0, w, h, h / 2, fill=fill, outline="")

    def reset(self):
        self._active = False
        self.delete("all")

    def _animate(self):
        if not self._active:
            return
        self.delete("all")
        w = max(40, self.winfo_width() or 360)
        h = 10
        _canvas_round_rect(self, 0, 0, w, h, h / 2, fill=BG3, outline="")
        t = (math.sin(self._shimmer_x * 0.05) + 1) / 2
        fill_w = int(w * (0.28 + 0.48 * t))
        _canvas_round_rect(self, 0, 0, fill_w, h, h / 2, fill=self._color, outline="")
        sx = int((self._shimmer_x % w))
        sw = 72
        for i in range(sw):
            alpha = max(0.0, 1.0 - abs(i - sw // 2) / (sw // 2))
            c = f"#{int(255*alpha):02x}{int(255*alpha):02x}{int(255*alpha):02x}"
            self.create_line(sx + i, 1, sx + i, h - 1, fill=c)
        self._shimmer_x += 5
        self.after(28, self._animate)


# ---------------------------------------------------------------------------
# Glow button
# ---------------------------------------------------------------------------
class _GlowButton(tk.Frame):
    """Primary / secondary button — subtle ring, calm hover (no jitter)."""

    def __init__(self, parent, text, command, color=ACCENT,
                 bg_btn=BG2, fg_btn=FG, width=None, font=FONT_BTN, **kw):
        super().__init__(parent, bg=color, padx=2, pady=2)
        self._color = color
        self._bg = bg_btn
        self._fg = fg_btn
        inner_kw = {"width": width} if width else {}
        self._btn = tk.Button(
            self, text=text, command=command,
            bg=bg_btn, fg=fg_btn,
            activebackground=color, activeforeground="#ffffff",
            relief=tk.FLAT, bd=0, padx=20, pady=12,
            font=font, cursor="hand2", **inner_kw,
        )
        self._btn.pack(fill=tk.BOTH, expand=True)
        self._btn.bind("<Enter>", self._on_enter)
        self._btn.bind("<Leave>", self._on_leave)

    def _on_enter(self, _=None):
        self._btn.config(bg=self._color, fg="#ffffff")
        self.config(bg=self._color, padx=3, pady=3)

    def _on_leave(self, _=None):
        self._btn.config(bg=self._bg, fg=self._fg)
        self.config(bg=self._color, padx=2, pady=2)

    def config_state(self, state):
        self._btn.config(state=state)
        if state == "disabled":
            self._btn.config(bg=BG3, fg=FG3)
        else:
            self._btn.config(bg=self._bg, fg=self._fg)


# ---------------------------------------------------------------------------
# Step tracker widget
# ---------------------------------------------------------------------------
class _StepTracker(tk.Canvas):
    """Animated pipeline stage indicator."""

    def __init__(self, parent, stages, **kw):
        super().__init__(parent, height=50, bg=BG,
                         highlightthickness=0, **kw)
        self._stages = stages
        self._current = -1
        self._phase = 0
        self._draw()

    def set_stage(self, name: str):
        name_lower = name.lower()
        for i, s in enumerate(self._stages):
            if s.lower() in name_lower or name_lower in s.lower():
                self._current = i
                break
        self._draw()

    def complete(self):
        self._current = len(self._stages) - 1
        self._draw()

    def reset(self):
        self._current = -1
        self._draw()

    def _draw(self):
        self.delete("all")
        w = self.winfo_width() or 800
        n = len(self._stages)
        step_w = w // n
        cy = 25

        for i, stage in enumerate(self._stages):
            cx = step_w * i + step_w // 2
            done = i < self._current
            active = i == self._current

            # Connector line
            if i < n - 1:
                lx = cx + 20
                rx = cx + step_w - 20
                line_color = CYAN if done else BORDER
                self.create_line(lx, cy, rx, cy, fill=line_color, width=2)

            # Circle
            r = 14
            if done:
                self.create_oval(cx-r, cy-r, cx+r, cy+r, fill=CYAN, outline=CYAN)
                self.create_text(cx, cy, text="✓", font=("Segoe UI", 9, "bold"), fill="#ffffff")
            elif active:
                # Glowing active circle
                for glow in range(4, 0, -1):
                    alpha = glow / 4
                    gc = int(0 + (1-alpha)*14)
                    gcolor = f"#{gc:02x}{int(212*alpha):02x}{int(255*alpha):02x}"
                    self.create_oval(cx-r-glow*2, cy-r-glow*2,
                                     cx+r+glow*2, cy+r+glow*2,
                                     fill="", outline=gcolor, width=1)
                self.create_oval(cx-r, cy-r, cx+r, cy+r,
                                 fill=BG3, outline=CYAN, width=2)
                self.create_text(cx, cy, text=str(i+1),
                                 font=("Segoe UI", 8, "bold"), fill=CYAN)
            else:
                self.create_oval(cx-r, cy-r, cx+r, cy+r,
                                 fill=BG3, outline=BORDER, width=1)
                self.create_text(cx, cy, text=str(i+1),
                                 font=("Segoe UI", 8), fill=FG3)

            # Label
            label_color = CYAN if (done or active) else FG3
            self.create_text(cx, cy+22, text=stage,
                             font=("Segoe UI", 8, "bold" if active else "normal"),
                             fill=label_color)


# ---------------------------------------------------------------------------
# Pipeline step indicator (numbered circles — wireframe)
# ---------------------------------------------------------------------------
class _StepDot(tk.Canvas):
    """28×28 circle: idle (grey #) · active (orange #) · done (green ✓)."""

    def __init__(self, parent, index: int, **kw):
        super().__init__(parent, width=28, height=28, bg=BG_ELEV, highlightthickness=0, **kw)
        self._n = index
        self.set_idle()

    def set_idle(self) -> None:
        self.delete("all")
        self.create_oval(3, 3, 25, 25, fill=BG3, outline=BORDER, width=1)
        self.create_text(14, 14, text=str(self._n), fill=FG3,
                         font=("Segoe UI", 10, "bold"))

    def set_active(self) -> None:
        self.delete("all")
        self.create_oval(3, 3, 25, 25, fill=ACCENT, outline=ACCENT, width=0)
        self.create_text(14, 14, text=str(self._n), fill="#ffffff",
                         font=("Segoe UI", 10, "bold"))

    def set_done(self) -> None:
        self.delete("all")
        self.create_oval(3, 3, 25, 25, fill=GREEN_N, outline=GREEN_N, width=0)
        self.create_text(14, 14, text="✓", fill="#ffffff",
                         font=("Segoe UI", 11, "bold"))


# ---------------------------------------------------------------------------
# Vertical pipeline (wireframe right column)
# ---------------------------------------------------------------------------
class _VerticalPipeline(tk.Frame):
    """Five-step vertical status: Story → … → Output."""

    def __init__(self, parent, rows: list[tuple[str, str]], **kw):
        super().__init__(parent, bg=BG_ELEV, **kw)
        self._rows = rows
        self._idx = -1
        self._dots: list[_StepDot] = []
        self._status: list[tk.Label] = []
        for i, (title, sub) in enumerate(rows):
            row = tk.Frame(self, bg=BG_ELEV)
            row.pack(fill=tk.X, pady=(0, 10))
            dot = _StepDot(row, i + 1)
            dot.pack(side=tk.LEFT, padx=(0, 10))
            self._dots.append(dot)
            mid = tk.Frame(row, bg=BG_ELEV)
            mid.pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Label(mid, text=title, font=("Segoe UI", 10, "bold"), fg=FG, bg=BG_ELEV, anchor="w").pack(anchor="w")
            tk.Label(mid, text=sub, font=FONT_SMALL, fg=FG_MUTED, bg=BG_ELEV, anchor="w").pack(anchor="w")
            st = tk.Label(row, text="Waiting", font=FONT_SMALL, fg=FG3, bg=BG_ELEV, width=16, anchor="e")
            st.pack(side=tk.RIGHT)
            self._status.append(st)
        self.reset()

    def reset(self):
        self._idx = -1
        for d in self._dots:
            d.set_idle()
        for st in self._status:
            st.config(text="Waiting", fg=FG3)

    def set_from_progress(self, stage: str, scene: int, total: int):
        sl = stage.lower()
        if "story" in sl:
            self._apply_active(0, scene, total)
        elif "image" in sl:
            self._apply_active(1, scene, total)
        elif "voice" in sl:
            self._apply_active(2, scene, total)
        elif "assembly" in sl:
            self._apply_active(3, scene, total)

    def _apply_active(self, active_idx: int, scene: int, total: int):
        self._idx = active_idx
        for j in range(active_idx):
            self._dots[j].set_done()
            self._status[j].config(text="Done", fg=GREEN_N)
        self._dots[active_idx].set_active()
        if active_idx == 1 and total > 0:
            self._status[active_idx].config(
                text=f"{scene} / {total}", fg=ACCENT)
        elif active_idx == 2 and total > 0:
            self._status[active_idx].config(
                text=f"{scene} / {total}", fg=ACCENT)
        elif active_idx == 3:
            self._status[active_idx].config(text="FFmpeg…", fg=ACCENT)
            self._dots[4].set_idle()
            self._status[4].config(text="Waiting", fg=FG3)
        else:
            self._status[active_idx].config(text="In progress…", fg=ACCENT)
        for j in range(active_idx + 1, len(self._dots)):
            if j == 4 and active_idx == 3:
                continue
            self._dots[j].set_idle()
            self._status[j].config(text="Waiting", fg=FG3)

    def complete_all(self):
        for d in self._dots:
            d.set_done()
        for st in self._status:
            st.config(text="Done", fg=GREEN_N)


# ---------------------------------------------------------------------------
# Pill selector (source / format)
# ---------------------------------------------------------------------------
class _PillSelector(tk.Frame):
    def __init__(self, parent, options, variable, color=ACCENT, **kw):
        super().__init__(parent, bg=BG_ELEV, **kw)
        self._var = variable
        self._btns = {}
        self._color = color
        for label, val in options:
            btn = tk.Button(
                self, text=label, font=("Segoe UI", 10, "bold"),
                bg=BG3, fg=FG_MUTED, relief=tk.FLAT, bd=0,
                padx=16, pady=9, cursor="hand2",
                activebackground=color, activeforeground="#ffffff",
                command=lambda v=val: self._select(v),
            )
            btn.pack(side=tk.LEFT, padx=(0, 6))
            self._btns[val] = btn
        variable.trace_add("write", lambda *_: self._refresh())
        self._refresh()

    def _select(self, val):
        self._var.set(val)

    def _refresh(self):
        cur = self._var.get()
        for val, btn in self._btns.items():
            if val == cur:
                btn.config(bg=self._color, fg="#ffffff")
            else:
                btn.config(bg=BG3, fg=FG2)


# ---------------------------------------------------------------------------
# Chip selector (scene count)
# ---------------------------------------------------------------------------
class _ChipSelector(tk.Frame):
    def __init__(self, parent, options, variable, color=PURPLE, **kw):
        super().__init__(parent, bg=BG_ELEV, **kw)
        self._var = variable
        self._btns = {}
        self._color = color
        for val in options:
            btn = tk.Button(
                self, text=str(val), font=("Segoe UI", 11, "bold"),
                bg=BG3, fg=FG2, relief=tk.FLAT, bd=0,
                width=3, pady=6, cursor="hand2",
                activebackground=color, activeforeground="#ffffff",
                command=lambda v=val: self._select(v),
            )
            btn.pack(side=tk.LEFT, padx=(0, 6))
            self._btns[val] = btn
        variable.trace_add("write", lambda *_: self._refresh())
        self._refresh()

    def _select(self, val):
        self._var.set(val)

    def _refresh(self):
        cur = self._var.get()
        for val, btn in self._btns.items():
            btn.config(bg=self._color if val == cur else BG3,
                       fg="#ffffff" if val == cur else FG2)


# ---------------------------------------------------------------------------
# Quality card grid
# ---------------------------------------------------------------------------
class _QualityGrid(tk.Frame):
    def __init__(self, parent, variable, **kw):
        super().__init__(parent, bg=BG_ELEV, **kw)
        self._var = variable
        self._frames = {}
        for q in QualityPreset:
            card_bg, glow, label = _Q_THEME[q]
            spec = _Q_SPEC[q]
            f = tk.Frame(self, bg=card_bg, cursor="hand2",
                         highlightthickness=1, highlightbackground=BORDER_SOFT,
                         padx=12, pady=12)
            f.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
            icon_lbl = tk.Label(f, text=label.split()[0], font=("Segoe UI", 20),
                                bg=card_bg, fg=glow)
            icon_lbl.pack()
            name_lbl = tk.Label(f, text=" ".join(label.split()[1:]),
                                font=("Segoe UI", 9, "bold"), bg=card_bg, fg=glow)
            name_lbl.pack()
            spec_lbl = tk.Label(f, text=spec, font=("Segoe UI", 8),
                                bg=card_bg, fg=FG2)
            spec_lbl.pack(pady=(2, 0))
            self._frames[q] = (f, icon_lbl, name_lbl, spec_lbl, card_bg, glow)
            for w in (f, icon_lbl, name_lbl, spec_lbl):
                w.bind("<Button-1>", lambda e, v=q: self._select(v))
        variable.trace_add("write", lambda *_: self._refresh())
        self._refresh()

    def _select(self, q):
        self._var.set(q.value)

    def _refresh(self):
        cur = self._var.get()
        for q, (f, il, nl, sl, card_bg, glow) in self._frames.items():
            sel = cur == q.value
            f.config(highlightbackground=glow if sel else BORDER_SOFT,
                     highlightthickness=2 if sel else 1,
                     bg=card_bg)
            for w in (il, nl, sl):
                w.config(bg=card_bg)


# ---------------------------------------------------------------------------
# Dark styled entry / combo helpers
# ---------------------------------------------------------------------------
def _entry(parent, var, **kw) -> tk.Entry:
    return tk.Entry(parent, textvariable=var, bg=BG3, fg=FG,
                    insertbackground=ACCENT, relief=tk.FLAT, bd=8,
                    font=FONT_LABEL, **kw)


def _combo(parent, var, values, width=18) -> ttk.Combobox:
    s = ttk.Style()
    s.theme_use("clam")
    s.configure("N.TCombobox", fieldbackground=BG3, background=BG3,
                foreground=FG, selectbackground=ACCENT, selectforeground="#ffffff",
                arrowcolor=FG_MUTED, bordercolor=BORDER_SOFT,
                lightcolor=BORDER_SOFT, darkcolor=BORDER_SOFT)
    s.map("N.TCombobox", fieldbackground=[("readonly", BG3)],
          foreground=[("readonly", FG)])
    return ttk.Combobox(parent, textvariable=var, values=values,
                        state="readonly", width=width,
                        style="N.TCombobox", font=FONT_LABEL)


def _card(parent, title: str, accent=ACCENT) -> tk.Frame:
    """Raised card: hairline border + accent rule under title (no loud orange frame)."""
    outer = tk.Frame(parent, bg=BG, highlightthickness=0)
    inner = tk.Frame(
        outer, bg=BG_ELEV,
        highlightthickness=1, highlightbackground=BORDER_SOFT,
        padx=20, pady=18,
    )
    inner.pack(fill=tk.BOTH, expand=True)
    tk.Label(inner, text=title, font=("Segoe UI", 9, "bold"),
             fg=FG_MUTED, bg=BG_ELEV).pack(anchor="w", pady=(0, 8))
    tk.Frame(inner, bg=accent, height=2).pack(fill=tk.X, pady=(0, 14))
    return inner


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class RAGAIApp(tk.Tk):

    def __init__(self, app_config: AppConfig) -> None:
        super().__init__()
        self.app_config = app_config
        self.title("RAGAI — AI Video Factory")
        self.configure(bg=BG)
        self.minsize(1120, 820)
        self.resizable(True, True)

        self._queue: Optional[queue.Queue] = None
        self._output_dir: Optional[Path] = None
        self._audio_file_path: Optional[str] = None
        self._image_file_paths: list = []
        self._bgm_path: Optional[str] = None
        self._cancel_event = threading.Event()
        self._start_time: float = 0.0
        self._log_handler: Optional[_QueueLogHandler] = None
        self._pipeline: Optional[object] = None   # holds Pipeline after run for scene regen

        self._setup_ttk_style()
        self._build_ui()

    def _setup_ttk_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TNotebook", background=BG, borderwidth=0, tabmargins=[2, 2, 0, 0])
        s.configure(
            "TNotebook.Tab",
            background=BG2,
            foreground=FG_MUTED,
            padding=[18, 11],
            font=("Segoe UI", 10),
            borderwidth=0,
        )
        s.map(
            "TNotebook.Tab",
            background=[("selected", BG3), ("active", BG3)],
            foreground=[("selected", ACCENT), ("active", FG2)],
        )
        s.configure("TScrollbar", background=BG3, troughcolor=BG,
                    bordercolor=BORDER, arrowcolor=FG3, relief=tk.FLAT)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_ui(self):
        self._header = _PremiumHeader(self)
        self._header.pack(fill=tk.X)

        self._build_top_bar()

        # Notebook — inset for breathable layout
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill=tk.BOTH, expand=True, padx=14, pady=(4, 12))

        settings_host = tk.Frame(self._nb, bg=BG)
        self._nb.add(settings_host, text="  ⚙  Settings  ")

        scenes_host = tk.Frame(self._nb, bg=BG)
        self._nb.add(scenes_host, text="  🖼  Scenes  ")

        log_host = tk.Frame(self._nb, bg=BG)
        self._nb.add(log_host, text="  📋  Live Log  ")

        sched_host = tk.Frame(self._nb, bg=BG)
        self._nb.add(sched_host, text="  ⏱  Scheduler  ")

        trends_host = tk.Frame(self._nb, bg=BG)
        self._nb.add(trends_host, text="  📈  Trends  ")

        self._build_settings(settings_host)
        self._build_scenes_tab(scenes_host)
        self._build_log(log_host)
        self._build_scheduler_tab(sched_host)
        self._build_trends_tab(trends_host)
        self._build_statusbar()
        self._refresh_quota_bars()
        self.after(30_000, self._quota_tick)

    def _build_statusbar(self):
        bar = tk.Frame(self, bg=BG_ELEV)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Frame(bar, bg=LINE, height=1).pack(fill=tk.X)
        row = tk.Frame(bar, bg=BG_ELEV, padx=18, pady=8)
        row.pack(fill=tk.X)
        self._status_var = tk.StringVar(value="Select a topic and press Generate")
        tk.Label(row, textvariable=self._status_var,
                 font=FONT_SMALL, fg=FG_MUTED, bg=BG_ELEV).pack(side=tk.LEFT)
        self._elapsed_var = tk.StringVar(value="")
        tk.Label(row, textvariable=self._elapsed_var,
                 font=("Segoe UI", 9, "bold"), fg=ACCENT, bg=BG_ELEV).pack(side=tk.RIGHT)

    def _build_top_bar(self):
        """Animated status bar: Groq / Leo / YT quota bars + Ready badge."""
        bar = tk.Frame(self, bg=BG_HEADER, padx=20, pady=9)
        bar.pack(fill=tk.X, after=self._header)
        tk.Frame(bar, bg=LINE, height=1).pack(fill=tk.X, side=tk.BOTTOM)

        left = tk.Frame(bar, bg=BG_HEADER)
        left.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ── Groq bar ──────────────────────────────────────────────────────
        tk.Label(left, text="Groq", font=("Segoe UI", 9, "bold"),
                 fg=FG2, bg=BG_HEADER).pack(side=tk.LEFT, padx=(0, 8))
        self._top_groq_canvas = tk.Canvas(
            left, bg=BG_HEADER, height=8, width=110, highlightthickness=0)
        self._top_groq_canvas.pack(side=tk.LEFT, padx=(0, 6))
        self._top_groq_var = tk.StringVar(value="0%")
        tk.Label(left, textvariable=self._top_groq_var,
                 font=("Segoe UI", 9), fg=FG_MUTED, bg=BG_HEADER,
                 width=5, anchor="w").pack(side=tk.LEFT, padx=(0, 22))

        # ── Leo bar ───────────────────────────────────────────────────────
        tk.Label(left, text="Leo", font=("Segoe UI", 9, "bold"),
                 fg=FG2, bg=BG_HEADER).pack(side=tk.LEFT, padx=(0, 8))
        self._top_leo_canvas = tk.Canvas(
            left, bg=BG_HEADER, height=8, width=110, highlightthickness=0)
        self._top_leo_canvas.pack(side=tk.LEFT, padx=(0, 6))
        self._top_leo_var = tk.StringVar(value="0%")
        tk.Label(left, textvariable=self._top_leo_var,
                 font=("Segoe UI", 9), fg=FG_MUTED, bg=BG_HEADER,
                 width=5, anchor="w").pack(side=tk.LEFT, padx=(0, 22))

        # ── YT API bar ────────────────────────────────────────────────────
        tk.Label(left, text="YT API", font=("Segoe UI", 9, "bold"),
                 fg=FG2, bg=BG_HEADER).pack(side=tk.LEFT, padx=(0, 8))
        self._top_yt_canvas = tk.Canvas(
            left, bg=BG_HEADER, height=8, width=110, highlightthickness=0)
        self._top_yt_canvas.pack(side=tk.LEFT, padx=(0, 6))
        self._top_yt_var = tk.StringVar(value="0%")
        tk.Label(left, textvariable=self._top_yt_var,
                 font=("Segoe UI", 9), fg=FG_MUTED, bg=BG_HEADER,
                 width=5, anchor="w").pack(side=tk.LEFT)

        # ── Ready badge ───────────────────────────────────────────────────
        self._top_ready_var = tk.StringVar(value=f"v{RAGAI_VERSION}")
        ready_fr = tk.Frame(bar, bg=BG_HEADER)
        ready_fr.pack(side=tk.RIGHT)
        self._top_ready_dot = tk.Label(
            ready_fr, text="●", font=("Segoe UI", 9), fg=GREEN_N, bg=BG_HEADER)
        self._top_ready_dot.pack(side=tk.LEFT, padx=(0, 5))
        tk.Label(ready_fr, text="Ready", font=("Segoe UI", 9, "bold"),
                 fg=FG2, bg=BG_HEADER).pack(side=tk.LEFT, padx=(0, 6))
        tk.Label(ready_fr, text="·", font=("Segoe UI", 9),
                 fg=FG3, bg=BG_HEADER).pack(side=tk.LEFT, padx=(0, 6))
        tk.Label(ready_fr, textvariable=self._top_ready_var,
                 font=("Segoe UI", 9), fg=FG_MUTED, bg=BG_HEADER).pack(side=tk.LEFT)

        # stagger bar entrance animations
        self.after(300, lambda: self._animate_bar_in(self._top_groq_canvas, 0, CYAN))
        self.after(500, lambda: self._animate_bar_in(self._top_leo_canvas,  0, YELLOW_N))
        self.after(700, lambda: self._animate_bar_in(self._top_yt_canvas,   0, FG3))

    def _animate_bar_in(self, canvas: tk.Canvas, current_pct: float, color: str,
                        target_pct: float = None):
        """Animate a quota bar from 0 to its real value on load."""
        if target_pct is None:
            # first call — load real value
            st = _load_quota_state()
            if canvas is self._top_groq_canvas:
                target_pct = min(100, st.get("groq_used", 0) * 100 / max(1, _GROQ_DAILY))
            elif canvas is self._top_leo_canvas:
                target_pct = min(100, st.get("leonardo_used", 0) * 100 / max(1, _LEONARDO_DAILY))
            else:
                target_pct = min(100, st.get("yt_used", 0) * 100 / max(1, _YT_UNITS_DAILY))
        step = max(0.8, (target_pct - current_pct) * 0.12)
        current_pct = min(target_pct, current_pct + step)
        self._draw_mini_bar(canvas, current_pct, color)
        if current_pct < target_pct - 0.3:
            self.after(16, lambda: self._animate_bar_in(
                canvas, current_pct, color, target_pct))

    def _refresh_quota_bars(self):
        st = _load_quota_state()
        g_pct = min(100, int(st.get("groq_used", 0) * 100 / max(1, _GROQ_DAILY)))
        l_pct = min(100, int(st.get("leonardo_used", 0) * 100 / max(1, _LEONARDO_DAILY)))
        y_pct = min(100, int(st.get("yt_used", 0) * 100 / max(1, _YT_UNITS_DAILY)))
        self._top_groq_var.set(f"{g_pct}%")
        self._top_leo_var.set(f"{l_pct}%")
        self._top_yt_var.set(f"{y_pct}%")
        self._draw_mini_bar(self._top_groq_canvas, g_pct, CYAN)
        self._draw_mini_bar(self._top_leo_canvas,  l_pct, YELLOW_N)
        self._draw_mini_bar(self._top_yt_canvas,   y_pct, FG3)
        if hasattr(self, "_quota_groq_canvas"):
            self._draw_quota_block(
                self._quota_groq_canvas, st.get("groq_used", 0), _GROQ_DAILY, ACCENT)
            self._draw_quota_block(
                self._quota_leo_canvas, st.get("leonardo_used", 0), _LEONARDO_DAILY, PURPLE)
            self._draw_quota_block(
                self._quota_yt_canvas, st.get("yt_used", 0), _YT_UNITS_DAILY, CYAN)
            rem = max(0, (_GROQ_DAILY - int(st.get("groq_used", 0))) // _GROQ_EST_PER_VIDEO)
            self._quota_footer_var.set(f"~{rem} video(s) remaining today (Groq estimate)")

    def _draw_mini_bar(self, canvas: tk.Canvas, pct: int, color: str = ACCENT):
        w = int(canvas.cget("width") or 110)
        h = 8
        _canvas_pill_bar(canvas, 0, 0, w, h, float(pct), color, BG3)

    def _draw_quota_block(self, canvas: tk.Canvas, used: int, limit: int, color: str):
        w = int(canvas.cget("width") or 340)
        h = 8
        pct = min(100, int(used * 100 / max(1, limit)))
        _canvas_pill_bar(canvas, 0, 0, w, h, float(pct), color, BG3)

    def _quota_tick(self):
        self._refresh_quota_bars()
        self.after(30_000, self._quota_tick)

    def _build_scheduler_tab(self, parent: tk.Frame):
        outer = tk.Frame(parent, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True, padx=14, pady=12)
        tk.Label(outer, text="Scheduler status (scheduler_v2.py)",
                 font=FONT_TITLE, fg=ACCENT, bg=BG).pack(anchor="w")
        tk.Label(
            outer,
            text="Run overnight queue:  python scheduler_v2.py\n"
                 "Or double-click START_SCHEDULER_V2.bat",
            font=FONT_SMALL, fg=FG2, bg=BG, justify="left",
        ).pack(anchor="w", pady=(4, 10))
        self._sched_status_text = tk.Text(
            outer, height=16, wrap=tk.WORD, bg=BG3, fg=FG, font=FONT_MONO,
            relief=tk.FLAT, bd=8, state="disabled",
        )
        self._sched_status_text.pack(fill=tk.BOTH, expand=True)
        row = tk.Frame(outer, bg=BG)
        row.pack(fill=tk.X, pady=(10, 0))
        _GlowButton(row, "Refresh status", self._refresh_scheduler_tab,
                    color=ACCENT, bg_btn=BG2, fg_btn=ACCENT).pack(side=tk.LEFT)
        self._refresh_scheduler_tab()

    def _refresh_scheduler_tab(self):
        lines = []
        p = Path("tmp/scheduler_status.json")
        if p.exists():
            try:
                lines.append(p.read_text(encoding="utf-8"))
            except Exception as exc:
                lines.append(f"(read error: {exc})")
        else:
            lines.append("No tmp/scheduler_status.json yet — start the scheduler once.")
        lines.append("")
        tq = Path("topics_queue.json")
        if tq.exists():
            try:
                topics = json.loads(tq.read_text(encoding="utf-8"))
                lines.append(f"topics_queue.json: {len(topics)} topic(s) waiting")
                for i, topic in enumerate(topics[:12]):
                    lines.append(f"  {i+1}. {topic[:80]}")
            except Exception as exc:
                lines.append(f"topics_queue.json: (parse error {exc})")
        else:
            lines.append("topics_queue.json: not found")
        txt = "\n".join(lines)
        self._sched_status_text.config(state="normal")
        self._sched_status_text.delete("1.0", tk.END)
        self._sched_status_text.insert("1.0", txt)
        self._sched_status_text.config(state="disabled")

    def _build_trends_tab(self, parent: tk.Frame):
        outer = tk.Frame(parent, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True, padx=14, pady=12)
        tk.Label(outer, text="Trend Booster (same controls as Settings)",
                 font=FONT_TITLE, fg=ACCENT, bg=BG).pack(anchor="w")
        tk.Label(outer, text="Use keyword + Fetch for SEO angles. Results sync with Settings.",
                 font=FONT_SMALL, fg=FG2, bg=BG).pack(anchor="w", pady=(2, 10))
        tb = _card(outer, "🔥  TREND BOOSTER", ACCENT)
        tb.pack(fill=tk.BOTH, expand=True)
        tb_topic_row = tk.Frame(tb, bg=BG2)
        tb_topic_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(tb_topic_row, text="Keyword:", font=FONT_LABEL, fg=FG, bg=BG2).pack(
            side=tk.LEFT, padx=(0, 8))
        _entry(tb_topic_row, self._trend_kw_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tb_row1 = tk.Frame(tb, bg=BG2)
        tb_row1.pack(fill=tk.X, pady=(0, 6))
        _GlowButton(tb_row1, "Fetch", self._on_fetch_trends,
                    color=ACCENT, bg_btn=BG3, fg_btn=ACCENT).pack(side=tk.LEFT, padx=(0, 10))
        tk.Label(tb_row1, textvariable=self._tb_status_var,
                 font=FONT_SMALL, fg=FG, bg=BG2, anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(tb, text="Trending angle:", font=FONT_LABEL, fg=FG, bg=BG2).pack(anchor="w")
        self._tb_angle_combo_t = ttk.Combobox(
            tb, textvariable=self._tb_angle_var, values=[], state="readonly", width=70,
            font=FONT_LABEL,
        )
        self._tb_angle_combo_t.pack(fill=tk.X, pady=(2, 6))
        self._tb_angle_combo_t.bind("<<ComboboxSelected>>", lambda _: self._on_angle_selected())
        row3 = tk.Frame(tb, bg=BG2)
        row3.pack(fill=tk.X, pady=(0, 6))
        tk.Label(row3, text="Viral Score:", font=FONT_LABEL, fg=FG, bg=BG2).pack(side=tk.LEFT)
        tk.Label(row3, textvariable=self._tb_score_var, font=("Segoe UI", 11, "bold"),
                 fg=FG, bg=BG2).pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(tb, text="Suggested hook:", font=FONT_LABEL, fg=FG, bg=BG2).pack(anchor="w")
        _entry(tb, self._tb_hook_var).pack(fill=tk.X, pady=(2, 6))
        tk.Label(tb, textvariable=self._tb_hashtags_var, font=FONT_SMALL, fg=CYAN, bg=BG2,
                 wraplength=720, justify="left").pack(anchor="w")

    def _build_settings(self, parent: tk.Frame):
        self._trend_kw_var = tk.StringVar(value="")

        split = tk.Frame(parent, bg=BG)
        split.pack(fill=tk.BOTH, expand=True)

        left_wrap = tk.Frame(split, bg=BG)
        left_wrap.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(16, 10))

        canvas = tk.Canvas(left_wrap, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(left_wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sf = tk.Frame(canvas, bg=BG)
        win = canvas.create_window((0, 0), window=sf, anchor="nw")
        sf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        right = tk.Frame(
            split, bg=BG_ELEV, width=400,
            highlightthickness=1, highlightbackground=BORDER_SOFT,
            padx=20, pady=18,
        )
        right.pack(side=tk.RIGHT, fill=tk.Y)
        right.pack_propagate(False)

        PAD = {"padx": 4, "pady": 8}

        # ── Story Source ──────────────────────────────────────────────
        src = _card(sf, "📖  STORY SOURCE", ACCENT)
        src.master.pack(fill=tk.X, **PAD)
        self._source_var = tk.StringVar(value="topic")
        _PillSelector(src, [
            ("Topic", "topic"), ("Script", "script"),
            ("Audio", "audio"), ("Images", "image"),
        ], self._source_var, color=ACCENT).pack(anchor="w", pady=(0, 10))

        self._src_input_host = tk.Frame(src, bg=BG2)
        self._src_input_host.pack(fill=tk.X)
        self._build_source_inputs(self._src_input_host)
        self._source_var.trace_add("write", lambda *_: self._on_source_change())
        self._on_source_change()

        # ── Trend Booster ─────────────────────────────────────────────
        tb = _card(sf, "🔥  TREND BOOSTER", ACCENT)
        tb.master.pack(fill=tk.X, **PAD)

        tb_topic_row = tk.Frame(tb, bg=BG2)
        tb_topic_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(tb_topic_row, text="Keyword for trend analysis:", font=FONT_LABEL, fg=FG, bg=BG2).pack(
            side=tk.LEFT, padx=(0, 8))
        _entry(tb_topic_row, self._trend_kw_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Row 1: Fetch button + status
        tb_row1 = tk.Frame(tb, bg=BG2)
        tb_row1.pack(fill=tk.X, pady=(0, 6))
        _GlowButton(tb_row1, "Fetch", self._on_fetch_trends,
                    color=ACCENT, bg_btn=BG3, fg_btn=ACCENT).pack(side=tk.LEFT, padx=(0, 10))
        self._tb_status_var = tk.StringVar(value="Enter a keyword and click Fetch")
        tk.Label(tb_row1, textvariable=self._tb_status_var,
                 font=FONT_SMALL, fg=FG, bg=BG2, anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Row 2: Trending angles dropdown
        tb_row2 = tk.Frame(tb, bg=BG2)
        tb_row2.pack(fill=tk.X, pady=(0, 6))
        tk.Label(tb_row2, text="Trending Angle:", font=FONT_LABEL, fg=FG, bg=BG2).pack(side=tk.LEFT, padx=(0, 8))
        self._tb_angle_var = tk.StringVar(value="— fetch trends first —")
        self._tb_angle_combo = ttk.Combobox(
            tb_row2, textvariable=self._tb_angle_var,
            values=[], state="readonly", width=50,
            font=FONT_LABEL,
        )
        self._tb_angle_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._tb_angle_combo.bind("<<ComboboxSelected>>", lambda _: self._on_angle_selected())

        # Style the combobox for dark theme
        style = ttk.Style()
        style.configure("TCombobox",
                         fieldbackground=BG3, background=BG3,
                         foreground=FG, selectbackground=ACCENT,
                         selectforeground=BG)
        self._tb_angle_combo.configure(style="TCombobox")

        # Row 3: Viral score meter (wireframe: /100)
        tb_row3 = tk.Frame(tb, bg=BG2)
        tb_row3.pack(fill=tk.X, pady=(0, 6))
        tk.Label(tb_row3, text="Viral Score:", font=FONT_LABEL, fg=FG, bg=BG2).pack(side=tk.LEFT, padx=(0, 8))
        self._tb_score_var = tk.StringVar(value="—")
        self._tb_score_label = tk.Label(
            tb_row3, textvariable=self._tb_score_var,
            font=("Segoe UI", 11, "bold"), fg=FG, bg=BG2, width=8,
        )
        self._tb_score_label.pack(side=tk.LEFT, padx=(0, 10))
        self._tb_score_bar = tk.Canvas(tb_row3, bg=BG3, height=14, width=200,
                                       highlightthickness=1, highlightbackground=BORDER)
        self._tb_score_bar.pack(side=tk.LEFT)

        # Row 4: Suggested hook
        tk.Label(tb, text="Suggested hook:", font=FONT_LABEL, fg=FG, bg=BG2).pack(anchor="w", pady=(4, 0))
        self._tb_hook_var = tk.StringVar()
        _entry(tb, self._tb_hook_var).pack(fill=tk.X, pady=(2, 0))

        # Row 5: Auto-inject checkbox
        tb_row5 = tk.Frame(tb, bg=BG2)
        tb_row5.pack(fill=tk.X, pady=(6, 4))
        self._tb_autoboost_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            tb_row5, text="Auto-inject trending angle into story prompt",
            variable=self._tb_autoboost_var,
            font=FONT_LABEL, fg=ACCENT, bg=BG2,
            activeforeground=ACCENT, activebackground=BG2,
            selectcolor=BG3,
        ).pack(anchor="w")

        # Row 6: Hashtags
        self._tb_hashtags_var = tk.StringVar(value="")
        tk.Label(tb, text="Hashtags:", font=FONT_LABEL, fg=FG, bg=BG2).pack(anchor="w", pady=(4, 0))
        tk.Label(tb, textvariable=self._tb_hashtags_var,
                 font=FONT_SMALL, fg=ACCENT, bg=BG2,
                 wraplength=560, justify="left").pack(anchor="w", pady=(2, 4))

        # Internal state
        self._tb_trends: list[str] = []
        self._tb_viral_score = None  # ViralScore | None

        # ── Row: Audience · Language · Style ─────────────────────────
        row3 = tk.Frame(sf, bg=BG)
        row3.pack(fill=tk.X, **PAD)
        for title, attr, vals, default, accent in [
            ("👥  AUDIENCE",     "_audience_var",  list(_AUDIENCE_LABELS.keys()), "Family",   ORANGE),
            ("🌐  LANGUAGE",     "_language_var",  list(_LANGUAGE_LABELS.keys()), "Hindi",    MAGENTA),
            ("🎨  VISUAL STYLE", "_style_var",     list(_STYLE_LABELS.keys()),    "✨ AUTO",  PURPLE),
        ]:
            c = _card(row3, title, accent)
            c.master.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            _combo(c, var, vals, width=17).pack(fill=tk.X)

        # ── Scene Count ───────────────────────────────────────────────
        sc = _card(sf, "🎞  SCENE COUNT", YELLOW_N)
        sc.master.pack(fill=tk.X, **PAD)
        self._scene_count_var = tk.IntVar(value=8)
        _ChipSelector(sc, _SCENE_COUNT_OPTIONS, self._scene_count_var, color=YELLOW_N).pack(anchor="w")

        # ── Video Length ──────────────────────────────────────────────
        vl = _card(sf, "⏱  VIDEO LENGTH", GREEN_N)
        vl.master.pack(fill=tk.X, **PAD)
        self._duration_var = tk.DoubleVar(value=0.0)
        dur_row = tk.Frame(vl, bg=BG2)
        dur_row.pack(anchor="w")
        self._dur_btns: dict = {}
        for label, val in _DURATION_OPTIONS:
            is_sel = val == 0.0
            btn = tk.Label(
                dur_row, text=label,
                font=FONT_LABEL,
                fg="#ffffff" if is_sel else FG2,
                bg=GREEN_N if is_sel else BG3,
                padx=10, pady=4, cursor="hand2",
                relief=tk.FLAT,
            )
            btn.pack(side=tk.LEFT, padx=(0, 6), pady=2)
            self._dur_btns[val] = btn
            btn.bind("<Button-1>", lambda e, v=val: self._select_duration(v))

        self._dur_hint = tk.Label(
            vl, text="Auto: LLM decides scene durations",
            font=FONT_SMALL, fg=FG2, bg=BG2,
        )
        self._dur_hint.pack(anchor="w", pady=(2, 0))

        # ── Background Music ──────────────────────────────────────────
        bgm = _card(sf, "🎵  BACKGROUND MUSIC", PURPLE)
        bgm.master.pack(fill=tk.X, **PAD)

        self._bgm_genre_var = tk.StringVar(value="auto")
        genre_row = tk.Frame(bgm, bg=BG2)
        genre_row.pack(fill=tk.X, pady=(0, 6))
        tk.Label(genre_row, text="Style:", font=FONT_LABEL, fg=FG2, bg=BG2).pack(side=tk.LEFT, padx=(0, 8))
        for label, val in [
            ("Auto", "auto"), ("Epic", "epic"), ("Mystery", "mystery"),
            ("Romantic", "romantic"), ("Nature", "nature"),
        ]:
            tk.Button(
                genre_row, text=label, font=("Segoe UI", 9, "bold"),
                bg=BG3, fg=FG2, relief=tk.FLAT, bd=0, padx=8, pady=5, cursor="hand2",
                command=lambda v=val: self._select_bgm_genre(v),
            ).pack(side=tk.LEFT, padx=(0, 4))

        bgm_row = tk.Frame(bgm, bg=BG2)
        bgm_row.pack(fill=tk.X)

        self._bgm_label = tk.Label(
            bgm_row, text="Auto-selected from story",
            font=FONT_LABEL, fg=FG2, bg=BG2, anchor="w",
        )
        self._bgm_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        _GlowButton(bgm_row, "Browse…", self._browse_bgm,
                    color=PURPLE, bg_btn=BG3, fg_btn=PURPLE).pack(side=tk.LEFT, padx=(0, 6))
        _GlowButton(bgm_row, "✕ Clear", self._clear_bgm,
                    color=FG3, bg_btn=BG3, fg_btn=FG2).pack(side=tk.LEFT)

        tk.Label(bgm, text="Auto mode scores all tracks; genre picks a specific file from music/",
                 font=FONT_SMALL, fg=FG3, bg=BG2).pack(anchor="w", pady=(4, 0))

        # ── Quality ───────────────────────────────────────────────────
        qc = _card(sf, "🏆  OUTPUT QUALITY", MAGENTA)
        qc.master.pack(fill=tk.X, **PAD)
        self._quality_var = tk.StringVar(value=QualityPreset.CINEMA.value)
        _QualityGrid(qc, self._quality_var).pack(fill=tk.X)

        # ── Format ────────────────────────────────────────────────────
        fc = _card(sf, "📐  FORMAT", ORANGE)
        fc.master.pack(fill=tk.X, **PAD)
        self._format_var = tk.StringVar(value="landscape")
        _PillSelector(fc, [
            ("🖥  Landscape 4K  (3840×2160)", "landscape"),
            ("📱  Shorts 4K  (2160×3840)", "shorts"),
        ], self._format_var, color=ORANGE).pack(anchor="w")

        # ── Character Names ───────────────────────────────────────────
        cc = _card(sf, "👤  CHARACTER NAMES  (optional)", FG3)
        cc.master.pack(fill=tk.X, **PAD)
        self._char_names_var = tk.StringVar()
        _entry(cc, self._char_names_var).pack(fill=tk.X)
        tk.Label(cc, text='Format: "placeholder=name, ..." comma-separated',
                 font=FONT_SMALL, fg=FG3, bg=BG2).pack(anchor="w", pady=(3, 0))

        # ── Output Directory ──────────────────────────────────────────
        oc = _card(sf, "📁  OUTPUT DIRECTORY", GREEN_N)
        oc.master.pack(fill=tk.X, **PAD)
        out_row = tk.Frame(oc, bg=BG2)
        out_row.pack(fill=tk.X)
        self._output_dir_var = tk.StringVar(value="./output")
        _entry(out_row, self._output_dir_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        _GlowButton(out_row, "Browse…", self._browse_output_dir,
                    color=GREEN_N, bg_btn=BG3).pack(side=tk.LEFT, padx=(0, 6))
        _GlowButton(out_row, "Open", self._open_output_dir,
                    color=GREEN_N, bg_btn=BG3, fg_btn=FG).pack(side=tk.LEFT)

        # Thumbnail preview (left column)
        self._thumb_label = tk.Label(sf, bg=BG, bd=0)
        self._thumb_label.pack(pady=(10, 6))

        # ── Right column: generate, pipeline, quotas, recent ─────────
        tk.Label(right, text="PIPELINE", font=("Segoe UI", 9, "bold"), fg=FG_MUTED, bg=BG_ELEV).pack(anchor="w")
        self._gen_btn = _GlowButton(
            right, "▶  GENERATE VIDEO", self._on_generate,
            color=ACCENT_DIM, bg_btn=ACCENT, fg_btn="#ffffff",
            font=("Segoe UI", 12, "bold"),
        )
        self._gen_btn.pack(fill=tk.X, pady=(6, 10))

        self._shimmer = _ShimmerBar(right)
        self._shimmer.pack(fill=tk.X, pady=(0, 12))

        self._v_pipeline = _VerticalPipeline(right, _PIPELINE_ROWS)
        self._v_pipeline.pack(fill=tk.X, pady=(0, 14))

        self._stage_var = tk.StringVar(value="")
        tk.Label(right, textvariable=self._stage_var,
                 font=("Segoe UI", 9), fg=FG_MUTED, bg=BG_ELEV,
                 wraplength=360, justify="left").pack(anchor="w", pady=(0, 10))

        tk.Label(right, text="API QUOTA TODAY", font=("Segoe UI", 9, "bold"),
                 fg=FG, bg=BG_ELEV).pack(anchor="w", pady=(0, 6))
        self._quota_footer_var = tk.StringVar(value="")
        for lab, attr, lim, col in [
            ("Groq (tokens)", "_quota_groq_canvas", _GROQ_DAILY, ACCENT),
            ("Leonardo (credits)", "_quota_leo_canvas", _LEONARDO_DAILY, MAGENTA),
            ("YouTube API (units)", "_quota_yt_canvas", _YT_UNITS_DAILY, CYAN),
        ]:
            tk.Label(right, text=lab, font=FONT_SMALL, fg=FG_MUTED, bg=BG_ELEV).pack(anchor="w", pady=(4, 0))
            c = tk.Canvas(right, bg=BG_ELEV, height=10, width=340, highlightthickness=0)
            c.pack(fill=tk.X, pady=(2, 0))
            setattr(self, attr, c)
        tk.Label(right, textvariable=self._quota_footer_var, font=FONT_SMALL,
                 fg=FG3, bg=BG_ELEV).pack(anchor="w", pady=(6, 10))

        tk.Label(right, text="RECENT VIDEOS", font=("Segoe UI", 9, "bold"),
                 fg=FG, bg=BG_ELEV).pack(anchor="w", pady=(0, 4))
        recent_fr = tk.Frame(right, bg=BG3, height=180, highlightthickness=1,
                             highlightbackground=BORDER_SOFT)
        recent_fr.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        recent_fr.pack_propagate(False)
        self._recent_inner = tk.Frame(recent_fr, bg=BG3)
        self._recent_inner.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self._refresh_recent_videos()

        foot = tk.Frame(right, bg=BG_ELEV)
        foot.pack(fill=tk.X, side=tk.BOTTOM)
        self._cancel_btn = _GlowButton(
            foot, "Cancel", self._on_cancel,
            color="#e05c5c", bg_btn="#1a0a0a", fg_btn="#e05c5c",
        )
        self._cancel_btn.pack(fill=tk.X, pady=(0, 6))
        self._cancel_btn.config_state("disabled")
        self._folder_btn = _GlowButton(
            foot, "Open Folder", self._open_output_dir,
            color=YELLOW_N, bg_btn=BG3, fg_btn=YELLOW_N,
        )
        self._folder_btn.pack(fill=tk.X)
        self._folder_btn.config_state("disabled")

        # Horizontal step tracker removed — vertical pipeline on the right
        self._step_tracker = None

        self._output_dir_var.trace_add("write", lambda *_: self._refresh_recent_videos())

    # ------------------------------------------------------------------
    # Source input panels
    # ------------------------------------------------------------------
    def _sync_topic_from_text(self, _event=None):
        if hasattr(self, "_topic_text"):
            self._topic_var.set(self._topic_text.get("1.0", tk.END).strip())

    def _build_source_inputs(self, parent: tk.Frame):
        self._topic_frame = tk.Frame(parent, bg=BG2)
        tk.Label(self._topic_frame, text="Describe your story:", font=FONT_LABEL,
                 fg=FG2, bg=BG2).pack(anchor="w", pady=(0, 4))
        self._topic_var = tk.StringVar()
        self._topic_text = tk.Text(
            self._topic_frame, height=5, width=60, bg=BG3, fg=FG,
            insertbackground=ACCENT, relief=tk.FLAT, bd=8, font=FONT_LABEL,
            wrap=tk.WORD,
        )
        self._topic_text.pack(fill=tk.X, expand=True)
        self._topic_text.bind("<KeyRelease>", self._sync_topic_from_text)
        tk.Label(
            self._topic_frame,
            text="e.g. A poor farmer who saves his village from drought",
            font=FONT_SMALL, fg=FG3, bg=BG2,
        ).pack(anchor="w", pady=(4, 0))

        self._script_frame = tk.Frame(parent, bg=BG2)
        self._script_var = tk.StringVar()
        _entry(self._script_frame, self._script_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        _GlowButton(self._script_frame, "Browse…", self._browse_script,
                    color=CYAN, bg_btn=BG3).pack(side=tk.LEFT)

        self._audio_frame = tk.Frame(parent, bg=BG2)
        _GlowButton(self._audio_frame, "🎙  Browse Audio", self._browse_audio,
                    color=MAGENTA, bg_btn=BG3, fg_btn=MAGENTA).pack(side=tk.LEFT, padx=(0, 10))
        self._audio_path_label = tk.Label(self._audio_frame, text="No file selected",
                                          font=FONT_SMALL, fg=FG2, bg=BG2)
        self._audio_path_label.pack(side=tk.LEFT)

        self._image_frame = tk.Frame(parent, bg=BG2)
        _GlowButton(self._image_frame, "🖼  Browse Images", self._browse_images,
                    color=ORANGE, bg_btn=BG3, fg_btn=ORANGE).pack(side=tk.LEFT, padx=(0, 10))
        self._image_paths_label = tk.Label(self._image_frame, text="No images selected",
                                           font=FONT_SMALL, fg=FG2, bg=BG2)
        self._image_paths_label.pack(side=tk.LEFT)

        self._image_ctx_frame = tk.Frame(parent, bg=BG2)
        tk.Label(self._image_ctx_frame, text="Context:", font=FONT_LABEL,
                 fg=FG2, bg=BG2).pack(side=tk.LEFT, padx=(0, 8))
        self._image_context_var = tk.StringVar()
        _entry(self._image_ctx_frame, self._image_context_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _on_source_change(self):
        source = self._source_var.get()
        for f in (self._topic_frame, self._script_frame,
                  self._audio_frame, self._image_frame, self._image_ctx_frame):
            f.pack_forget()
        if source == "topic":
            self._topic_frame.pack(fill=tk.X)
        elif source == "script":
            self._script_frame.pack(fill=tk.X)
        elif source == "audio":
            self._audio_frame.pack(fill=tk.X)
        else:
            self._image_frame.pack(fill=tk.X)
            self._image_ctx_frame.pack(fill=tk.X, pady=(6, 0))

    # ------------------------------------------------------------------
    # Trend Booster handlers
    # ------------------------------------------------------------------
    def _on_fetch_trends(self):
        """Fetch trending angles in a background thread and update UI."""
        if not _TREND_BOOSTER_AVAILABLE:
            messagebox.showwarning(
                "Trend Booster",
                "Required packages not installed.\nRun: pip install pytrends feedparser"
            )
            return

        kw = self._trend_kw_var.get().strip() if hasattr(self, "_trend_kw_var") else ""
        topic = self._topic_var.get().strip() if hasattr(self, "_topic_var") else ""
        fetch_topic = kw or topic or "india trending"

        self._tb_status_var.set("⏳ Fetching trends...")

        def _worker():
            try:
                trends = fetch_trends(fetch_topic)
                hashtags = generate_hashtags(fetch_topic, trends)
                viral = score_topic(fetch_topic, trends)
                self.after(0, lambda: self._apply_trend_results(trends, hashtags, viral))
            except Exception as exc:
                self.after(0, lambda: self._tb_status_var.set(f"⚠ Error: {exc}"))

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_trend_results(self, trends, hashtags, viral):
        """Apply fetched trend data to the UI (called on main thread)."""
        self._tb_trends = trends

        # Update dropdown
        angles = trends if trends else ["No trends found — using fallback"]
        self._tb_angle_combo.configure(values=angles)
        self._tb_angle_combo.current(0)
        self._tb_angle_var.set(angles[0])
        if hasattr(self, "_tb_angle_combo_t"):
            self._tb_angle_combo_t.configure(values=angles)
            self._tb_angle_combo_t.current(0)

        # Update viral score
        self._tb_viral_score = viral
        score_colors = {"red": "#ff4444", "yellow": YELLOW_N, "green": GREEN_N}
        color = score_colors.get(viral.score_color, FG2)
        s100 = viral.score * 10
        self._tb_score_var.set(f"{s100}/100")
        self._tb_score_label.configure(fg=color)

        # Draw score bar (0–100)
        self._tb_score_bar.delete("all")
        bar_w = int(200 * viral.score / 10)
        self._tb_score_bar.create_rectangle(0, 0, bar_w, 14, fill=color, outline="")

        # Update hook
        self._tb_hook_var.set(viral.hook_line)

        # Update hashtags
        self._tb_hashtags_var.set("  ".join(hashtags))

        self._tb_status_var.set(
            f"✅ {len(trends)} trends fetched · Emotion: {viral.dominant_emotion}"
        )

    def _on_angle_selected(self):
        """When user picks a different angle, re-score and update hook."""
        if not _TREND_BOOSTER_AVAILABLE or not self._tb_trends:
            return
        kw = self._trend_kw_var.get().strip() if hasattr(self, "_trend_kw_var") else ""
        topic = self._topic_var.get().strip() if hasattr(self, "_topic_var") else ""
        base = kw or topic
        selected = self._tb_angle_var.get()
        viral = score_topic(base, [selected])
        self._tb_hook_var.set(viral.hook_line)

    def _get_trend_context(self) -> str:
        """Return trend context string if auto-boost is enabled and trends exist."""
        try:
            if not self._tb_autoboost_var.get():
                return ""
            trends = self._tb_trends
            hook = self._tb_hook_var.get().strip()
            if not trends:
                return ""
            parts = [self._tb_angle_var.get()] + [t for t in trends if t != self._tb_angle_var.get()]
            context = "; ".join(parts[:3])
            if hook:
                context += f". Hook: {hook}"
            return context
        except AttributeError:
            return ""

    # ------------------------------------------------------------------
    # Scenes tab — per-scene image preview + re-generate
    # ------------------------------------------------------------------
    def _build_scenes_tab(self, parent: tk.Frame):
        hdr = tk.Frame(parent, bg=BG2, padx=14, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="🖼  SCENE IMAGES", font=("Segoe UI", 10, "bold"),
                 fg=CYAN, bg=BG2).pack(side=tk.LEFT)
        tk.Label(hdr, text="Re-generate any scene image after a run",
                 font=FONT_SMALL, fg=FG2, bg=BG2).pack(side=tk.LEFT, padx=(12, 0))

        # Scrollable canvas for scene cards
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._scenes_frame = tk.Frame(canvas, bg=BG)
        self._scenes_win = canvas.create_window((0, 0), window=self._scenes_frame, anchor="nw")
        self._scenes_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(self._scenes_win, width=e.width))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        self._no_scenes_label = tk.Label(
            self._scenes_frame,
            text="Generate a video first — scene images will appear here.",
            font=FONT_LABEL, fg=FG3, bg=BG, pady=40,
        )
        self._no_scenes_label.pack()

    def _populate_scenes_tab(self, scenes):
        """Fill the Scenes tab with cards for each scene after a successful run."""
        # Clear existing
        for w in self._scenes_frame.winfo_children():
            w.destroy()

        if not scenes:
            tk.Label(self._scenes_frame, text="No scenes available.",
                     font=FONT_LABEL, fg=FG3, bg=BG).pack(pady=40)
            return

        for scene in scenes:
            self._add_scene_card(scene)

    def _add_scene_card(self, scene):
        """Create one scene card with thumbnail + narration + re-generate button."""
        card = tk.Frame(self._scenes_frame, bg=BG2,
                        highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill=tk.X, padx=14, pady=6)

        # Left: thumbnail
        thumb_frame = tk.Frame(card, bg=BG2, width=160, height=90)
        thumb_frame.pack(side=tk.LEFT, padx=(10, 12), pady=10)
        thumb_frame.pack_propagate(False)
        thumb_lbl = tk.Label(thumb_frame, bg=BG3, text="…", fg=FG3,
                             font=FONT_SMALL)
        thumb_lbl.pack(fill=tk.BOTH, expand=True)
        self._load_scene_thumb(scene, thumb_lbl)

        # Right: info + button
        info = tk.Frame(card, bg=BG2)
        info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=10)

        tk.Label(info, text=f"Scene {scene.number:02d}",
                 font=("Segoe UI", 10, "bold"), fg=CYAN, bg=BG2).pack(anchor="w")

        narration_preview = (scene.narration[:120] + "…") if len(scene.narration) > 120 else scene.narration
        tk.Label(info, text=narration_preview, font=FONT_SMALL, fg=FG2, bg=BG2,
                 wraplength=480, justify=tk.LEFT).pack(anchor="w", pady=(2, 6))

        provider_lbl = tk.Label(info, text="", font=FONT_SMALL, fg=FG3, bg=BG2)
        provider_lbl.pack(anchor="w")

        btn_row = tk.Frame(info, bg=BG2)
        btn_row.pack(anchor="w", pady=(4, 0))

        regen_btn = _GlowButton(
            btn_row, "🔄  Re-generate Image", color=ORANGE, bg_btn=BG3, fg_btn=ORANGE,
            command=lambda s=scene, tl=thumb_lbl, pl=provider_lbl: self._regen_scene(s, tl, pl),
        )
        regen_btn.pack(side=tk.LEFT)

        # Store ref so we can disable during regen
        scene._regen_btn = regen_btn  # type: ignore[attr-defined]

    def _load_scene_thumb(self, scene, label: tk.Label):
        """Load scene image as a small thumbnail into the label."""
        try:
            if scene.image_path and Path(scene.image_path).exists():
                from PIL import Image as _Img, ImageTk as _ITk
                img = _Img.open(scene.image_path)
                img.thumbnail((160, 90), _Img.LANCZOS)
                photo = _ITk.PhotoImage(img)
                label.config(image=photo, text="")
                label._photo = photo  # type: ignore[attr-defined]
        except Exception:
            pass

    def _regen_scene(self, scene, thumb_lbl: tk.Label, provider_lbl: tk.Label):
        """Re-generate one scene's image in a background thread."""
        if self._pipeline is None:
            messagebox.showwarning("No Pipeline", "Run a generation first.")
            return

        pipeline = self._pipeline
        style = getattr(pipeline, "last_style", None)
        if style is None:
            messagebox.showwarning("No Style", "Style not available — run a generation first.")
            return

        # Disable button during regen
        if hasattr(scene, "_regen_btn"):
            scene._regen_btn.config_state("disabled")
        provider_lbl.config(text="⏳ Generating…", fg=YELLOW_N)
        self._append_log(f"Re-generating scene {scene.number} image…", "info")

        def worker():
            try:
                pipeline.regenerate_scene_image(scene, style)
                self.after(0, lambda: self._on_regen_done(scene, thumb_lbl, provider_lbl))
            except Exception as exc:
                self.after(0, lambda: self._on_regen_error(scene, provider_lbl, exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_regen_done(self, scene, thumb_lbl: tk.Label, provider_lbl: tk.Label):
        self._load_scene_thumb(scene, thumb_lbl)
        provider = getattr(self._pipeline, "image_generator", None)
        pname = provider.active_provider if provider else "unknown"
        provider_lbl.config(text=f"✅ Done via {pname}", fg=GREEN_N)
        if hasattr(scene, "_regen_btn"):
            scene._regen_btn.config_state("normal")
        self._append_log(f"Scene {scene.number} image updated via {pname}", "ok")

    def _on_regen_error(self, scene, provider_lbl: tk.Label, exc: Exception):
        provider_lbl.config(text=f"❌ {exc}", fg="#e05c5c")
        if hasattr(scene, "_regen_btn"):
            scene._regen_btn.config_state("normal")
        self._append_log(f"Scene {scene.number} regen failed: {exc}", "error")

    # ------------------------------------------------------------------
    # Log tab
    # ------------------------------------------------------------------
    def _build_log(self, parent: tk.Frame):
        hdr = tk.Frame(parent, bg=BG2, padx=14, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="📋  PIPELINE LOG", font=("Segoe UI", 10, "bold"),
                 fg=CYAN, bg=BG2).pack(side=tk.LEFT)
        _GlowButton(hdr, "Clear", self._clear_log,
                    color="#e05c5c", bg_btn=BG3, fg_btn=FG2).pack(side=tk.RIGHT)

        txt_host = tk.Frame(parent, bg=BG)
        txt_host.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        txt_host.rowconfigure(0, weight=1)
        txt_host.columnconfigure(0, weight=1)

        self._log_text = tk.Text(
            txt_host, wrap=tk.WORD, state="disabled",
            bg="#050810", fg="#b0c0e0",
            font=FONT_MONO, relief=tk.FLAT, bd=0,
            selectbackground=CYAN, selectforeground=BG,
        )
        self._log_text.grid(row=0, column=0, sticky="nsew")
        self._log_text.tag_config("info",  foreground=CYAN)
        self._log_text.tag_config("warn",  foreground=YELLOW_N)
        self._log_text.tag_config("error", foreground="#e05c5c")
        self._log_text.tag_config("ok",    foreground=GREEN_N)

        sb = ttk.Scrollbar(txt_host, orient=tk.VERTICAL, command=self._log_text.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self._log_text.configure(yscrollcommand=sb.set)

    # ------------------------------------------------------------------
    # Browse helpers
    # ------------------------------------------------------------------
    def _browse_script(self):
        p = filedialog.askopenfilename(title="Select Script",
                                       filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if p:
            self._script_var.set(p)

    def _browse_output_dir(self):
        p = filedialog.askdirectory(title="Select Output Directory")
        if p:
            self._output_dir_var.set(p)

    def _browse_audio(self):
        p = filedialog.askopenfilename(
            title="Select Audio",
            filetypes=[("Audio", "*.mp3 *.wav *.m4a *.ogg *.flac"), ("All", "*.*")])
        if p:
            self._audio_file_path = p
            self._audio_path_label.config(text=Path(p).name, fg=MAGENTA)

    def _browse_bgm(self):
        p = filedialog.askopenfilename(
            title="Select Custom BGM",
            filetypes=[("Audio", "*.mp3 *.wav *.m4a *.ogg *.flac"), ("All", "*.*")])
        if p:
            self._bgm_path = p
            if hasattr(self, "_bgm_genre_var"):
                self._bgm_genre_var.set("auto")
            self._bgm_label.config(text=f"🎵  {Path(p).name}", fg=GREEN_N)
        else:
            self._bgm_path = None
            self._bgm_label.config(text="Auto-selected from story", fg=FG2)

    def _clear_bgm(self):
        self._bgm_path = None
        if hasattr(self, "_bgm_genre_var"):
            self._bgm_genre_var.set("auto")
        self._bgm_label.config(text="Auto-selected from story", fg=FG2)

    def _select_bgm_genre(self, val: str):
        self._bgm_path = None
        self._bgm_genre_var.set(val)
        if val == "auto":
            self._bgm_label.config(text="Auto-selected from story", fg=FG2)
            return
        name = {"epic": "epic.mp3", "mystery": "mystery.mp3",
                "romantic": "romantic.mp3", "nature": "nature.mp3"}.get(val, "")
        self._bgm_label.config(text=f"Genre → music/{name}", fg=GREEN_N)

    def _resolve_bgm_path(self) -> Optional[str]:
        if self._bgm_path:
            return self._bgm_path
        g = self._bgm_genre_var.get() if hasattr(self, "_bgm_genre_var") else "auto"
        if g == "auto":
            return None
        name = {"epic": "epic.mp3", "mystery": "mystery.mp3",
                "romantic": "romantic.mp3", "nature": "nature.mp3"}.get(g)
        if not name:
            return None
        p = Path("music") / name
        return str(p.resolve()) if p.exists() else None

    def _refresh_recent_videos(self):
        if not hasattr(self, "_recent_inner"):
            return
        for w in self._recent_inner.winfo_children():
            w.destroy()
        root = Path(self._output_dir_var.get().strip() or "./output")
        if not root.is_dir():
            tk.Label(self._recent_inner, text="Output folder not found.",
                     font=FONT_SMALL, fg=FG3, bg=BG3).pack(anchor="w")
            return
        dirs = sorted(
            [p for p in root.iterdir() if p.is_dir() and (p / "video.mp4").exists()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:8]
        if not dirs:
            tk.Label(self._recent_inner, text="No videos yet.",
                     font=FONT_SMALL, fg=FG3, bg=BG3).pack(anchor="w")
            return
        for d in dirs:
            meta = d / "metadata.txt"
            title = d.name
            if meta.exists():
                try:
                    line = meta.read_text(encoding="utf-8", errors="ignore").splitlines()[0]
                    if line.strip():
                        title = line.strip()[:48]
                except Exception:
                    pass
            row = tk.Frame(self._recent_inner, bg=BG3)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text="●", font=FONT_SMALL, fg=GREEN_N, bg=BG3).pack(side=tk.LEFT)
            tk.Label(row, text=title, font=FONT_SMALL, fg=FG, bg=BG3,
                     wraplength=280, justify="left").pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _browse_images(self):
        paths = filedialog.askopenfilenames(
            title="Select Images",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.webp"), ("All", "*.*")])
        if paths:
            self._image_file_paths = list(paths)
            n = len(self._image_file_paths)
            self._image_paths_label.config(
                text=f"{n} image{'s' if n != 1 else ''} selected", fg=ORANGE)

    def _parse_character_names(self, raw: str) -> dict:
        result = {}
        for pair in raw.split(","):
            if "=" in pair:
                k, _, v = pair.strip().partition("=")
                if k.strip() and v.strip():
                    result[k.strip()] = v.strip()
        return result

    def _select_duration(self, val: float):
        self._duration_var.set(val)
        for v, btn in self._dur_btns.items():
            selected = v == val
            btn.config(fg="#ffffff" if selected else FG2,
                       bg=GREEN_N if selected else BG3)
        if val == 0.0:
            self._dur_hint.config(text="Auto: LLM decides scene durations")
        else:
            sc = self._scene_count_var.get()
            secs = max(4.0, min((val * 60) / sc, 30.0))
            self._dur_hint.config(
                text=f"~{val:.0f} min total · ~{secs:.0f}s per scene ({sc} scenes)"
            )

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------
    def _on_generate(self):
        self._sync_topic_from_text()
        source = self._source_var.get()
        topic = self._topic_var.get().strip()
        script_file = self._script_var.get().strip() or None

        if source == "topic" and not topic:
            messagebox.showerror("Validation", "Please enter a topic.")
            return
        if source == "script" and (not script_file or not Path(script_file).is_file()):
            messagebox.showerror("Validation", "Please select a valid script file.")
            return
        if source == "audio" and not self._audio_file_path:
            messagebox.showerror("Validation", "Please select an audio file.")
            return
        if source == "image" and not self._image_file_paths:
            messagebox.showerror("Validation", "Please select at least one image.")
            return

        output_dir = Path(self._output_dir_var.get().strip() or "./output")
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Output Directory Error", str(exc))
            return

        cfg = PipelineConfig(
            topic=topic if source == "topic" else "",
            script_file=script_file if source == "script" else None,
            audience=_AUDIENCE_LABELS.get(self._audience_var.get(), Audience.FAMILY),
            language=_LANGUAGE_LABELS.get(self._language_var.get(), Language.HI),
            style=_STYLE_LABELS.get(self._style_var.get(), VisualStyle.AUTO),
            format=VideoFormat(self._format_var.get()),
            character_names=self._parse_character_names(self._char_names_var.get()),
            output_dir=output_dir,
            use_edge_tts=self.app_config.use_edge_tts,
            groq_api_key=self.app_config.groq_api_key,
            leonardo_api_key=self.app_config.leonardo_api_key,
            input_mode={"topic": InputMode.TOPIC, "script": InputMode.SCRIPT,
                        "audio": InputMode.AUDIO, "image": InputMode.IMAGE}[source],
            audio_file=self._audio_file_path if source == "audio" else None,
            image_files=list(self._image_file_paths) if source == "image" else [],
            image_context=self._image_context_var.get().strip() if source == "image" else "",
            scene_count=self._scene_count_var.get(),
            quality=QualityPreset(self._quality_var.get()),
            target_duration_minutes=self._duration_var.get(),
            custom_music_path=self._resolve_bgm_path(),
            hf_token=self.app_config.hf_token,
            trend_context=self._get_trend_context(),
        )
        self._output_dir = output_dir
        self._start_pipeline(cfg)

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------
    def _start_pipeline(self, cfg: PipelineConfig):
        self._queue = queue.Queue()
        self._cancel_event.clear()
        self._start_time = time.monotonic()

        if self._log_handler:
            logging.getLogger().removeHandler(self._log_handler)
        self._log_handler = _QueueLogHandler(self._queue)
        self._log_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                              datefmt="%H:%M:%S"))
        logging.getLogger().addHandler(self._log_handler)

        self._gen_btn.config_state("disabled")
        self._cancel_btn.config_state("normal")
        self._folder_btn.config_state("disabled")
        self._shimmer.start(ACCENT)
        if self._v_pipeline:
            self._v_pipeline.reset()
        self._top_ready_var.set("Running…")
        if hasattr(self, "_top_ready_dot"):
            self._top_ready_dot.config(fg=ACCENT)
        self._stage_var.set("⏳  Initialising…")
        self._status_var.set("Pipeline running…")
        self._elapsed_var.set("")
        self._clear_thumbnail()

        def worker():
            try:
                p = Pipeline(cfg, self._enqueue_progress)
                result = p.run()
                self._queue.put(("done", result, p))
            except Exception as exc:
                self._queue.put(("error", exc))

        threading.Thread(target=worker, daemon=True).start()
        self._poll()

    def _enqueue_progress(self, stage: str, scene: int, total: int):
        if self._queue:
            self._queue.put(("progress", stage, scene, total))

    def _poll(self):
        try:
            while True:
                msg = self._queue.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    self._on_progress(msg[1], msg[2], msg[3])
                elif kind == "log":
                    self._append_log(msg[1])
                elif kind == "done":
                    self._on_complete(msg[1], msg[2])
                    return
                elif kind == "error":
                    self._on_error(msg[1])
                    return
        except queue.Empty:
            pass
        elapsed = time.monotonic() - self._start_time
        self._elapsed_var.set(f"⏱  {elapsed:.0f}s")
        self.after(100, self._poll)

    def _on_progress(self, stage: str, scene: int, total: int):
        label = f"⚙  {stage}" + (f"  —  scene {scene}/{total}" if total > 0 else "")
        self._stage_var.set(label)
        if self._v_pipeline:
            self._v_pipeline.set_from_progress(stage, scene, total)

    def _on_complete(self, result: PipelineResult, pipeline=None):
        elapsed = time.monotonic() - self._start_time
        self._shimmer.stop(success=True)
        if self._v_pipeline:
            self._v_pipeline.complete_all()
        self._stage_var.set("✅  Complete!")
        self._elapsed_var.set(f"✅  {elapsed:.1f}s")
        self._status_var.set(f"Saved → {result.output_path}")
        self._top_ready_var.set(f"Ready · v{RAGAI_VERSION}")
        if hasattr(self, "_top_ready_dot"):
            self._top_ready_dot.config(fg=GREEN_N)
        _record_quota_after_video()
        self._refresh_quota_bars()
        self._refresh_recent_videos()
        self._gen_btn.config_state("normal")
        self._cancel_btn.config_state("disabled")
        self._folder_btn.config_state("normal")
        self._append_log(f"✅ Done in {elapsed:.1f}s → {result.output_path}", "ok")
        self._show_thumbnail(result.thumbnail_path)
        # Store pipeline for scene re-generate and populate Scenes tab
        if pipeline is not None:
            self._pipeline = pipeline
            self._populate_scenes_tab(result.scenes)
        self._nb.select(0)
        self._remove_log_handler()

    def _on_error(self, exc: Exception):
        elapsed = time.monotonic() - self._start_time
        self._shimmer.stop(success=False)
        self._stage_var.set("❌  Error")
        self._elapsed_var.set(f"❌  {elapsed:.1f}s")
        self._status_var.set(f"Error: {exc}")
        self._top_ready_var.set("Error — see Live Log")
        if hasattr(self, "_top_ready_dot"):
            self._top_ready_dot.config(fg="#e57373")
        self._gen_btn.config_state("normal")
        self._cancel_btn.config_state("disabled")
        self._append_log(f"❌ {exc}", "error")
        messagebox.showerror("Pipeline Error", str(exc))
        self._remove_log_handler()

    def _on_cancel(self):
        self._cancel_event.set()
        self._cancel_btn.config_state("disabled")
        self._stage_var.set("⚠  Cancelling…")
        self._append_log("⚠️  Cancel requested…", "warn")

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------
    def _append_log(self, text: str, tag: str = ""):
        self._log_text.config(state="normal")
        if not tag:
            tag = ("error" if "[ERROR]" in text else
                   "warn"  if "[WARNING]" in text else "info")
        self._log_text.insert(tk.END, text + "\n", tag)
        self._log_text.see(tk.END)
        self._log_text.config(state="disabled")

    def _clear_log(self):
        self._log_text.config(state="normal")
        self._log_text.delete("1.0", tk.END)
        self._log_text.config(state="disabled")

    def _remove_log_handler(self):
        if self._log_handler:
            logging.getLogger().removeHandler(self._log_handler)
            self._log_handler = None

    # ------------------------------------------------------------------
    # Thumbnail
    # ------------------------------------------------------------------
    def _show_thumbnail(self, thumb_path: Path):
        if not thumb_path.exists():
            return
        try:
            from PIL import Image, ImageTk
            img = Image.open(thumb_path)
            img.thumbnail((540, 304), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._thumb_label.config(image=photo, bg=BG)
            self._thumb_label._photo = photo
        except Exception:
            pass

    def _clear_thumbnail(self):
        self._thumb_label.config(image="")

    # ------------------------------------------------------------------
    # Open folder
    # ------------------------------------------------------------------
    def _open_output_dir(self):
        target = (self._output_dir or Path(
            self._output_dir_var.get().strip() or "./output")).resolve()
        if sys.platform == "win32":
            os.startfile(str(target))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
