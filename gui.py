import ctypes
import json
import os
import tempfile
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import cv2
from PIL import Image, ImageTk

from control import controlfun, reset_control
from cvfile import Cameraf, canvas_to_frame, frame_to_canvas, scan_all_lanes, validate_roi
from ambdet import get_detector_config, list_local_models, set_detector_config


# ═══════════════════════════════════════════════════════════════════
# THEME SYSTEM
# ═══════════════════════════════════════════════════════════════════
PALETTES = {
    "dark": {
        "BG":              "#0b0f14",
        "PANEL":           "#121820",
        "PANEL_ALT":       "#0e141b",
        "BORDER":          "#1f2a37",
        "ACCENT":          "#3b82f6",
        "ACCENT_HOVER":    "#2563eb",
        "GREEN":           "#22c55e",
        "RED":             "#ef4444",
        "YELLOW":          "#f59e0b",
        "TEXT":            "#e5edf5",
        "SUBTEXT":         "#7c8ea3",
        "MUTED":           "#4a5a6a",
        "INPUT_BG":        "#0a0f16",
        "CANVAS":          "#000000",
    },
    "light": {
        "BG":              "#f5f7fa",
        "PANEL":           "#ffffff",
        "PANEL_ALT":       "#f3f4f6",
        "BORDER":          "#e5e7eb",
        "ACCENT":          "#2563eb",
        "ACCENT_HOVER":    "#1d4ed8",
        "GREEN":           "#16a34a",
        "RED":             "#dc2626",
        "YELLOW":          "#d97706",
        "TEXT":            "#111827",
        "SUBTEXT":         "#6b7280",
        "MUTED":           "#9ca3af",
        "INPUT_BG":        "#f3f4f6",
        "CANVAS":          "#f3f4f6",
    },
}


class Theme:
    current = "dark"
    _bindings = []   # (widget, prop, key)
    _callbacks = []  # (widget, fn)

    @classmethod
    def get(cls, key):
        return PALETTES[cls.current].get(key, "#ff00ff")

    @classmethod
    def bind(cls, widget, prop, key):
        cls._bindings.append((widget, prop, key))
        try:
            widget.configure({prop: cls.get(key)})
        except (tk.TclError, AttributeError):
            pass

    @classmethod
    def on_change(cls, widget, fn):
        cls._callbacks.append((widget, fn))

    @classmethod
    def set(cls, mode):
        if mode not in PALETTES:
            return
        cls.current = mode
        alive_b = []
        for w, prop, key in cls._bindings:
            try:
                if w.winfo_exists():
                    w.configure({prop: cls.get(key)})
                    alive_b.append((w, prop, key))
            except tk.TclError:
                pass
        cls._bindings = alive_b

        alive_c = []
        for w, fn in cls._callbacks:
            try:
                if w.winfo_exists():
                    fn()
                    alive_c.append((w, fn))
            except tk.TclError:
                pass
        cls._callbacks = alive_c
        _apply_ttk_style()


def _apply_ttk_style():
    """Theme the ttk comboboxes and their dropdown listboxes."""
    try:
        style = ttk.Style()
        style.theme_use("clam")
        bg = Theme.get("INPUT_BG")
        fg = Theme.get("TEXT")
        style.configure(
            "TCombobox",
            fieldbackground=bg,
            background=Theme.get("PANEL"),
            foreground=fg,
            arrowcolor=fg,
            selectbackground=Theme.get("ACCENT"),
            selectforeground=Theme.get("BG"),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", bg)],
            foreground=[("readonly", fg)],
            selectbackground=[("readonly", Theme.get("ACCENT"))],
            selectforeground=[("readonly", Theme.get("BG"))],
        )
        root = getattr(tk, "_default_root", None)
        if root is not None:
            root.option_add("*TCombobox*Listbox.background", bg)
            root.option_add("*TCombobox*Listbox.foreground", fg)
            root.option_add("*TCombobox*Listbox.selectBackground", Theme.get("ACCENT"))
            root.option_add("*TCombobox*Listbox.selectForeground", Theme.get("BG"))
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════
def load_config():
    cfg_path = Path("config.json")
    if cfg_path.exists():
        try:
            with open(cfg_path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def save_config_updates(updates, path=None):
    """Merge updates into config.json and replace it atomically."""
    target = Path(path) if path else CONFIG_PATH
    try:
        with open(target, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            cfg = {}
    except Exception:
        cfg = {}
    cfg.update(updates)
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=target.parent, delete=False, encoding="utf-8"
        ) as f:
            json.dump(cfg, f, indent=2)
            tmp_name = f.name
        os.replace(tmp_name, target)
    finally:
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass
    return cfg


def validate_timing(yellow, green, starvation, green_options):
    """Return (updates, error); reject bools, non-integers and invalid ranges."""
    if isinstance(yellow, bool) or isinstance(green, bool) or isinstance(starvation, bool):
        return None, "Timing values must be whole numbers."
    try:
        y = int(str(yellow).strip())
        g = int(str(green).strip())
        s = int(str(starvation).strip())
    except (TypeError, ValueError):
        return None, "Timing values must be whole numbers."
    if not green_options:
        return None, "No green durations are configured."
    if not 1 <= y < min(green_options):
        return None, f"Yellow time must be between 1 and {min(green_options) - 1} seconds."
    if g not in green_options:
        return None, "Default green must be one of the configured options."
    if s < 1:
        return None, "Starvation threshold must be at least 1."
    return {"yellow_time": y, "default_green": g, "starvation_threshold": s}, None


def set_session_key(provider, key):
    """Store a cloud API key in process memory only; return True on success."""
    env_var = {
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }.get(provider)
    key = (key or "").strip()
    if not env_var or not key:
        return False
    os.environ[env_var] = key
    return True


CONFIG = load_config()
GREEN_OPTIONS = CONFIG.get("green_options", [15, 30, 40, 50, 60])
DEFAULT_GREEN = CONFIG.get("default_green", 30)
DEFAULT_YELLOW = CONFIG.get("yellow_time", 5)
TIME_INTERVAL = 2

_UI_SCALE = 1.0


def scale_px(val):
    """Scale a fixed pixel dimension for the display DPI."""
    try:
        if _UI_SCALE == 1.0:
            return int(val)
        return int(round(val * _UI_SCALE))
    except Exception:
        return int(val)


def body_box(canvas_w, canvas_h, req_h, max_w=None):
    """Return (x, width, height) for the scroll body window."""
    return 0, max(1, int(canvas_w)), max(int(canvas_h), int(req_h))


def tile_row_h(holder_w, pad=6, max_w=None):
    """Height of one 16:9 tile row for a 2-column holder, or None if not laid out."""
    if holder_w <= 20:
        return None
    cell_w = holder_w / 2 - pad * 2
    if max_w is not None:
        cell_w = min(cell_w, max_w)
    return round(cell_w * 9 / 16) + pad * 2


def sb_needed(visible, req_h, canvas_h, margin=12):
    """Return whether the vertical scrollbar should be shown, with hysteresis."""
    if visible:
        return req_h > canvas_h - margin
    return req_h > canvas_h + margin


# Initialise theme from config
if CONFIG.get("theme") in PALETTES:
    Theme.current = CONFIG["theme"]


# ═══════════════════════════════════════════════════════════════════
# UI HELPERS
# ═══════════════════════════════════════════════════════════════════
FONT_TITLE = ("Courier New", 14, "bold")
FONT_H     = ("Courier New", 11, "bold")
FONT_B     = ("Courier New", 10)
FONT_MONO  = ("Courier New", 9)


def make_label(parent, text=None, font=FONT_B, fg_key="TEXT", bg_key="PANEL",
               textvariable=None, **kw):
    lbl = tk.Label(parent, text=text, font=font, textvariable=textvariable, **kw)
    Theme.bind(lbl, "fg", fg_key)
    Theme.bind(lbl, "bg", bg_key)
    return lbl


def round_rect(canvas, x1, y1, x2, y2, r, **kw):
    pts = [x1+r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y2-r, x2, y2,
           x2-r, y2, x1+r, y2, x1, y2, x1, y2-r, x1, y1+r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


class RoundedButton(tk.Canvas):
    """Rounded pill button drawn on a Canvas so we control its look."""
    def __init__(self, master, text, command=None, fill_key="ACCENT",
                 text_key="BG", hover_key="ACCENT_HOVER", radius=10,
                 height=40, font=FONT_TITLE, **kw):
        super().__init__(master, height=height, highlightthickness=0, bd=0, **kw)
        Theme.bind(self, "bg", "BG")
        self.text_str = text
        self.command = command
        self.fill_key = fill_key
        self.text_key = text_key
        self.hover_key = hover_key
        self.radius = radius
        self.font = font
        self._hover = False
        self._disabled = False
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Button-1>", self._click)
        Theme.on_change(self, self._draw)
        self._draw()

    def _set_hover(self, h):
        if self._disabled: return
        self._hover = h
        self._draw()

    def _click(self, _e):
        if not self._disabled and self.command:
            self.command()

    def set_text(self, text):
        self.text_str = text
        self._draw()

    def set_enabled(self, en):
        self._disabled = not en
        self._draw()

    def _draw(self):
        try:
            self.delete("all")
            w = self.winfo_width() or 1
            h = self.winfo_height() or 1
            if w < 4 or h < 4:
                return
            if self._disabled:
                fill = Theme.get("MUTED"); fg = Theme.get("SUBTEXT")
            elif self._hover:
                fill = Theme.get(self.hover_key); fg = Theme.get(self.text_key)
            else:
                fill = Theme.get(self.fill_key); fg = Theme.get(self.text_key)
            round_rect(self, 1, 1, w-1, h-1, self.radius, fill=fill, outline=fill)
            self.create_text(w//2, h//2, text=self.text_str, fill=fg, font=self.font)
        except tk.TclError:
            pass


def make_pill_radio(parent, text, variable, value, command=None, bg_key="PANEL"):
    """Pill-shaped radio that colours itself when selected."""
    rb = tk.Radiobutton(
        parent, text=text, variable=variable, value=value,
        indicatoron=False, font=FONT_B, relief="flat", bd=0,
        padx=12, pady=5, cursor="hand2",
    )
    def update():
        try:
            if variable.get() == value:
                rb.config(bg=Theme.get("ACCENT"), fg=Theme.get("BG"),
                          activebackground=Theme.get("ACCENT_HOVER"),
                          activeforeground=Theme.get("BG"),
                          selectcolor=Theme.get("ACCENT"))
            else:
                rb.config(bg=Theme.get(bg_key), fg=Theme.get("TEXT"),
                          activebackground=Theme.get("PANEL_ALT"),
                          activeforeground=Theme.get("TEXT"),
                          selectcolor=Theme.get(bg_key))
        except tk.TclError:
            pass
    variable.trace_add("write", lambda *a: update())
    Theme.on_change(rb, update)
    if command:
        rb.config(command=lambda: (command(), update()))
    update()
    return rb


def make_section(parent, title, pack_kw=None):
    """Bordered card with a header label; returns inner body frame."""
    outer = tk.Frame(parent, highlightthickness=1, bd=0)
    Theme.bind(outer, "bg", "PANEL")
    Theme.bind(outer, "highlightbackground", "BORDER")
    outer.pack(fill="x", **(pack_kw or {"pady": (0, 10)}))

    hdr = make_label(outer, text=title, font=FONT_MONO, fg_key="SUBTEXT",
                     bg_key="PANEL", anchor="w")
    hdr.pack(fill="x", padx=14, pady=(10, 4))

    body = tk.Frame(outer)
    Theme.bind(body, "bg", "PANEL")
    body.pack(fill="x", padx=14, pady=(0, 12))
    return body


def make_entry(parent, width=30, textvariable=None, show=None):
    e = tk.Entry(parent, font=FONT_MONO, relief="flat", bd=6,
                 width=width, textvariable=textvariable, show=show)
    Theme.bind(e, "bg", "INPUT_BG")
    Theme.bind(e, "fg", "TEXT")
    Theme.bind(e, "insertbackground", "ACCENT")
    Theme.bind(e, "highlightbackground", "BORDER")
    e.config(highlightthickness=1, highlightcolor=Theme.get("ACCENT"))
    return e


# ═══════════════════════════════════════════════════════════════════
# LANE CARD
# ═══════════════════════════════════════════════════════════════════
class LaneCard(tk.Frame):
    def __init__(self, master, lane_no, show_feed=True):
        super().__init__(master, highlightthickness=1, bd=0)
        Theme.bind(self, "bg", "PANEL")
        Theme.bind(self, "highlightbackground", "BORDER")
        self.lane_no = lane_no
        self.show_feed = show_feed
        self._photo = None
        self.camera = None
        self.is_editing = False
        self.draft_points = []
        self.frozen_frame = None
        self._cur_state = None
        self._canvas_dims = None
        self._render_box = None
        self._canvas_img_id = None
        self._last_frame = None
        self._resize_logged = False
        self._build()
        Theme.on_change(self, self._on_theme_change)

    def _build(self):
        hdr = tk.Frame(self, height=30)
        Theme.bind(hdr, "bg", "PANEL_ALT")
        hdr.pack(side="top", fill="x")
        hdr.pack_propagate(False)

        self.title_lbl = make_label(hdr, text=f"LANE {self.lane_no + 1}",
                                    font=FONT_H, fg_key="ACCENT", bg_key="PANEL_ALT")
        self.title_lbl.pack(side="left", padx=(12, 6))

        if self.show_feed:
            self.btn_edit_roi = tk.Button(
                hdr, text="Edit ROI", font=FONT_MONO, relief="flat",
                padx=6, pady=1, cursor="hand2", command=self.toggle_edit_roi)
            Theme.bind(self.btn_edit_roi, "bg", "PANEL_ALT")
            Theme.bind(self.btn_edit_roi, "fg", "ACCENT")
            Theme.bind(self.btn_edit_roi, "activebackground", "PANEL")
            Theme.bind(self.btn_edit_roi, "activeforeground", "ACCENT")
            self.btn_edit_roi.pack(side="left", padx=2)

            self.btn_clear_roi = tk.Button(
                hdr, text="Clear", font=FONT_MONO, relief="flat",
                padx=6, pady=1, cursor="hand2", command=self.clear_roi)
            Theme.bind(self.btn_clear_roi, "bg", "PANEL_ALT")
            Theme.bind(self.btn_clear_roi, "fg", "SUBTEXT")
            Theme.bind(self.btn_clear_roi, "activebackground", "PANEL")
            Theme.bind(self.btn_clear_roi, "activeforeground", "RED")
            self.btn_clear_roi.pack(side="left", padx=2)

        self.sig_label = tk.Label(hdr, text="● WAIT", font=FONT_B)
        Theme.bind(self.sig_label, "bg", "PANEL_ALT")
        self.sig_label.pack(side="right", padx=12)

        stats = tk.Frame(self)
        Theme.bind(stats, "bg", "PANEL")
        stats.pack(side="bottom", fill="x", padx=12, pady=6)

        self.count_var = tk.StringVar(value="Veh —")
        self.amb_var = tk.StringVar(value="Emer —")
        make_label(stats, textvariable=self.count_var, font=FONT_MONO,
                   fg_key="SUBTEXT", bg_key="PANEL").pack(side="left")
        make_label(stats, textvariable=self.amb_var, font=FONT_MONO,
                   fg_key="SUBTEXT", bg_key="PANEL").pack(side="right")

        if self.show_feed:
            self.canvas = tk.Canvas(self, width=320, height=180,
                                    bd=0, highlightthickness=0)
            Theme.bind(self.canvas, "bg", "CANVAS")
            self.canvas.pack(fill="both", expand=True, padx=1, pady=(1, 0))
            self.canvas.bind("<Button-1>", self._on_canvas_click)
            self.canvas.bind("<Configure>", self._on_canvas_configure)

    # ── camera / ROI plumbing (unchanged logic) ─────────────────────
    def set_camera(self, cam):
        self.camera = cam

    def _get_cam(self):
        return self.camera

    def _get_dashboard(self):
        p = self.master
        while p is not None:
            if isinstance(p, Dashboard):
                return p
            p = getattr(p, "master", None)
        return None

    def _log(self, msg):
        dash = self._get_dashboard()
        if dash and hasattr(dash, "_log"):
            dash._log(msg)
        else:
            print(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def start_edit_roi(self):
        if not getattr(self, "show_feed", False) or getattr(self, "is_editing", False):
            return
        cam = self._get_cam()
        frame = None
        if cam is not None:
            if getattr(cam, "last_frame", None) is not None:
                frame = cam.last_frame.copy()
            elif hasattr(cam, "read_frame"):
                frame = cam.read_frame()
        if frame is None:
            self._log(f"Lane {self.lane_no + 1}: No frame available to set ROI")
            return
        self.is_editing = True
        self.frozen_frame = frame.copy()
        self.draft_points = []
        self._resize_logged = False
        if hasattr(self, "btn_edit_roi"):
            self.btn_edit_roi.config(text="Cancel")
        self._redraw_edit_canvas()
        self._log(f"Lane {self.lane_no + 1}: Click 4 corners of lane ROI")

    def cancel_edit_roi(self):
        if not getattr(self, "is_editing", False):
            return
        self.is_editing = False
        self.draft_points = []
        last_f = self.frozen_frame
        self.frozen_frame = None
        if hasattr(self, "btn_edit_roi"):
            self.btn_edit_roi.config(text="Edit ROI")
        self._log(f"Lane {self.lane_no + 1}: ROI edit cancelled")
        cam = self._get_cam()
        if cam and getattr(cam, "last_frame", None) is not None:
            self.update_frame(cam.last_frame)
        elif last_f is not None:
            self.update_frame(last_f)

    def toggle_edit_roi(self):
        if getattr(self, "is_editing", False):
            self.cancel_edit_roi()
        else:
            self.start_edit_roi()

    def clear_roi(self):
        if getattr(self, "is_editing", False):
            self.cancel_edit_roi()
        cam = self._get_cam()
        if cam and hasattr(cam, "set_roi"):
            cam.set_roi(None)
            self._log(f"Lane {self.lane_no + 1}: ROI cleared (using full frame)")
            if getattr(cam, "last_frame", None) is not None:
                self.update_frame(cam.last_frame)

    def _on_canvas_configure(self, event):
        try:
            self._canvas_dims = (event.width, event.height)
        except Exception:
            return
        if getattr(self, "is_editing", False):
            self.draft_points = []
            self._redraw_edit_canvas()
            if not getattr(self, "_resize_logged", False):
                self._resize_logged = True
                self._log(f"Lane {self.lane_no + 1}: view resized — ROI draft cleared")
        elif getattr(self, "_last_frame", None) is not None:
            self.update_frame(self._last_frame)

    def _get_canvas_dims(self):
        dims = getattr(self, "_canvas_dims", None)
        if dims and dims[0] > 10 and dims[1] > 10:
            return dims
        try:
            w = self.canvas.winfo_width()
            h = self.canvas.winfo_height()
            if w > 10 and h > 10:
                return (w, h)
        except Exception:
            pass
        return (320, 200)

    def _canvas_realized(self):
        dims = getattr(self, "_canvas_dims", None)
        if dims and dims[0] > 10 and dims[1] > 10:
            return True
        try:
            return self.canvas.winfo_width() > 10 and self.canvas.winfo_height() > 10
        except Exception:
            return False

    def _render_geometry(self, frame_bgr):
        cw, ch = self._get_canvas_dims()
        if not self._canvas_realized():
            return 320, 200, 0, 0
        fh, fw = frame_bgr.shape[:2]
        if fw <= 0 or fh <= 0:
            return cw, ch, 0, 0
        scale = min(cw / fw, ch / fh)
        dw = max(1, int(fw * scale))
        dh = max(1, int(fh * scale))
        return dw, dh, (cw - dw) // 2, (ch - dh) // 2

    def _render_frame(self, frame_bgr):
        """Render a BGR frame into the canvas; return (disp_w, disp_h, ox, oy)."""
        dw, dh, ox, oy = self._render_geometry(frame_bgr)
        fh, fw = frame_bgr.shape[:2]
        interp = cv2.INTER_AREA if dw < fw else cv2.INTER_LINEAR
        img = cv2.resize(frame_bgr, (dw, dh), interpolation=interp)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        self._photo = ImageTk.PhotoImage(Image.fromarray(img))
        if getattr(self, "_canvas_img_id", None) is None:
            self._canvas_img_id = self.canvas.create_image(
                ox, oy, anchor="nw", image=self._photo)
        else:
            self.canvas.coords(self._canvas_img_id, ox, oy)
            self.canvas.itemconfig(self._canvas_img_id, image=self._photo)
        self._render_box = (dw, dh, ox, oy)
        return dw, dh, ox, oy

    def _on_canvas_click(self, event):
        if not getattr(self, "is_editing", False) or self.frozen_frame is None:
            return
        dw, dh, ox, oy = self._render_geometry(self.frozen_frame)
        cx = int(getattr(event, "x", 0)) - ox
        cy = int(getattr(event, "y", 0)) - oy
        if cx < 0 or cy < 0 or cx >= dw or cy >= dh:
            return
        self.draft_points.append((cx, cy))
        self._redraw_edit_canvas()

        if len(self.draft_points) == 4:
            fh, fw = self.frozen_frame.shape[:2]
            frame_pts = [canvas_to_frame(px, py, dw, dh, fw, fh)
                         for px, py in self.draft_points]
            valid_pts = validate_roi(frame_pts, fw, fh)
            cam = self._get_cam()
            if valid_pts is not None and cam is not None and hasattr(cam, "set_roi"):
                saved = cam.set_roi(valid_pts)
                if saved:
                    self.is_editing = False
                    self.draft_points = []
                    last_f = self.frozen_frame
                    self.frozen_frame = None
                    if hasattr(self, "btn_edit_roi"):
                        self.btn_edit_roi.config(text="Edit ROI")
                    self._log(f"Lane {self.lane_no + 1}: ROI configured")
                    if last_f is not None:
                        self.update_frame(last_f)
                    dash = self._get_dashboard()
                    if dash and hasattr(dash, "_on_lane_roi_configured"):
                        dash._on_lane_roi_configured(self.lane_no)
                    return
            self._log(f"Invalid ROI for Lane {self.lane_no + 1} — click 4 corners again")
            self.draft_points = []
            self._redraw_edit_canvas()

    def _redraw_edit_canvas(self):
        if self.frozen_frame is None or not getattr(self, "show_feed", False) \
                or not hasattr(self, "canvas"):
            return
        try:
            dw, dh, ox, oy = self._render_frame(self.frozen_frame)
            self.canvas.delete("overlay")
            pts = self.draft_points
            accent = Theme.get("ACCENT")
            for i, (cx, cy) in enumerate(pts):
                x, y = cx + ox, cy + oy
                r = 4
                self.canvas.create_oval(x-r, y-r, x+r, y+r,
                                        fill=accent, outline="#fff", width=1,
                                        tags=("overlay",))
                self.canvas.create_text(x+8, y-8, text=str(i+1),
                                        fill="#fff", font=FONT_MONO,
                                        tags=("overlay",))
                if i > 0:
                    px, py = pts[i-1]
                    self.canvas.create_line(px + ox, py + oy, x, y,
                                            fill=accent, width=2,
                                            tags=("overlay",))
            if len(pts) == 4:
                self.canvas.create_line(pts[3][0] + ox, pts[3][1] + oy,
                                        pts[0][0] + ox, pts[0][1] + oy,
                                        fill=accent, width=2,
                                        tags=("overlay",))
        except Exception:
            pass

    def update_frame(self, frame_bgr):
        if not getattr(self, "show_feed", False) or getattr(self, "is_editing", False) \
                or not hasattr(self, "canvas"):
            return
        try:
            self._last_frame = frame_bgr
            dw, dh, ox, oy = self._render_frame(frame_bgr)
            self.canvas.delete("overlay")
            cam = self._get_cam()
            if cam is not None and hasattr(cam, "get_roi"):
                roi = cam.get_roi()
                if roi is not None and len(roi) == 4:
                    fh, fw = frame_bgr.shape[:2]
                    canvas_pts = []
                    for fx, fy in roi:
                        cx, cy = frame_to_canvas(fx, fy, dw, dh, fw, fh)
                        canvas_pts.append((cx + ox, cy + oy))
                    flat = []
                    accent = Theme.get("ACCENT")
                    for cx, cy in canvas_pts:
                        flat.extend([cx, cy])
                        r = 3
                        self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                                fill=accent, outline="#fff",
                                                tags=("overlay",))
                    self.canvas.create_polygon(flat, outline=accent,
                                               fill="", width=2,
                                               tags=("overlay",))
        except Exception:
            pass

    def set_signal(self, signal, density=None, ambulance=None,
                   emergency_type=None, time_left=None):
        sig = signal.upper()
        suffix = f" ({time_left}s)" if time_left is not None else ""
        if sig == "GREEN":
            self.sig_label.config(text=f"● GO{suffix}", fg=Theme.get("GREEN"))
            self.config(highlightbackground=Theme.get("GREEN"))
        elif sig == "RED":
            self.sig_label.config(text="● STOP", fg=Theme.get("RED"))
            self.config(highlightbackground=Theme.get("RED"))
        else:
            self.sig_label.config(text=f"● WAIT{suffix}", fg=Theme.get("YELLOW"))
            self.config(highlightbackground=Theme.get("YELLOW"))

        if density is not None:
            self.count_var.set(f"Veh {density}")

        if emergency_type is not None:
            e = str(emergency_type).strip().lower()
            if e == "firetruck":
                self.amb_var.set("Emer 🚒")
            elif e == "ambulance":
                self.amb_var.set("Emer 🚨")
            else:
                self.amb_var.set("Emer —")
        elif ambulance is not None:
            self.amb_var.set("Emer 🚨" if ambulance else "Emer —")

        self._cur_state = (signal, density, ambulance, emergency_type, time_left)

    def _on_theme_change(self):
        if self._cur_state:
            self.set_signal(*self._cur_state)


# ═══════════════════════════════════════════════════════════════════
# SETUP SCREEN (Split Console)
# ═══════════════════════════════════════════════════════════════════
class SetupScreen(tk.Frame):
    def __init__(self, master, on_start, on_settings=None):
        super().__init__(master)
        Theme.bind(self, "bg", "BG")
        self.on_start = on_start
        self.on_settings = on_settings
        self.video_paths = []
        self._path_entries = []
        self._preview_canvases = []
        self._clock_job = None
        self._build()
        self._rebuild_previews()
        self._tick_clock()
        self.bind("<Destroy>", self._on_destroy)

    def _build(self):
        # ── top bar ────────────────────────────────────────────────
        top = tk.Frame(self)
        Theme.bind(top, "bg", "PANEL")
        top.pack(fill="x")
        top_inner = tk.Frame(top)
        Theme.bind(top_inner, "bg", "PANEL")
        top_inner.pack(fill="x", padx=20, pady=10)

        make_label(top_inner, text="▶ TRAFFIC OPS — CONFIGURE",
                   font=FONT_TITLE, fg_key="ACCENT", bg_key="PANEL"
                   ).pack(side="left")

        gear = tk.Button(top_inner, text="⚙", font=("Courier New", 14),
                         relief="flat", cursor="hand2", padx=10,
                         command=self.on_settings)
        Theme.bind(gear, "bg", "PANEL"); Theme.bind(gear, "fg", "TEXT")
        Theme.bind(gear, "activebackground", "PANEL_ALT")
        Theme.bind(gear, "activeforeground", "ACCENT")
        gear.pack(side="right")

        self.clock_var = tk.StringVar(value="")
        clock = make_label(top_inner, textvariable=self.clock_var,
                           font=FONT_MONO, fg_key="SUBTEXT", bg_key="PANEL")
        clock.pack(side="right", padx=12)

        # ── scrollable body split ─────────────────────────────────
        scroll_wrap = tk.Frame(self)
        Theme.bind(scroll_wrap, "bg", "BG")
        scroll_wrap.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(scroll_wrap, bd=0, highlightthickness=0)
        Theme.bind(self.canvas, "bg", "BG")
        scrollbar = ttk.Scrollbar(scroll_wrap, orient="vertical",
                                  command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self._scrollbar = scrollbar
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.body_frame = tk.Frame(self.canvas)
        Theme.bind(self.body_frame, "bg", "BG")
        self._body_window = self.canvas.create_window(
            (0, 0), window=self.body_frame, anchor="nw")
        self._last_body_box = None
        self.body_frame.bind("<Configure>", self._layout_body)
        self.canvas.bind("<Configure>", self._layout_body)
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)

        self.col_left = tk.Frame(self.body_frame, width=scale_px(290))
        Theme.bind(self.col_left, "bg", "BG")
        self.col_left.grid(row=0, column=0, sticky="nsew",
                           padx=(20, 10), pady=16)

        self.col_right = tk.Frame(self.body_frame)
        Theme.bind(self.col_right, "bg", "BG")
        self.col_right.grid(row=0, column=1, sticky="nsew",
                            padx=(10, 20), pady=16)
        self.body_frame.columnconfigure(0, weight=0,
                                        minsize=scale_px(340))
        self.body_frame.columnconfigure(1, weight=1)
        self.body_frame.rowconfigure(0, weight=1)

        self._build_left(self.col_left)
        self._build_right(self.col_right)

        # ── bottom log strip ──────────────────────────────────────
        strip = tk.Frame(self, height=40)
        Theme.bind(strip, "bg", "PANEL")
        strip.pack(fill="x", side="bottom")
        strip.pack_propagate(False)
        make_label(strip, text="LOG", font=FONT_MONO, fg_key="SUBTEXT",
                   bg_key="PANEL").pack(side="left", padx=(20, 8))
        self.log_var = tk.StringVar(value="Waiting for configuration…")
        make_label(strip, textvariable=self.log_var, font=FONT_MONO,
                   fg_key="TEXT", bg_key="PANEL").pack(side="left")
        self._update_summary()

    def _layout_body(self, _e=None):
        try:
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            req_h = self.body_frame.winfo_reqheight()
            x, w, h = body_box(cw, ch, req_h)
            y = 0
            show_sb = sb_needed(getattr(self, "_sb_visible", False),
                                req_h, ch, 12)
            self._sb_visible = show_sb
            layout = (x, w, h, y, show_sb)
            if layout == getattr(self, "_last_body_box", None):
                return
            self._last_body_box = layout
            self.canvas.coords(self._body_window, x, y)
            self.canvas.itemconfig(self._body_window, width=w, height=h)
            self.canvas.configure(scrollregion=(0, 0, cw, h))
            if show_sb:
                self._scrollbar.pack(side="right", fill="y",
                                     before=self.canvas)
            else:
                self._scrollbar.pack_forget()
        except Exception:
            pass

    def _bind_wheel(self, _e=None):
        try:
            self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        except Exception:
            pass

    def _unbind_wheel(self, _e=None):
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass

    def _on_mousewheel(self, event):
        try:
            if self.body_frame.winfo_reqheight() <= self.canvas.winfo_height():
                return
            self.canvas.yview_scroll(int(-event.delta / 120), "units")
        except Exception:
            pass

    # ── left rail ──────────────────────────────────────────────────
    def _build_left(self, parent):
        # INPUT MODE
        mode_body = make_section(parent, "INPUT MODE", {"pady": (0, 10)})
        self.mode_var = tk.IntVar(value=0)
        for val, lbl in [(0, "Live Camera"), (1, "Video Files"), (2, "Manual Input")]:
            make_pill_radio(mode_body, lbl, self.mode_var, val,
                            command=self._on_mode_change).pack(fill="x", pady=2)

        # LANES
        lane_body = make_section(parent, "LANES", {"pady": (0, 10)})
        self.lane_var = tk.IntVar(value=2)
        lane_row = tk.Frame(lane_body)
        Theme.bind(lane_row, "bg", "PANEL")
        lane_row.pack(fill="x")
        for n in (1, 2, 3, 4):
            make_pill_radio(lane_row, str(n), self.lane_var, n,
                            command=self._on_lane_change
                            ).pack(side="left", fill="x", expand=True, padx=2)

        # GREEN DURATION
        green_body = make_section(parent, "GREEN DURATION", {"pady": (0, 10)})
        self.green_var = tk.IntVar(value=DEFAULT_GREEN)
        green_row = tk.Frame(green_body)
        Theme.bind(green_row, "bg", "PANEL")
        green_row.pack(fill="x")
        for g in GREEN_OPTIONS:
            make_pill_radio(green_row, f"{g}s", self.green_var, g,
                            command=self._update_summary
                            ).pack(side="left", fill="x", expand=True, padx=2)

        # DETECTOR
        det_body = make_section(parent, "DETECTOR", {"pady": (0, 10)})
        self.engine_card = det_body
        cfg = get_detector_config()
        init_choice = "yolo" if cfg.get("detector") == "yolo" \
                      else cfg.get("provider", "gemini")
        self.provider_var = tk.StringVar(value=init_choice)
        for val, lbl in [("gemini", "Gemini"), ("groq", "Groq"),
                         ("openrouter", "OpenRouter"), ("yolo", "Local YOLO")]:
            make_pill_radio(det_body, lbl, self.provider_var, val,
                            command=self._on_provider_change).pack(fill="x", pady=2)

        # MODEL
        model_body = make_section(parent, "MODEL", {"pady": (0, 10)})
        row = tk.Frame(model_body)
        Theme.bind(row, "bg", "PANEL")
        row.pack(fill="x")
        self.model_combo = ttk.Combobox(row, font=FONT_MONO, width=22)
        self.model_combo.pack(side="left", fill="x", expand=True)
        self.model_combo.bind("<<ComboboxSelected>>",
                              lambda e: self._update_summary())
        self.model_combo.bind("<KeyRelease>", lambda e: self._update_summary())
        self.model_combo.bind("<MouseWheel>", self._on_combo_mousewheel)
        self.btn_refresh_models = tk.Button(row, text="↻", font=FONT_MONO,
                                            relief="flat", padx=6, cursor="hand2",
                                            command=self._refresh_local_models)
        Theme.bind(self.btn_refresh_models, "bg", "PANEL_ALT")
        Theme.bind(self.btn_refresh_models, "fg", "ACCENT")
        Theme.bind(self.btn_refresh_models, "activebackground", "PANEL")
        self.btn_refresh_models.pack(side="left", padx=(4, 0))
        self._update_model_options()

    # ── right pane ─────────────────────────────────────────────────
    def _build_right(self, parent):
        # LANES card (packed last so it claims the remaining space)
        prev_outer = tk.Frame(parent, highlightthickness=1, bd=0)
        Theme.bind(prev_outer, "bg", "PANEL")
        Theme.bind(prev_outer, "highlightbackground", "BORDER")
        self._lanes_card = prev_outer

        prev_hdr = make_label(prev_outer, text="LANES", font=FONT_MONO,
                              fg_key="SUBTEXT", bg_key="PANEL", anchor="w")
        prev_hdr.pack(fill="x", padx=14, pady=(10, 4))

        self.preview_holder = tk.Frame(prev_outer, height=scale_px(220))
        Theme.bind(self.preview_holder, "bg", "PANEL")
        self.preview_holder.grid_propagate(False)
        self.preview_holder.pack(fill="x", padx=14, pady=(4, 12))
        self.preview_holder.bind("<Configure>", self._fit_holder)
        Theme.on_change(self.preview_holder, self._refresh_preview_text)

        # SOURCE FILES (mode-dependent)
        self.path_card = tk.Frame(parent, highlightthickness=1, bd=0)
        Theme.bind(self.path_card, "bg", "PANEL")
        Theme.bind(self.path_card, "highlightbackground", "BORDER")
        self._path_card_visible = False

        path_hdr = make_label(self.path_card, text="SOURCE FILES",
                              font=FONT_MONO, fg_key="SUBTEXT",
                              bg_key="PANEL", anchor="w")
        path_hdr.pack(fill="x", padx=14, pady=(10, 4))

        self.path_frame = tk.Frame(self.path_card)
        Theme.bind(self.path_frame, "bg", "PANEL")
        self.path_frame.pack(fill="x", padx=14, pady=(0, 12))

        # SUMMARY (2-column KPI grid)
        sum_outer = tk.Frame(parent, highlightthickness=1, bd=0)
        Theme.bind(sum_outer, "bg", "PANEL")
        Theme.bind(sum_outer, "highlightbackground", "BORDER")

        sum_hdr = make_label(sum_outer, text="SUMMARY", font=FONT_MONO,
                             fg_key="SUBTEXT", bg_key="PANEL", anchor="w")
        sum_hdr.pack(fill="x", padx=14, pady=(10, 4))

        self.summary_body = tk.Frame(sum_outer)
        Theme.bind(self.summary_body, "bg", "PANEL")
        self.summary_body.pack(fill="x", padx=14, pady=(0, 12))

        self._summary_vars = {}
        for idx, key in enumerate(("Mode", "Lanes", "Green", "Detector", "Status")):
            cell = tk.Frame(self.summary_body)
            Theme.bind(cell, "bg", "PANEL")
            cell.grid(row=idx // 2, column=idx % 2,
                      sticky="nsew", padx=6, pady=4)
            make_label(cell, text=key.upper(), font=FONT_MONO,
                       fg_key="SUBTEXT", bg_key="PANEL", anchor="w"
                       ).pack(fill="x")
            var = tk.StringVar(value="—")
            lbl = make_label(cell, textvariable=var, font=FONT_H,
                             fg_key="TEXT", bg_key="PANEL", anchor="w")
            lbl.pack(fill="x")
            self._summary_vars[key] = (var, lbl)
        for col in range(2):
            self.summary_body.columnconfigure(col, weight=1)

        # Compact top-down stack: LANES, SUMMARY, then START.
        start_wrap = tk.Frame(parent)
        Theme.bind(start_wrap, "bg", "BG")
        self.start_btn = RoundedButton(start_wrap, text="START CONTROLLER  →",
                                       command=self._start, radius=10, height=44)
        self.start_btn.pack(fill="x")
        prev_outer.pack(fill="x", pady=(0, 10))
        sum_outer.pack(fill="x", pady=(0, 10))
        start_wrap.pack(fill="x")

    # ── preview logic ──────────────────────────────────────────────
    def _rebuild_previews(self):
        n = self.lane_var.get()
        key = (self.mode_var.get(), n)
        if key == getattr(self, "_previews_key", None):
            self._refresh_preview_text()
            return
        self._previews_key = key
        self._tile_size = None
        if len(self._preview_canvases) != n:
            for w in self.preview_holder.winfo_children():
                w.destroy()
            self._preview_canvases = []
            for i in range(n):
                c = tk.Canvas(self.preview_holder, width=10, height=10, bd=0,
                              highlightthickness=0)
                Theme.bind(c, "bg", "PANEL")
                c.bind("<Configure>",
                       lambda e, i=i: self._draw_preview_tile(i, e.width, e.height))
                self._preview_canvases.append(c)
        for c in self._preview_canvases:
            c.grid_forget()
        for i, c in enumerate(self._preview_canvases):
            if n == 1:
                c.grid(row=0, column=0, rowspan=2, columnspan=2,
                       padx=6, pady=6, sticky="nsew")
            elif n == 2:
                c.grid(row=0, column=i, rowspan=2,
                       padx=6, pady=6, sticky="nsew")
            else:
                c.grid(row=i // 2, column=i % 2,
                       padx=6, pady=6, sticky="nsew")
        for col in range(2):
            self.preview_holder.columnconfigure(col, weight=1)
        for row in range(2):
            self.preview_holder.rowconfigure(row, weight=1)
        self._refresh_preview_text()

    def _fit_holder(self, event=None):
        try:
            holder_w = self.preview_holder.winfo_width()
            row_h = tile_row_h(holder_w, 6, scale_px(480))
            if row_h is None:
                return
            fit = (holder_w, row_h)
            if fit == getattr(self, "_last_holder_fit", None):
                return
            self._last_holder_fit = fit
            self.preview_holder.configure(height=2 * row_h)
            self.preview_holder.rowconfigure(0, minsize=row_h)
            self.preview_holder.rowconfigure(1, minsize=row_h)
        except tk.TclError:
            pass

    def _resize_tiles(self, event=None):
        """Compatibility no-op: grid weights size the tiles, not this method."""
        return None

    def _draw_preview_tile(self, i, w, h):
        if w <= 10 or h <= 10:
            return
        try:
            c = self._preview_canvases[i]
        except (IndexError, AttributeError):
            return
        c.delete("all")
        avail_w = max(10, w - 4)
        avail_h = max(10, h - 4)
        if avail_w / avail_h > 16 / 9:
            th = avail_h
            tw = max(10, int(round(th * 16 / 9)))
        else:
            tw = avail_w
            th = max(10, int(round(tw * 9 / 16)))
        x1 = (w - tw) // 2
        y1 = (h - th) // 2
        x2 = x1 + tw
        y2 = y1 + th
        c.create_rectangle(
            x1, y1, x2, y2,
            fill=Theme.get("INPUT_BG"),
            outline=Theme.get("BORDER"),
            width=1,
        )
        mode = self.mode_var.get()
        if mode == 1 and i < len(self._path_entries):
            path = self._path_entries[i].get().strip()
            text = f"L{i+1}  {'✓ READY' if path else '— IDLE'}"
        elif mode == 0:
            text = f"L{i+1}  ● CAM {i}"
        else:
            text = f"L{i+1}"
        c.create_text(w//2, h//2, text=text, fill=Theme.get("SUBTEXT"),
                      font=FONT_MONO)

    def _refresh_preview_text(self):
        for i, c in enumerate(self._preview_canvases):
            try:
                w = c.winfo_width()
                h = c.winfo_height()
            except Exception:
                continue
            if w > 10 and h > 10:
                self._draw_preview_tile(i, w, h)

    # ── callbacks ──────────────────────────────────────────────────
    def _tick_clock(self):
        self.clock_var.set(time.strftime("%H:%M:%S"))
        self._clock_job = self.after(1000, self._tick_clock)

    def _on_destroy(self, _e):
        if self._clock_job:
            try: self.after_cancel(self._clock_job)
            except Exception: pass
        self._unbind_wheel()

    def on_settings_saved(self, updates):
        """Refresh the green-default selection and summary after a settings save."""
        if "default_green" in updates:
            try:
                self.green_var.set(updates["default_green"])
            except Exception:
                pass
        self._update_summary()

    def _on_mode_change(self):
        mode = self.mode_var.get()
        self._rebuild_previews()
        want = mode == 1
        if want != getattr(self, "_path_card_visible", False):
            self._path_card_visible = want
            if want:
                self.path_card.pack(fill="x", pady=(0, 10),
                                    before=self.summary_body.master)
            else:
                self.path_card.pack_forget()
        if want:
            self._rebuild_paths()
        else:
            self._path_entries = []
            self._paths_key = None
        self._update_summary()

    def _on_lane_change(self):
        self._rebuild_previews()
        if self.mode_var.get() == 1:
            self._rebuild_paths()
        self._update_summary()

    def _rebuild_paths(self):
        n = self.lane_var.get()
        key = (self.mode_var.get(), n)
        if key == getattr(self, "_paths_key", None):
            return
        self._paths_key = key
        for w in self.path_frame.winfo_children():
            w.destroy()
        self.video_paths = [""] * n
        self._path_entries = []
        for i in range(n):
            row = tk.Frame(self.path_frame)
            Theme.bind(row, "bg", "PANEL")
            row.pack(fill="x", pady=3)
            make_label(row, text=f"L{i+1}", font=FONT_MONO, fg_key="SUBTEXT",
                       bg_key="PANEL", width=4, anchor="w").pack(side="left")
            e = make_entry(row, width=28)
            e.pack(side="left", fill="x", expand=True, padx=(0, 6))
            self._path_entries.append(e)

            def browse(_e=e):
                path = filedialog.askopenfilename(
                    filetypes=[("Video", "*.mp4 *.avi *.mov *.mkv"),
                               ("All", "*.*")])
                if path:
                    _e.delete(0, tk.END)
                    _e.insert(0, path)
                    self._update_summary()
                    self._refresh_preview_text()

            btn = tk.Button(row, text="Browse", font=FONT_MONO, relief="flat",
                            padx=8, cursor="hand2", command=browse)
            Theme.bind(btn, "bg", "PANEL_ALT"); Theme.bind(btn, "fg", "ACCENT")
            Theme.bind(btn, "activebackground", "PANEL")
            Theme.bind(btn, "activeforeground", "ACCENT")
            btn.pack(side="left")
        self._update_summary()

    def _on_provider_change(self):
        self._update_model_options()
        self._update_summary()

    def _on_combo_mousewheel(self, event):
        """Keep mouse-wheel scrolling from changing the model selection."""
        return "break"

    def _refresh_local_models(self):
        if self.provider_var.get() == "yolo":
            models = list_local_models("Model")
            self.model_combo["values"] = models
            if models:
                self.model_combo.set(models[0])
                self.model_combo.selection_clear()

    def _update_model_options(self):
        choice = self.provider_var.get()
        cfg = get_detector_config()
        v_models = cfg.get("vision_models", {})
        if choice == "yolo":
            self.btn_refresh_models.pack(side="left", padx=(4, 0))
            local = list_local_models("Model")
            self.model_combo["values"] = local
            curr = cfg.get("ambulance_model", "Model/best.pt")
            self.model_combo.set(curr if curr in local else (local[0] if local else ""))
        else:
            self.btn_refresh_models.pack_forget()
            opts = v_models.get(choice, [])
            self.model_combo["values"] = opts
            curr = cfg.get("vision_model", "")
            self.model_combo.set(curr if curr in opts else (opts[0] if opts else ""))
        self.model_combo.selection_clear()
        self._update_summary()

    def _update_summary(self):
        try:
            mode = self.mode_var.get()
            mode_name = ["Live Camera", "Video Files", "Manual Input"][mode]
            lanes = self.lane_var.get()
            green = self.green_var.get()
            prov = self.provider_var.get().upper()
            model = self.model_combo.get() or "—"
            detector = f"{prov} / {model}"

            ok = True
            issue = ""
            if mode == 1:
                for i, e in enumerate(self._path_entries):
                    if not e.get().strip():
                        ok = False
                        issue = f"missing L{i+1} path"
                        break
            status_text = "● ready" if ok else f"● {issue}"
            status_key = "GREEN" if ok else "RED"

            self._summary_vars["Mode"][0].set(mode_name)
            self._summary_vars["Lanes"][0].set(str(lanes))
            self._summary_vars["Green"][0].set(f"{green}s")
            self._summary_vars["Detector"][0].set(detector)
            self._summary_vars["Status"][0].set(status_text)
            lbl = self._summary_vars["Status"][1]
            try:
                lbl.configure(fg=Theme.get(status_key))
            except tk.TclError:
                pass
            self.start_btn.set_enabled(ok)
        except Exception:
            pass

    def _start(self):
        mode = self.mode_var.get()
        lanes = self.lane_var.get()
        green = self.green_var.get()

        if mode != 2:
            choice = self.provider_var.get()
            model = self.model_combo.get().strip()
            if choice == "yolo":
                set_detector_config(detector="yolo", ambulance_model=model)
            else:
                set_detector_config(detector="vision", provider=choice,
                                    vision_model=model)

        if mode == 1:
            paths = [e.get().strip() for e in self._path_entries]
            if any(p == "" for p in paths):
                messagebox.showwarning("Missing paths",
                                       "Please select a video for every lane.")
                return
            self.on_start(mode, lanes, paths, green)
        else:
            self.on_start(mode, lanes, [], green)


# ═══════════════════════════════════════════════════════════════════
# MANUAL INPUT DIALOG
# ═══════════════════════════════════════════════════════════════════
class ManualDialog(tk.Toplevel):
    def __init__(self, master, lanes, on_submit, initial_data=None):
        super().__init__(master)
        self.title("Manual Input")
        self.resizable(False, False)
        self.lanes = lanes
        self.on_submit = on_submit
        self.initial_data = initial_data or {}
        self.entries = {}
        self.emerg_vars = {}
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        try:
            self.configure(bg=Theme.get("BG"))
        except Exception:
            pass
        self._build()
        self.grab_set()

    def _build(self):
        make_label(self, text="MANUAL LANE INPUT", font=FONT_H,
                   fg_key="ACCENT", bg_key="BG").pack(pady=(20, 2), padx=30)
        make_label(self, text="enter values for each lane",
                   font=FONT_MONO, fg_key="SUBTEXT", bg_key="BG"
                   ).pack(pady=(0, 12))

        for i in range(self.lanes):
            card = tk.Frame(self, highlightthickness=1, bd=0)
            Theme.bind(card, "bg", "PANEL")
            Theme.bind(card, "highlightbackground", "BORDER")
            card.pack(padx=24, pady=4, fill="x")

            make_label(card, text=f"Lane {i+1}", font=FONT_H,
                       fg_key="ACCENT", bg_key="PANEL"
                       ).pack(anchor="w", padx=14, pady=(8, 2))

            row1 = tk.Frame(card); Theme.bind(row1, "bg", "PANEL")
            row1.pack(fill="x", padx=14, pady=2)
            make_label(row1, text="Vehicles:", font=FONT_B, fg_key="TEXT",
                       bg_key="PANEL", width=10, anchor="w").pack(side="left")
            init_d = str(self.initial_data.get(i, {}).get("density", 0))
            e = make_entry(row1, width=10)
            e.insert(0, init_d)
            e.pack(side="left")
            self.entries[i] = e

            row2 = tk.Frame(card); Theme.bind(row2, "bg", "PANEL")
            row2.pack(fill="x", padx=14, pady=(2, 8))
            make_label(row2, text="Emergency:", font=FONT_B, fg_key="TEXT",
                       bg_key="PANEL", width=10, anchor="w").pack(side="left")
            init_emerg = self.initial_data.get(i, {}).get("emergency_type", "")
            if not init_emerg:
                init_emerg = "ambulance" if self.initial_data.get(i, {}).get("ambulance") else "none"
            init_emerg = str(init_emerg).strip().lower()
            if init_emerg not in ("none", "ambulance", "firetruck"):
                init_emerg = "none"
            var = tk.StringVar(value=init_emerg)
            for val, lbl in [("none", "None"), ("ambulance", "Ambulance 🚨"),
                             ("firetruck", "Firetruck 🚒")]:
                make_pill_radio(row2, lbl, var, val).pack(side="left", padx=2)
            self.emerg_vars[i] = var

        self.run_btn = RoundedButton(self, text="RUN CONTROL  ▶",
                                     command=self._submit, radius=8, height=40)
        self.run_btn.pack(padx=24, pady=16, fill="x")

    def _submit(self):
        data = {}
        for i in range(self.lanes):
            try:
                d = int(self.entries[i].get())
                if d < 0: raise ValueError
            except ValueError:
                messagebox.showerror("Invalid", f"Lane {i+1}: valid positive number.")
                return
            sel = self.emerg_vars[i].get().lower()
            is_e = sel in ("ambulance", "firetruck")
            data[i] = {"density": d, "ambulance": is_e,
                       "emergency": is_e,
                       "emergency_type": sel if is_e else "none"}
        self._clear_dashboard_ref()
        self.destroy()
        self.on_submit(data)

    def _clear_dashboard_ref(self):
        dash = getattr(self, "master", None)
        if dash is not None and hasattr(dash, "_manual_dialog"):
            dash._manual_dialog = None

    def _on_close(self):
        fallback = self.initial_data if self.initial_data else {
            i: {"density": 0, "ambulance": False, "emergency": False,
                "emergency_type": "none"}
            for i in range(self.lanes)}
        self._clear_dashboard_ref()
        self.destroy()
        self.on_submit(fallback)


# ═══════════════════════════════════════════════════════════════════
# SETTINGS DIALOG
# ═══════════════════════════════════════════════════════════════════
class SettingsDialog(tk.Toplevel):
    def __init__(self, master, on_saved=None):
        super().__init__(master)
        self.title("Settings")
        self.geometry(f"{scale_px(520)}x{scale_px(780)}")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.on_saved = on_saved
        try:
            self.configure(bg=Theme.get("BG"))
        except Exception:
            pass
        self._orig_theme = Theme.current
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._build()
        self._center_on(master)

    def _center_on(self, parent):
        try:
            parent.update_idletasks()
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            self.update_idletasks()
            w, h = self.winfo_width(), self.winfo_height()
            x = px + (pw - w) // 2
            y = py + (ph - h) // 2
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _build(self):
        # header
        hdr = tk.Frame(self)
        Theme.bind(hdr, "bg", "PANEL")
        hdr.pack(fill="x")
        inner = tk.Frame(hdr); Theme.bind(inner, "bg", "PANEL")
        inner.pack(fill="x", padx=20, pady=12)
        make_label(inner, text="⚙  SETTINGS", font=FONT_TITLE,
                   fg_key="ACCENT", bg_key="PANEL").pack(side="left")
        close_btn = tk.Button(inner, text="✕", font=("Courier New", 12),
                              relief="flat", cursor="hand2", padx=8,
                              command=self._cancel)
        Theme.bind(close_btn, "bg", "PANEL"); Theme.bind(close_btn, "fg", "TEXT")
        Theme.bind(close_btn, "activebackground", "PANEL_ALT")
        Theme.bind(close_btn, "activeforeground", "RED")
        close_btn.pack(side="right")

        # body
        body = tk.Frame(self)
        Theme.bind(body, "bg", "BG")
        body.pack(fill="both", expand=True, padx=20, pady=14)

        # APPEARANCE
        app_body = make_section(body, "APPEARANCE", {"pady": (0, 12)})
        self.theme_var = tk.StringVar(value=Theme.current)
        row = tk.Frame(app_body); Theme.bind(row, "bg", "PANEL")
        row.pack(fill="x")
        for val, lbl in [("dark", "Dark"), ("light", "Light")]:
            make_pill_radio(row, lbl, self.theme_var, val,
                            command=self._on_theme_radio).pack(side="left", padx=2)

        # DETECTOR
        det_body = make_section(body, "DETECTOR", {"pady": (0, 12)})
        dcfg = get_detector_config()
        init_provider = "yolo" if dcfg.get("detector") == "yolo" \
                        else dcfg.get("provider", "gemini")
        self.provider_var = tk.StringVar(value=init_provider)

        prow = tk.Frame(det_body); Theme.bind(prow, "bg", "PANEL")
        prow.pack(fill="x", pady=2)
        make_label(prow, text="Provider", font=FONT_MONO, fg_key="SUBTEXT",
                   bg_key="PANEL", width=10, anchor="w").pack(side="left")
        for val, lbl in [("gemini", "Gemini"), ("groq", "Groq"),
                         ("openrouter", "OpenRouter"), ("yolo", "YOLO")]:
            make_pill_radio(prow, lbl, self.provider_var, val,
                            command=self._on_provider_change).pack(side="left", padx=2)

        mrow = tk.Frame(det_body); Theme.bind(mrow, "bg", "PANEL")
        mrow.pack(fill="x", pady=(6, 2))
        make_label(mrow, text="Model", font=FONT_MONO, fg_key="SUBTEXT",
                   bg_key="PANEL", width=10, anchor="w").pack(side="left")
        self.model_combo = ttk.Combobox(mrow, font=FONT_MONO, width=32)
        self.model_combo.pack(side="left", fill="x", expand=True)
        self._load_models()

        # API KEYS
        keys_body = make_section(body, "API KEYS", {"pady": (0, 12)})
        make_label(keys_body, text="Session only. Add keys to .env to persist.",
                   font=FONT_MONO, fg_key="MUTED", bg_key="PANEL", anchor="w"
                   ).pack(fill="x")
        self.key_status_var = tk.StringVar(value="")
        make_label(keys_body, textvariable=self.key_status_var, font=FONT_MONO,
                   fg_key="TEXT", bg_key="PANEL", anchor="w"
                   ).pack(fill="x", pady=(4, 4))
        self.api_key_var = tk.StringVar(value="")
        self.api_key_entry = make_entry(keys_body, width=34,
                                        textvariable=self.api_key_var, show="•")
        self.api_key_entry.pack(fill="x")
        self._refresh_key_status()

        # TIMING
        tm_body = make_section(body, "SIGNAL TIMING", {"pady": (0, 12)})
        yrow = tk.Frame(tm_body); Theme.bind(yrow, "bg", "PANEL")
        yrow.pack(fill="x", pady=2)
        make_label(yrow, text="Yellow (s)", font=FONT_MONO, fg_key="SUBTEXT",
                   bg_key="PANEL", width=12, anchor="w").pack(side="left")
        self.yellow_var = tk.StringVar(value=str(DEFAULT_YELLOW))
        make_entry(yrow, width=8, textvariable=self.yellow_var).pack(side="left")

        grow = tk.Frame(tm_body); Theme.bind(grow, "bg", "PANEL")
        grow.pack(fill="x", pady=(6, 2))
        make_label(grow, text="Default green", font=FONT_MONO, fg_key="SUBTEXT",
                   bg_key="PANEL", width=12, anchor="w").pack(side="left")
        self.default_green_var = tk.StringVar(value=str(DEFAULT_GREEN))
        gc = ttk.Combobox(grow, font=FONT_MONO, width=10, state="readonly",
                          values=[str(g) for g in GREEN_OPTIONS])
        gc.set(str(DEFAULT_GREEN))
        self.default_green_var.trace_add("write",
            lambda *a: gc.set(self.default_green_var.get()))
        gc.bind("<<ComboboxSelected>>",
                lambda e: self.default_green_var.set(gc.get()))
        gc.pack(side="left")

        srow = tk.Frame(tm_body); Theme.bind(srow, "bg", "PANEL")
        srow.pack(fill="x", pady=(6, 2))
        make_label(srow, text="Starvation", font=FONT_MONO, fg_key="SUBTEXT",
                   bg_key="PANEL", width=12, anchor="w").pack(side="left")
        self.starvation_var = tk.StringVar(
            value=str(load_config().get("starvation_threshold", 3)))
        make_entry(srow, width=8, textvariable=self.starvation_var).pack(side="left")

        make_label(tm_body, text="(timing applies from the next cycle)",
                   font=FONT_MONO, fg_key="MUTED", bg_key="PANEL"
                   ).pack(anchor="w", pady=(6, 0))

        # SYSTEM
        sys_body = make_section(body, "SYSTEM", {"pady": (0, 12)})
        for label, value in [("Config", "config.json"),
                             ("Version", "v1.0")]:
            row = tk.Frame(sys_body); Theme.bind(row, "bg", "PANEL")
            row.pack(fill="x", pady=1)
            make_label(row, text=label, font=FONT_MONO, fg_key="SUBTEXT",
                       bg_key="PANEL", width=10, anchor="w").pack(side="left")
            make_label(row, text=value, font=FONT_MONO, fg_key="TEXT",
                       bg_key="PANEL", anchor="w").pack(side="left")

        # footer
        footer = tk.Frame(self)
        Theme.bind(footer, "bg", "BG")
        footer.pack(fill="x", padx=20, pady=(0, 16))
        self.cancel_btn = RoundedButton(footer, text="CANCEL",
                                        command=self._cancel,
                                        fill_key="PANEL_ALT", text_key="TEXT",
                                        hover_key="BORDER",
                                        radius=8, height=40, font=FONT_H)
        self.cancel_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.save_btn = RoundedButton(footer, text="SAVE",
                                      command=self._save,
                                      radius=8, height=40, font=FONT_H)
        self.save_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

    def _on_theme_radio(self):
        Theme.set(self.theme_var.get())

    def _on_provider_change(self):
        self._load_models()
        self._refresh_key_status()

    def _refresh_key_status(self):
        provider = self.provider_var.get()
        env_var = {
            "gemini": "GEMINI_API_KEY",
            "groq": "GROQ_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }.get(provider)
        if env_var is None:
            self.key_status_var.set("Local YOLO — no cloud key needed")
        elif os.environ.get(env_var, "").strip():
            self.key_status_var.set(f"{env_var}: configured for this session")
        else:
            self.key_status_var.set(f"{env_var}: not set")

    def _load_models(self):
        choice = self.provider_var.get()
        cfg = get_detector_config()
        if choice == "yolo":
            opts = list_local_models("Model")
            self.model_combo["values"] = opts
            curr = cfg.get("ambulance_model", "")
            self.model_combo.set(curr if curr in opts else (opts[0] if opts else ""))
        else:
            opts = cfg.get("vision_models", {}).get(choice, [])
            self.model_combo["values"] = opts
            curr = cfg.get("vision_model", "")
            self.model_combo.set(curr if curr in opts else (opts[0] if opts else ""))

    def _save(self):
        global DEFAULT_GREEN, DEFAULT_YELLOW
        updates, error = validate_timing(
            self.yellow_var.get(), self.default_green_var.get(),
            self.starvation_var.get(), GREEN_OPTIONS)
        if error:
            messagebox.showerror("Invalid settings", error)
            return

        choice = self.provider_var.get()
        model = self.model_combo.get().strip()
        try:
            if choice == "yolo":
                set_detector_config(detector="yolo", ambulance_model=model)
            else:
                set_detector_config(detector="vision", provider=choice,
                                    vision_model=model)
        except Exception:
            pass

        key_val = self.api_key_var.get().strip()
        if key_val:
            set_session_key(choice, key_val)
        self.api_key_var.set("")
        try:
            self.api_key_entry.delete(0, tk.END)
        except Exception:
            pass

        DEFAULT_GREEN = updates["default_green"]
        DEFAULT_YELLOW = updates["yellow_time"]
        try:
            save_config_updates(updates)
        except Exception as e:
            messagebox.showerror("Settings error", f"Could not save settings: {e}")
            return
        CONFIG.update(updates)
        if self.on_saved is not None:
            self.on_saved(updates)
        self.destroy()

    def _cancel(self):
        if Theme.current != self._orig_theme:
            Theme.set(self._orig_theme)
            try: self.theme_var.set(self._orig_theme)
            except Exception: pass
        self.destroy()


# ═══════════════════════════════════════════════════════════════════
# DASHBOARD (Ops Command Center)
# ═══════════════════════════════════════════════════════════════════
class Dashboard(tk.Frame):
    def __init__(self, master, mode, lanes, paths, on_stop,
                 green_time=DEFAULT_GREEN, on_settings=None):
        super().__init__(master)
        Theme.bind(self, "bg", "BG")
        self.mode = mode
        self.lanes = lanes
        self.paths = paths
        self.on_stop = on_stop
        self.on_settings = on_settings
        self.green_time = green_time
        self.yellow_time = DEFAULT_YELLOW
        self.running = False
        self.cameras = {}
        self.lane_data = {}
        self.next_lane_data = None
        self.next_winner = None
        self.active_lane = 0
        self.current_signal = "GREEN"
        self.time_left = self.green_time
        self.scanning = False
        self.cards = {}
        self._timer_job = None
        self._video_job = None
        self._stopped = False
        self._manual_dialog = None
        self.paused = False
        self._pending_yellow_time = None
        self._video_tick = 0
        self._cached_det_text = ""
        self._led_w = 0
        self._cycle_w = 0
        self._cycle_h = 0
        self._space_bind_id = None
        self._esc_bind_id = None
        self.btn_skip_roi = None
        self.lbl_status = None
        self.btn_manual = None
        self._build()
        self.btn_skip_roi = self.skip_btn
        self.lbl_status = self.status_lbl
        self.btn_manual = self.enter_btn

    # ── build ──────────────────────────────────────────────────────
    def _build(self):
        # top bar
        top = tk.Frame(self)
        Theme.bind(top, "bg", "PANEL")
        top.pack(fill="x")
        tinner = tk.Frame(top); Theme.bind(tinner, "bg", "PANEL")
        tinner.pack(fill="x", padx=20, pady=10)

        make_label(tinner, text="▶ TRAFFIC OPS", font=FONT_TITLE,
                   fg_key="ACCENT", bg_key="PANEL").pack(side="left")

        gear = tk.Button(tinner, text="⚙", font=("Courier New", 14),
                         relief="flat", cursor="hand2", padx=10, takefocus=0,
                         command=self.on_settings)
        Theme.bind(gear, "bg", "PANEL"); Theme.bind(gear, "fg", "TEXT")
        Theme.bind(gear, "activebackground", "PANEL_ALT")
        Theme.bind(gear, "activeforeground", "ACCENT")
        gear.pack(side="right")

        self.status_var = tk.StringVar(value="⬤ INITIALISING")
        self.status_lbl = make_label(tinner, textvariable=self.status_var,
                                     font=FONT_B, fg_key="YELLOW", bg_key="PANEL")
        self.status_lbl.pack(side="right", padx=16)

        self.enter_btn = None
        if self.mode == 2:
            self.enter_btn = tk.Button(tinner, text="Enter Values",
                                       font=FONT_B, relief="flat",
                                       padx=10, pady=2, cursor="hand2",
                                       takefocus=0, command=self._open_manual)
            Theme.bind(self.enter_btn, "bg", "YELLOW")
            Theme.bind(self.enter_btn, "fg", "BG")
            Theme.bind(self.enter_btn, "activebackground", "ACCENT")
            Theme.bind(self.enter_btn, "activeforeground", "BG")
            self.enter_btn.pack(side="right", padx=(0, 8))

        self.skip_btn = tk.Button(tinner, text="Skip ROI",
                                  font=FONT_B, relief="flat",
                                  padx=10, pady=2, cursor="hand2",
                                  takefocus=0, command=self._on_skip_roi)
        Theme.bind(self.skip_btn, "bg", "YELLOW")
        Theme.bind(self.skip_btn, "fg", "BG")
        Theme.bind(self.skip_btn, "activebackground", "ACCENT")
        Theme.bind(self.skip_btn, "activeforeground", "BG")

        # body: left rail + right lane grid
        body = tk.Frame(self)
        Theme.bind(body, "bg", "BG")
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, width=scale_px(220))
        Theme.bind(left, "bg", "BG")
        left.pack(side="left", fill="y", padx=(16, 10), pady=14)
        left.pack_propagate(False)
        self._build_left_rail(left)

        right = tk.Frame(body)
        Theme.bind(right, "bg", "BG")
        right.pack(side="left", fill="both", expand=True, padx=(10, 16), pady=14)

        show_feed = self.mode != 2
        cols = min(self.lanes, 2)
        for i in range(self.lanes):
            card = LaneCard(right, i, show_feed=show_feed)
            card.grid(row=i // cols, column=i % cols,
                      padx=8, pady=8, sticky="nsew")
            self.cards[i] = card
        for c in range(cols):
            right.columnconfigure(c, weight=1)
        rows = (self.lanes + cols - 1) // cols
        for r in range(rows):
            right.rowconfigure(r, weight=1)

        # log strip
        strip = tk.Frame(self, height=44)
        Theme.bind(strip, "bg", "PANEL")
        strip.pack(fill="x", side="bottom")
        strip.pack_propagate(False)
        make_label(strip, text="LOG", font=FONT_MONO, fg_key="SUBTEXT",
                   bg_key="PANEL").pack(side="left", padx=(20, 8))
        self.log_var = tk.StringVar(value="System starting…")
        self._log_lbl = make_label(strip, textvariable=self.log_var, font=FONT_MONO,
                                   fg_key="TEXT", bg_key="PANEL", justify="left")
        self._log_lbl.pack(side="left")
        strip.bind("<Configure>", self._on_log_configure)

    def _on_log_configure(self, event):
        try:
            self._log_lbl.configure(
                wraplength=max(200, event.width - scale_px(120)))
        except Exception:
            pass

    def _build_left_rail(self, parent):
        # SIGNAL block
        sig_card = make_section(parent, "SIGNAL", {"pady": (0, 10)})
        self.led_canvas = tk.Canvas(sig_card, height=34, bd=0, highlightthickness=0)
        Theme.bind(self.led_canvas, "bg", "PANEL")
        self.led_canvas.pack(fill="x")
        Theme.on_change(self.led_canvas, self._draw_leds)
        self.led_canvas.bind("<Configure>", self._on_led_configure)

        self.active_lbl_var = tk.StringVar(value="Lane —")
        make_label(sig_card, textvariable=self.active_lbl_var, font=FONT_H,
                   fg_key="TEXT", bg_key="PANEL", anchor="w"
                   ).pack(fill="x", pady=(4, 0))

        # CYCLE block
        cyc_card = make_section(parent, "CYCLE", {"pady": (0, 10)})
        self.cycle_canvas = tk.Canvas(cyc_card, height=10, bd=0,
                                      highlightthickness=0)
        Theme.bind(self.cycle_canvas, "bg", "INPUT_BG")
        self.cycle_canvas.pack(fill="x", pady=(0, 6))
        self.cycle_lbl_var = tk.StringVar(value="—")
        make_label(cyc_card, textvariable=self.cycle_lbl_var, font=FONT_MONO,
                   fg_key="SUBTEXT", bg_key="PANEL", anchor="w"
                   ).pack(fill="x")
        self.cycle_canvas.bind("<Configure>", self._on_cycle_configure)

        # DETECTOR block
        det_card = make_section(parent, "DETECTOR", {"pady": (0, 10)})
        self.det_lbl_var = tk.StringVar(value="—")
        make_label(det_card, textvariable=self.det_lbl_var, font=FONT_MONO,
                   fg_key="TEXT", bg_key="PANEL", anchor="w",
                   justify="left", wraplength=170).pack(fill="x")

        # bottom stop button
        self.stop_rail_btn = RoundedButton(parent, text="■  STOP",
                                           command=self._stop,
                                           fill_key="RED", text_key="BG",
                                           hover_key="YELLOW", takefocus=0,
                                           radius=8, height=40, font=FONT_H)
        self.stop_rail_btn.pack(fill="x", side="bottom", pady=(10, 0))

    # ── left rail draw ─────────────────────────────────────────────
    def _on_led_configure(self, event):
        self._led_w = event.width
        self._draw_leds()

    def _on_cycle_configure(self, event):
        self._cycle_w = event.width
        self._cycle_h = event.height
        self._draw_cycle()

    def _draw_leds(self):
        try:
            c = self.led_canvas
            c.delete("all")
            w = getattr(self, "_led_w", 0) or 180
            n = self.lanes
            if n <= 0:
                return
            step = w / n
            for i in range(n):
                cx = step * i + step / 2
                cy = 17
                r = 8
                if i == self.active_lane:
                    color = Theme.get("GREEN") if self.current_signal == "GREEN" \
                            else Theme.get("YELLOW")
                else:
                    color = Theme.get("RED")
                c.create_oval(cx-r, cy-r, cx+r, cy+r, fill=color, outline="")
        except Exception:
            pass

    def _draw_cycle(self):
        try:
            c = self.cycle_canvas
            c.delete("all")
            w = getattr(self, "_cycle_w", 0) or 180
            h = getattr(self, "_cycle_h", 0) or 10
            if self.green_time <= 0:
                return
            frac = max(0.0, min(1.0, self.time_left / self.green_time))
            fill_w = int(w * frac)
            round_rect(c, 0, 0, w, h, min(h, 5),
                       fill=Theme.get("INPUT_BG"), outline=Theme.get("BORDER"))
            if fill_w > 0:
                color = Theme.get("GREEN") if self.current_signal == "GREEN" \
                        else Theme.get("YELLOW")
                round_rect(c, 0, 0, fill_w, h, min(h, 5),
                           fill=color, outline=color)
        except Exception:
            pass

    def _refresh_detector_label(self):
        try:
            cfg = get_detector_config()
            if cfg.get("detector") == "vision":
                prov = cfg.get("provider", "gemini").upper()
                model = cfg.get("active_model", "") or "—"
                if not cfg.get("has_api_key", False):
                    model = cfg.get("ambulance_model", "Model/best.pt") + " (fallback)"
                text = f"{prov}\n{model}"
            else:
                text = f"LOCAL\n{cfg.get('ambulance_model', 'Model/best.pt')}"
        except Exception:
            text = "—"
        self._cached_det_text = text
        var = getattr(self, "det_lbl_var", None)
        if var is not None:
            try:
                var.set(text)
            except Exception:
                pass
        return text

    def _update_left_rail(self):
        self._draw_leds()
        self._draw_cycle()
        active_var = getattr(self, "active_lbl_var", None)
        if active_var is not None:
            active_var.set(f"Lane {self.active_lane + 1} · {self.current_signal}")
        cycle_var = getattr(self, "cycle_lbl_var", None)
        if cycle_var is not None:
            cycle_var.set(f"{self.time_left}s / {self.green_time}s")
        det_var = getattr(self, "det_lbl_var", None)
        if det_var is not None:
            det_var.set(getattr(self, "_cached_det_text", "") or "—")

    def on_settings_saved(self, updates):
        """Defer yellow changes to the next cycle switch and refresh detector text."""
        if "yellow_time" in updates:
            self._pending_yellow_time = updates["yellow_time"]
        self._refresh_detector_label()

    # ── lifecycle (unchanged business logic) ───────────────────────
    def start(self):
        self._bind_shortcuts()
        self._refresh_detector_label()
        if self.mode in (0, 1):
            threading.Thread(target=self._init_cameras, daemon=True).start()
        else:
            self.running = True
            self.status_var.set("⬤ INITIALISING")
            self._update_left_rail()
            self.after(0, self._init_manual)

    def _bind_shortcuts(self):
        try:
            top = self.winfo_toplevel()
            self._space_bind_id = top.bind("<space>", self._toggle_pause, add="+")
            self._esc_bind_id = top.bind("<Escape>", self._on_escape, add="+")
        except Exception:
            pass

    def _release_opened_cameras(self):
        for cam in self.cameras.values():
            try:
                cam.releasevid()
            except Exception:
                pass

    def _init_cameras(self):
        try:
            for i in range(self.lanes):
                src = i if self.mode == 0 else self.paths[i]
                cam = Cameraf(i, src)
                self.cameras[i] = cam
                if i in self.cards:
                    self.cards[i].set_camera(cam)
                if getattr(self, "_stopped", False):
                    self._release_opened_cameras()
                    return
                cam.read_frame()
                if getattr(self, "_stopped", False):
                    self._release_opened_cameras()
                    return
        except RuntimeError as e:
            err_msg = str(e)
            try:
                self.after(0, lambda: messagebox.showerror("Camera Error", err_msg))
                self.after(0, self._stop)
            except (RuntimeError, tk.TclError):
                pass
            return

        unconfigured = [i for i, cam in self.cameras.items()
                        if cam.get_roi() is None]

        if unconfigured:
            def _setup_roi():
                btn = getattr(self, "btn_skip_roi", None)
                if btn is not None:
                    btn.pack(side="right", padx=(0, 8))
                self.status_var.set("⬤ CONFIGURING ROI")
                self._log("ROI setup: click 4 corners per lane, or Skip ROI")
                for i, cam in self.cameras.items():
                    if cam.last_frame is not None and i in self.cards:
                        self.cards[i].update_frame(cam.last_frame)
                first = unconfigured[0]
                if first in self.cards:
                    self.cards[first].start_edit_roi()
            try:
                self.after(0, _setup_roi)
            except (RuntimeError, tk.TclError):
                pass
        else:
            try:
                self.after(0, self._boot_and_start_cycle)
            except (RuntimeError, tk.TclError):
                pass

    def _on_skip_roi(self):
        btn = getattr(self, "btn_skip_roi", None)
        if btn is not None:
            try:
                btn.pack_forget()
            except Exception:
                pass
        for card in self.cards.values():
            if getattr(card, "is_editing", False):
                card.cancel_edit_roi()
        self._log("Skipped ROI — using full frames")
        if not self.running:
            self._boot_and_start_cycle()

    def _on_lane_roi_configured(self, lane_no):
        if not self.running:
            unconfigured = [i for i, cam in self.cameras.items()
                            if cam.get_roi() is None]
            if unconfigured:
                nxt = unconfigured[0]
                if nxt in self.cards:
                    self.cards[nxt].start_edit_roi()
            else:
                btn = getattr(self, "btn_skip_roi", None)
                if btn is not None:
                    try:
                        btn.pack_forget()
                    except Exception:
                        pass
                self._log("All ROIs configured.")
                self._boot_and_start_cycle()
        else:
            self._log(f"Lane {lane_no + 1}: ROI updated.")

    def _boot_and_start_cycle(self):
        btn = getattr(self, "btn_skip_roi", None)
        if btn is not None:
            try:
                btn.pack_forget()
            except Exception:
                pass

        def _bg():
            if getattr(self, "_stopped", False):
                return
            reset_control()
            try:
                lane_data, _frames = scan_all_lanes(self.cameras, live=False)
                res = controlfun(lane_data, self.lanes)
                self.lane_data = lane_data
                self.active_lane = res["lane_no"]
            except Exception as e:
                self._log(f"Boot scan error: {e}")
                self.lane_data = {i: {"density": 0, "ambulance": False,
                                       "emergency": False,
                                       "emergency_type": "none"}
                                   for i in range(self.lanes)}
                self.active_lane = 0
            if getattr(self, "_stopped", False):
                return
            self.running = True
            self.current_signal = "GREEN"
            self.time_left = self.green_time
            try:
                self.after(0, self._gui_start)
            except (RuntimeError, tk.TclError):
                pass

        thread = threading.Thread(target=_bg, daemon=True)
        thread.start()
        return thread

    def _log_detector_status(self):
        cfg = get_detector_config()
        if cfg.get("detector") == "vision":
            prov = cfg.get("provider", "gemini").upper()
            model = cfg.get("active_model", "") or "—"
            if not cfg.get("has_api_key", False):
                self._log(f"Detector: {prov} (no key -> fallback "
                          f"{cfg.get('ambulance_model', 'Model/best.pt')})")
            else:
                self._log(f"Detector: {prov} ({model})")
        else:
            self._log(f"Detector: LOCAL ({cfg.get('ambulance_model', 'Model/best.pt')})")

    def _start_gui(self):
        if getattr(self, "_stopped", False) or not self.running:
            return
        self._refresh_detector_label()
        self._log_detector_status()
        self.status_var.set(f"⬤ LANE {self.active_lane + 1} GREEN ({self.time_left}s)")
        for i in range(self.lanes):
            sig = "GREEN" if i == self.active_lane else "RED"
            d = self.lane_data.get(i, {})
            self.cards[i].set_signal(
                sig, density=d.get("density"), ambulance=d.get("ambulance"),
                emergency_type=d.get("emergency_type"),
                time_left=self.time_left if sig == "GREEN" else None)
        self._log(f"Lane {self.active_lane + 1} → GREEN ({self.green_time}s) | others RED")
        self._update_left_rail()
        self._video_loop()
        self._timer_job = self.after(1000, self._tick_timer)

    _gui_start = _start_gui

    def _init_manual(self):
        self._manual_dialog = ManualDialog(
            self, self.lanes, self._on_manual_boot, initial_data=None)

    def _on_manual_boot(self, data):
        if not self.running:
            return
        reset_control()
        try:
            res = controlfun(data, self.lanes)
            self.active_lane = res["lane_no"]
        except Exception as e:
            self._log(f"Control error: {e}")
            self.active_lane = 0
        self.lane_data = data
        self.current_signal = "GREEN"
        self.time_left = self.green_time
        self.status_var.set(f"⬤ LANE {self.active_lane + 1} GREEN ({self.time_left}s)")
        for i in range(self.lanes):
            sig = "GREEN" if i == self.active_lane else "RED"
            d = self.lane_data.get(i, {})
            self.cards[i].set_signal(
                sig, density=d.get("density"), ambulance=d.get("ambulance"),
                emergency_type=d.get("emergency_type"),
                time_left=self.time_left if sig == "GREEN" else None)
        self._log(f"Lane {self.active_lane + 1} → GREEN ({self.green_time}s)")
        self._update_left_rail()
        self._timer_job = self.after(1000, self._tick_timer)

    def _video_loop(self):
        if not getattr(self, "running", False):
            return
        self._video_tick = getattr(self, "_video_tick", 0) + 1
        for i, cam in self.cameras.items():
            try:
                frame = cam.read_frame()
            except Exception:
                continue
            if frame is None or i not in self.cards:
                continue
            active = i == getattr(self, "active_lane", -1)
            editing = getattr(self.cards[i], "is_editing", False)
            if active or editing or self._video_tick % 4 == 0:
                try:
                    self.cards[i].update_frame(frame)
                except Exception:
                    pass
        if getattr(self, "running", False):
            try:
                self._video_job = self.after(40, self._video_loop)
            except (RuntimeError, tk.TclError):
                pass

    def _bg_scan(self):
        try:
            lane_data, _ = scan_all_lanes(self.cameras, live=True)
            res = controlfun(lane_data, self.lanes)
            self.next_lane_data = lane_data
            self.next_winner = res["lane_no"]
        except Exception as e:
            self._log(f"Scan error: {e}")
            self.next_lane_data = self.lane_data
            self.next_winner = (self.active_lane + 1) % self.lanes
        finally:
            self.scanning = False

    def _on_manual_cycle(self, data):
        try:
            res = controlfun(data, self.lanes)
            self.next_winner = res["lane_no"]
            self.next_lane_data = data
        except Exception as e:
            self._log(f"Control error: {e}")
            self.next_winner = (self.active_lane + 1) % self.lanes
            self.next_lane_data = data
        finally:
            self.scanning = False

    def _open_manual(self):
        if not getattr(self, "running", False):
            return
        dlg = getattr(self, "_manual_dialog", None)
        if dlg is not None:
            try:
                if dlg.winfo_exists():
                    dlg.lift()
                    return
            except Exception:
                pass
            self._manual_dialog = None
        self.scanning = True
        self._manual_dialog = ManualDialog(self, self.lanes, self._on_manual_cycle,
                                           initial_data=self.lane_data)

    def _tick_timer(self):
        if not getattr(self, "running", False) or getattr(self, "_stopped", False):
            return

        if getattr(self, "paused", False):
            try:
                self.status_var.set(f"⬤ PAUSED ({self.time_left}s)")
            except Exception:
                pass
            self._timer_job = self.after(1000, self._tick_timer)
            return

        if self.time_left <= 0 and self.scanning:
            self.current_signal = "YELLOW"
            d = self.lane_data.get(self.active_lane, {})
            self.cards[self.active_lane].set_signal(
                "YELLOW", density=d.get("density"),
                ambulance=d.get("ambulance"),
                emergency_type=d.get("emergency_type"), time_left=0)
            self.status_var.set(f"⬤ LANE {self.active_lane + 1} YELLOW (0s)")
            self._update_left_rail()
            self._timer_job = self.after(200, self._tick_timer)
            return

        if self.time_left <= 0 and not self.scanning:
            if self.next_winner is not None:
                self.active_lane = self.next_winner
            else:
                self.active_lane = (self.active_lane + 1) % self.lanes
            if self.next_lane_data is not None:
                self.lane_data = self.next_lane_data
            self.next_winner = None
            self.next_lane_data = None
            self.time_left = self.green_time
            self.current_signal = "GREEN"
            pending = getattr(self, "_pending_yellow_time", None)
            if pending is not None:
                self.yellow_time = pending
                self._pending_yellow_time = None

            for i in range(self.lanes):
                sig = "GREEN" if i == self.active_lane else "RED"
                d = self.lane_data.get(i, {})
                self.cards[i].set_signal(
                    sig, density=d.get("density"),
                    ambulance=d.get("ambulance"),
                    emergency_type=d.get("emergency_type"),
                    time_left=self.time_left if sig == "GREEN" else None)
            self._log(f"Lane {self.active_lane + 1} → GREEN ({self.green_time}s)")
            self.status_var.set(f"⬤ LANE {self.active_lane + 1} GREEN ({self.time_left}s)")
            self._update_left_rail()
            self._timer_job = self.after(1000, self._tick_timer)
            return

        self.time_left -= 1

        if self.time_left > self.yellow_time:
            self.current_signal = "GREEN"
            d = self.lane_data.get(self.active_lane, {})
            self.cards[self.active_lane].set_signal(
                "GREEN", density=d.get("density"),
                ambulance=d.get("ambulance"),
                emergency_type=d.get("emergency_type"),
                time_left=self.time_left)
            self.status_var.set(f"⬤ LANE {self.active_lane + 1} GREEN ({self.time_left}s)")
        elif self.time_left == self.yellow_time:
            self.current_signal = "YELLOW"
            d = self.lane_data.get(self.active_lane, {})
            self.cards[self.active_lane].set_signal(
                "YELLOW", density=d.get("density"),
                ambulance=d.get("ambulance"),
                emergency_type=d.get("emergency_type"),
                time_left=self.time_left)
            self.status_var.set(f"⬤ LANE {self.active_lane + 1} YELLOW ({self.time_left}s)")
            self._log(f"Lane {self.active_lane + 1} YELLOW — scanning next cycle...")
            if self.mode == 2:
                dlg = getattr(self, "_manual_dialog", None)
                if dlg is not None:
                    try:
                        if dlg.winfo_exists():
                            dlg.lift()
                            self._update_left_rail()
                            self._timer_job = self.after(1000, self._tick_timer)
                            return
                    except Exception:
                        pass
                    self._manual_dialog = None
            self.scanning = True
            self.next_winner = None
            self.next_lane_data = None
            if self.mode in (0, 1):
                threading.Thread(target=self._bg_scan, daemon=True).start()
            elif self.mode == 2:
                self._manual_dialog = ManualDialog(
                    self, self.lanes, self._on_manual_cycle,
                    initial_data=self.lane_data)
        elif 0 < self.time_left < self.yellow_time:
            self.current_signal = "YELLOW"
            d = self.lane_data.get(self.active_lane, {})
            self.cards[self.active_lane].set_signal(
                "YELLOW", density=d.get("density"),
                ambulance=d.get("ambulance"),
                emergency_type=d.get("emergency_type"),
                time_left=self.time_left)
            self.status_var.set(f"⬤ LANE {self.active_lane + 1} YELLOW ({self.time_left}s)")
        elif self.time_left <= 0:
            if self.scanning:
                self.current_signal = "YELLOW"
                d = self.lane_data.get(self.active_lane, {})
                self.cards[self.active_lane].set_signal(
                    "YELLOW", density=d.get("density"),
                    ambulance=d.get("ambulance"),
                    emergency_type=d.get("emergency_type"), time_left=0)
                self.status_var.set(f"⬤ LANE {self.active_lane + 1} YELLOW (0s)")
                self._update_left_rail()
                self._timer_job = self.after(200, self._tick_timer)
                return
            else:
                self._tick_timer()
                return

        self._update_left_rail()
        self._timer_job = self.after(1000, self._tick_timer)

    def _stop(self):
        self._stopped = True
        self.paused = False
        try:
            top = self.winfo_toplevel()
            if getattr(self, "_space_bind_id", None):
                top.unbind("<space>", self._space_bind_id)
            if getattr(self, "_esc_bind_id", None):
                top.unbind("<Escape>", self._esc_bind_id)
        except Exception:
            pass
        self._space_bind_id = None
        self._esc_bind_id = None
        btn = getattr(self, "btn_skip_roi", None)
        if btn is not None:
            try:
                btn.pack_forget()
            except Exception:
                pass
        if getattr(self, "_timer_job", None) is not None:
            try: self.after_cancel(self._timer_job)
            except Exception: pass
            self._timer_job = None
        if getattr(self, "_video_job", None) is not None:
            try: self.after_cancel(self._video_job)
            except Exception: pass
            self._video_job = None
        self.running = False
        var = getattr(self, "status_var", None)
        if var is not None:
            var.set("⬤ STOPPED")
        for c in getattr(self, "cameras", {}).values():
            try: c.releasevid()
            except Exception: pass
        on_stop = getattr(self, "on_stop", None)
        if on_stop is not None:
            on_stop()

    def _toggle_pause(self, event=None):
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        except Exception:
            pass
        if not getattr(self, "running", False):
            return
        if getattr(self, "_manual_dialog", None) is not None:
            return
        try:
            focus = self.focus_get()
        except Exception:
            focus = None
        if isinstance(focus, (tk.Entry, ttk.Combobox)):
            return
        self.paused = not getattr(self, "paused", False)
        if self.paused:
            try:
                self.status_var.set("⬤ PAUSED")
            except Exception:
                pass
            self._log("Paused")
        else:
            try:
                self.status_var.set(
                    f"⬤ LANE {self.active_lane + 1} {self.current_signal} "
                    f"({self.time_left}s)")
            except Exception:
                pass
            self._log("Resumed")

    def _on_escape(self, event=None):
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        except Exception:
            pass
        for card in getattr(self, "cards", {}).values():
            if getattr(card, "is_editing", False):
                card.cancel_edit_roi()
                return
        if getattr(self, "running", False):
            if messagebox.askyesno(
                    "Stop controller?",
                    "Stop the traffic controller and return to setup?"):
                self._stop()

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        try:
            self.after(0, lambda: self.log_var.set(f"[{ts}]  {msg}"))
        except (RuntimeError, tk.TclError):
            pass


# ═══════════════════════════════════════════════════════════════════
# APP ROOT
# ═══════════════════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        global _UI_SCALE
        try:
            if os.name == "nt":
                try:
                    ctypes.windll.shcore.SetProcessDpiAwareness(1)
                except Exception:
                    ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
        super().__init__()
        try:
            _UI_SCALE = self.winfo_fpixels("1i") / 96.0
        except Exception:
            _UI_SCALE = 1.0
        self._screen = None
        self.title("Traffic Control System")
        self.geometry(f"{scale_px(1000)}x{scale_px(720)}")
        self.minsize(scale_px(880), scale_px(620))
        try:
            self.configure(bg=Theme.get("BG"))
        except Exception:
            pass
        _apply_ttk_style()
        Theme.on_change(self, lambda: self.configure(bg=Theme.get("BG")))
        self._show_setup()

    def _open_settings(self):
        SettingsDialog(
            self,
            on_saved=getattr(self._screen, "on_settings_saved", None),
        )

    def _show_setup(self):
        for w in self.winfo_children():
            w.destroy()
        self._screen = SetupScreen(self, on_start=self._show_dashboard,
                                   on_settings=self._open_settings)
        self._screen.pack(fill="both", expand=True)

    def _show_dashboard(self, mode, lanes, paths, green_time=DEFAULT_GREEN):
        for w in self.winfo_children():
            w.destroy()
        self._screen = Dashboard(self, mode, lanes, paths,
                                 on_stop=self._show_setup,
                                 green_time=green_time,
                                 on_settings=self._open_settings)
        self._screen.pack(fill="both", expand=True)
        self._screen.start()


if __name__ == "__main__":
    app = App()
    app.mainloop()