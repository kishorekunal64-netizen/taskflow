"""
gui.py — Professional animated GUI for RAGAI Video Factory.

Design:
  - Deep space dark theme with vibrant neon accents
  - Animated gradient header (cycling hue)
  - Glowing buttons with hover pulse
  - Animated shimmer progress bar
  - Colour-coded quality cards with glow borders
  - Animated stage step tracker
  - Floating particle background
"""

from __future__ import annotations

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

from config import AppConfig
from models import (
    Audience, InputMode, Language, PipelineConfig, PipelineResult,
    QualityPreset, QUALITY_CONFIGS, VideoFormat, VisualStyle,
)
from pipeline import Pipeline

# ---------------------------------------------------------------------------
# Colour system
# ---------------------------------------------------------------------------
BG          = "#080b12"   # deep space black
BG2         = "#0e1420"   # card background
BG3         = "#141c2e"   # input background
BORDER      = "#1e2a42"   # subtle border

# Neon accents
CYAN        = "#00d4ff"
MAGENTA     = "#ff00aa"
ORANGE      = "#ff6b00"
GREEN_N     = "#00ff88"
PURPLE      = "#8b5cf6"
YELLOW_N    = "#ffd700"

FG          = "#e8f0ff"
FG2         = "#6b7a99"
FG3         = "#3a4560"

FONT_HERO   = ("Segoe UI", 26, "bold")
FONT_TITLE  = ("Segoe UI", 13, "bold")
FONT_LABEL  = ("Segoe UI", 10)
FONT_SMALL  = ("Segoe UI", 8)
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

# Pipeline stage names for step tracker
_STAGES = ["Story", "Images", "Voice", "Assembly", "Done"]


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
# Animated canvas header
# ---------------------------------------------------------------------------
class _AnimatedHeader(tk.Canvas):
    """Canvas that cycles a gradient, draws the app title,
    and floats 'Radha' & 'Gauri' as glowing drifting name particles."""

    _HUE_PAIRS = [
        ("#00d4ff", "#8b5cf6"),
        ("#8b5cf6", "#ff00aa"),
        ("#ff00aa", "#ff6b00"),
        ("#ff6b00", "#ffd700"),
        ("#ffd700", "#00ff88"),
        ("#00ff88", "#00d4ff"),
    ]

    # Name particles: (text, color, x_frac, y_frac, speed_x, speed_y, alpha, fade_dir)
    _NAMES = [
        {"text": "Radha",  "color": "#ff88cc", "x": 0.12, "y": 0.35,
         "vx": 0.0003, "vy": -0.0008, "alpha": 0.0, "fade": 1, "size": 14},
        {"text": "Gauri",  "color": "#88ddff", "x": 0.78, "y": 0.55,
         "vx": -0.0002, "vy": 0.0006, "alpha": 0.0, "fade": 1, "size": 14},
        {"text": "✦ Radha", "color": "#ffaaee", "x": 0.55, "y": 0.25,
         "vx": 0.0001, "vy": 0.0005, "alpha": 0.5, "fade": 1, "size": 10},
        {"text": "Gauri ✦", "color": "#aaeeff", "x": 0.30, "y": 0.70,
         "vx": -0.0003, "vy": -0.0004, "alpha": 0.8, "fade": -1, "size": 10},
    ]

    def __init__(self, parent, **kw):
        super().__init__(parent, height=120, bg=BG, highlightthickness=0, **kw)
        self._phase = 0.0
        self._pair_idx = 0
        self._particles = [dict(p) for p in self._NAMES]
        self._animate()

    def _hex_to_rgb(self, h: str):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    def _lerp_color(self, c1, c2, t):
        r = int(c1[0] + (c2[0]-c1[0])*t)
        g = int(c1[1] + (c2[1]-c1[1])*t)
        b = int(c1[2] + (c2[2]-c1[2])*t)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _alpha_color(self, hex_color: str, alpha: float) -> str:
        """Blend hex_color toward BG by alpha (0=invisible, 1=full color)."""
        bg = self._hex_to_rgb(BG)
        fg = self._hex_to_rgb(hex_color)
        r = int(bg[0] + (fg[0]-bg[0])*alpha)
        g = int(bg[1] + (fg[1]-bg[1])*alpha)
        b = int(bg[2] + (fg[2]-bg[2])*alpha)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _animate(self):
        self.delete("all")
        w = self.winfo_width() or 900
        h = 120

        # Gradient background bands
        pair = self._HUE_PAIRS[self._pair_idx]
        c1 = self._hex_to_rgb(pair[0])
        c2 = self._hex_to_rgb(pair[1])
        bands = 80
        for i in range(bands):
            t = i / bands
            t_mod = (t + 0.25 * math.sin(self._phase + t * math.pi * 2)) % 1.0
            color = self._lerp_color(c1, c2, t_mod)
            x0 = int(i * w / bands)
            x1 = int((i+1) * w / bands) + 1
            self.create_rectangle(x0, 0, x1, h, fill=color, outline="")

        # Dark overlay
        self.create_rectangle(0, 0, w, h, fill=BG, stipple="gray50", outline="")

        # Glowing bottom border
        next_pair = self._HUE_PAIRS[(self._pair_idx + 1) % len(self._HUE_PAIRS)]
        t_line = (math.sin(self._phase) + 1) / 2
        line_color = self._lerp_color(
            self._hex_to_rgb(pair[0]), self._hex_to_rgb(next_pair[1]), t_line
        )
        self.create_rectangle(0, h-3, w, h, fill=line_color, outline="")

        # ── Floating name particles ───────────────────────────────────
        for p in self._particles:
            # Update position
            p["x"] = (p["x"] + p["vx"]) % 1.0
            p["y"] = (p["y"] + p["vy"]) % 1.0

            # Fade in/out
            p["alpha"] += p["fade"] * 0.012
            if p["alpha"] >= 1.0:
                p["alpha"] = 1.0
                p["fade"] = -1
            elif p["alpha"] <= 0.0:
                p["alpha"] = 0.0
                p["fade"] = 1

            px = int(p["x"] * w)
            py = int(p["y"] * h)
            color = self._alpha_color(p["color"], p["alpha"])
            size = p["size"]

            # Glow layers (larger, more transparent)
            for glow_r in range(3, 0, -1):
                glow_alpha = p["alpha"] * (glow_r / 6)
                glow_color = self._alpha_color(p["color"], glow_alpha)
                self.create_text(px + glow_r, py + glow_r,
                                 text=p["text"],
                                 font=("Segoe UI", size, "bold"),
                                 fill=glow_color, anchor="center")

            # Main text
            self.create_text(px, py, text=p["text"],
                             font=("Segoe UI", size, "bold"),
                             fill=color, anchor="center")

        # ── App title ─────────────────────────────────────────────────
        cx = w // 2
        # Shadow
        self.create_text(cx+2, 44, text="🎬  RAGAI",
                         font=("Segoe UI", 26, "bold"), fill="#000000", anchor="center")
        # Main title
        self.create_text(cx, 42, text="🎬  RAGAI",
                         font=("Segoe UI", 26, "bold"), fill=line_color, anchor="center")
        # Subtitle
        self.create_text(cx, 78, text="AI  VIDEO  FACTORY  ·  CINEMATIC  4K",
                         font=("Segoe UI", 10, "bold"), fill=FG2, anchor="center")

        # Advance
        self._phase += 0.04
        if self._phase > math.pi * 2:
            self._phase = 0.0
            self._pair_idx = (self._pair_idx + 1) % len(self._HUE_PAIRS)

        self.after(50, self._animate)


# ---------------------------------------------------------------------------
# Animated shimmer progress bar
# ---------------------------------------------------------------------------
class _ShimmerBar(tk.Canvas):
    """Custom animated progress bar with shimmer sweep."""

    def __init__(self, parent, **kw):
        super().__init__(parent, height=8, bg=BG3,
                         highlightthickness=1, highlightbackground=BORDER, **kw)
        self._active = False
        self._shimmer_x = 0
        self._color = CYAN

    def start(self, color=CYAN):
        self._active = True
        self._color = color
        self._shimmer_x = 0
        self._animate()

    def stop(self, success=True):
        self._active = False
        self.delete("all")
        w = self.winfo_width() or 800
        fill = GREEN_N if success else "#e05c5c"
        self.create_rectangle(0, 0, w, 8, fill=fill, outline="")

    def reset(self):
        self._active = False
        self.delete("all")

    def _animate(self):
        if not self._active:
            return
        self.delete("all")
        w = self.winfo_width() or 800
        # Base fill
        self.create_rectangle(0, 0, w, 8, fill=BG3, outline="")
        # Animated fill (bouncing)
        t = (math.sin(self._shimmer_x * 0.05) + 1) / 2
        fill_w = int(w * (0.3 + 0.5 * t))
        self.create_rectangle(0, 0, fill_w, 8, fill=self._color, outline="")
        # Shimmer sweep
        sx = int((self._shimmer_x % w))
        sw = 80
        for i in range(sw):
            alpha = 1.0 - abs(i - sw//2) / (sw//2)
            r, g, b = 255, 255, 255
            c = f"#{int(r*alpha):02x}{int(g*alpha):02x}{int(b*alpha):02x}"
            self.create_line(sx + i, 0, sx + i, 8, fill=c)
        self._shimmer_x += 4
        self.after(30, self._animate)


# ---------------------------------------------------------------------------
# Glow button
# ---------------------------------------------------------------------------
class _GlowButton(tk.Frame):
    """Button with animated glow border on hover."""

    def __init__(self, parent, text, command, color=CYAN,
                 bg_btn=BG2, fg_btn=FG, width=None, font=FONT_BTN, **kw):
        super().__init__(parent, bg=color, padx=2, pady=2)
        self._color = color
        self._bg = bg_btn
        self._active = False
        inner_kw = {"width": width} if width else {}
        self._btn = tk.Button(
            self, text=text, command=command,
            bg=bg_btn, fg=fg_btn,
            activebackground=color, activeforeground=BG,
            relief=tk.FLAT, bd=0, padx=16, pady=9,
            font=font, cursor="hand2", **inner_kw,
        )
        self._btn.pack(fill=tk.BOTH, expand=True)
        self._btn.bind("<Enter>", self._on_enter)
        self._btn.bind("<Leave>", self._on_leave)
        self._glow_phase = 0

    def _on_enter(self, _=None):
        self._active = True
        self._btn.config(bg=self._color, fg=BG)
        self._pulse()

    def _on_leave(self, _=None):
        self._active = False
        self._btn.config(bg=self._bg, fg=FG)
        self.config(bg=self._color, padx=2, pady=2)

    def _pulse(self):
        if not self._active:
            return
        self._glow_phase += 0.3
        pad = int(2 + math.sin(self._glow_phase) * 1.5)
        self.config(padx=pad, pady=pad)
        self.after(40, self._pulse)

    def config_state(self, state):
        self._btn.config(state=state)
        if state == "disabled":
            self._btn.config(bg=BG3, fg=FG3)
        else:
            self._btn.config(bg=self._bg, fg=FG)


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
                self.create_text(cx, cy, text="✓", font=("Segoe UI", 9, "bold"), fill=BG)
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
# Pill selector (source / format)
# ---------------------------------------------------------------------------
class _PillSelector(tk.Frame):
    def __init__(self, parent, options, variable, color=CYAN, **kw):
        super().__init__(parent, bg=BG2, **kw)
        self._var = variable
        self._btns = {}
        self._color = color
        for label, val in options:
            btn = tk.Button(
                self, text=label, font=("Segoe UI", 9, "bold"),
                bg=BG3, fg=FG2, relief=tk.FLAT, bd=0,
                padx=14, pady=7, cursor="hand2",
                activebackground=color, activeforeground=BG,
                command=lambda v=val: self._select(v),
            )
            btn.pack(side=tk.LEFT, padx=(0, 4))
            self._btns[val] = btn
        variable.trace_add("write", lambda *_: self._refresh())
        self._refresh()

    def _select(self, val):
        self._var.set(val)

    def _refresh(self):
        cur = self._var.get()
        for val, btn in self._btns.items():
            if val == cur:
                btn.config(bg=self._color, fg=BG)
            else:
                btn.config(bg=BG3, fg=FG2)


# ---------------------------------------------------------------------------
# Chip selector (scene count)
# ---------------------------------------------------------------------------
class _ChipSelector(tk.Frame):
    def __init__(self, parent, options, variable, color=PURPLE, **kw):
        super().__init__(parent, bg=BG2, **kw)
        self._var = variable
        self._btns = {}
        self._color = color
        for val in options:
            btn = tk.Button(
                self, text=str(val), font=("Segoe UI", 11, "bold"),
                bg=BG3, fg=FG2, relief=tk.FLAT, bd=0,
                width=3, pady=6, cursor="hand2",
                activebackground=color, activeforeground=BG,
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
                       fg=BG if val == cur else FG2)


# ---------------------------------------------------------------------------
# Quality card grid
# ---------------------------------------------------------------------------
class _QualityGrid(tk.Frame):
    def __init__(self, parent, variable, **kw):
        super().__init__(parent, bg=BG2, **kw)
        self._var = variable
        self._frames = {}
        for q in QualityPreset:
            card_bg, glow, label = _Q_THEME[q]
            spec = _Q_SPEC[q]
            f = tk.Frame(self, bg=card_bg, cursor="hand2",
                         highlightthickness=2, highlightbackground=BORDER,
                         padx=10, pady=10)
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
            f.config(highlightbackground=glow if sel else BORDER,
                     highlightthickness=2 if sel else 1,
                     bg=card_bg)
            for w in (il, nl, sl):
                w.config(bg=card_bg)


# ---------------------------------------------------------------------------
# Dark styled entry / combo helpers
# ---------------------------------------------------------------------------
def _entry(parent, var, **kw) -> tk.Entry:
    return tk.Entry(parent, textvariable=var, bg=BG3, fg=FG,
                    insertbackground=CYAN, relief=tk.FLAT, bd=6,
                    font=FONT_LABEL, **kw)


def _combo(parent, var, values, width=18) -> ttk.Combobox:
    s = ttk.Style()
    s.theme_use("clam")
    s.configure("N.TCombobox", fieldbackground=BG3, background=BG3,
                foreground=FG, selectbackground=CYAN, selectforeground=BG,
                arrowcolor=CYAN, bordercolor=BORDER,
                lightcolor=BORDER, darkcolor=BORDER)
    s.map("N.TCombobox", fieldbackground=[("readonly", BG3)],
          foreground=[("readonly", FG)])
    return ttk.Combobox(parent, textvariable=var, values=values,
                        state="readonly", width=width,
                        style="N.TCombobox", font=FONT_LABEL)


def _card(parent, title: str, accent=CYAN) -> tk.Frame:
    outer = tk.Frame(parent, bg=accent, padx=1, pady=1)
    inner = tk.Frame(outer, bg=BG2, padx=12, pady=10)
    inner.pack(fill=tk.BOTH, expand=True)
    tk.Label(inner, text=title, font=("Segoe UI", 9, "bold"),
             fg=accent, bg=BG2).pack(anchor="w", pady=(0, 8))
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
        self.minsize(900, 820)
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
        s.configure("TNotebook", background=BG, borderwidth=0, tabmargins=[0, 0, 0, 0])
        s.configure("TNotebook.Tab", background=BG2, foreground=FG2,
                    padding=[20, 10], font=("Segoe UI", 10, "bold"), borderwidth=0)
        s.map("TNotebook.Tab",
              background=[("selected", BG3), ("active", BG3)],
              foreground=[("selected", CYAN), ("active", FG)])
        s.configure("TScrollbar", background=BG3, troughcolor=BG,
                    bordercolor=BORDER, arrowcolor=FG2, relief=tk.FLAT)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_ui(self):
        # Animated header
        self._header = _AnimatedHeader(self)
        self._header.pack(fill=tk.X)

        # Notebook
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        settings_host = tk.Frame(self._nb, bg=BG)
        self._nb.add(settings_host, text="  ⚙  Settings  ")

        scenes_host = tk.Frame(self._nb, bg=BG)
        self._nb.add(scenes_host, text="  🖼  Scenes  ")

        log_host = tk.Frame(self._nb, bg=BG)
        self._nb.add(log_host, text="  📋  Live Log  ")

        self._build_settings(settings_host)
        self._build_scenes_tab(scenes_host)
        self._build_log(log_host)
        self._build_statusbar()

    def _build_statusbar(self):
        bar = tk.Frame(self, bg=BG2)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Frame(bar, bg=CYAN, height=1).pack(fill=tk.X)
        row = tk.Frame(bar, bg=BG2, padx=14, pady=6)
        row.pack(fill=tk.X)
        self._status_var = tk.StringVar(value="Ready  ·  Select a topic and hit Generate")
        tk.Label(row, textvariable=self._status_var,
                 font=FONT_SMALL, fg=FG2, bg=BG2).pack(side=tk.LEFT)
        self._elapsed_var = tk.StringVar(value="")
        tk.Label(row, textvariable=self._elapsed_var,
                 font=("Segoe UI", 9, "bold"), fg=CYAN, bg=BG2).pack(side=tk.RIGHT)

    def _build_settings(self, parent: tk.Frame):
        # Scrollable canvas
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sf = tk.Frame(canvas, bg=BG)
        win = canvas.create_window((0, 0), window=sf, anchor="nw")
        sf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        PAD = {"padx": 14, "pady": 5}

        # ── Story Source ──────────────────────────────────────────────
        src = _card(sf, "📖  STORY SOURCE", CYAN)
        src.master.pack(fill=tk.X, **PAD)
        self._source_var = tk.StringVar(value="topic")
        _PillSelector(src, [
            ("🖊  Topic", "topic"), ("📄  Script", "script"),
            ("🎙  Audio", "audio"), ("🖼  Images", "image"),
        ], self._source_var, color=CYAN).pack(anchor="w", pady=(0, 10))

        self._src_input_host = tk.Frame(src, bg=BG2)
        self._src_input_host.pack(fill=tk.X)
        self._build_source_inputs(self._src_input_host)
        self._source_var.trace_add("write", lambda *_: self._on_source_change())
        self._on_source_change()

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
                fg=BG if is_sel else FG2,
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

        tk.Label(bgm, text="Auto mode scores all tracks against your topic keywords",
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
                    color=GREEN_N, bg_btn=BG3).pack(side=tk.LEFT)

        # ── Action buttons ────────────────────────────────────────────
        btn_row = tk.Frame(sf, bg=BG)
        btn_row.pack(fill=tk.X, padx=14, pady=(10, 6))

        self._gen_btn = _GlowButton(
            btn_row, "▶   GENERATE VIDEO", self._on_generate,
            color=CYAN, bg_btn="#0a1a2a", fg_btn=CYAN,
            font=("Segoe UI", 12, "bold"),
        )
        self._gen_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self._cancel_btn = _GlowButton(
            btn_row, "✕  Cancel", self._on_cancel,
            color="#e05c5c", bg_btn="#1a0a0a", fg_btn="#e05c5c",
        )
        self._cancel_btn.pack(side=tk.LEFT, padx=(0, 8))
        self._cancel_btn.config_state("disabled")

        self._folder_btn = _GlowButton(
            btn_row, "📂  Open Folder", self._open_output_dir,
            color=GREEN_N, bg_btn=BG3, fg_btn=FG2,
        )
        self._folder_btn.pack(side=tk.LEFT)
        self._folder_btn.config_state("disabled")

        # ── Step tracker ──────────────────────────────────────────────
        self._step_tracker = _StepTracker(sf, _STAGES)
        self._step_tracker.pack(fill=tk.X, padx=14, pady=(8, 2))

        # ── Shimmer progress bar ──────────────────────────────────────
        self._shimmer = _ShimmerBar(sf)
        self._shimmer.pack(fill=tk.X, padx=14, pady=(4, 2))

        # Stage label
        self._stage_var = tk.StringVar(value="")
        tk.Label(sf, textvariable=self._stage_var,
                 font=("Segoe UI", 9, "italic"), fg=CYAN, bg=BG,
                 ).pack(anchor="w", padx=16, pady=(2, 0))

        # Thumbnail
        self._thumb_label = tk.Label(sf, bg=BG, bd=0)
        self._thumb_label.pack(pady=(10, 6))

    # ------------------------------------------------------------------
    # Source input panels
    # ------------------------------------------------------------------
    def _build_source_inputs(self, parent: tk.Frame):
        self._topic_frame = tk.Frame(parent, bg=BG2)
        tk.Label(self._topic_frame, text="Topic:", font=FONT_LABEL,
                 fg=FG2, bg=BG2).pack(side=tk.LEFT, padx=(0, 8))
        self._topic_var = tk.StringVar()
        _entry(self._topic_frame, self._topic_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

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
            self._bgm_label.config(text=f"🎵  {Path(p).name}", fg=GREEN_N)
        else:
            self._bgm_path = None
            self._bgm_label.config(text="Auto-selected from story", fg=FG2)

    def _clear_bgm(self):
        self._bgm_path = None
        self._bgm_label.config(text="Auto-selected from story", fg=FG2)

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
            btn.config(fg=BG if selected else FG2,
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
            custom_music_path=self._bgm_path or None,
            hf_token=self.app_config.hf_token,
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
        self._shimmer.start(CYAN)
        self._step_tracker.reset()
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
        self._step_tracker.set_stage(stage)
        self._nb.select(1)

    def _on_complete(self, result: PipelineResult, pipeline=None):
        elapsed = time.monotonic() - self._start_time
        self._shimmer.stop(success=True)
        self._step_tracker.complete()
        self._stage_var.set("✅  Complete!")
        self._elapsed_var.set(f"✅  {elapsed:.1f}s")
        self._status_var.set(f"Saved → {result.output_path}")
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
