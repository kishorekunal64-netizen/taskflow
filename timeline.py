"""
timeline.py — Visual Canvas Timeline for RAGAI Editor.

Horizontal scrollable timeline. Each clip is a draggable tile showing
thumbnail, title, and duration. Supports reorder, trim, and transitions.
"""

from __future__ import annotations

import logging
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import ttk
from typing import Callable, List, Optional

from clip_manager import Clip

logger = logging.getLogger(__name__)

# Theme colours (match gui.py)
BG      = "#080b12"
BG2     = "#0e1420"
BG3     = "#141c2e"
BORDER  = "#1e2a42"
CYAN    = "#00d4ff"
GREEN_N = "#00ff88"
ORANGE  = "#ff6b00"
FG      = "#e8f0ff"
FG2     = "#a0aec0"
FG3     = "#3a4560"

TILE_W  = 140   # px per clip tile
TILE_H  = 100
TILE_PAD = 8
TRACK_H  = TILE_H + TILE_PAD * 2

TRANSITIONS = ["Cut", "Dissolve 0.5s", "Dissolve 1s", "Dissolve 2s", "Fade Black 1s"]


@dataclass
class TimelineEntry:
    clip: Clip
    transition: str = "Cut"   # transition BEFORE this clip


class TimelineCanvas(tk.Frame):
    """
    3-row layout:
      Row 0 — transition labels (between tiles)
      Row 1 — clip tiles (draggable)
      Row 2 — trim controls (shown when a tile is selected)
    """

    def __init__(self, parent, on_change: Optional[Callable] = None, **kw):
        super().__init__(parent, bg=BG2, **kw)
        self._entries: List[TimelineEntry] = []
        self._on_change = on_change
        self._selected: Optional[int] = None   # index of selected tile
        self._drag_idx: Optional[int] = None
        self._drag_start_x: int = 0
        self._drag_origin_x: int = 0
        self._thumb_images = {}   # keep refs to avoid GC

        self._build()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_clip(self, clip: Clip):
        entry = TimelineEntry(clip=clip)
        self._entries.append(entry)
        self._redraw()
        if self._on_change:
            self._on_change()

    def remove_selected(self):
        if self._selected is not None and 0 <= self._selected < len(self._entries):
            self._entries.pop(self._selected)
            self._selected = None
            self._redraw()
            if self._on_change:
                self._on_change()

    def clear(self):
        self._entries.clear()
        self._selected = None
        self._redraw()
        if self._on_change:
            self._on_change()

    def get_entries(self) -> List[TimelineEntry]:
        return list(self._entries)

    def total_duration(self) -> float:
        total = 0.0
        for e in self._entries:
            c = e.clip
            start = c.trim_in if c.trim_in >= 0 else 0.0
            end   = c.trim_out if c.trim_out >= 0 else c.duration
            total += max(0.0, end - start)
        return total

    def total_duration_str(self) -> str:
        s = int(self.total_duration())
        return f"{s // 60}:{s % 60:02d}"

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self):
        # Scrollable canvas area
        self._canvas = tk.Canvas(self, bg=BG2, height=TRACK_H + 30,
                                  highlightthickness=0, bd=0)
        self._hbar = ttk.Scrollbar(self, orient="horizontal",
                                    command=self._canvas.xview)
        self._canvas.configure(xscrollcommand=self._hbar.set)
        self._canvas.pack(fill="both", expand=True)
        self._hbar.pack(fill="x")

        # Trim panel (hidden until clip selected)
        self._trim_frame = tk.Frame(self, bg=BG3)
        self._trim_lbl = tk.Label(self._trim_frame, text="Trim", bg=BG3,
                                   fg=FG2, font=("Segoe UI", 9))
        self._trim_lbl.pack(side="left", padx=6)

        tk.Label(self._trim_frame, text="In:", bg=BG3, fg=FG2,
                 font=("Segoe UI", 9)).pack(side="left")
        self._trim_in_var = tk.StringVar(value="0.0")
        self._trim_in_entry = tk.Entry(self._trim_frame, textvariable=self._trim_in_var,
                                        width=6, bg=BG, fg=FG, insertbackground=FG,
                                        relief="flat", font=("Segoe UI", 9))
        self._trim_in_entry.pack(side="left", padx=2)

        tk.Label(self._trim_frame, text="Out:", bg=BG3, fg=FG2,
                 font=("Segoe UI", 9)).pack(side="left", padx=(8, 0))
        self._trim_out_var = tk.StringVar(value="0.0")
        self._trim_out_entry = tk.Entry(self._trim_frame, textvariable=self._trim_out_var,
                                         width=6, bg=BG, fg=FG, insertbackground=FG,
                                         relief="flat", font=("Segoe UI", 9))
        self._trim_out_entry.pack(side="left", padx=2)

        tk.Button(self._trim_frame, text="Apply", bg=CYAN, fg=BG,
                  font=("Segoe UI", 9, "bold"), relief="flat", padx=8,
                  command=self._apply_trim).pack(side="left", padx=8)

        tk.Button(self._trim_frame, text="Remove Clip", bg=ORANGE, fg=FG,
                  font=("Segoe UI", 9, "bold"), relief="flat", padx=8,
                  command=self.remove_selected).pack(side="left", padx=4)

        # Transition selector (shown in trim panel)
        tk.Label(self._trim_frame, text="Transition:", bg=BG3, fg=FG2,
                 font=("Segoe UI", 9)).pack(side="left", padx=(16, 0))
        self._trans_var = tk.StringVar(value="Cut")
        self._trans_combo = ttk.Combobox(self._trim_frame, textvariable=self._trans_var,
                                          values=TRANSITIONS, width=14, state="readonly")
        self._trans_combo.pack(side="left", padx=4)
        self._trans_combo.bind("<<ComboboxSelected>>", self._apply_transition)

        self._canvas.bind("<Button-1>", self._on_click)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)

        self._redraw()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _redraw(self):
        self._canvas.delete("all")
        self._thumb_images.clear()

        if not self._entries:
            self._canvas.create_text(
                200, TRACK_H // 2 + 15,
                text="← Drag clips here or double-click in library",
                fill=FG3, font=("Segoe UI", 11)
            )
            self._trim_frame.pack_forget()
            total_w = 400
        else:
            x = TILE_PAD
            for i, entry in enumerate(self._entries):
                self._draw_tile(i, entry, x)
                x += TILE_W + TILE_PAD
            total_w = x + TILE_PAD

        self._canvas.configure(scrollregion=(0, 0, total_w, TRACK_H + 30))

    def _draw_tile(self, idx: int, entry: TimelineEntry, x: int):
        y = TILE_PAD + 20   # leave room for transition label above
        selected = (idx == self._selected)
        border_color = CYAN if selected else BORDER
        fill_color   = BG3 if selected else BG2

        # Transition label above (except first clip)
        if idx > 0:
            lx = x - TILE_PAD // 2
            self._canvas.create_text(
                lx, 10, text=entry.transition,
                fill=FG3, font=("Segoe UI", 7), anchor="n"
            )

        # Tile background
        self._canvas.create_rectangle(
            x, y, x + TILE_W, y + TILE_H,
            fill=fill_color, outline=border_color, width=2 if selected else 1,
            tags=(f"tile_{idx}",)
        )

        # Thumbnail
        thumb_h = 56
        if entry.clip.thumbnail and Path(entry.clip.thumbnail).exists():
            try:
                from PIL import Image, ImageTk
                img = Image.open(entry.clip.thumbnail).resize((TILE_W - 4, thumb_h))
                photo = ImageTk.PhotoImage(img)
                self._thumb_images[idx] = photo
                self._canvas.create_image(x + 2, y + 2, anchor="nw", image=photo,
                                           tags=(f"tile_{idx}",))
            except Exception:
                self._canvas.create_rectangle(x + 2, y + 2, x + TILE_W - 2, y + thumb_h,
                                               fill=BG3, outline="")
        else:
            self._canvas.create_rectangle(x + 2, y + 2, x + TILE_W - 2, y + thumb_h,
                                           fill=BG3, outline="")
            self._canvas.create_text(x + TILE_W // 2, y + thumb_h // 2,
                                      text="🎬", font=("Segoe UI", 18))

        # Title
        title = entry.clip.topic or entry.clip.filename
        if len(title) > 16:
            title = title[:14] + "…"
        self._canvas.create_text(
            x + TILE_W // 2, y + thumb_h + 10,
            text=title, fill=FG, font=("Segoe UI", 8, "bold"), anchor="n",
            tags=(f"tile_{idx}",)
        )

        # Duration
        self._canvas.create_text(
            x + TILE_W // 2, y + thumb_h + 24,
            text=entry.clip.display_duration, fill=FG2, font=("Segoe UI", 8),
            anchor="n", tags=(f"tile_{idx}",)
        )

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def _tile_at(self, canvas_x: int) -> Optional[int]:
        """Return tile index under canvas_x, or None."""
        for i in range(len(self._entries)):
            x = TILE_PAD + i * (TILE_W + TILE_PAD)
            if x <= canvas_x <= x + TILE_W:
                return i
        return None

    def _on_click(self, event):
        cx = self._canvas.canvasx(event.x)
        idx = self._tile_at(cx)
        if idx is not None:
            self._selected = idx
            self._drag_idx = idx
            self._drag_start_x = cx
            self._drag_origin_x = cx
            self._show_trim_panel(idx)
        else:
            self._selected = None
            self._trim_frame.pack_forget()
        self._redraw()

    def _on_drag(self, event):
        if self._drag_idx is None:
            return
        cx = self._canvas.canvasx(event.x)
        dx = cx - self._drag_start_x
        if abs(dx) < TILE_W // 2:
            return
        direction = 1 if dx > 0 else -1
        new_idx = self._drag_idx + direction
        if 0 <= new_idx < len(self._entries):
            self._entries[self._drag_idx], self._entries[new_idx] = \
                self._entries[new_idx], self._entries[self._drag_idx]
            self._drag_idx = new_idx
            self._selected = new_idx
            self._drag_start_x = cx
            self._redraw()
            if self._on_change:
                self._on_change()

    def _on_release(self, event):
        self._drag_idx = None

    def _show_trim_panel(self, idx: int):
        clip = self._entries[idx].clip
        self._trim_in_var.set(str(clip.trim_in if clip.trim_in >= 0 else 0.0))
        self._trim_out_var.set(str(clip.trim_out if clip.trim_out >= 0 else round(clip.duration, 1)))
        self._trans_var.set(self._entries[idx].transition)
        self._trim_lbl.config(text=f"Trim: {clip.filename}")
        self._trim_frame.pack(fill="x", padx=4, pady=(0, 4))

    def _apply_trim(self):
        if self._selected is None:
            return
        try:
            tin  = float(self._trim_in_var.get())
            tout = float(self._trim_out_var.get())
            clip = self._entries[self._selected].clip
            clip.trim_in  = max(0.0, tin)
            clip.trim_out = min(clip.duration, tout)
            self._redraw()
            if self._on_change:
                self._on_change()
        except ValueError:
            pass

    def _apply_transition(self, _=None):
        if self._selected is not None:
            self._entries[self._selected].transition = self._trans_var.get()
            self._redraw()
