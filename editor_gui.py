"""
editor_gui.py - Main Tkinter GUI for RAGAI Editor V2.

Layout:
  LEFT   - Clip Library (thumbnail grid, search/filter)
  CENTER - Visual Timeline editor with total duration display
  RIGHT  - Export settings, estimates, PREVIEW button, EXPORT, AUTO MODE
"""
from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from clip_manager import ClipManager, Clip
from timeline import TimelineCanvas
from assembler import Assembler
from auto_pipeline import AutoPipeline
from watcher import OutputWatcher
from smart_compiler import SmartCompiler

logger = logging.getLogger(__name__)

BG       = "#080b12"
BG2      = "#0e1420"
BG3      = "#141c2e"
BORDER   = "#1e2a42"
CYAN     = "#00d4ff"
MAGENTA  = "#ff00aa"
GREEN_N  = "#00ff88"
YELLOW_N = "#ffd700"
FG       = "#e8f0ff"
FG2      = "#a0aec0"
FG3      = "#3a4560"

FONT_HERO  = ("Segoe UI", 20, "bold")
FONT_TITLE = ("Segoe UI", 11, "bold")
FONT_LABEL = ("Segoe UI", 9)
FONT_BTN   = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 8)


def _btn(parent, text, cmd, color=CYAN, fg=BG, **kw):
    return tk.Button(
        parent, text=text, command=cmd, bg=color, fg=fg,
        font=FONT_BTN, relief="flat", padx=10, pady=4,
        activebackground=color, activeforeground=fg,
        cursor="hand2", **kw
    )


class ClipLibraryPanel(tk.Frame):
    """Left panel: scrollable thumbnail grid with search/filter."""

    THUMB_W = 118
    THUMB_H = 66
    COLS    = 2

    def __init__(self, parent, on_add_to_timeline, **kw):
        super().__init__(parent, bg=BG2, **kw)
        self._on_add = on_add_to_timeline
        self._clips = []
        self._filter_var = tk.StringVar()
        self._thumb_refs = {}
        self._build()

    def _build(self):
        tk.Label(self, text="Clip Library", bg=BG2, fg=CYAN,
                 font=FONT_TITLE).pack(fill="x", padx=8, pady=(8, 2))

        sf = tk.Frame(self, bg=BG3)
        sf.pack(fill="x", padx=6, pady=2)
        tk.Label(sf, text="Search:", bg=BG3, fg=FG2,
                 font=FONT_LABEL).pack(side="left", padx=4)
        tk.Entry(sf, textvariable=self._filter_var, bg=BG3, fg=FG,
                 insertbackground=FG, relief="flat",
                 font=FONT_LABEL).pack(side="left", fill="x", expand=True, padx=2)
        self._filter_var.trace_add("write", lambda *_: self._refresh())

        self._canvas = tk.Canvas(self, bg=BG2, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._inner = tk.Frame(self._canvas, bg=BG2)
        self._win_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        )
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfig(self._win_id, width=e.width)
        )

        self._status = tk.Label(self, text="No clips", bg=BG2, fg=FG3, font=FONT_SMALL)
        self._status.pack(fill="x", padx=8, pady=2)

    def set_clips(self, clips):
        self._clips = clips
        self._refresh()

    def _refresh(self):
        q = self._filter_var.get().lower()
        filtered = [
            c for c in self._clips
            if not q or q in c.topic.lower() or any(q in t.lower() for t in c.tags)
        ]
        for w in self._inner.winfo_children():
            w.destroy()
        self._thumb_refs.clear()
        for i, clip in enumerate(filtered):
            row, col = divmod(i, self.COLS)
            self._draw_card(clip, row, col)
        self._status.config(text=f"{len(filtered)} clip(s)")

    def _draw_card(self, clip, row, col):
        card = tk.Frame(self._inner, bg=BG3,
                        highlightbackground=BORDER, highlightthickness=1)
        card.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
        self._inner.columnconfigure(col, weight=1)

        thumb_lbl = tk.Label(card, bg=BG3)
        thumb_lbl.pack(fill="x")
        if clip.thumbnail and Path(clip.thumbnail).exists():
            try:
                from PIL import Image, ImageTk
                img = Image.open(clip.thumbnail).resize((self.THUMB_W, self.THUMB_H))
                photo = ImageTk.PhotoImage(img)
                self._thumb_refs[clip.clip_id] = photo
                thumb_lbl.config(image=photo)
            except Exception:
                thumb_lbl.config(text="[video]", fg=FG3, font=FONT_LABEL, pady=8)
        else:
            thumb_lbl.config(text="[video]", fg=FG3, font=FONT_LABEL, pady=8)

        tk.Label(card, text=(clip.topic or clip.filename)[:18], bg=BG3, fg=FG,
                 font=FONT_SMALL, wraplength=self.THUMB_W).pack(fill="x", padx=2)
        tk.Label(card, text=clip.display_duration, bg=BG3, fg=FG2,
                 font=FONT_SMALL).pack()
        if clip.tags:
            tk.Label(card, text=" ".join(clip.tags[:3]), bg=BG3, fg=CYAN,
                     font=("Segoe UI", 7),
                     wraplength=self.THUMB_W).pack(fill="x", padx=2)
        _btn(card, "+ Add to Timeline", lambda c=clip: self._on_add(c),
             color=GREEN_N, fg=BG).pack(fill="x", padx=4, pady=4)


class ExportPanel(tk.Frame):
    """Right panel: export settings, estimates, preview, export, auto mode."""

    def __init__(self, parent, on_export, on_auto_toggle, on_batch_change,
                 on_preview=None, **kw):
        super().__init__(parent, bg=BG2, **kw)
        self._on_export      = on_export
        self._on_auto_toggle = on_auto_toggle
        self._on_batch_change = on_batch_change
        self._on_preview     = on_preview
        self._auto_on        = False
        self._format_var  = tk.StringVar(value="YouTube Long")
        self._quality_var = tk.StringVar(value="Standard 1080p")
        self._fade_var    = tk.BooleanVar(value=True)
        self._hook_var    = tk.BooleanVar(value=True)
        self._outro_var   = tk.BooleanVar(value=True)
        self._batch_var   = tk.StringVar(value="3")
        self._build()

    def _build(self):
        tk.Label(self, text="Export Settings", bg=BG2, fg=CYAN,
                 font=FONT_TITLE).pack(fill="x", padx=8, pady=(8, 4))

        def _row(label, widget_fn):
            f = tk.Frame(self, bg=BG2)
            f.pack(fill="x", padx=8, pady=2)
            tk.Label(f, text=label, bg=BG2, fg=FG2, font=FONT_LABEL,
                     width=13, anchor="w").pack(side="left")
            widget_fn(f).pack(side="left", fill="x", expand=True)

        _row("Format:", lambda p: ttk.Combobox(
            p, textvariable=self._format_var,
            values=["YouTube Long", "YouTube Shorts", "Instagram Reels"],
            state="readonly", width=15))
        _row("Quality:", lambda p: ttk.Combobox(
            p, textvariable=self._quality_var,
            values=["Standard 1080p", "High 1440p", "Cinema 4K"],
            state="readonly", width=15))
        _row("Fade in/out:", lambda p: tk.Checkbutton(
            p, variable=self._fade_var, bg=BG2, fg=FG2,
            selectcolor=BG3, activebackground=BG2))
        _row("Add Hook:", lambda p: tk.Checkbutton(
            p, variable=self._hook_var, bg=BG2, fg=FG2,
            selectcolor=BG3, activebackground=BG2))
        _row("Add Outro:", lambda p: tk.Checkbutton(
            p, variable=self._outro_var, bg=BG2, fg=FG2,
            selectcolor=BG3, activebackground=BG2))

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=8, pady=6)

        # Export estimates
        self._est_lbl = tk.Label(
            self, text="Duration: --   Size: --",
            bg=BG2, fg=FG2, font=FONT_SMALL
        )
        self._est_lbl.pack(fill="x", padx=8, pady=(0, 4))

        _btn(self, "PREVIEW (720p fast)", self._preview_clicked,
             color=BG3, fg=CYAN).pack(fill="x", padx=8, pady=2)
        _btn(self, "EXPORT VIDEO", self._on_export,
             color=MAGENTA, fg=FG).pack(fill="x", padx=8, pady=4)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=8, pady=6)

        tk.Label(self, text="Auto Mode", bg=BG2, fg=YELLOW_N,
                 font=FONT_TITLE).pack(fill="x", padx=8)
        self._auto_btn = tk.Button(
            self, text="AUTO MODE: OFF", command=self._toggle_auto,
            bg=BG3, fg=FG2, font=FONT_BTN, relief="flat",
            padx=10, pady=4, cursor="hand2"
        )
        self._auto_btn.pack(fill="x", padx=8, pady=4)

        bf = tk.Frame(self, bg=BG2)
        bf.pack(fill="x", padx=8, pady=2)
        tk.Label(bf, text="Batch size:", bg=BG2, fg=FG2,
                 font=FONT_LABEL, width=13, anchor="w").pack(side="left")
        cb = ttk.Combobox(bf, textvariable=self._batch_var,
                          values=["3", "5", "10"], state="readonly", width=5)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>",
                lambda _: self._on_batch_change(int(self._batch_var.get())))

        self._status_lbl = tk.Label(
            self, text="Ready", bg=BG2, fg=FG3,
            font=FONT_SMALL, wraplength=190, justify="left"
        )
        self._status_lbl.pack(fill="x", padx=8, pady=6)

    def set_status(self, msg: str):
        self._status_lbl.config(text=msg)

    def update_estimates(self, duration_s: float, size_mb: float):
        m = int(duration_s // 60)
        s = int(duration_s % 60)
        self._est_lbl.config(text=f"Duration: {m}:{s:02d}   Size: ~{size_mb:.0f} MB")

    def get_settings(self):
        return {
            "format":    self._format_var.get(),
            "quality":   self._quality_var.get(),
            "add_fade":  self._fade_var.get(),
            "add_hook":  self._hook_var.get(),
            "add_outro": self._outro_var.get(),
        }

    def _preview_clicked(self):
        if self._on_preview:
            self._on_preview()

    def _toggle_auto(self):
        self._auto_on = not self._auto_on
        if self._auto_on:
            self._auto_btn.config(text="AUTO MODE: ON", bg=GREEN_N, fg=BG)
        else:
            self._auto_btn.config(text="AUTO MODE: OFF", bg=BG3, fg=FG2)
        self._on_auto_toggle(self._auto_on)


class RAGAIEditorApp(tk.Tk):
    """RAGAI Editor V2 main window."""

    _HDR_COLOURS = [CYAN, MAGENTA, YELLOW_N, GREEN_N]

    def __init__(self, clip_manager, output_dir, compiled_dir, groq_api_key=""):
        super().__init__()
        self._cm           = clip_manager
        self._output_dir   = Path(output_dir)
        self._compiled_dir = Path(compiled_dir)
        self._groq_key     = groq_api_key
        self._ui_queue     = queue.Queue()
        self._hdr_idx      = 0
        self._smart        = SmartCompiler()

        self.title("RAGAI Editor V2")
        self.configure(bg=BG)
        self.geometry("1420x840")
        self.minsize(1100, 680)

        self._build_header()
        self._build_body()
        self._build_statusbar()

        self._watcher = OutputWatcher(self._output_dir, self._on_new_video)
        self._watcher.start()

        self._auto = AutoPipeline(
            clip_manager=self._cm,
            timeline=self._timeline,
            compiled_dir=self._compiled_dir,
            music_dir=Path("music"),
            batch_size=3,
            groq_api_key=groq_api_key,
            on_export_trigger=self._on_auto_export_done,
            on_status_update=lambda m: self._ui_queue.put(("status", m)),
        )

        self.after(400, self._scan_existing)
        self.after(100, self._poll_queue)
        self._animate_header()

    def _build_header(self):
        hdr = tk.Frame(self, bg=BG, height=54)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        self._title_lbl = tk.Label(hdr, text="RAGAI Editor V2",
                                   bg=BG, fg=CYAN, font=FONT_HERO)
        self._title_lbl.pack(side="left", padx=16, pady=8)
        tk.Label(hdr, text="Automated YouTube Compilation Studio",
                 bg=BG, fg=FG3, font=FONT_LABEL).pack(side="left", padx=4)
        _btn(hdr, "Import Video", self._import_video,
             color=BG3, fg=FG2).pack(side="right", padx=6, pady=10)
        _btn(hdr, "Scan Output", self._scan_existing,
             color=BG3, fg=CYAN).pack(side="right", padx=2, pady=10)

    def _animate_header(self):
        self._hdr_idx = (self._hdr_idx + 1) % len(self._HDR_COLOURS)
        self._title_lbl.config(fg=self._HDR_COLOURS[self._hdr_idx])
        self.after(2200, self._animate_header)

    def _build_body(self):
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=4, pady=4)

        self._library = ClipLibraryPanel(body, on_add_to_timeline=self._add_to_timeline)
        self._library.pack(side="left", fill="y", padx=(0, 4))
        self._library.config(width=280)
        self._library.pack_propagate(False)

        center = tk.Frame(body, bg=BG2)
        center.pack(side="left", fill="both", expand=True, padx=4)
        tk.Label(center, text="Timeline", bg=BG2, fg=CYAN,
                 font=FONT_TITLE).pack(fill="x", padx=8, pady=(8, 2))
        self._timeline = TimelineCanvas(center, on_change=self._on_timeline_change)
        self._timeline.pack(fill="both", expand=True, padx=4, pady=4)
        self._dur_lbl = tk.Label(center, text="Total: 0:00",
                                 bg=BG2, fg=FG2, font=FONT_LABEL)
        self._dur_lbl.pack(anchor="e", padx=8, pady=2)

        self._export_panel = ExportPanel(
            body,
            on_export=self._start_export,
            on_auto_toggle=self._on_auto_toggle,
            on_batch_change=self._on_batch_change,
            on_preview=self._start_preview,
        )
        self._export_panel.pack(side="right", fill="y", padx=(4, 0))
        self._export_panel.config(width=230)
        self._export_panel.pack_propagate(False)

    def _build_statusbar(self):
        sb = tk.Frame(self, bg=BG3, height=26)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        self._statusbar = tk.Label(sb, text="Ready - RAGAI Editor V2",
                                   bg=BG3, fg=FG2, font=FONT_SMALL, anchor="w")
        self._statusbar.pack(fill="x", padx=8)

    def _scan_existing(self):
        paths = self._watcher.scan_existing()
        self._set_status(f"Scanning {len(paths)} existing video(s)...")
        for p in paths:
            self._cm.import_clip(p, on_done=self._on_clip_imported)

    def _import_video(self):
        paths = filedialog.askopenfilenames(
            title="Import video files",
            filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")]
        )
        for p in paths:
            self._cm.import_clip(Path(p), on_done=self._on_clip_imported)

    def _on_new_video(self, path):
        self._cm.import_clip(path, on_done=self._on_clip_imported)

    def _on_clip_imported(self, clip):
        """Export a fast 720p preview to compiled/preview_*.mp4"""

    def _add_to_timeline(self, clip):
        self._timeline.add_clip(clip)
        self._cm.set_state(clip.clip_id, "in_timeline")
        self._refresh_estimates()

    def _on_timeline_change(self):
        self._dur_lbl.config(text=f"Total: {self._timeline.total_duration_str()}")
        self._refresh_estimates()

    def _refresh_estimates(self):
        entries = self._timeline.get_entries()
        clips = [e.clip for e in entries]
        dur = self._smart.estimate_duration(clips)
        quality = self._export_panel.get_settings().get("quality", "Standard 1080p")
        size_mb = self._smart.estimate_filesize_mb(clips, quality)
        self._export_panel.update_estimates(dur, size_mb)

    def _start_preview(self):
        entries = self._timeline.get_entries()
        if not entries:
            messagebox.showwarning("Empty Timeline", "Add clips before previewing.")
            return
        asm = Assembler()
        if not asm.is_ready():
            messagebox.showerror("FFmpeg Missing", "FFmpeg not found.")
            return
        self._set_status("Generating 720p preview...")
        asm.export(
            entries=entries,
            topic="preview",
            output_format="YouTube Long",
            quality="Standard 1080p",
            add_fade=False,
            hook_path=None,
            outro_path=None,
            on_progress=lambda pct, msg: self._ui_queue.put(
                ("status", f"Preview: {msg} ({int(pct*100)}%)")),
            on_done=lambda p: self._ui_queue.put(("preview_done", p)),
            on_error=lambda e: self._ui_queue.put(("error", str(e))),
        )

    def _start_export(self):
        entries = self._timeline.get_entries()
        if not entries:
            messagebox.showwarning("Empty Timeline",
                                   "Add clips to the timeline before exporting.")
            return
        asm = Assembler()
        if not asm.is_ready():
            messagebox.showerror("FFmpeg Missing",
                                 "FFmpeg not found. Install FFmpeg and add it to PATH.")
            return
        settings   = self._export_panel.get_settings()
        topic      = entries[0].clip.topic or "Compilation"
        hook_path  = None
        outro_path = None

        if settings["add_hook"] and self._groq_key:
            try:
                from hook_generator import HookGenerator
                self._set_status("Generating hook clip...")
                hg = HookGenerator(self._groq_key, music_dir=Path("music"))
                hook_path = self._compiled_dir / "hook_tmp.mp4"
                self._compiled_dir.mkdir(parents=True, exist_ok=True)
                hg.generate(topic, len(entries), hook_path)
            except Exception as exc:
                logger.warning("Hook failed: %s", exc)

        if settings["add_outro"]:
            try:
                from outro_generator import OutroGenerator
                self._set_status("Generating outro clip...")
                og = OutroGenerator(music_dir=Path("music"))
                outro_path = self._compiled_dir / "outro_tmp.mp4"
                og.generate(outro_path)
            except Exception as exc:
                logger.warning("Outro failed: %s", exc)

        self._set_status("Exporting compilation...")
        asm.export(
            entries=entries,
            topic=topic,
            output_format=settings["format"],
            quality=settings["quality"],
            add_fade=settings["add_fade"],
            hook_path=hook_path,
            outro_path=outro_path,
            on_progress=lambda pct, msg: self._ui_queue.put(
                ("status", f"Export: {msg} ({int(pct * 100)}%)")),
            on_done=lambda p: self._ui_queue.put(("export_done", p)),
            on_error=lambda e: self._ui_queue.put(("error", str(e))),
        )

    def _on_auto_export_done(self):
        self._ui_queue.put(("status", "Auto export complete - timeline cleared"))
        self._ui_queue.put(("refresh_library", None))

    def _on_auto_toggle(self, enabled):
        self._auto.set_enabled(enabled)

    def _on_batch_change(self, size):
        self._auto.set_batch_size(size)

    def _poll_queue(self):
        try:
            while True:
                event, data = self._ui_queue.get_nowait()
                if event == "clip_imported":
                    self._library.set_clips(self._cm.get_all())
                    self._set_status(f"Imported: {data.filename}")
                    self._auto.on_new_clip(data)
                elif event == "status":
                    self._set_status(data)
                elif event == "export_done":
                    self._set_status(f"Export complete: {data.name}")
                    messagebox.showinfo("Export Complete", f"Compilation saved:\n{data}")
                elif event == "preview_done":
                    self._set_status(f"Preview ready: {data.name}")
                    messagebox.showinfo("Preview Ready", f"720p preview saved:\n{data}")
                elif event == "error":
                    self._set_status(f"Error: {data}")
                    messagebox.showerror("Export Error", data)
                elif event == "refresh_library":
                    self._library.set_clips(self._cm.get_all())
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def _set_status(self, msg):
        self._statusbar.config(text=msg)
        self._export_panel.set_status(msg)

    def on_close(self):
        self._watcher.stop()
        self.destroy()
"""
editor_gui.py — RAGAI Editor V3 — Cinematic dark UI.

Layout:
  LEFT   — Clip Library (search, hashtag filter, thumbnail cards)
  CENTER — Scene Timeline + Preview Player + Waveform + Scene Markers
  RIGHT  — Export / Auto Mode / Compilation Queue / Scheduler Status
"""
from __future__ import annotations

import logging
import math
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from clip_manager import ClipManager, Clip
from timeline import TimelineCanvas
from assembler import Assembler
from auto_pipeline import AutoPipeline
from watcher import OutputWatcher
from smart_compiler import SmartCompiler

logger = logging.getLogger(__name__)

# ── Colour system — match RAGAI main UI ──────────────────────────────────────
BG          = "#0d0d10"
BG_HEADER   = "#121214"
BG_ELEV     = "#16161c"
BG2         = "#16161c"
BG3         = "#1e1e26"
BORDER      = "#2a2a34"
LINE        = "#1f1f28"

ACCENT      = "#ff5722"
ACCENT_DIM  = "#c43e1a"
CYAN        = "#26c6da"
GREEN_N     = "#66bb6a"
YELLOW_N    = "#ffca28"
MAGENTA     = "#e040fb"
PURPLE      = "#ab47bc"

FG          = "#f0f2f5"
FG_MUTED    = "#9ca3af"
FG2         = "#a8b0bc"
FG3         = "#6b7280"

FONT_HERO   = ("Segoe UI", 18, "bold")
FONT_TITLE  = ("Segoe UI", 11, "bold")
FONT_LABEL  = ("Segoe UI", 10)
FONT_SMALL  = ("Segoe UI", 9)
FONT_BTN    = ("Segoe UI", 10, "bold")
FONT_MONO   = ("Consolas", 9)


def _card(parent, title: str, color=ACCENT, **kw) -> tk.Frame:
    """Create a titled card frame matching RAGAI style."""
    outer = tk.Frame(parent, bg=BG_ELEV, highlightthickness=1,
                     highlightbackground=BORDER, **kw)
    hdr = tk.Frame(outer, bg=BG_ELEV)
    hdr.pack(fill="x", padx=10, pady=(8, 4))
    tk.Frame(hdr, bg=color, width=3, height=14).pack(side="left", padx=(0, 6))
    tk.Label(hdr, text=title.upper(), bg=BG_ELEV, fg=color,
             font=("Segoe UI", 9, "bold")).pack(side="left")
    body = tk.Frame(outer, bg=BG_ELEV)
    body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
    return body


def _btn(parent, text, cmd, color=ACCENT, fg="#ffffff", **kw):
    b = tk.Button(parent, text=text, command=cmd, bg=color, fg=fg,
                  font=FONT_BTN, relief="flat", bd=0, padx=14, pady=7,
                  activebackground=color, activeforeground=fg,
                  cursor="hand2", **kw)
    b.bind("<Enter>", lambda e: b.config(bg=_lighten(color)))
    b.bind("<Leave>", lambda e: b.config(bg=color))
    return b


def _lighten(hex_color: str) -> str:
    try:
        r = min(255, int(hex_color[1:3], 16) + 20)
        g = min(255, int(hex_color[3:5], 16) + 20)
        b = min(255, int(hex_color[5:7], 16) + 20)
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return hex_color


# ── LEFT PANEL: Clip Library ──────────────────────────────────────────────────

class ClipLibraryPanel(tk.Frame):
    """Left panel: scrollable thumbnail cards with search + hashtag filter."""

    THUMB_W = 120
    THUMB_H = 68
    COLS    = 2

    def __init__(self, parent, on_add_to_timeline, **kw):
        super().__init__(parent, bg=BG2, **kw)
        self._on_add = on_add_to_timeline
        self._clips: List[Clip] = []
        self._filter_var = tk.StringVar()
        self._tag_var    = tk.StringVar(value="All")
        self._thumb_refs = {}
        self._build()

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=BG_HEADER)
        hdr.pack(fill="x")
        tk.Frame(hdr, bg=ACCENT, width=3).pack(side="left", fill="y")
        tk.Label(hdr, text="CLIP LIBRARY", bg=BG_HEADER, fg=ACCENT,
                 font=("Segoe UI", 9, "bold"), padx=10, pady=8).pack(side="left")

        # Search
        sf = tk.Frame(self, bg=BG3, pady=6)
        sf.pack(fill="x", padx=6, pady=(4, 2))
        tk.Label(sf, text="🔍", bg=BG3, fg=FG_MUTED, font=FONT_SMALL).pack(side="left", padx=(6, 2))
        tk.Entry(sf, textvariable=self._filter_var, bg=BG3, fg=FG,
                 insertbackground=ACCENT, relief="flat",
                 font=FONT_LABEL).pack(side="left", fill="x", expand=True, padx=4)
        self._filter_var.trace_add("write", lambda *_: self._refresh())

        # Tag filter
        tf = tk.Frame(self, bg=BG2)
        tf.pack(fill="x", padx=6, pady=2)
        tk.Label(tf, text="Tag:", bg=BG2, fg=FG_MUTED, font=FONT_SMALL).pack(side="left")
        self._tag_combo = ttk.Combobox(tf, textvariable=self._tag_var,
                                        values=["All"], state="readonly", width=14,
                                        font=FONT_SMALL)
        self._tag_combo.pack(side="left", padx=4)
        self._tag_combo.bind("<<ComboboxSelected>>", lambda _: self._refresh())

        # Scrollable grid
        self._canvas = tk.Canvas(self, bg=BG2, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._inner = tk.Frame(self._canvas, bg=BG2)
        self._win_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
            lambda e: self._canvas.itemconfig(self._win_id, width=e.width))

        self._status = tk.Label(self, text="No clips", bg=BG2, fg=FG3, font=FONT_SMALL)
        self._status.pack(fill="x", padx=8, pady=2)

    def set_clips(self, clips: List[Clip]):
        self._clips = clips
        # Update tag filter
        all_tags = {"All"}
        for c in clips:
            all_tags.update(c.tags)
        self._tag_combo["values"] = sorted(all_tags)
        self._refresh()

    def _refresh(self):
        q   = self._filter_var.get().lower()
        tag = self._tag_var.get()
        filtered = [
            c for c in self._clips
            if (not q or q in c.topic.lower() or any(q in t.lower() for t in c.tags))
            and (tag == "All" or tag in c.tags)
        ]
        for w in self._inner.winfo_children():
            w.destroy()
        self._thumb_refs.clear()
        for i, clip in enumerate(filtered):
            row, col = divmod(i, self.COLS)
            self._draw_card(clip, row, col)
        self._status.config(text=f"{len(filtered)} clip(s)")

    def _draw_card(self, clip: Clip, row: int, col: int):
        card = tk.Frame(self._inner, bg=BG3,
                        highlightbackground=BORDER, highlightthickness=1)
        card.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
        self._inner.columnconfigure(col, weight=1)

        # Thumbnail
        thumb_lbl = tk.Label(card, bg=BG3, height=4)
        thumb_lbl.pack(fill="x")
        if clip.thumbnail and Path(clip.thumbnail).exists():
            try:
                from PIL import Image, ImageTk
                img = Image.open(clip.thumbnail).resize((self.THUMB_W, self.THUMB_H))
                photo = ImageTk.PhotoImage(img)
                self._thumb_refs[clip.clip_id] = photo
                thumb_lbl.config(image=photo, height=self.THUMB_H)
            except Exception:
                thumb_lbl.config(text="🎬", fg=ACCENT, font=("Segoe UI", 20))
        else:
            thumb_lbl.config(text="🎬", fg=ACCENT, font=("Segoe UI", 20))

        tk.Label(card, text=(clip.topic or clip.filename)[:20], bg=BG3, fg=FG,
                 font=FONT_SMALL, wraplength=self.THUMB_W).pack(fill="x", padx=4, pady=(2, 0))
        tk.Label(card, text=clip.display_duration, bg=BG3, fg=CYAN,
                 font=("Segoe UI", 8, "bold")).pack()
        if clip.tags:
            tk.Label(card, text=" ".join(f"#{t}" for t in clip.tags[:2]),
                     bg=BG3, fg=FG_MUTED, font=("Segoe UI", 7),
                     wraplength=self.THUMB_W).pack(fill="x", padx=4)
        _btn(card, "+ Timeline", lambda c=clip: self._on_add(c),
             color=ACCENT, fg="#fff").pack(fill="x", padx=4, pady=4)


# ── RIGHT PANEL: Export + Auto + Scheduler ────────────────────────────────────

class ExportPanel(tk.Frame):
    """Right panel: export settings, auto mode, compilation queue, scheduler status."""

    def __init__(self, parent, on_export, on_auto_toggle, on_batch_change,
                 on_preview=None, cfg=None, **kw):
        super().__init__(parent, bg=BG2, **kw)
        self._on_export       = on_export
        self._on_auto_toggle  = on_auto_toggle
        self._on_batch_change = on_batch_change
        self._on_preview      = on_preview
        self._cfg             = cfg or {}
        self._auto_on         = False
        self._format_var      = tk.StringVar(value="YouTube Long")
        self._quality_var     = tk.StringVar(value="Standard 1080p")
        self._fade_var        = tk.BooleanVar(value=True)
        self._hook_var        = tk.BooleanVar(value=True)
        self._outro_var       = tk.BooleanVar(value=True)
        self._batch_var       = tk.StringVar(value="3")
        self._target_var      = tk.StringVar(value="10 min")
        self._build()

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=BG_HEADER)
        hdr.pack(fill="x")
        tk.Frame(hdr, bg=ACCENT, width=3).pack(side="left", fill="y")
        tk.Label(hdr, text="EXPORT / AUTO", bg=BG_HEADER, fg=ACCENT,
                 font=("Segoe UI", 9, "bold"), padx=10, pady=8).pack(side="left")

        scroll_canvas = tk.Canvas(self, bg=BG2, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=sb.set)
        scroll_canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        inner = tk.Frame(scroll_canvas, bg=BG2)
        win = scroll_canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
            lambda e: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all")))
        scroll_canvas.bind("<Configure>",
            lambda e: scroll_canvas.itemconfig(win, width=e.width))

        def _row(parent, label, widget_fn):
            f = tk.Frame(parent, bg=BG2)
            f.pack(fill="x", pady=2)
            tk.Label(f, text=label, bg=BG2, fg=FG_MUTED, font=FONT_SMALL,
                     width=12, anchor="w").pack(side="left")
            widget_fn(f).pack(side="left", fill="x", expand=True)

        # Export settings card
        ec = tk.Frame(inner, bg=BG_ELEV, highlightthickness=1,
                      highlightbackground=BORDER)
        ec.pack(fill="x", padx=6, pady=6)
        tk.Frame(ec, bg=ACCENT, height=2).pack(fill="x")
        tk.Label(ec, text="EXPORT SETTINGS", bg=BG_ELEV, fg=ACCENT,
                 font=("Segoe UI", 8, "bold"), padx=8, pady=4).pack(anchor="w")
        ep = tk.Frame(ec, bg=BG_ELEV, padx=8, pady=4)
        ep.pack(fill="x")

        _row(ep, "Format:", lambda p: ttk.Combobox(
            p, textvariable=self._format_var,
            values=["YouTube Long", "YouTube Shorts", "Instagram Reels"],
            state="readonly", width=14, font=FONT_SMALL))
        _row(ep, "Quality:", lambda p: ttk.Combobox(
            p, textvariable=self._quality_var,
            values=["Standard 1080p", "High 1440p", "Cinema 4K"],
            state="readonly", width=14, font=FONT_SMALL))

        for var, label in [(self._fade_var, "Fade in/out"),
                           (self._hook_var, "Add Hook"),
                           (self._outro_var, "Add Outro")]:
            f = tk.Frame(ep, bg=BG_ELEV)
            f.pack(fill="x", pady=1)
            tk.Checkbutton(f, text=label, variable=var, bg=BG_ELEV, fg=FG2,
                           selectcolor=BG3, activebackground=BG_ELEV,
                           font=FONT_SMALL).pack(side="left")

        self._est_lbl = tk.Label(ep, text="Duration: --   Size: --",
                                  bg=BG_ELEV, fg=FG_MUTED, font=FONT_SMALL)
        self._est_lbl.pack(fill="x", pady=(4, 0))

        if self._cfg.get("enable_fast_preview_render", True):
            _btn(ep, "▶ PREVIEW (720p fast)", self._preview_clicked,
                 color=BG3, fg=CYAN).pack(fill="x", pady=(6, 2))
        _btn(ep, "⬆ EXPORT VIDEO", self._on_export,
             color=ACCENT, fg="#fff").pack(fill="x", pady=2)

        # Auto Mode card
        ac = tk.Frame(inner, bg=BG_ELEV, highlightthickness=1,
                      highlightbackground=BORDER)
        ac.pack(fill="x", padx=6, pady=6)
        tk.Frame(ac, bg=YELLOW_N, height=2).pack(fill="x")
        tk.Label(ac, text="AUTO MODE", bg=BG_ELEV, fg=YELLOW_N,
                 font=("Segoe UI", 8, "bold"), padx=8, pady=4).pack(anchor="w")
        ap = tk.Frame(ac, bg=BG_ELEV, padx=8, pady=4)
        ap.pack(fill="x")

        self._auto_btn = tk.Button(
            ap, text="AUTO MODE: OFF", command=self._toggle_auto,
            bg=BG3, fg=FG2, font=FONT_BTN, relief="flat", padx=10, pady=6,
            cursor="hand2", activebackground=YELLOW_N, activeforeground=BG
        )
        self._auto_btn.pack(fill="x", pady=(0, 6))

        bf = tk.Frame(ap, bg=BG_ELEV)
        bf.pack(fill="x", pady=2)
        tk.Label(bf, text="Batch:", bg=BG_ELEV, fg=FG_MUTED,
                 font=FONT_SMALL, width=8, anchor="w").pack(side="left")
        cb = ttk.Combobox(bf, textvariable=self._batch_var,
                          values=["3", "5", "10"], state="readonly", width=5,
                          font=FONT_SMALL)
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>",
                lambda _: self._on_batch_change(int(self._batch_var.get())))

        tf = tk.Frame(ap, bg=BG_ELEV)
        tf.pack(fill="x", pady=2)
        tk.Label(tf, text="Target:", bg=BG_ELEV, fg=FG_MUTED,
                 font=FONT_SMALL, width=8, anchor="w").pack(side="left")
        ttk.Combobox(tf, textvariable=self._target_var,
                     values=["10 min", "15 min", "30 min"],
                     state="readonly", width=8, font=FONT_SMALL).pack(side="left", padx=4)

        self._status_lbl = tk.Label(ap, text="Ready", bg=BG_ELEV, fg=FG3,
                                     font=FONT_SMALL, wraplength=190, justify="left")
        self._status_lbl.pack(fill="x", pady=4)

        # Scheduler Status card (if enabled)
        if self._cfg.get("enable_scheduler_panel", True):
            sc = tk.Frame(inner, bg=BG_ELEV, highlightthickness=1,
                          highlightbackground=BORDER)
            sc.pack(fill="x", padx=6, pady=6)
            tk.Frame(sc, bg=GREEN_N, height=2).pack(fill="x")
            tk.Label(sc, text="SCHEDULER STATUS", bg=BG_ELEV, fg=GREEN_N,
                     font=("Segoe UI", 8, "bold"), padx=8, pady=4).pack(anchor="w")
            sp = tk.Frame(sc, bg=BG_ELEV, padx=8, pady=4)
            sp.pack(fill="x")

            self._sched_dot = tk.Label(sp, text="●", bg=BG_ELEV, fg=FG3,
                                        font=("Segoe UI", 9))
            self._sched_dot.pack(side="left")
            self._sched_lbl = tk.Label(sp, text="Stopped", bg=BG_ELEV, fg=FG_MUTED,
                                        font=FONT_SMALL)
            self._sched_lbl.pack(side="left", padx=4)

            self._sched_detail = tk.Label(sc, text="Queue: 0  |  Next: —",
                                           bg=BG_ELEV, fg=FG3, font=FONT_SMALL,
                                           padx=8, pady=2, anchor="w")
            self._sched_detail.pack(fill="x")
            self._sched_last = tk.Label(sc, text="Last: —",
                                         bg=BG_ELEV, fg=FG3, font=FONT_SMALL,
                                         padx=8, pady=2, anchor="w")
            self._sched_last.pack(fill="x")
            _btn(sp, "↻", self._refresh_scheduler,
                 color=BG3, fg=GREEN_N).pack(side="right")
        else:
            self._sched_dot = self._sched_lbl = self._sched_detail = self._sched_last = None

    def refresh_scheduler(self):
        self._refresh_scheduler()

    def _refresh_scheduler(self):
        if not self._cfg.get("enable_scheduler_panel", True):
            return
        try:
            from scheduler_monitor import read_status
            st = read_status()
            if st.running:
                self._sched_dot.config(fg=GREEN_N)
                self._sched_lbl.config(text=f"Running: {st.current_topic or 'idle'}")
            else:
                self._sched_dot.config(fg=FG3)
                self._sched_lbl.config(text="Stopped")
            self._sched_detail.config(
                text=f"Queue: {st.queue_size}  |  Next: {st.next_job or '—'}")
            self._sched_last.config(text=f"Last: {st.last_result or '—'}")
        except Exception as exc:
            logger.debug("Scheduler monitor error: %s", exc)

    def set_status(self, msg: str):
        self._status_lbl.config(text=msg)

    def update_estimates(self, duration_s: float, size_mb: float):
        m, s = int(duration_s // 60), int(duration_s % 60)
        self._est_lbl.config(text=f"Duration: {m}:{s:02d}   Size: ~{size_mb:.0f} MB")

    def get_settings(self) -> dict:
        return {
            "format":    self._format_var.get(),
            "quality":   self._quality_var.get(),
            "add_fade":  self._fade_var.get(),
            "add_hook":  self._hook_var.get(),
            "add_outro": self._outro_var.get(),
            "target_minutes": int(self._target_var.get().split()[0]),
        }

    def _preview_clicked(self):
        if self._on_preview:
            self._on_preview()

    def _toggle_auto(self):
        self._auto_on = not self._auto_on
        if self._auto_on:
            self._auto_btn.config(text="AUTO MODE: ON", bg=YELLOW_N, fg=BG)
        else:
            self._auto_btn.config(text="AUTO MODE: OFF", bg=BG3, fg=FG2)
        self._on_auto_toggle(self._auto_on)


# ── MAIN APP ──────────────────────────────────────────────────────────────────

class RAGAIEditorApp(tk.Tk):
    """RAGAI Editor V3 — cinematic dark UI matching RAGAI main app."""

    def __init__(self, clip_manager: ClipManager, output_dir, compiled_dir,
                 groq_api_key: str = "", cfg: dict = None, load_folder: str = ""):
        super().__init__()
        self._cm           = clip_manager
        self._output_dir   = Path(output_dir)
        self._compiled_dir = Path(compiled_dir)
        self._groq_key     = groq_api_key
        self._cfg          = cfg or {}
        self._ui_queue     = queue.Queue()
        self._smart        = SmartCompiler()
        self._hdr_phase    = 0.0

        self.title("RAGAI Editor V3 — AI Video Studio")
        self.configure(bg=BG)
        self.geometry("1480x880")
        self.minsize(1100, 700)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_header()
        self._build_body()
        self._build_statusbar()

        # Watcher
        self._watcher = OutputWatcher(self._output_dir, self._on_new_video)
        self._watcher.start()

        # Auto pipeline
        self._auto = AutoPipeline(
            clip_manager=self._cm,
            timeline=self._timeline,
            compiled_dir=self._compiled_dir,
            music_dir=Path("music"),
            batch_size=3,
            groq_api_key=groq_api_key,
            on_export_trigger=self._on_auto_export_done,
            on_status_update=lambda m: self._ui_queue.put(("status", m)),
            target_minutes=self._cfg.get("compilation_target_minutes", 10),
        )

        # Preview player
        if self._cfg.get("enable_preview_player", True):
            from preview_player import PreviewPlayer
            self._preview_player = PreviewPlayer(
                on_status=lambda m: self._ui_queue.put(("status", m)),
                on_done=lambda p: self._ui_queue.put(("preview_done", p)),
                on_error=lambda m: self._ui_queue.put(("error", m)),
                crf=self._cfg.get("preview_crf", 28),
                preset=self._cfg.get("preview_preset", "ultrafast"),
            )
        else:
            self._preview_player = None

        self.after(400, self._scan_existing)
        self.after(100, self._poll_queue)
        self.after(80,  self._animate_header)
        self.after(10_000, self._scheduler_tick)

        # Load folder if passed via CLI
        if load_folder:
            self.after(800, lambda: self._load_folder(Path(load_folder)))

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        self._hdr_canvas = tk.Canvas(self, bg=BG_HEADER, height=72,
                                      highlightthickness=0)
        self._hdr_canvas.pack(fill="x")
        # Accent separator
        tk.Frame(self, bg=ACCENT, height=2).pack(fill="x")
        # Status bar
        sb = tk.Frame(self, bg=BG_HEADER, padx=16, pady=6)
        sb.pack(fill="x")
        tk.Frame(sb, bg=LINE, height=1).pack(fill="x", side="bottom")
        left = tk.Frame(sb, bg=BG_HEADER)
        left.pack(side="left", fill="x", expand=True)
        self._clips_lbl = tk.Label(left, text="Clips: 0", bg=BG_HEADER,
                                    fg=FG_MUTED, font=FONT_SMALL)
        self._clips_lbl.pack(side="left", padx=(0, 20))
        self._timeline_lbl = tk.Label(left, text="Timeline: 0:00", bg=BG_HEADER,
                                       fg=FG_MUTED, font=FONT_SMALL)
        self._timeline_lbl.pack(side="left", padx=(0, 20))
        self._auto_status = tk.Label(left, text="Auto: OFF", bg=BG_HEADER,
                                      fg=FG3, font=FONT_SMALL)
        self._auto_status.pack(side="left")
        # Right side buttons
        right = tk.Frame(sb, bg=BG_HEADER)
        right.pack(side="right")
        _btn(right, "Import Video", self._import_video,
             color=BG3, fg=FG2).pack(side="right", padx=4)
        _btn(right, "Scan Output", self._scan_existing,
             color=BG3, fg=CYAN).pack(side="right", padx=4)

    def _animate_header(self):
        c = self._hdr_canvas
        c.delete("all")
        W = max(800, c.winfo_width() or 1400)
        H = 72
        # Ember particles (lightweight — 20 particles)
        if not hasattr(self, "_embers"):
            import random
            self._embers = [
                [random.uniform(0, W), random.uniform(0, H),
                 random.uniform(1, 2.2), random.uniform(0.3, 1.0),
                 random.uniform(0, math.pi * 2)]
                for _ in range(20)
            ]
        for e in self._embers:
            e[0] = (e[0] + e[3]) % W
            e[4] += 0.05
            a = int(15 + 12 * (math.sin(e[4]) + 1) / 2)
            col = f"#{a:02x}{int(a*0.34):02x}00"
            r = e[2]
            c.create_oval(e[0]-r, e[1]-r, e[0]+r, e[1]+r, fill=col, outline="")

        # Logo
        cx = W // 2
        c.create_text(cx - 80, 36, text="🎬", font=("Segoe UI", 22),
                      fill=ACCENT, anchor="e")
        c.create_text(cx - 72, 30, text="RAG", font=("Segoe UI", 20, "bold"),
                      fill="#ffffff", anchor="w")
        c.create_text(cx - 72 + 50, 30, text="AI", font=("Segoe UI", 20, "bold"),
                      fill=ACCENT, anchor="w")
        c.create_text(cx - 72 + 2, 52, text="EDITOR V3  ·  AI VIDEO STUDIO",
                      font=("Segoe UI", 8, "bold"), fill=FG_MUTED, anchor="w")
        self._hdr_phase += 0.03
        self.after(40, self._animate_header)

    # ── Body ──────────────────────────────────────────────────────────────────

    def _build_body(self):
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=4, pady=4)

        # LEFT — Clip Library
        self._library = ClipLibraryPanel(body, on_add_to_timeline=self._add_to_timeline)
        self._library.pack(side="left", fill="y", padx=(0, 4))
        self._library.config(width=290)
        self._library.pack_propagate(False)

        # CENTER — Timeline + Preview
        center = tk.Frame(body, bg=BG2)
        center.pack(side="left", fill="both", expand=True, padx=4)
        self._build_center(center)

        # RIGHT — Export / Auto / Scheduler
        self._export_panel = ExportPanel(
            body,
            on_export=self._start_export,
            on_auto_toggle=self._on_auto_toggle,
            on_batch_change=self._on_batch_change,
            on_preview=self._start_preview,
            cfg=self._cfg,
        )
        self._export_panel.pack(side="right", fill="y", padx=(4, 0))
        self._export_panel.config(width=240)
        self._export_panel.pack_propagate(False)

    def _build_center(self, parent: tk.Frame):
        # Preview player strip (if enabled)
        if self._cfg.get("enable_preview_player", True):
            pf = tk.Frame(parent, bg=BG_ELEV, height=36)
            pf.pack(fill="x", padx=4, pady=(4, 2))
            pf.pack_propagate(False)
            tk.Label(pf, text="PREVIEW", bg=BG_ELEV, fg=ACCENT,
                     font=("Segoe UI", 8, "bold"), padx=8).pack(side="left")
            for sym, cmd in [("⏮", self._prev_scene), ("▶", self._play_preview),
                              ("⏸", self._pause_preview), ("⏭", self._next_scene)]:
                _btn(pf, sym, cmd, color=BG3, fg=FG2).pack(side="left", padx=2, pady=4)
            self._preview_time = tk.Label(pf, text="0:00 / 0:00", bg=BG_ELEV,
                                           fg=FG_MUTED, font=FONT_SMALL)
            self._preview_time.pack(side="left", padx=8)

        # Timeline label + controls
        tl_hdr = tk.Frame(parent, bg=BG2)
        tl_hdr.pack(fill="x", padx=4, pady=(4, 0))
        tk.Frame(tl_hdr, bg=ACCENT, width=3, height=14).pack(side="left", padx=(0, 6))
        tk.Label(tl_hdr, text="SCENE TIMELINE", bg=BG2, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        self._dur_lbl = tk.Label(tl_hdr, text="Total: 0:00", bg=BG2,
                                  fg=FG_MUTED, font=FONT_SMALL)
        self._dur_lbl.pack(side="right", padx=8)
        _btn(tl_hdr, "✕ Remove", self._remove_selected,
             color=BG3, fg=FG2).pack(side="right", padx=4)
        _btn(tl_hdr, "Clear All", self._clear_timeline,
             color=BG3, fg=FG2).pack(side="right", padx=4)

        # Timeline canvas
        self._timeline = TimelineCanvas(parent, on_change=self._on_timeline_change)
        self._timeline.pack(fill="both", expand=True, padx=4, pady=4)

        # Waveform strip (if enabled)
        if self._cfg.get("enable_waveform_view", True):
            self._wave_canvas = tk.Canvas(parent, bg=BG3, height=32,
                                           highlightthickness=0)
            self._wave_canvas.pack(fill="x", padx=4, pady=(0, 2))
            tk.Label(parent, text="▲ waveform", bg=BG2, fg=FG3,
                     font=("Segoe UI", 7)).pack(anchor="w", padx=8)
        else:
            self._wave_canvas = None

        # Scene markers strip (if enabled)
        if self._cfg.get("enable_scene_markers", True):
            self._marker_frame = tk.Frame(parent, bg=BG2)
            self._marker_frame.pack(fill="x", padx=4, pady=(0, 4))
        else:
            self._marker_frame = None

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_statusbar(self):
        sb = tk.Frame(self, bg=BG_ELEV, height=28)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        tk.Frame(sb, bg=LINE, height=1).pack(fill="x")
        self._statusbar = tk.Label(sb, text="Ready — RAGAI Editor V3",
                                    bg=BG_ELEV, fg=FG_MUTED, font=FONT_SMALL,
                                    anchor="w")
        self._statusbar.pack(fill="x", padx=12, pady=4)

    # ── Clip operations ───────────────────────────────────────────────────────

    def _scan_existing(self):
        paths = self._watcher.scan_existing()
        self._set_status(f"Scanning {len(paths)} existing video(s)…")
        for p in paths:
            self._cm.import_clip(p, on_done=self._on_clip_imported)

    def _import_video(self):
        paths = filedialog.askopenfilenames(
            title="Import video files",
            filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")]
        )
        for p in paths:
            self._cm.import_clip(Path(p), on_done=self._on_clip_imported)

    def _load_folder(self, folder: Path):
        """Load all MP4s from a generator output folder (--load CLI)."""
        if not folder.exists():
            return
        for p in sorted(folder.glob("*.mp4")):
            self._cm.import_clip(p, on_done=self._on_clip_imported)
        self._set_status(f"Loaded folder: {folder.name}")

    def _on_new_video(self, path: Path):
        self._cm.import_clip(path, on_done=self._on_clip_imported)

    def _on_clip_imported(self, clip: Clip):
        self._ui_queue.put(("clip_imported", clip))

    def _add_to_timeline(self, clip: Clip):
        self._timeline.add_clip(clip)
        self._cm.set_state(clip.clip_id, "in_timeline")
        self._refresh_estimates()
        self._refresh_waveform()
        self._refresh_markers()

    def _remove_selected(self):
        self._timeline.remove_selected()
        self._refresh_estimates()

    def _clear_timeline(self):
        if messagebox.askyesno("Clear Timeline", "Remove all clips from timeline?"):
            self._timeline.clear()
            self._refresh_estimates()

    # ── Timeline change ───────────────────────────────────────────────────────

    def _on_timeline_change(self):
        entries = self._timeline.get_entries()
        dur = self._timeline.total_duration()
        m, s = int(dur // 60), int(dur % 60)
        self._dur_lbl.config(text=f"Total: {m}:{s:02d}")
        self._timeline_lbl.config(text=f"Timeline: {m}:{s:02d}")
        self._refresh_estimates()
        self._refresh_waveform()
        self._refresh_markers()

    def _refresh_estimates(self):
        entries = self._timeline.get_entries()
        clips = [e.clip for e in entries]
        dur = self._smart.estimate_duration(clips)
        quality = self._export_panel.get_settings().get("quality", "Standard 1080p")
        size_mb = self._smart.estimate_filesize_mb(clips, quality)
        self._export_panel.update_estimates(dur, size_mb)
        self._clips_lbl.config(text=f"Clips: {len(self._cm.get_all())}")

    # ── Waveform ──────────────────────────────────────────────────────────────

    def _refresh_waveform(self):
        if not self._wave_canvas or not self._cfg.get("enable_waveform_view", True):
            return
        entries = self._timeline.get_entries()
        if not entries:
            self._wave_canvas.delete("all")
            return
        # Use first clip's audio for waveform
        clip = entries[0].clip
        threading.Thread(target=self._draw_waveform,
                         args=(clip,), daemon=True).start()

    def _draw_waveform(self, clip: Clip):
        try:
            from waveform_generator import extract_waveform
            samples = extract_waveform(Path(clip.filepath), samples=200)
            self._ui_queue.put(("waveform", samples))
        except Exception as exc:
            logger.debug("Waveform error: %s", exc)

    def _render_waveform(self, samples: list):
        c = self._wave_canvas
        c.delete("all")
        W = max(200, c.winfo_width() or 800)
        H = 32
        if not samples:
            return
        step = W / len(samples)
        mid = H // 2
        for i, amp in enumerate(samples):
            x = int(i * step)
            h = max(1, int(amp * mid * 0.9))
            a = int(80 + 120 * amp)
            col = f"#{min(255,a):02x}{int(min(255,a)*0.34):02x}00"
            c.create_line(x, mid - h, x, mid + h, fill=col, width=1)

    # ── Scene markers ─────────────────────────────────────────────────────────

    def _refresh_markers(self):
        if not self._marker_frame or not self._cfg.get("enable_scene_markers", True):
            return
        for w in self._marker_frame.winfo_children():
            w.destroy()
        entries = self._timeline.get_entries()
        if not entries:
            return
        try:
            from scene_marker_engine import assign_markers
            clips = [e.clip for e in entries]
            markers = assign_markers(clips)
            _MARKER_COLORS = {
                "Hook": ACCENT, "Rising": YELLOW_N, "Conflict": "#ef5350",
                "Climax": MAGENTA, "Resolution": GREEN_N, "Outro": CYAN,
            }
            for m in markers:
                col = _MARKER_COLORS.get(m.marker, FG_MUTED)
                tk.Label(self._marker_frame, text=m.marker, bg=BG2, fg=col,
                         font=("Segoe UI", 7, "bold"),
                         padx=4, pady=1,
                         relief="flat").pack(side="left", padx=2)
        except Exception as exc:
            logger.debug("Marker error: %s", exc)

    # ── Preview controls ──────────────────────────────────────────────────────

    def _play_preview(self):
        self._start_preview()

    def _pause_preview(self):
        if self._preview_player:
            self._preview_player.stop()

    def _prev_scene(self):
        pass  # future: seek to previous scene

    def _next_scene(self):
        pass  # future: seek to next scene

    def _start_preview(self):
        entries = self._timeline.get_entries()
        if not entries:
            messagebox.showwarning("Empty Timeline", "Add clips before previewing.")
            return
        if self._preview_player:
            self._set_status("Building 720p preview…")
            self._preview_player.play(entries, output_dir=Path("tmp"))
        else:
            # Fallback to assembler preview
            asm = Assembler()
            if not asm.is_ready():
                messagebox.showerror("FFmpeg Missing", "FFmpeg not found.")
                return
            self._set_status("Generating 720p preview…")
            asm.export(
                entries=entries, topic="preview",
                output_format="YouTube Long", quality="Standard 1080p",
                add_fade=False, hook_path=None, outro_path=None,
                on_progress=lambda pct, msg: self._ui_queue.put(
                    ("status", f"Preview: {msg} ({int(pct*100)}%)")),
                on_done=lambda p: self._ui_queue.put(("preview_done", p)),
                on_error=lambda e: self._ui_queue.put(("error", str(e))),
            )

    # ── Export ────────────────────────────────────────────────────────────────

    def _start_export(self):
        entries = self._timeline.get_entries()
        if not entries:
            messagebox.showwarning("Empty Timeline",
                                   "Add clips to the timeline before exporting.")
            return
        asm = Assembler()
        if not asm.is_ready():
            messagebox.showerror("FFmpeg Missing",
                                 "FFmpeg not found. Install FFmpeg and add it to PATH.")
            return
        settings   = self._export_panel.get_settings()
        topic      = entries[0].clip.topic or "Compilation"
        hook_path  = None
        outro_path = None

        if settings.get("add_hook") and self._groq_key:
            try:
                from hook_generator import HookGenerator
                self._set_status("Generating hook clip…")
                hg = HookGenerator(self._groq_key, music_dir=Path("music"))
                hook_path = self._compiled_dir / "hook_tmp.mp4"
                self._compiled_dir.mkdir(parents=True, exist_ok=True)
                hg.generate(topic, len(entries), hook_path)
            except Exception as exc:
                logger.warning("Hook failed: %s", exc)

        if settings.get("add_outro"):
            try:
                from outro_generator import OutroGenerator
                self._set_status("Generating outro clip…")
                og = OutroGenerator(music_dir=Path("music"))
                outro_path = self._compiled_dir / "outro_tmp.mp4"
                og.generate(outro_path)
            except Exception as exc:
                logger.warning("Outro failed: %s", exc)

        self._set_status("Exporting compilation…")
        asm.export(
            entries=entries, topic=topic,
            output_format=settings["format"],
            quality=settings["quality"],
            add_fade=settings["add_fade"],
            hook_path=hook_path, outro_path=outro_path,
            on_progress=lambda pct, msg: self._ui_queue.put(
                ("status", f"Export: {msg} ({int(pct * 100)}%)")),
            on_done=lambda p: self._ui_queue.put(("export_done", p)),
            on_error=lambda e: self._ui_queue.put(("error", str(e))),
        )

    # ── Auto pipeline ─────────────────────────────────────────────────────────

    def _on_auto_export_done(self):
        self._ui_queue.put(("status", "Auto export complete — timeline cleared"))
        self._ui_queue.put(("refresh_library", None))

    def _on_auto_toggle(self, enabled: bool):
        self._auto.set_enabled(enabled)
        self._auto_status.config(
            text="Auto: ON" if enabled else "Auto: OFF",
            fg=YELLOW_N if enabled else FG3,
        )

    def _on_batch_change(self, size: int):
        self._auto.set_batch_size(size)

    # ── Scheduler tick ────────────────────────────────────────────────────────

    def _scheduler_tick(self):
        self._export_panel.refresh_scheduler()
        self.after(15_000, self._scheduler_tick)

    # ── UI queue polling ──────────────────────────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                event, data = self._ui_queue.get_nowait()
                if event == "clip_imported":
                    self._library.set_clips(self._cm.get_all())
                    self._set_status(f"Imported: {data.filename}")
                    self._auto.on_new_clip(data)
                    self._clips_lbl.config(text=f"Clips: {len(self._cm.get_all())}")
                elif event == "status":
                    self._set_status(data)
                elif event == "export_done":
                    self._set_status(f"Export complete: {data.name}")
                    messagebox.showinfo("Export Complete",
                                        f"Compilation saved:\n{data}")
                elif event == "preview_done":
                    self._set_status(f"Preview ready: {data.name}")
                elif event == "error":
                    self._set_status(f"Error: {data}")
                    messagebox.showerror("Error", data)
                elif event == "refresh_library":
                    self._library.set_clips(self._cm.get_all())
                elif event == "waveform":
                    self._render_waveform(data)
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def _set_status(self, msg: str):
        self._statusbar.config(text=msg)
        self._export_panel.set_status(msg)

    def on_close(self):
        self._watcher.stop()
        if self._preview_player:
            self._preview_player.stop()
        self.destroy()
