import json
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import cv2
from PIL import Image, ImageTk

try:
    from control import controlfun, reset_control
except ImportError:
    from control import controlfun
    def reset_control():
        pass

try:
    from cvfile import (
        Cameraf,
        scan_all_lanes,
        roi_key,
        validate_roi,
        crop_roi,
        canvas_to_frame,
        frame_to_canvas,
        load_roi,
        save_roi,
    )
except ImportError:
    from cvfile import Cameraf
    def scan_all_lanes(cameras, live=False):
        return {}, {}
    def roi_key(source):
        return str(source)
    def validate_roi(points, frame_w, frame_h):
        return points if points and len(points) == 4 else None
    def crop_roi(frame, points):
        return frame
    def canvas_to_frame(x, y, canvas_w, canvas_h, frame_w, frame_h):
        return (x, y)
    def frame_to_canvas(x, y, canvas_w, canvas_h, frame_w, frame_h):
        return (x, y)
    def load_roi(source):
        return None
    def save_roi(source, points):
        pass

try:
    from ambdet import get_detector_config, set_detector_config, list_local_models
except ImportError:
    def get_detector_config():
        return {
            "detector": "vision",
            "provider": "gemini",
            "active_model": "gemini-3.5-flash-lite",
            "ambulance_model": "Model/best.pt",
            "has_api_key": False,
            "vision_models": {},
        }
    def set_detector_config(detector=None, provider=None, vision_model=None, ambulance_model=None):
        pass
    def list_local_models(model_dir="Model"):
        return ["Model/best.pt"]


def load_config():
    cfg_path = Path("config.json")
    if cfg_path.exists():
        try:
            with open(cfg_path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


CONFIG = load_config()
GREEN_OPTIONS = CONFIG.get("green_options", [15, 30, 40, 50, 60])
DEFAULT_GREEN = CONFIG.get("default_green", 30)
DEFAULT_YELLOW = CONFIG.get("yellow_time", 5)
TIME_INTERVAL = 2

#font and color

BG       = "#0d0d0f"
PANEL    = "#16161a"
BORDER   = "#2a2a30"
ACCENT   = "#00e5ff"
GREEN    = "#00e676"
RED      = "#ff1744"
YELLOW   = "#ffd600"
TEXT     = "#e8e8f0"
SUBTEXT  = "#6b6b80"

FONT_H    = ("Courier New", 13, "bold")
FONT_B    = ("Courier New", 10)
FONT_MONO = ("Courier New", 9)

# start screen
class SetupScreen(tk.Frame):
    def __init__(self, master, on_start):
        super().__init__(master, bg=BG)
        self.on_start    = on_start
        self.video_paths = []
        self._build()

    def _build(self):
        tk.Label(self, text="▶ TRAFFIC CONTROL SYSTEM",
                 font=("Courier New", 18, "bold"),
                 fg=ACCENT, bg=BG).pack(pady=(50, 4))
        tk.Label(self, text="intelligent lane signal manager",
                 font=FONT_B, fg=SUBTEXT, bg=BG).pack(pady=(0, 40))

        #mode card
        card = tk.Frame(self, bg=PANEL, highlightthickness=1,
                        highlightbackground=BORDER)
        card.pack(padx=80, pady=8, fill="x")
        tk.Label(card, text="INPUT MODE", font=FONT_H,
                 fg=SUBTEXT, bg=PANEL).pack(anchor="w", padx=20, pady=(18, 6))

        self.mode_var = tk.IntVar(value=0)
        modes = [(0, "  🎥  Live Camera"),
                 (1, "  📂  Video Files"),
                 (2, "  ✏️   Manual Input")]
        for val, label in modes:
            tk.Radiobutton(card, text=label, variable=self.mode_var,
                           value=val, font=FONT_B,
                           fg=TEXT, bg=PANEL, selectcolor=BG,
                           activebackground=PANEL, activeforeground=ACCENT,
                           command=self._on_mode_change).pack(anchor="w",
                                                              padx=30, pady=4)
        tk.Label(card, text="", bg=PANEL).pack(pady=4)

        #lanes card
        card2 = tk.Frame(self, bg=PANEL, highlightthickness=1,
                         highlightbackground=BORDER)
        card2.pack(padx=80, pady=8, fill="x")
        tk.Label(card2, text="NUMBER OF LANES", font=FONT_H,
                 fg=SUBTEXT, bg=PANEL).pack(anchor="w", padx=20,
                                            pady=(18, 6))
        self.lane_var = tk.IntVar(value=2)
        row = tk.Frame(card2, bg=PANEL)
        row.pack(padx=20, pady=(0, 18))
        for n in [1, 2, 3, 4]:
            tk.Radiobutton(row, text=str(n), variable=self.lane_var,
                           value=n, font=("Courier New", 12, "bold"),
                           fg=TEXT, bg=PANEL, selectcolor=BG,
                           activebackground=PANEL, activeforeground=ACCENT,
                           indicatoron=False, width=4, relief="flat",
                           command=self._on_lane_change).pack(side="left",
                                                              padx=6)

        #green duration card
        card3 = tk.Frame(self, bg=PANEL, highlightthickness=1,
                         highlightbackground=BORDER)
        card3.pack(padx=80, pady=8, fill="x")
        tk.Label(card3, text="GREEN SIGNAL DURATION (SECONDS)", font=FONT_H,
                 fg=SUBTEXT, bg=PANEL).pack(anchor="w", padx=20,
                                            pady=(18, 6))
        self.green_var = tk.IntVar(value=DEFAULT_GREEN)
        row_g = tk.Frame(card3, bg=PANEL)
        row_g.pack(padx=20, pady=(0, 18))
        for g in GREEN_OPTIONS:
            tk.Radiobutton(row_g, text=f"{g}s", variable=self.green_var,
                           value=g, font=("Courier New", 12, "bold"),
                           fg=TEXT, bg=PANEL, selectcolor=BG,
                           activebackground=PANEL, activeforeground=ACCENT,
                           indicatoron=False, width=5, relief="flat").pack(side="left",
                                                                          padx=6)

        #emergency detection engine card
        self.engine_card = tk.Frame(self, bg=PANEL, highlightthickness=1,
                                    highlightbackground=BORDER)
        self.engine_card.pack(padx=80, pady=8, fill="x")
        tk.Label(self.engine_card, text="EMERGENCY DETECTION ENGINE", font=FONT_H,
                 fg=SUBTEXT, bg=PANEL).pack(anchor="w", padx=20, pady=(18, 6))

        init_cfg = get_detector_config()
        init_detector = init_cfg.get("detector", "vision")
        init_provider = init_cfg.get("provider", "gemini")
        init_choice = "yolo" if init_detector == "yolo" else init_provider

        self.provider_var = tk.StringVar(value=init_choice)
        row_p = tk.Frame(self.engine_card, bg=PANEL)
        row_p.pack(anchor="w", padx=20, pady=(0, 10))

        providers = [
            ("gemini", "Gemini"),
            ("groq", "Groq"),
            ("openrouter", "OpenRouter"),
            ("yolo", "Local YOLO (Model/)")
        ]
        for val, lbl in providers:
            tk.Radiobutton(
                row_p, text=lbl, variable=self.provider_var, value=val,
                font=FONT_B, fg=TEXT, bg=PANEL, selectcolor=BG,
                activebackground=PANEL, activeforeground=ACCENT,
                command=self._on_provider_change
            ).pack(side="left", padx=8)

        row_m = tk.Frame(self.engine_card, bg=PANEL)
        row_m.pack(fill="x", padx=20, pady=(0, 18))
        tk.Label(row_m, text="Model:", font=FONT_B, fg=TEXT, bg=PANEL, width=8, anchor="w").pack(side="left")

        self.model_combo = ttk.Combobox(row_m, font=FONT_MONO, width=36)
        self.model_combo.pack(side="left", padx=(0, 8))

        self.btn_refresh_models = tk.Button(
            row_m, text="↻ Refresh", font=FONT_MONO,
            fg=ACCENT, bg=BORDER, relief="flat", cursor="hand2", padx=8,
            command=self._refresh_local_models
        )
        self._update_model_options()

        #video path card for mode 1)
        self.path_card = tk.Frame(self, bg=PANEL, highlightthickness=1,
                                  highlightbackground=BORDER)
        tk.Label(self.path_card, text="VIDEO FILES", font=FONT_H,
                 fg=SUBTEXT, bg=PANEL).pack(anchor="w", padx=20,
                                            pady=(18, 6))
        self.path_frame = tk.Frame(self.path_card, bg=PANEL)
        self.path_frame.pack(padx=20, pady=(0, 18), fill="x")

        #start button
        self.start_btn = tk.Button(
            self, text="START SYSTEM  ▶",
            font=("Courier New", 12, "bold"),
            fg=BG, bg=ACCENT, relief="flat",
            activebackground=GREEN, activeforeground=BG,
            cursor="hand2", pady=12, command=self._start)
        self.start_btn.pack(padx=80, pady=30, fill="x")

    #callbacks
    def _on_provider_change(self):
        self._update_model_options()

    def _refresh_local_models(self):
        if self.provider_var.get() == "yolo":
            models = list_local_models("Model")
            self.model_combo["values"] = models
            if models:
                self.model_combo.set(models[0])

    def _update_model_options(self):
        choice = self.provider_var.get()
        cfg = get_detector_config()
        v_models = cfg.get("vision_models", {})

        if choice == "yolo":
            self.btn_refresh_models.pack(side="left")
            local_models = list_local_models("Model")
            self.model_combo["values"] = local_models
            curr_amb = cfg.get("ambulance_model", "Model/best.pt")
            if curr_amb in local_models:
                self.model_combo.set(curr_amb)
            elif local_models:
                self.model_combo.set(local_models[0])
            else:
                self.model_combo.set("Model/best.pt")
        else:
            self.btn_refresh_models.pack_forget()
            options = v_models.get(choice, [])
            self.model_combo["values"] = options
            if choice == cfg.get("provider") and cfg.get("vision_model") in options:
                self.model_combo.set(cfg["vision_model"])
            elif options:
                self.model_combo.set(options[0])
            else:
                self.model_combo.set("")

    def _on_mode_change(self):
        mode = self.mode_var.get()
        if mode == 1:
            self.path_card.pack(padx=80, pady=8, fill="x",
                                 before=self.start_btn)
            self._rebuild_paths()
        else:
            self.path_card.pack_forget()

        if mode == 2:
            self.engine_card.pack_forget()
        else:
            target_before = self.path_card if mode == 1 else self.start_btn
            self.engine_card.pack(padx=80, pady=8, fill="x", before=target_before)

    def _on_lane_change(self):
        if self.mode_var.get() == 1:
            self._rebuild_paths()

    def _rebuild_paths(self):
        for w in self.path_frame.winfo_children():
            w.destroy()
        n = self.lane_var.get()
        self.video_paths = [""] * n
        self._path_entries = []
        for i in range(n):
            row = tk.Frame(self.path_frame, bg=PANEL)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=f"Lane {i+1}:", font=FONT_B,
                     fg=TEXT, bg=PANEL, width=8).pack(side="left")
            entry = tk.Entry(row, font=FONT_MONO, fg=TEXT, bg=BG,
                             insertbackground=ACCENT,
                             relief="flat", bd=4, width=36)
            entry.pack(side="left", padx=(0, 6))
            self._path_entries.append(entry)

            def browse(idx=i, e=entry):
                path = filedialog.askopenfilename(
                    filetypes=[("Video files",
                                "*.mp4 *.avi *.mov *.mkv"),
                               ("All", "*.*")])
                if path:
                    e.delete(0, tk.END)
                    e.insert(0, path)

            tk.Button(row, text="Browse", font=FONT_MONO,
                      fg=ACCENT, bg=BORDER, relief="flat",
                      cursor="hand2", padx=8,
                      command=browse).pack(side="left")

    def _start(self):
        mode  = self.mode_var.get()
        lanes = self.lane_var.get()
        green_time = self.green_var.get()

        if mode != 2:
            choice = self.provider_var.get()
            selected_model = self.model_combo.get().strip()
            if choice == "yolo":
                set_detector_config(detector="yolo", ambulance_model=selected_model)
            else:
                set_detector_config(detector="vision", provider=choice, vision_model=selected_model)

        if mode == 1:
            paths = [e.get().strip() for e in self._path_entries]
            if any(p == "" for p in paths):
                messagebox.showwarning("Missing paths",
                                       "Please select a video for every lane.")
                return
            self.on_start(mode, lanes, paths, green_time)
        else:
            self.on_start(mode, lanes, [], green_time)


#lane card
class LaneCard(tk.Frame):
    def __init__(self, master, lane_no, show_feed=True):
        super().__init__(master, bg=PANEL, highlightthickness=1,
                         highlightbackground=BORDER)
        self.lane_no   = lane_no
        self.show_feed = show_feed
        self._photo    = None
        self.camera    = None
        self.is_editing = False
        self.draft_points = []
        self.frozen_frame = None
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=BORDER)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"LANE {self.lane_no + 1}",
                 font=FONT_H, fg=ACCENT, bg=BORDER,
                 pady=6).pack(side="left", padx=(12, 6))

        if self.show_feed:
            self.btn_edit_roi = tk.Button(
                hdr, text="Edit ROI", font=FONT_MONO,
                fg=ACCENT, bg=BORDER, relief="flat",
                activebackground=PANEL, activeforeground=ACCENT,
                padx=6, pady=2, cursor="hand2",
                command=self.toggle_edit_roi
            )
            self.btn_edit_roi.pack(side="left", padx=2)

            self.btn_clear_roi = tk.Button(
                hdr, text="Clear", font=FONT_MONO,
                fg=SUBTEXT, bg=BORDER, relief="flat",
                activebackground=PANEL, activeforeground=RED,
                padx=6, pady=2, cursor="hand2",
                command=self.clear_roi
            )
            self.btn_clear_roi.pack(side="left", padx=2)

        self.sig_label = tk.Label(hdr, text="● WAITING",
                                  font=FONT_B, fg=YELLOW, bg=BORDER)
        self.sig_label.pack(side="right", padx=12)

        if self.show_feed:
            self.canvas = tk.Canvas(self, width=320, height=200,
                                    bg="#000", bd=0,
                                    highlightthickness=0)
            self.canvas.pack(padx=1, pady=1)
            self.canvas.bind("<Button-1>", self._on_canvas_click)
            self.bind("<Escape>", lambda e: self.cancel_edit_roi())
            self.canvas.bind("<Escape>", lambda e: self.cancel_edit_roi())

        stats = tk.Frame(self, bg=PANEL)
        stats.pack(fill="x", padx=12, pady=8)
        self.count_var = tk.StringVar(value="Vehicles: —")
        self.amb_var   = tk.StringVar(value="Ambulance: —")
        tk.Label(stats, textvariable=self.count_var,
                 font=FONT_MONO, fg=SUBTEXT, bg=PANEL).pack(side="left")
        tk.Label(stats, textvariable=self.amb_var,
                 font=FONT_MONO, fg=SUBTEXT, bg=PANEL).pack(side="right")

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
        if hasattr(self, "btn_edit_roi"):
            self.btn_edit_roi.config(text="Cancel", fg=YELLOW)
        self._redraw_edit_canvas()
        self._log(f"Lane {self.lane_no + 1}: Click 4 corners of lane ROI (clockwise or counter-clockwise)")

    def cancel_edit_roi(self):
        if not getattr(self, "is_editing", False):
            return
        self.is_editing = False
        self.draft_points = []
        last_f = self.frozen_frame
        self.frozen_frame = None
        if hasattr(self, "btn_edit_roi"):
            self.btn_edit_roi.config(text="Edit ROI", fg=ACCENT)
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

    def _on_canvas_click(self, event):
        if not getattr(self, "is_editing", False) or self.frozen_frame is None:
            return
        cw = 320
        ch = 200
        if hasattr(self, "canvas"):
            try:
                w = self.canvas.winfo_width()
                h = self.canvas.winfo_height()
                if w > 1:
                    cw = w
                if h > 1:
                    ch = h
            except Exception:
                pass
        cx = max(0, min(cw - 1, int(getattr(event, "x", 0))))
        cy = max(0, min(ch - 1, int(getattr(event, "y", 0))))
        self.draft_points.append((cx, cy))
        self._redraw_edit_canvas()

        if len(self.draft_points) == 4:
            fh, fw = self.frozen_frame.shape[:2]
            frame_pts = [
                canvas_to_frame(pt_x, pt_y, cw, ch, fw, fh)
                for pt_x, pt_y in self.draft_points
            ]
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
                        self.btn_edit_roi.config(text="Edit ROI", fg=ACCENT)
                    self._log(f"Lane {self.lane_no + 1}: ROI configured successfully")
                    if last_f is not None:
                        self.update_frame(last_f)
                    dash = self._get_dashboard()
                    if dash and hasattr(dash, "_on_lane_roi_configured"):
                        dash._on_lane_roi_configured(self.lane_no)
                    return

            self._log(f"Invalid ROI for Lane {self.lane_no + 1} (area too small) — click 4 corners again")
            self.draft_points = []
            self._redraw_edit_canvas()

    def _redraw_edit_canvas(self):
        if self.frozen_frame is None or not getattr(self, "show_feed", False) or not hasattr(self, "canvas"):
            return
        try:
            img = cv2.cvtColor(self.frozen_frame, cv2.COLOR_BGR2RGB)
            img = cv2.resize(img, (320, 200))
            pil = Image.fromarray(img)
            self._photo = ImageTk.PhotoImage(pil)
            self.canvas.create_image(0, 0, anchor="nw", image=self._photo)

            pts = self.draft_points
            for i, (cx, cy) in enumerate(pts):
                r = 4
                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=ACCENT, outline="#ffffff", width=1)
                self.canvas.create_text(cx + 8, cy - 8, text=str(i + 1), fill="#ffffff", font=FONT_MONO)
                if i > 0:
                    px, py = pts[i - 1]
                    self.canvas.create_line(px, py, cx, cy, fill=ACCENT, width=2)
            if len(pts) == 4:
                self.canvas.create_line(pts[3][0], pts[3][1], pts[0][0], pts[0][1], fill=ACCENT, width=2)
        except Exception:
            pass

    def update_frame(self, frame_bgr):
        """Push a new OpenCV BGR frame to the canvas and overlay ROI polygon if configured."""
        if not getattr(self, "show_feed", False) or getattr(self, "is_editing", False) or not hasattr(self, "canvas"):
            return
        try:
            img = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            img = cv2.resize(img, (320, 200))
            pil = Image.fromarray(img)
            self._photo = ImageTk.PhotoImage(pil)
            self.canvas.create_image(0, 0, anchor="nw", image=self._photo)

            cam = self._get_cam()
            if cam is not None and hasattr(cam, "get_roi"):
                roi = cam.get_roi()
                if roi is not None and len(roi) == 4:
                    fh, fw = frame_bgr.shape[:2]
                    cw = 320
                    ch = 200
                    try:
                        w = self.canvas.winfo_width()
                        h = self.canvas.winfo_height()
                        if w > 1:
                            cw = w
                        if h > 1:
                            ch = h
                    except Exception:
                        pass
                    canvas_pts = [
                        frame_to_canvas(fx, fy, cw, ch, fw, fh)
                        for fx, fy in roi
                    ]
                    flat = []
                    for cx, cy in canvas_pts:
                        flat.extend([cx, cy])
                        r = 3
                        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=ACCENT, outline="#ffffff")
                    self.canvas.create_polygon(flat, outline=ACCENT, fill="", width=2)
        except Exception:
            pass

    def set_signal(self, signal: str, density=None, ambulance=None, emergency_type=None, time_left=None):
        sig = signal.upper()
        suffix = f" ({time_left}s)" if time_left is not None else ""
        if sig == "GREEN":
            self.sig_label.config(text=f"● GO{suffix}", fg=GREEN)
            self.config(highlightbackground=GREEN)
        elif sig == "RED":
            self.sig_label.config(text="● STOP", fg=RED)
            self.config(highlightbackground=RED)
        else:
            self.sig_label.config(text=f"● WAIT{suffix}", fg=YELLOW)
            self.config(highlightbackground=YELLOW)

        if density is not None:
            self.count_var.set(f"Vehicles: {density}")

        if emergency_type is not None:
            etype = str(emergency_type).strip().lower()
            if etype == "firetruck":
                self.amb_var.set("Emergency: FIRETRUCK 🚒")
            elif etype == "ambulance":
                self.amb_var.set("Emergency: AMBULANCE 🚨")
            else:
                self.amb_var.set("Emergency: No")
        elif ambulance is not None:
            self.amb_var.set(f"Emergency: {'AMBULANCE 🚨' if ambulance else 'No'}")


#manual input
class ManualDialog(tk.Toplevel):
    """Popup to collect manual density + emergency vehicle per lane."""
    def __init__(self, master, lanes, on_submit, initial_data=None):
        super().__init__(master, bg=BG)
        self.title("Manual Input")
        self.resizable(False, False)
        self.lanes     = lanes
        self.on_submit = on_submit
        self.initial_data = initial_data or {}
        self.entries   = {}
        self.emerg_vars = {}
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build()
        self.grab_set()

    def _build(self):
        tk.Label(self, text="MANUAL LANE INPUT", font=FONT_H,
                 fg=ACCENT, bg=BG).pack(pady=(20, 4), padx=30)
        tk.Label(self, text="enter values for each lane",
                 font=FONT_MONO, fg=SUBTEXT, bg=BG).pack(pady=(0, 16))

        for i in range(self.lanes):
            card = tk.Frame(self, bg=PANEL, highlightthickness=1,
                            highlightbackground=BORDER)
            card.pack(padx=24, pady=6, fill="x")
            tk.Label(card, text=f"Lane {i+1}", font=FONT_H,
                     fg=ACCENT, bg=PANEL).pack(anchor="w",
                                               padx=14, pady=(10, 4))

            row1 = tk.Frame(card, bg=PANEL)
            row1.pack(fill="x", padx=14, pady=4)
            tk.Label(row1, text="Vehicles:", font=FONT_B,
                     fg=TEXT, bg=PANEL, width=10,
                     anchor="w").pack(side="left")
            init_d = str(self.initial_data.get(i, {}).get("density", 0))
            e = tk.Entry(row1, font=FONT_MONO, fg=TEXT, bg=BG,
                         insertbackground=ACCENT, relief="flat",
                         bd=4, width=10)
            e.insert(0, init_d)
            e.pack(side="left")
            self.entries[i] = e

            row2 = tk.Frame(card, bg=PANEL)
            row2.pack(fill="x", padx=14, pady=(2, 10))
            tk.Label(row2, text="Emergency:", font=FONT_B,
                     fg=TEXT, bg=PANEL, width=10,
                     anchor="w").pack(side="left")

            init_emerg = self.initial_data.get(i, {}).get("emergency_type", "")
            if not init_emerg:
                init_emerg = "ambulance" if self.initial_data.get(i, {}).get("ambulance") else "none"
            init_emerg = str(init_emerg).strip().lower()
            if init_emerg not in ("none", "ambulance", "firetruck"):
                init_emerg = "none"

            var = tk.StringVar(value=init_emerg)
            for opt_val, opt_lbl in [("none", "None"),
                                     ("ambulance", "Ambulance 🚨"),
                                     ("firetruck", "Firetruck 🚒")]:
                tk.Radiobutton(row2, text=opt_lbl, variable=var,
                               value=opt_val, font=FONT_B,
                               fg=TEXT, bg=PANEL, selectcolor=BG,
                               activebackground=PANEL, activeforeground=ACCENT).pack(side="left", padx=4)
            self.emerg_vars[i] = var

        tk.Button(self, text="RUN CONTROL  ▶",
                  font=("Courier New", 11, "bold"),
                  fg=BG, bg=ACCENT, relief="flat",
                  activebackground=GREEN, cursor="hand2",
                  pady=10, command=self._submit).pack(
                      padx=24, pady=20, fill="x")

    def _submit(self):
        data = {}
        for i in range(self.lanes):
            try:
                density = int(self.entries[i].get())
                if density < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid",
                    f"Lane {i+1}: enter a valid positive number.")
                return
            sel = self.emerg_vars[i].get().lower()
            is_emerg = sel in ("ambulance", "firetruck")
            data[i] = {
                "density": density,
                "ambulance": sel == "ambulance",
                "emergency": is_emerg,
                "emergency_type": sel if is_emerg else "none"
            }
        self.destroy()
        self.on_submit(data)

    def _on_close(self):
        fallback = self.initial_data if self.initial_data else {
            i: {"density": 0, "ambulance": False, "emergency": False, "emergency_type": "none"}
            for i in range(self.lanes)
        }
        self.destroy()
        self.on_submit(fallback)


#dashboard
class Dashboard(tk.Frame):
    def __init__(self, master, mode, lanes, paths, on_stop, green_time=DEFAULT_GREEN):
        super().__init__(master, bg=BG)
        self.mode = mode
        self.lanes = lanes
        self.paths = paths
        self.on_stop = on_stop
        self.green_time = green_time
        self.yellow_time = DEFAULT_YELLOW
        self.running = False
        self.cameras = {}          # Cameraf instances
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
        self._build()

    def _build(self):
        # top bar
        bar = tk.Frame(self, bg=PANEL, pady=10)
        bar.pack(fill="x")
        tk.Label(bar, text="▶ TRAFFIC CONTROL SYSTEM",
                 font=("Courier New", 14, "bold"),
                 fg=ACCENT, bg=PANEL).pack(side="left", padx=20)
        self.status_var = tk.StringVar(value="⬤  INITIALISING")
        tk.Label(bar, textvariable=self.status_var,
                 font=FONT_B, fg=YELLOW, bg=PANEL).pack(side="left",
                                                         padx=20)
        tk.Button(bar, text="■  STOP", font=FONT_H,
                  fg=BG, bg=RED, relief="flat",
                  padx=16, pady=4, cursor="hand2",
                  command=self._stop).pack(side="right", padx=20)

        self.btn_skip_roi = tk.Button(
            bar, text="Skip ROI (use full frame)", font=FONT_B,
            fg=BG, bg=YELLOW, relief="flat", padx=10, pady=4,
            cursor="hand2", command=self._on_skip_roi
        )

        # manual trigger button 
        if self.mode == 2:
            tk.Button(bar, text="  Enter Values  ",
                      font=FONT_B, fg=BG, bg=YELLOW,
                      relief="flat", padx=10, pady=4,
                      cursor="hand2",
                      command=self._open_manual).pack(side="right",
                                                       padx=8)

        # lane grid
        grid = tk.Frame(self, bg=BG)
        grid.pack(padx=20, pady=20, fill="both", expand=True)
        show_feed = self.mode != 2
        cols = min(self.lanes, 2)
        for i in range(self.lanes):
            card = LaneCard(grid, i, show_feed=show_feed)
            card.grid(row=i // cols, column=i % cols,
                      padx=12, pady=12, sticky="nsew")
            self.cards[i] = card
            grid.columnconfigure(i % cols, weight=1)

        # log strip
        log_f = tk.Frame(self, bg=PANEL, height=60)
        log_f.pack(fill="x", side="bottom")
        log_f.pack_propagate(False)
        tk.Label(log_f, text="LOG", font=FONT_H,
                 fg=SUBTEXT, bg=PANEL).pack(side="left", padx=12)
        self.log_var = tk.StringVar(value="System starting…")
        tk.Label(log_f, textvariable=self.log_var,
                 font=FONT_MONO, fg=TEXT, bg=PANEL,
                 wraplength=860, justify="left").pack(side="left",
                                                       padx=8)

    # lifecycle
    def start(self):
        """Called after the frame is packed."""
        if self.mode in (0, 1):
            t = threading.Thread(target=self._init_cameras, daemon=True)
            t.start()
        else:
            self.running = True
            self.status_var.set("⬤  INITIALISING")
            self.after(0, self._init_manual)

    def _init_cameras(self):
        try:
            for i in range(self.lanes):
                src = i if self.mode == 0 else self.paths[i]
                cam = Cameraf(i, src)
                self.cameras[i] = cam
                if i in self.cards:
                    self.cards[i].set_camera(cam)
                cam.read_frame()
        except RuntimeError as e:
            self.after(0, lambda: messagebox.showerror("Camera Error", str(e)))
            self.after(0, self._stop)
            return

        unconfigured = [
            i for i, cam in self.cameras.items()
            if cam.get_roi() is None
        ]

        if unconfigured:
            def _setup_roi_gui():
                self.btn_skip_roi.pack(side="right", padx=10)
                self.status_var.set("⬤  CONFIGURING ROI")
                self._log("ROI setup: Please configure ROI for each lane, or click 'Skip ROI'")
                for i, cam in self.cameras.items():
                    if cam.last_frame is not None and i in self.cards:
                        self.cards[i].update_frame(cam.last_frame)
                first = unconfigured[0]
                if first in self.cards:
                    self.cards[first].start_edit_roi()

            self.after(0, _setup_roi_gui)
        else:
            self.after(0, self._boot_and_start_cycle)

    def _on_skip_roi(self):
        if hasattr(self, "btn_skip_roi"):
            self.btn_skip_roi.pack_forget()
        for card in self.cards.values():
            if getattr(card, "is_editing", False):
                card.cancel_edit_roi()
        self._log("Skipped ROI setup — using full frames for all lanes")
        if not self.running:
            self._boot_and_start_cycle()

    def _on_lane_roi_configured(self, lane_no):
        if not self.running:
            unconfigured = [
                i for i, cam in self.cameras.items()
                if cam.get_roi() is None
            ]
            if unconfigured:
                next_lane = unconfigured[0]
                if next_lane in self.cards:
                    self.cards[next_lane].start_edit_roi()
            else:
                if hasattr(self, "btn_skip_roi"):
                    self.btn_skip_roi.pack_forget()
                self._log("All lane ROIs configured successfully.")
                self._boot_and_start_cycle()
        else:
            self._log(f"Lane {lane_no + 1}: ROI updated for live operation.")

    def _boot_and_start_cycle(self):
        if hasattr(self, "btn_skip_roi"):
            self.btn_skip_roi.pack_forget()

        def _bg_boot():
            reset_control()
            try:
                lane_data, frames = scan_all_lanes(self.cameras, live=False)
                res = controlfun(lane_data, self.lanes)
                self.lane_data = lane_data
                self.active_lane = res["lane_no"]
            except Exception as e:
                self._log(f"Boot scan error: {e}")
                self.lane_data = {
                    i: {"density": 0, "ambulance": False, "emergency": False, "emergency_type": "none"}
                    for i in range(self.lanes)
                }
                self.active_lane = 0

            self.running = True
            self.current_signal = "GREEN"
            self.time_left = self.green_time

            def _start_gui():
                if not self.running:
                    return
                self.status_var.set(f"⬤  Lane {self.active_lane + 1} GREEN ({self.time_left}s)")
                for i in range(self.lanes):
                    sig = "GREEN" if i == self.active_lane else "RED"
                    d = self.lane_data.get(i, {})
                    self.cards[i].set_signal(
                        sig,
                        density=d.get("density"),
                        ambulance=d.get("ambulance"),
                        emergency_type=d.get("emergency_type"),
                        time_left=self.time_left if sig == "GREEN" else None
                    )
                etype = self.lane_data.get(self.active_lane, {}).get("emergency_type", "none")
                if etype == "ambulance":
                    self._log(f"🚨 Ambulance override → Lane {self.active_lane + 1} GO ({self.green_time}s)")
                elif etype == "firetruck":
                    self._log(f"🚒 Firetruck override → Lane {self.active_lane + 1} GO ({self.green_time}s)")
                else:
                    self._log(f"Lane {self.active_lane + 1} → GREEN ({self.green_time}s) | others → RED")

                det_cfg = get_detector_config()
                if det_cfg.get("detector") == "vision":
                    prov_name = det_cfg.get("provider", "gemini").upper()
                    if not det_cfg.get("has_api_key", False):
                        amb_m = det_cfg.get("ambulance_model", "Model/best.pt")
                        self._log(f"Detector: {prov_name} (no key -> fallback {amb_m})")
                    else:
                        act_m = det_cfg.get("active_model", "")
                        self._log(f"Detector: {prov_name} ({act_m})")
                else:
                    amb_m = det_cfg.get("ambulance_model", "Model/best.pt")
                    self._log(f"Detector: LOCAL ({amb_m})")

                self._video_loop()
                self._timer_job = self.after(1000, self._tick_timer)

            self.after(0, _start_gui)

        t = threading.Thread(target=_bg_boot, daemon=True)
        t.start()
        return t

    def _init_manual(self):
        ManualDialog(self, self.lanes, self._on_manual_boot, initial_data=None)

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

        self.status_var.set(f"⬤  Lane {self.active_lane + 1} GREEN ({self.time_left}s)")
        for i in range(self.lanes):
            sig = "GREEN" if i == self.active_lane else "RED"
            d = self.lane_data.get(i, {})
            self.cards[i].set_signal(
                sig,
                density=d.get("density"),
                ambulance=d.get("ambulance"),
                emergency_type=d.get("emergency_type"),
                time_left=self.time_left if sig == "GREEN" else None
            )

        etype = self.lane_data.get(self.active_lane, {}).get("emergency_type", "none")
        if etype == "ambulance":
            self._log(f"🚨 Ambulance override → Lane {self.active_lane + 1} GO ({self.green_time}s)")
        elif etype == "firetruck":
            self._log(f"🚒 Firetruck override → Lane {self.active_lane + 1} GO ({self.green_time}s)")
        else:
            self._log(f"Lane {self.active_lane + 1} → GREEN ({self.green_time}s) | others → RED")

        self._timer_job = self.after(1000, self._tick_timer)

    def _video_loop(self):
        if not self.running:
            return
        for i, cam in self.cameras.items():
            try:
                frame = cam.read_frame()
                if frame is not None and i in self.cards:
                    self.cards[i].update_frame(frame)
            except Exception:
                pass
        if self.running:
            self._video_job = self.after(40, self._video_loop)

    def _bg_scan(self):
        try:
            lane_data, frames = scan_all_lanes(self.cameras, live=True)
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
        if not self.running:
            return
        self.scanning = True
        ManualDialog(self, self.lanes, self._on_manual_cycle, initial_data=self.lane_data)

    def _tick_timer(self):
        if not self.running:
            return

        # 1. Hold on YELLOW (0s) while scanning is True
        if self.time_left <= 0 and self.scanning:
            self.current_signal = "YELLOW"
            d = self.lane_data.get(self.active_lane, {})
            self.cards[self.active_lane].set_signal(
                "YELLOW",
                density=d.get("density"),
                ambulance=d.get("ambulance"),
                emergency_type=d.get("emergency_type"),
                time_left=0
            )
            self.status_var.set(f"⬤  Lane {self.active_lane + 1} YELLOW (0s)")
            self._timer_job = self.after(200, self._tick_timer)
            return

        # 2. Timer expired and scan finished -> switch active lane
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

            for i in range(self.lanes):
                sig = "GREEN" if i == self.active_lane else "RED"
                d = self.lane_data.get(i, {})
                self.cards[i].set_signal(
                    sig,
                    density=d.get("density"),
                    ambulance=d.get("ambulance"),
                    emergency_type=d.get("emergency_type"),
                    time_left=self.time_left if sig == "GREEN" else None
                )

            etype = self.lane_data.get(self.active_lane, {}).get("emergency_type", "none")
            if etype == "ambulance":
                self._log(f"🚨 Ambulance override → Lane {self.active_lane + 1} GO ({self.green_time}s)")
            elif etype == "firetruck":
                self._log(f"🚒 Firetruck override → Lane {self.active_lane + 1} GO ({self.green_time}s)")
            else:
                self._log(f"Lane {self.active_lane + 1} → GREEN ({self.green_time}s) | others → RED")

            self.status_var.set(f"⬤  Lane {self.active_lane + 1} GREEN ({self.time_left}s)")
            self._timer_job = self.after(1000, self._tick_timer)
            return

        # 3. Decrement timer
        self.time_left -= 1

        if self.time_left > self.yellow_time:
            self.current_signal = "GREEN"
            d = self.lane_data.get(self.active_lane, {})
            self.cards[self.active_lane].set_signal(
                "GREEN",
                density=d.get("density"),
                ambulance=d.get("ambulance"),
                emergency_type=d.get("emergency_type"),
                time_left=self.time_left
            )
            self.status_var.set(f"⬤  Lane {self.active_lane + 1} GREEN ({self.time_left}s)")

        elif self.time_left == self.yellow_time:
            self.current_signal = "YELLOW"
            d = self.lane_data.get(self.active_lane, {})
            self.cards[self.active_lane].set_signal(
                "YELLOW",
                density=d.get("density"),
                ambulance=d.get("ambulance"),
                emergency_type=d.get("emergency_type"),
                time_left=self.time_left
            )
            self.status_var.set(f"⬤  Lane {self.active_lane + 1} YELLOW ({self.time_left}s)")
            self._log(f"Lane {self.active_lane + 1} YELLOW — scanning next cycle...")

            self.scanning = True
            self.next_winner = None
            self.next_lane_data = None

            if self.mode in (0, 1):
                threading.Thread(target=self._bg_scan, daemon=True).start()
            elif self.mode == 2:
                ManualDialog(self, self.lanes, self._on_manual_cycle, initial_data=self.lane_data)

        elif self.time_left < self.yellow_time and self.time_left > 0:
            self.current_signal = "YELLOW"
            d = self.lane_data.get(self.active_lane, {})
            self.cards[self.active_lane].set_signal(
                "YELLOW",
                density=d.get("density"),
                ambulance=d.get("ambulance"),
                emergency_type=d.get("emergency_type"),
                time_left=self.time_left
            )
            self.status_var.set(f"⬤  Lane {self.active_lane + 1} YELLOW ({self.time_left}s)")

        elif self.time_left <= 0:
            if self.scanning:
                self.current_signal = "YELLOW"
                d = self.lane_data.get(self.active_lane, {})
                self.cards[self.active_lane].set_signal(
                    "YELLOW",
                    density=d.get("density"),
                    ambulance=d.get("ambulance"),
                    emergency_type=d.get("emergency_type"),
                    time_left=0
                )
                self.status_var.set(f"⬤  Lane {self.active_lane + 1} YELLOW (0s)")
                self._timer_job = self.after(200, self._tick_timer)
                return
            else:
                self._tick_timer()
                return

        self._timer_job = self.after(1000, self._tick_timer)

    def _stop(self):
        if hasattr(self, "btn_skip_roi"):
            self.btn_skip_roi.pack_forget()
        if self._timer_job is not None:
            self.after_cancel(self._timer_job)
            self._timer_job = None
        if self._video_job is not None:
            self.after_cancel(self._video_job)
            self._video_job = None
        self.running = False
        self.status_var.set("⬤  STOPPED")
        for c in self.cameras.values():
            try:
                c.releasevid()
            except Exception:
                pass
        self.on_stop()

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.after(0, lambda: self.log_var.set(f"[{ts}]  {msg}"))


# app root
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Traffic Control System")
        self.configure(bg=BG)
        self.geometry("940x700")
        self.resizable(True, True)
        self._show_setup()

    def _show_setup(self):
        for w in self.winfo_children():
            w.destroy()
        SetupScreen(self, on_start=self._show_dashboard).pack(
            fill="both", expand=True)

    def _show_dashboard(self, mode, lanes, paths, green_time=DEFAULT_GREEN):
        for w in self.winfo_children():
            w.destroy()
        dash = Dashboard(self, mode, lanes, paths,
                         on_stop=self._show_setup,
                         green_time=green_time)
        dash.pack(fill="both", expand=True)
        dash.start()


if __name__ == "__main__":
    app = App()
    app.mainloop()