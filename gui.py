import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import time
import cv2
from PIL import Image, ImageTk

from cvfile import Cameraf
from control import controlfun

TIME_INTERVAL = 2

# ─────────────────────────────────────────────
# COLOURS & FONTS
# ─────────────────────────────────────────────
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


# ─────────────────────────────────────────────
# SETUP SCREEN
# ─────────────────────────────────────────────
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

        # ── mode card ──
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

        # ── lanes card ──
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

        # ── video path card (shown only for mode 1) ──
        self.path_card = tk.Frame(self, bg=PANEL, highlightthickness=1,
                                  highlightbackground=BORDER)
        tk.Label(self.path_card, text="VIDEO FILES", font=FONT_H,
                 fg=SUBTEXT, bg=PANEL).pack(anchor="w", padx=20,
                                            pady=(18, 6))
        self.path_frame = tk.Frame(self.path_card, bg=PANEL)
        self.path_frame.pack(padx=20, pady=(0, 18), fill="x")

        # ── start button ──
        self.start_btn = tk.Button(
            self, text="START SYSTEM  ▶",
            font=("Courier New", 12, "bold"),
            fg=BG, bg=ACCENT, relief="flat",
            activebackground=GREEN, activeforeground=BG,
            cursor="hand2", pady=12, command=self._start)
        self.start_btn.pack(padx=80, pady=30, fill="x")

    # ── callbacks ────────────────────────────
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

        if mode == 1:
            paths = [e.get().strip() for e in self._path_entries]
            if any(p == "" for p in paths):
                messagebox.showwarning("Missing paths",
                                       "Please select a video for every lane.")
                return
            self.on_start(mode, lanes, paths)
        else:
            self.on_start(mode, lanes, [])


# ─────────────────────────────────────────────
# LANE CARD
# ─────────────────────────────────────────────
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

    def set_signal(self, signal: str, density=None, ambulance=None):
        sig = signal.upper()
        if sig == "GREEN":
            self.sig_label.config(text="● GO", fg=GREEN)
            self.config(highlightbackground=GREEN)
        elif sig == "RED":
            self.sig_label.config(text="● STOP", fg=RED)
            self.config(highlightbackground=RED)
        else:
            self.sig_label.config(text="● WAIT", fg=YELLOW)
            self.config(highlightbackground=YELLOW)

        if density is not None:
            self.count_var.set(f"Vehicles: {density}")
        if ambulance is not None:
            self.amb_var.set(f"Ambulance: {'YES 🚨' if ambulance else 'No'}")


# ─────────────────────────────────────────────
# MANUAL INPUT DIALOG
# ─────────────────────────────────────────────
class ManualDialog(tk.Toplevel):
    """Popup to collect manual density + ambulance per lane."""
    def __init__(self, master, lanes, on_submit):
        super().__init__(master, bg=BG)
        self.title("Manual Input")
        self.resizable(False, False)
        self.lanes     = lanes
        self.on_submit = on_submit
        self.entries   = {}
        self.amb_vars  = {}
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
            e = tk.Entry(row1, font=FONT_MONO, fg=TEXT, bg=BG,
                         insertbackground=ACCENT, relief="flat",
                         bd=4, width=10)
            e.insert(0, "0")
            e.pack(side="left")
            self.entries[i] = e

            row2 = tk.Frame(card, bg=PANEL)
            row2.pack(fill="x", padx=14, pady=(2, 10))
            tk.Label(row2, text="Ambulance:", font=FONT_B,
                     fg=TEXT, bg=PANEL, width=10,
                     anchor="w").pack(side="left")
            var = tk.BooleanVar(value=False)
            tk.Checkbutton(row2, variable=var, bg=PANEL,
                           activebackground=PANEL,
                           selectcolor=BG, fg=TEXT,
                           text="Yes").pack(side="left")
            self.amb_vars[i] = var

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
            data[i] = {
                "density":   density,
                "ambulance": self.amb_vars[i].get()
            }
        self.destroy()
        self.on_submit(data)


# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────
class Dashboard(tk.Frame):
    def __init__(self, master, mode, lanes, paths, on_stop):
        super().__init__(master, bg=BG)
        self.mode    = mode
        self.lanes   = lanes
        self.paths   = paths
        self.on_stop = on_stop
        self.running = False
        self.cameras  = {}          # Cameraf instances
        self.lane_data_lock = threading.Lock()
        self.lane_data      = {}
        self.cards   = {}
        self._build()

    def _build(self):
        # ── top bar ──
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

        # ── manual trigger button (mode 2 only) ──
        if self.mode == 2:
            tk.Button(bar, text="  Enter Values  ",
                      font=FONT_B, fg=BG, bg=YELLOW,
                      relief="flat", padx=10, pady=4,
                      cursor="hand2",
                      command=self._open_manual).pack(side="right",
                                                       padx=8)

        # ── lane grid ──
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

        # ── log strip ──
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

    # ── lifecycle ────────────────────────────
    def start(self):
        """Called after the frame is packed."""
        if self.mode in (0, 1):
            t = threading.Thread(target=self._init_cameras, daemon=True)
            t.start()
        else:
            # manual mode — just mark ready
            self.after(0, lambda: self.status_var.set("⬤  READY — press Enter Values"))

    def _init_cameras(self):
        try:
            for i in range(self.lanes):
                src = i if self.mode == 0 else self.paths[i]
                self.cameras[i] = Cameraf(i, src)   # ✅ uses your Cameraf
            self.after(0, lambda: self.status_var.set("⬤  RUNNING"))
            self.running = True
            self._run_loop()
        except RuntimeError as e:
            self.after(0, lambda: messagebox.showerror("Camera Error", str(e)))
            self.after(0, self._stop)

    def _stop(self):
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

    # ── manual mode ──────────────────────────
    def _open_manual(self):
        ManualDialog(self, self.lanes, self._run_manual)

    def _run_manual(self, data):
        """Process one manual round and update cards."""
        try:
            result = controlfun(data, self.lanes)   # ✅ your controlfun
        except Exception as e:
            messagebox.showerror("Control Error", str(e))
            return

        for i in range(self.lanes):
            sig = "GREEN" if i == result["lane_no"] else "RED"
            d   = data[i]
            self.cards[i].set_signal(sig,
                                     density=d["density"],
                                     ambulance=d["ambulance"])

        amb_lane = result["lane_no"] if any(
            data[i]["ambulance"] for i in range(self.lanes)) else None
        msg = (f"🚨 Ambulance override → Lane {result['lane_no']+1}  GO"
               if amb_lane is not None
               else f"Lane {result['lane_no']+1} → GO  |  others → STOP")
        self._log(msg)
        self.status_var.set(
            f"⬤  Lane {result['lane_no']+1} GREEN")

    # ── camera loop (runs in background thread) ──
    def _run_loop(self):
        while self.running:
            lane_data  = {}
            frames     = {}

            # ── per-lane threads so cameras process in parallel ──
            results_lock = threading.Lock()

            def process_lane(idx):
                try:
                    data = self.cameras[idx].cvfun()   # ✅ your cvfun
                    frame = self._grab_raw_frame(idx)
                    with results_lock:
                        lane_data[idx]  = data
                        frames[idx]     = frame
                except Exception as e:
                    with results_lock:
                        lane_data[idx] = {"density": 0, "ambulance": False}
                        frames[idx]    = None
                    print(f"Lane {idx} error: {e}")

            threads = [threading.Thread(target=process_lane, args=(i,),
                                        daemon=True)
                       for i in range(self.lanes)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # ── update frames on main thread ──
            for i in range(self.lanes):
                if frames.get(i) is not None:
                    f = frames[i]
                    self.after(0, lambda f=f, idx=i:
                               self.cards[idx].update_frame(f))

            # ── run your controlfun ──
            try:
                result = controlfun(lane_data, self.lanes)  # ✅
            except Exception as e:
                self._log(f"Control error: {e}")
                time.sleep(TIME_INTERVAL)
                continue

            # ── update signals on main thread ──
            for i in range(self.lanes):
                sig = "GREEN" if i == result["lane_no"] else "RED"
                d   = lane_data.get(i, {})
                self.after(0, lambda idx=i, s=sig, d=d:
                           self.cards[idx].set_signal(
                               s,
                               density=d.get("density"),
                               ambulance=d.get("ambulance")))

            amb = any(lane_data[i].get("ambulance") for i in range(self.lanes))
            msg = (f"🚨 Ambulance → Lane {result['lane_no']+1} GREEN"
                   if amb
                   else f"Lane {result['lane_no']+1} → GREEN  |  others → RED")
            self._log(msg)

            time.sleep(TIME_INTERVAL)

    def _grab_raw_frame(self, idx):
        """Grab a raw frame directly for display (no YOLO processing)."""
        ret, frame = self.cameras[idx].vid.read()
        if not ret:
            self.cameras[idx].vid.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self.cameras[idx].vid.read()
        return frame if ret else None


# ─────────────────────────────────────────────
# APP ROOT
# ─────────────────────────────────────────────
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

    def _show_dashboard(self, mode, lanes, paths):
        for w in self.winfo_children():
            w.destroy()
        dash = Dashboard(self, mode, lanes, paths,
                         on_stop=self._show_setup)
        dash.pack(fill="both", expand=True)
        dash.start()


if __name__ == "__main__":
    app = App()
    app.mainloop()