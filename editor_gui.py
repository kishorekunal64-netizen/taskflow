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

        self._est_lbl = tk.Label(
            self, text="Duration: --   Size: --",
            bg=BG2, fg=FG2, font=FONT_SMALL
        )
        self._est_lbl.pack(fill="x", padx=8, pady=(0, 4))

        _btn(self, "PREVIEW (fast encode)", self._preview_clicked,
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
        self._ui_queue.put(("clip_imported", clip))

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
        # Generate a fast low-res preview of the current timeline
        entries = self._timeline.get_entries()
        if not entries:
            messagebox.showwarning("Empty Timeline", "Add clips before previewing.")
            return
        asm = Assembler()
        if not asm.is_ready():
            messagebox.showerror("FFmpeg Missing", "FFmpeg not found.")
            return
        self._set_status("Generating preview...")
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
                    messagebox.showinfo("Preview Ready", f"Preview saved:\n{data}")
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
