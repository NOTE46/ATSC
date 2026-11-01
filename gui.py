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
    from cvfile import Cameraf, scan_all_lanes
except ImportError:
    from cvfile import Cameraf
    def scan_all_lanes(cameras, live=False):
        return {}, {}


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
    def _on_mode_change(self):
        if self.mode_var.get() == 1:
            self.path_card.pack(padx=80, pady=8, fill="x",
                                 before=self.start_btn)
            self._rebuild_paths()
        else:
            self.path_card.pack_forget()

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
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=BORDER)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"LANE {self.lane_no + 1}",
                 font=FONT_H, fg=ACCENT, bg=BORDER,
                 pady=6).pack(side="left", padx=12)
        self.sig_label = tk.Label(hdr, text="● WAITING",
                                  font=FONT_B, fg=YELLOW, bg=BORDER)
        self.sig_label.pack(side="right", padx=12)

        if self.show_feed:
            self.canvas = tk.Canvas(self, width=320, height=200,
                                    bg="#000", bd=0,
                                    highlightthickness=0)
            self.canvas.pack(padx=1, pady=1)

        stats = tk.Frame(self, bg=PANEL)
        stats.pack(fill="x", padx=12, pady=8)
        self.count_var = tk.StringVar(value="Vehicles: —")
        self.amb_var   = tk.StringVar(value="Ambulance: —")
        tk.Label(stats, textvariable=self.count_var,
                 font=FONT_MONO, fg=SUBTEXT, bg=PANEL).pack(side="left")
        tk.Label(stats, textvariable=self.amb_var,
                 font=FONT_MONO, fg=SUBTEXT, bg=PANEL).pack(side="right")

    def update_frame(self, frame_bgr):
        """Push a new OpenCV BGR frame to the canvas."""
        if not self.show_feed:
            return
        img = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (320, 200))
        pil = Image.fromarray(img)
        self._photo = ImageTk.PhotoImage(pil)
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)

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
                self.cameras[i] = Cameraf(i, src)
        except RuntimeError as e:
            self.after(0, lambda: messagebox.showerror("Camera Error", str(e)))
            self.after(0, self._stop)
            return

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

            self._video_loop()
            self._timer_job = self.after(1000, self._tick_timer)

        self.after(0, _start_gui)

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