# Survey Report: Agent 3 Domain (main.py & gui.py)

## 1. Observation

### 1.1 Scope and Environment
- **Workspace**: `c:\python_code\ATSC`
- **Files Owned by Agent 3**: `main.py` (81 lines), `gui.py` (527 lines)
- **External Contracts & Dependencies**:
  - `config.json`: defines `green_options` (`[15, 30, 40, 50, 60]`), `default_green` (`30`), `yellow_time` (`5`).
  - `cvfile.py`: provides `Cameraf` and `scan_all_lanes(cameras, live=False) -> (lane_data, frames)`.
  - `control.py`: provides `controlfun(data, lanes) -> {"lane_no": int, "signal": "Green"}` and `reset_control() -> None`.
  - `manual_io.py`: provides `minput(lanes) -> None`.

---

### 1.2 Current State of `main.py`
Examining `c:\python_code\ATSC\main.py`:
- **Lines 1-5**:
  ```python
  from cvfile import Cameraf
  from control import controlfun
  import time
  from manual_io import minput
  import threading
  ```
  Missing: `json` import to parse `config.json`, `scan_all_lanes` from `cvfile`, and `reset_control` from `control`.
- **Line 7**: `TIME_INTERVAL=2` — Hardcoded polling constant; lacks timing configuration.
- **Lines 9-14**: `process_l(i, camera, lane_data)` — Dead/legacy threading helper that calls `camera[i].cvfun()`.
- **Lines 19-39**: CLI input loop prompts for mode (`0=live`, `1=video`, `2=manual`) and lane count.
- **Lines 40-48**:
  ```python
  if ty == 2:
      minput(lanes)
      return
  ```
  Manual mode immediately delegates to `minput(lanes)` and terminates execution without cycle timer.
- **Lines 50-56**: Camera dictionary initialization (`camera[i] = Cameraf(i, ...)`).
- **Lines 57-68**:
  ```python
  while True:
      lane_data = {}
      for i in range(lanes):
          data = camera[i].cvfun()
          lane_data[i] = data
      results = controlfun(lane_data, lanes)
      print(f"Lane:{results['lane_no']} Signal:{results['signal']}")
      time.sleep(TIME_INTERVAL)
  ```
  Observations:
  - Calls `cvfun()` sequentially per lane in the foreground.
  - Sleeps fixed 2 seconds (`TIME_INTERVAL`).
  - No countdown display.
  - No yellow transition state.
  - No background scan at yellow time.
  - No call to `reset_control()`.
  - No call to `scan_all_lanes(camera, live=False)`.
  - No prompt for green duration validating against `green_options` with `default_green` fallback.

---

### 1.3 Current State of `gui.py`
Examining `c:\python_code\ATSC\gui.py`:

#### 1. Imports and Constants (Lines 1-28)
- Imports `Cameraf` from `cvfile` and `controlfun` from `control`.
- Missing imports: `json`, `scan_all_lanes`, `reset_control`.
- UI Colors (`BG`, `PANEL`, `BORDER`, `ACCENT`, `GREEN`, `RED`, `YELLOW`, `TEXT`, `SUBTEXT`) and Fonts (`FONT_H`, `FONT_B`, `FONT_MONO`) are well defined.

#### 2. `SetupScreen` (Lines 30-159)
- `__init__(self, master, on_start)`
- `_build(self)`: Builds mode selection card (radio buttons 0, 1, 2) and lane selection card (radio buttons 1, 2, 3, 4).
- Missing: "GREEN SIGNAL DURATION (SECONDS)" radio button group (`[15, 30, 40, 50, 60]`, defaulting to 30).
- `_start(self)` (lines 145-158):
  ```python
  def _start(self):
      mode = self.mode_var.get()
      lanes = self.lane_var.get()
      if mode == 1:
          ...
          self.on_start(mode, lanes, paths)
      else:
          self.on_start(mode, lanes, [])
  ```
  Only passes `mode, lanes, paths`. Does not pass `green_time`.

#### 3. `LaneCard` (Lines 161-222)
- `__init__(self, master, lane_no, show_feed=True)`
- `_build(self)`:
  - `self.sig_label`: text `"● WAITING"`, fg `YELLOW`.
  - `self.canvas`: 320x200 canvas.
  - `self.count_var`: `"Vehicles: —"`.
  - `self.amb_var`: `"Ambulance: —"`.
- `update_frame(self, frame_bgr)`: Converts BGR to RGB, resizes to 320x200, updates canvas.
- `set_signal(self, signal: str, density=None, ambulance=None)` (lines 205-221):
  ```python
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
  ```
  Observations:
  - Missing `emergency_type=None` and `time_left=None` parameters.
  - Does not format countdown suffix `f" ({time_left}s)"` for GREEN and YELLOW signals.
  - Does not show `"Emergency: FIRETRUCK 🚒"`, `"Emergency: AMBULANCE 🚨"`, or `"Emergency: No"`.

#### 4. `ManualDialog` (Lines 224-300)
- `__init__(self, master, lanes, on_submit)`:
  - Currently takes only `(master, lanes, on_submit)` (no `initial_data`).
  - Calls `self.grab_set()`.
  - Does NOT bind `WM_DELETE_WINDOW`.
- `_build(self)`:
  - For each lane: text entry for vehicles, `tk.Checkbutton` for `ambulance` (boolean).
  - Missing: 3-option emergency selector (`None`, `Ambulance`, `Firetruck`).
- `_submit(self)` (lines 282-299):
  - Validates positive integers for density.
  - Passes `{"density": density, "ambulance": bool}`.
  - Missing `"emergency"` (`bool`) and `"emergency_type"` (`str`).
- Missing: `_on_close(self)` protocol handler for `WM_DELETE_WINDOW`. If a user closes the dialog with the "X" button without submitting, `on_submit` is never called, which would permanently freeze the signal on YELLOW.

#### 5. `Dashboard` (Lines 302-498)
- `__init__(self, master, mode, lanes, paths, on_stop)`:
  - Lacks `green_time` parameter.
  - Lacks timer state variables (`self.time_left`, `self.current_signal`, `self.active_lane`, `self.scanning`, `self.next_winner`, `self.next_lane_data`, `self._timer_job`, `self._video_job`).
- `_log(self, msg)` (lines 397-399):
  ```python
  def _log(self, msg):
      ts = time.strftime("%H:%M:%S")
      self.after(0, lambda: self.log_var.set(f"[{ts}]  {msg}"))
  ```
  Must be preserved verbatim.
- `start(self)` (lines 366-374):
  - For modes 0 and 1, spawns `_init_cameras` in a thread.
  - For mode 2 (manual), simply sets status to `"⬤  READY — press Enter Values"`. Does not trigger startup `ManualDialog` or initial GREEN lane selection.
- `_init_cameras(self)` (lines 375-386):
  - Initializes `Cameraf` instances.
  - Sets `self.running = True`.
  - Immediately invokes `self._run_loop()` in the same thread.
  - Does not call `reset_control()`.
  - Does not perform initial boot scan via `scan_all_lanes(self.cameras, live=False)`.
  - Does not set `self.active_lane`.
- `_run_loop(self)` (lines 430-490):
  - Loops while `self.running`:
    - Launches background threads per lane running `self.cameras[idx].cvfun()` (which performs blocking YOLO inference!).
    - Calls `_grab_raw_frame` which accesses `self.cameras[idx].vid.read()` directly without locks.
    - Joins threads, updates frames on main thread.
    - Calls `controlfun`.
    - Updates signals.
    - Sleeps `time.sleep(TIME_INTERVAL)`.
  - This architecture couples video playback tightly to YOLO inference. Because YOLO takes several hundred milliseconds to seconds per frame, video feeds stutter heavily (~0.5 fps slideshow instead of smooth video).
- `_grab_raw_frame(self, idx)` (lines 491-498):
  - Calls `self.cameras[idx].vid.read()` directly without mutex synchronization with `Cameraf` or `cvfun()`.

#### 6. `App` (Lines 501-527)
- `_show_dashboard(self, mode, lanes, paths)`:
  - Instantiates `Dashboard(self, mode, lanes, paths, on_stop=self._show_setup)`. Needs to accept and pass `green_time`.

---

## 2. Logic Chain

### 2.1 Decoupling GUI Video Playback from Vision Inference
1. **Observation**: `Dashboard._run_loop` executes `cvfun()` (which calls `uamodel` and `ambulance_detect` on every frame) synchronously inside a `time.sleep(2)` loop.
2. **Inference**: High-frequency video capture (~25 fps / 40ms) cannot coexist with YOLO vehicle detection and Gemini API calls within a single sequential loop.
3. **Requirement Reference (R4)**: "`Dashboard`: Decoupled `_video_loop` scheduled via `self.after(40, ...)` updating frames smoothly using `cam.read_frame()` with zero YOLO inference."
4. **Conclusion**:
   - `_run_loop()` must be completely removed from `gui.py`.
   - Replace with `_video_loop(self)` scheduled via `self.after(40, self._video_loop)`.
   - Each tick calls `cam.read_frame()`, which is thread-safe (Agent 1's `Cameraf._lock`) and updates `card.update_frame(frame)`.
   - Zero YOLO/vision calls occur in `_video_loop`.

### 2.2 Green/Yellow Countdown Timer Engine & State Transitions
1. **Observation**: Currently neither `main.py` nor `gui.py` has a countdown timer or yellow light phase. Lights abruptly stay GREEN for one lane and RED for others until the next polling tick.
2. **Requirement Reference (R4)**:
   - For `remaining` from `green_time` down to 1: GREEN when `remaining > yellow_time`.
   - When `remaining == yellow_time`: YELLOW status and trigger scan.
   - When `remaining < yellow_time` and `> 0`: YELLOW status switching countdown.
   - At expiry `time_left <= 0`: switch active lane and repeat.
3. **Inference**:
   - In `main.py`, a synchronous 1-second countdown loop (`for remaining in range(green_time, 0, -1): ... time.sleep(1)`) meets the requirement directly.
   - In `gui.py`, an event-driven `_tick_timer(self)` scheduled via `self.after(1000, self._tick_timer)` keeps Tkinter responsive without blocking the UI thread.
4. **Standardization of Expiry**:
   - The requirement explicitly mandates: "Standardize timer expiry checks to `time_left <= 0` everywhere in `_tick_timer`."
   - Checking `time_left <= 0` avoids negative countdown overruns or skipped ticks.

### 2.3 Timer Hold on Slow Scans & Yellow Freeze Prevention
1. **Observation**: If YOLO inference or network calls to Gemini take longer than `yellow_time` seconds, or if an unexpected exception occurs during scanning, the system could freeze on YELLOW or switch to an uninitialized winner.
2. **Requirement Reference (R4)**:
   - "Timer Hold on Slow Scans: When `time_left <= 0`, if `self.scanning` is still `True` (`next_winner` not ready yet), hold active lane on `YELLOW (0s)` and switch immediately on the first tick after the background scan completes."
   - "Prevent Yellow Freeze on Scan Failure: In `_bg_scan`, wrap scan and `controlfun` in a `try...except Exception as e:...finally:` block. On `except`, log `self._log(f"Scan error: {e}")`, set `self.next_lane_data = self.lane_data`, and set `self.next_winner = (self.active_lane + 1) % self.lanes`. In `finally`, ALWAYS set `self.scanning = False`."
3. **Inference**:
   - When `time_left <= 0` and `self.scanning == True`:
     Keep signal at `YELLOW (0s)`, do not switch yet, reschedule `_tick_timer` with short poll interval (e.g., 200ms).
   - Once `self.scanning == False`:
     Switch active lane to `self.next_winner` immediately and reset `time_left = self.green_time`.
   - The `try...except...finally` construct in `_bg_scan` guarantees `self.scanning` is always reset to `False`, preventing an infinite Yellow hold.

### 2.4 Mode 2 (Manual Mode) Integration
1. **Observation**: Currently in `gui.py`, Mode 2 only has a manual trigger button in the top bar. It does not run a timer loop and does not automatically prompt at yellow time.
2. **Observation**: `ManualDialog` currently has no window close handler (`WM_DELETE_WINDOW`). If dismissed via "X", callbacks are abandoned.
3. **Requirement Reference (R4)**:
   - "In Mode 2 (no cameras), open `ManualDialog` at startup to set initial `lane_data` and pick the initial GREEN lane."
   - "Automatically open `ManualDialog` again when `time_left == yellow_time` to collect `next_lane_data`, holding the transition at `YELLOW` until submitted or closed."
   - "Handle window close ("X" button): bind `self.protocol("WM_DELETE_WINDOW", self._on_close)` so if closed without clicking Submit, pass existing `lane_data` (or zero-density defaults on boot) to `on_submit` so Manual Mode never hangs on Yellow."
4. **Inference**:
   - `ManualDialog` must accept `initial_data=None`. On close without submission, it passes `self.initial_data` (or zero-density defaults) to `on_submit`.
   - When Mode 2 starts in `Dashboard`, it opens `ManualDialog` to obtain the initial active lane, sets `self.active_lane`, and starts `_tick_timer`.
   - When `time_left == yellow_time`, `Dashboard` sets `self.scanning = True` and opens `ManualDialog` pre-populated with `initial_data=self.lane_data`.
   - Submission or dismissal resets `self.scanning = False`, and `_tick_timer` proceeds with lane switching.

### 2.5 Emergency Display and Badge Requirements
1. **Observation**: `LaneCard.set_signal` only handles boolean `ambulance` and sets `"Ambulance: YES 🚨"` or `"Ambulance: No"`.
2. **Requirement Reference (R4)**:
   - "`LaneCard.set_signal(signal, density=None, ambulance=None, emergency_type=None, time_left=None)`: Format countdown suffix `f" ({time_left}s)"` for GREEN and YELLOW; show `"Emergency: FIRETRUCK 🚒"`, `"Emergency: AMBULANCE 🚨"`, or `"Emergency: No"`."
3. **Inference**:
   - Update `set_signal` signature to `(signal: str, density=None, ambulance=None, emergency_type=None, time_left=None)`.
   - Suffix logic: If `time_left is not None`, suffix is `f" ({time_left}s)"`, else `""`. For GREEN: `f"● GO{suffix}"`. For YELLOW: `f"● WAIT{suffix}"`. For RED: `f"● STOP"`.
   - Badge logic:
     - If `emergency_type == "firetruck"`: `"Emergency: FIRETRUCK 🚒"`
     - If `emergency_type == "ambulance"` or (`ambulance` is True and not `emergency_type`): `"Emergency: AMBULANCE 🚨"`
     - Otherwise: `"Emergency: No"`

---

## 3. Potential Breaking Changes & Interface Compatibility

| Area | Potential Risk | Mitigation / Preservation Strategy |
|---|---|---|
| `Dashboard._log` | External callers or sub-methods expecting `self._log(msg)` | Preserve exact method name and signature: `def _log(self, msg): ...` |
| `SetupScreen.on_start` callback | Adding `green_time` parameter could break callers expecting 3 arguments | Provide default argument in target: `def _show_dashboard(self, mode, lanes, paths, green_time=30):` and `Dashboard.__init__(..., green_time=30)` |
| `LaneCard.set_signal` | Existing callers only pass `(signal, density, ambulance)` | Use default keyword arguments: `set_signal(self, signal, density=None, ambulance=None, emergency_type=None, time_left=None)` |
| `ManualDialog` constructor | Callers passing `(master, lanes, on_submit)` | Make `initial_data` optional: `def __init__(self, master, lanes, on_submit, initial_data=None):` |
| VideoCapture concurrency | `_video_loop` reading frames while `_bg_scan` is active | Agent 1 wraps `Cameraf` methods with `self._lock` and `scan_all_lanes(live=True)` uses `cam.last_frame.copy()`. In `gui.py`, call `cam.read_frame()`, never `cam.vid.read()` directly. |
| CLI `main.py` inputs | User enters empty string, letters, or out-of-range number for green cycle time | Wrap input parsing in `try/except (ValueError, TypeError)` and validate `val in green_options`; fall back gracefully to `default_green`. |
| Scan failure / timeout | Background thread raises exception or Gemini times out | Wrap `_bg_scan` and CLI thread execution in `try...except...finally` ensuring fallback lane rotation and `scanning = False`. |

---

## 4. Precise Implementation Recommendations for Agent 3

### 4.1 Implementation Plan for `main.py`

#### A. Imports & Configuration Helper
```python
import json
from pathlib import Path
import threading
import time
from control import controlfun, reset_control
from cvfile import Cameraf, scan_all_lanes
from manual_io import minput

def load_config():
    cfg_path = Path("config.json")
    if cfg_path.exists():
        try:
            with open(cfg_path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}
```

#### B. CLI Prompting with Validation
```python
config = load_config()
green_options = config.get("green_options", [15, 30, 40, 50, 60])
default_green = config.get("default_green", 30)
yellow_time = config.get("yellow_time", 5)

# Prompt for green duration
opts_str = ", ".join(str(x) for x in green_options)
raw_green = input(f"Select green signal duration in seconds ({opts_str}) [default {default_green}]: ").strip()
try:
    val = int(raw_green)
    green_time = val if val in green_options else default_green
except (ValueError, TypeError):
    green_time = default_green
```

#### C. Boot Scan & Countdown Loop
```python
reset_control()
lane_data, frames = scan_all_lanes(camera, live=False)
results = controlfun(lane_data, lanes)
active_lane = results["lane_no"]
print(f"\n[BOOT SCAN COMPLETE] Initial Active Lane: {active_lane + 1} (GREEN for {green_time}s)")

while True:
    next_decision = [None]
    scan_data = [None]
    scan_thread = None

    for remaining in range(green_time, 0, -1):
        if remaining > yellow_time:
            print(f"[Lane {active_lane + 1} GREEN] Time remaining: {remaining}s")
            time.sleep(1)
        elif remaining == yellow_time:
            print(f"[Lane {active_lane + 1} YELLOW] Switching in {remaining}s — scanning traffic...")
            def _cli_scan():
                try:
                    data, _ = scan_all_lanes(camera, live=False)
                    scan_data[0] = data
                    next_decision[0] = controlfun(data, lanes)
                except Exception as e:
                    print(f"Scan error: {e}")
                    next_decision[0] = {"lane_no": (active_lane + 1) % lanes, "signal": "Green"}

            scan_thread = threading.Thread(target=_cli_scan, daemon=True)
            scan_thread.start()
            time.sleep(1)
        else:
            print(f"[Lane {active_lane + 1} YELLOW] Switching in {remaining}s")
            time.sleep(1)

    # Expiry at 0
    if scan_thread is not None:
        scan_thread.join(timeout=2)

    prev_lane = active_lane
    if next_decision[0] is not None:
        active_lane = next_decision[0]["lane_no"]
    else:
        active_lane = (prev_lane + 1) % lanes

    # Print cycle summary
    active_density = scan_data[0][active_lane].get("density", 0) if scan_data[0] else "N/A"
    active_emerg = scan_data[0][active_lane].get("emergency_type", "none") if scan_data[0] else "none"
    print(f"\n{'='*55}")
    print(f"CYCLE SUMMARY: Lane {prev_lane + 1} -> Lane {active_lane + 1} GREEN")
    print(f"Winner Density: {active_density} | Emergency: {active_emerg.upper()}")
    print(f"{'='*55}\n")
```

---

### 4.2 Implementation Plan for `gui.py`

#### A. `SetupScreen` Duration Radio Buttons
Add duration card below `card2` (lanes):
```python
card3 = tk.Frame(self, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
card3.pack(padx=80, pady=8, fill="x")
tk.Label(card3, text="GREEN SIGNAL DURATION (SECONDS)", font=FONT_H, fg=SUBTEXT, bg=PANEL).pack(anchor="w", padx=20, pady=(18, 6))

self.green_var = tk.IntVar(value=DEFAULT_GREEN)
row = tk.Frame(card3, bg=PANEL)
row.pack(padx=20, pady=(0, 18))
for g in GREEN_OPTIONS:
    tk.Radiobutton(
        row, text=f"{g}s", variable=self.green_var, value=g,
        font=("Courier New", 12, "bold"), fg=TEXT, bg=PANEL,
        selectcolor=BG, activebackground=PANEL, activeforeground=ACCENT,
        indicatoron=False, width=5, relief="flat"
    ).pack(side="left", padx=6)
```
In `_start(self)`:
```python
green_time = self.green_var.get()
self.on_start(mode, lanes, paths, green_time)
```

#### B. `LaneCard.set_signal` Countdown & Badges
```python
def set_signal(self, signal: str, density=None, ambulance=None, emergency_type=None, time_left=None):
    sig = signal.upper()
    suffix = f" ({time_left}s)" if time_left is not None else ""
    if sig == "GREEN":
        self.sig_label.config(text=f"● GO{suffix}", fg=GREEN)
        self.config(highlightbackground=GREEN)
    elif sig == "RED":
        self.sig_label.config(text="● STOP", fg=RED)
        self.config(highlightbackground=RED)
    else: # YELLOW
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
```

#### C. `ManualDialog` 3-Option Selector and WM_DELETE_WINDOW
```python
class ManualDialog(tk.Toplevel):
    def __init__(self, master, lanes, on_submit, initial_data=None):
        super().__init__(master, bg=BG)
        self.title("Manual Input")
        self.resizable(False, False)
        self.lanes = lanes
        self.on_submit = on_submit
        self.initial_data = initial_data or {}
        self.entries = {}
        self.emerg_vars = {}
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build()
        self.grab_set()

    def _build(self):
        # Header...
        for i in range(self.lanes):
            # Lane card...
            # Vehicles entry (pre-filled from initial_data if present)
            # Row 2: 3-option emergency selector
            self.emerg_vars[i] = tk.StringVar(value="None")
            for opt, lbl in [("None", "None"), ("Ambulance", "Ambulance 🚨"), ("Firetruck", "Firetruck 🚒")]:
                tk.Radiobutton(
                    row2, text=lbl, variable=self.emerg_vars[i], value=opt,
                    font=FONT_B, fg=TEXT, bg=PANEL, selectcolor=BG,
                    activebackground=PANEL, activeforeground=ACCENT
                ).pack(side="left", padx=4)

    def _submit(self):
        data = {}
        for i in range(self.lanes):
            try:
                density = int(self.entries[i].get())
                if density < 0: raise ValueError
            except ValueError:
                messagebox.showerror("Invalid", f"Lane {i+1}: enter a valid positive number.")
                return
            etype = self.emerg_vars[i].get().lower()
            is_emerg = etype in ("ambulance", "firetruck")
            data[i] = {
                "density": density,
                "ambulance": etype == "ambulance",
                "emergency": is_emerg,
                "emergency_type": etype if is_emerg else "none"
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
```

#### D. `Dashboard` Engine: Video Loop, Timer Ticks, Background Scan & Yellow Freeze Prevention
```python
class Dashboard(tk.Frame):
    def __init__(self, master, mode, lanes, paths, on_stop, green_time=30):
        super().__init__(master, bg=BG)
        self.mode = mode
        self.lanes = lanes
        self.paths = paths
        self.on_stop = on_stop
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
        self._build()

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

    def _tick_timer(self):
        if not self.running:
            return

        # 1. Hold on YELLOW 0s while scanning is True
        if self.time_left <= 0 and self.scanning:
            self.cards[self.active_lane].set_signal(
                "YELLOW",
                density=self.lane_data.get(self.active_lane, {}).get("density"),
                ambulance=self.lane_data.get(self.active_lane, {}).get("ambulance"),
                emergency_type=self.lane_data.get(self.active_lane, {}).get("emergency_type"),
                time_left=0
            )
            self.status_var.set(f"⬤  Lane {self.active_lane + 1} YELLOW (0s - holding for scan)")
            self._timer_job = self.after(200, self._tick_timer)
            return

        # 2. Timer expired and scan is complete -> switch lanes
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

            self.status_var.set(f"⬤  Lane {self.active_lane + 1} GREEN")
            self._timer_job = self.after(1000, self._tick_timer)
            return

        # 3. Decrement timer
        self.time_left -= 1

        if self.time_left > self.yellow_time:
            self.current_signal = "GREEN"
            self.cards[self.active_lane].set_signal(
                "GREEN",
                density=self.lane_data.get(self.active_lane, {}).get("density"),
                ambulance=self.lane_data.get(self.active_lane, {}).get("ambulance"),
                emergency_type=self.lane_data.get(self.active_lane, {}).get("emergency_type"),
                time_left=self.time_left
            )
            self.status_var.set(f"⬤  Lane {self.active_lane + 1} GREEN ({self.time_left}s)")

        elif self.time_left == self.yellow_time:
            self.current_signal = "YELLOW"
            self.cards[self.active_lane].set_signal(
                "YELLOW",
                density=self.lane_data.get(self.active_lane, {}).get("density"),
                ambulance=self.lane_data.get(self.active_lane, {}).get("ambulance"),
                emergency_type=self.lane_data.get(self.active_lane, {}).get("emergency_type"),
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
            self.cards[self.active_lane].set_signal(
                "YELLOW",
                density=self.lane_data.get(self.active_lane, {}).get("density"),
                ambulance=self.lane_data.get(self.active_lane, {}).get("ambulance"),
                emergency_type=self.lane_data.get(self.active_lane, {}).get("emergency_type"),
                time_left=self.time_left
            )
            self.status_var.set(f"⬤  Lane {self.active_lane + 1} YELLOW ({self.time_left}s)")

        elif self.time_left <= 0:
            if self.scanning:
                self.cards[self.active_lane].set_signal(
                    "YELLOW",
                    density=self.lane_data.get(self.active_lane, {}).get("density"),
                    ambulance=self.lane_data.get(self.active_lane, {}).get("ambulance"),
                    emergency_type=self.lane_data.get(self.active_lane, {}).get("emergency_type"),
                    time_left=0
                )
                self.status_var.set(f"⬤  Lane {self.active_lane + 1} YELLOW (0s - holding for scan)")
                self._timer_job = self.after(200, self._tick_timer)
                return
            else:
                self._tick_timer()
                return

        self._timer_job = self.after(1000, self._tick_timer)
```

---

## 5. Caveats
1. **Agent Coordination**: `main.py` and `gui.py` rely on `scan_all_lanes` (implemented by Agent 1 in `cvfile.py`) and `controlfun` / `reset_control` (implemented by Agent 2 in `control.py`). Agent 3's implementation must be testable via `unittest.mock` even before Agent 1 and Agent 2 finish their implementations.
2. **Headless Environment**: In automated CI/headless environments where a display may not be connected, Tkinter test suites must instantiate `App` with mock event loops or test individual component methods (`_tick_timer`, `_bg_scan`, `set_signal`) using mocks.
3. **No UI Changes for ROI**: As mandated by R1, Polygon ROI UI selection is out of scope and left as `"roi_points": {}` in `config.json`.

---

## 6. Conclusion
Agent 3's domain (`main.py` and `gui.py`) has been fully surveyed against all requirements of R1 and R4.
The current codebase lacks countdown timers, has stuttering video playback caused by inline YOLO inference, lacks yellow transition states, and risks signal freezing on manual dialog close or slow scans.
The proposed architectural redesign:
- Decouples video playback at 40ms without YOLO.
- Implements a robust countdown timer engine in both CLI (`main.py`) and GUI (`gui.py`).
- Introduces robust Yellow light hold logic (`time_left <= 0` and `self.scanning`) with yellow freeze prevention via `try...except...finally`.
- Seamlessly integrates Mode 2 manual input at boot and yellow phase with safe `WM_DELETE_WINDOW` handling.
- Conforms 100% to the shared data contract schema (`{"density": int, "ambulance": bool, "emergency": bool, "emergency_type": str}`) and emergency priority display (`FIRETRUCK 🚒`, `AMBULANCE 🚨`, `No`).

---

## 7. Verification Method
To independently verify Agent 3's implementation when constructed:
1. **Mock Unit / Integration Testing**:
   Create a temporary unit test (e.g. `tests/test_agent3.py` or `test_temp_gui.py`) using `unittest.mock`:
   - Mock `cvfile.scan_all_lanes` and `control.controlfun`, `control.reset_control`.
   - Test `LaneCard.set_signal` formatting for GREEN `(30s)`, YELLOW `(5s)`, RED, and emergency badges.
   - Test `ManualDialog` submit and `_on_close` returning valid data schema.
   - Test `Dashboard._tick_timer` decrements, yellow trigger at `time_left == yellow_time`, timer hold at `YELLOW (0s)` while `scanning=True`, and clean lane transition when `scanning=False`.
   - Test `Dashboard._bg_scan` error resilience (ensuring `self.scanning` becomes `False` on exception).
2. **Execution Command**:
   ```powershell
   python -m unittest tests/test_agent3.py
   ```
3. **Cleanup**:
   Ensure all temporary test files/folders are deleted after verification.
