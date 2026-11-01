Upgrade the Automated Traffic Signal Controller (ATSC) for production using a 3-agent parallel workflow. Implement batch 2-lane vision emergency detection, a 3-tier priority controller with anti-starvation queuing, and a green/yellow countdown timer engine.

Working directory: c:\python_code\ATSC
Integrity mode: development

## Requirements

### R1. Global Constraints, Strict File Ownership & Shared Data Contract
- Trace First: Preserve existing function names, signatures, and fallback keys.
- YAGNI & Standard Library First: Use only Python standard library modules (`json`, `os`, `time`, `threading`, `base64`, `urllib.request`, `pathlib`, `unittest`, `unittest.mock`) and existing packages (`cv2`, `numpy`, `PIL`, `ultralytics`, `tkinter`). Do not add new pip dependencies or create new application source files.
- Minimum Correct Implementation: Write concise, flat, readable functions without unnecessary classes or wrapper abstractions.
- Clean Workspace: Unit/integration tests may be placed in a temporary `tests/` folder or `test_temp.py`. After running verification tests, delete all temporary test files/folders so the repository stays completely clean.
- Do NOT touch Polygon ROI UI selection in this pass—leave `"roi_points": {}` in `config.json`.
- Enforce strict file ownership:
  - Agent 1 ONLY edits: `config.json`, `uafile.py`, `ambdet.py`, `cvfile.py`
  - Agent 2 ONLY edits: `control.py`, `manual_io.py`
  - Agent 3 ONLY edits: `main.py`, `gui.py`
- Shared Data Contract:
  - `cvfile.scan_all_lanes(cameras, live=False)` returns `(lane_data, frames)` where:
    - `lane_data = {i: {"density": int, "ambulance": bool, "emergency": bool, "emergency_type": str}}` (`"ambulance"`, `"firetruck"`, or `"none"`).
    - `frames = {i: numpy_bgr_frame}`.
  - `control.controlfun(data, lanes)` accepts `lane_data` and returns `{"lane_no": int, "signal": "Green"}`.
  - `control.reset_control()` resets internal wait-count and last-lane state when a session restarts.

### R2. Agent 1: Vision, 2-Lane Stitcher & Capture Backend
- `config.json`: Ensure valid JSON containing `green_options` ([15, 30, 40, 50, 60]), `default_green` (30), `yellow_time` (5), `frame_skip` (5), `vehicle_model` ("Model/yolov8n.pt"), `ambulance_model` ("Model/best.pt"), `emergency_detector` ("vision"), `vision_provider` ("gemini"), `gemini_model` ("gemini-2.5-flash"), `vision_stitch_limit` (2), `emergency_priority` ({"ambulance": 2, "firetruck": 1, "none": 0}), and `"roi_points": {}`.
- `uafile.py`:
  - Refactor `uamodel(frame)` into a fast, thread-safe vehicle counter.
  - Load `"vehicle_model"` from `config.json` (fallback to `"Model/yolov8n.pt"`).
  - Wrap `model(frame, conf=0.4, verbose=False)` with a module-level `_yolo_lock = threading.Lock()`.
  - Count bounding boxes with class in `{"car", "motorcycle", "truck", "bus"}` into `density`.
  - Do not call `ambulance_detect` inside `uafile.py`.
  - Return `{"density": density, "ambulance": False, "emergency": False, "emergency_type": "none"}`.
- `ambdet.py`:
  - Lazy-load `Model/best.pt` via `_get_yolo_model()` with a `threading.Lock()` so `best.pt` loads only when local mode or fallback is triggered.
  - Wrap the `best.pt` inference call (`model(frame, conf=0.45, verbose=False)`) inside the thread lock, not just model initialization.
  - Preserve `ambulance_detect(frame)`: runs `best.pt` under lock and returns `True` if `'ambulance'` detected, else `False`.
  - Implement a one-time console warning if `GEMINI_API_KEY` is missing before falling back to local YOLO.
  - Implement `_stitch_lanes(lane_pairs)`: accept up to `vision_stitch_limit` pairs of `(lane_id, frame)` where `frame is not None`, resize each to `(480, 360)`, draw a solid black header bar `(0, 0)` to `(480, 32)` with white text `"LANE {lane_id}"` via `cv2.putText`, and horizontally concatenate with `cv2.hconcat`.
  - Implement `_call_gemini_vision(stitched_bgr, lane_ids, model_name)`:
    - Read `os.environ.get("GEMINI_API_KEY")` (raise `RuntimeError` if missing).
    - Encode JPEG base64, send POST via `urllib.request.urlopen` (timeout=4) with generation config `{"responseMimeType": "application/json", "temperature": 0.0}`.
    - Parse JSON and filter keys: ignore any returned JSON keys not in requested `lane_ids` (only map `int(k) in lane_ids`), and default any missing requested `lane_id` to `"none"`.
    - Normalize labels: `val = str(val).strip().lower().replace(" ", "")`. Enforce strict allowlist validation: any value outside `{"ambulance", "firetruck", "none"}` must default to `"none"`.
  - Implement `detect_emergencies_batch(frames_dict)`: read config, chunk valid frames into slices of size `vision_stitch_limit`, call `_stitch_lanes` and `_call_gemini_vision` if `emergency_detector == "vision"`, and fall back to per-lane `ambulance_detect(f)` on any exception or if detector is `"yolo"`. Populate results mapping each lane to `{"ambulance": is_emerg, "emergency": is_emerg, "emergency_type": etype}` where `is_emerg = etype in ("ambulance", "firetruck")`.
- `cvfile.py`:
  - Load `frame_skip` from `config.json` (default 5).
  - In `Cameraf.__init__(self, lane_no, source)`: add `self.last_frame = None` and `self._lock = threading.Lock()`.
  - Wrap all `self.vid.read()`, `self.vid.grab()`, and `self.vid.set()` calls inside `with self._lock:` so concurrent access between video playback and scanning cannot collide on OpenCV VideoCapture.
  - In `Cameraf.read_frame(self)`: read frame, auto-loop to frame 0 via `self.vid.set(cv.CAP_PROP_POS_FRAMES, 0)` if EOF, store `self.last_frame`, and return frame.
  - In `Cameraf.cvfun(self)`: grab `FRAME_S` frames, retrieve (or loop to 0 if failed), update `self.last_frame`, run `uamodel(frame)`, and check `ambulance_detect(frame)` for single-lane fallback.
  - Implement module-level `scan_all_lanes(cameras, live=False)`:
    - If `live=True` (passed by `gui.py`), use `cam.last_frame.copy()` when `cam.last_frame is not None` (falling back to `cam.read_frame()`).
    - If `live=False` (default, used by `main.py`), always call `cam.read_frame()` so CLI mode grabs a fresh frame on every scan.
    - Null-Frame Guard: If a camera's `frame is None`, skip calling `uamodel(frame)` for that lane, default its `lane_data` entry to `{"density": 0, "ambulance": False, "emergency": False, "emergency_type": "none"}`, and exclude that lane from the dict passed to `detect_emergencies_batch` so the stitcher never receives `None`.
    - Run `uamodel(frame)` for valid frames, call `detect_emergencies_batch(valid_frames)` across lanes, and return `(lane_data, frames)`.

### R3. Agent 2: Emergency Priority & Anti-Starvation Controller
- `control.py`:
  - Replace stateless greedy loop with a 3-tier priority + anti-starvation queue while preserving `controlfun(data, lanes)` signature and return format `{"lane_no": int, "signal": "Green"}`.
  - Maintain module-level state `_wait_counts = {}` and `_last_lane = None`.
  - Implement `reset_control()` to clear `_wait_counts` and reset `_last_lane = None`.
  - Helper `_load_priorities()` reading `"emergency_priority"` from `config.json` (fallback `{"ambulance": 2, "firetruck": 1, "none": 0}`).
  - `controlfun(data, lanes)` decision logic:
    - Tier 1 (Emergency Override): Lanes with priority > 0; winner selected by highest `(lane_prio, density, wait_count)`.
    - Tier 2 (Anti-Starvation Queue): When no emergency, apply cooldown (`_last_lane` excluded if other lanes have density > 0); starving lanes with `_wait_counts[i] >= lanes` and `density > 0` selected by highest `(_wait_counts[i], density)`.
    - Tier 3 (Weighted Density Score): Winner selected by highest `(density + (_wait_counts[i] * 3), _wait_counts[i])`. If all densities are 0 and `_last_lane is not None`, rotate to `(_last_lane + 1) % lanes`.
    - Counter updates: reset winner wait count to 0, record `_last_lane = winner`, and increment `_wait_counts[i] += 1` for all other lanes with `density > 0`.
- `manual_io.py`:
  - Update `minput(lanes)` to prompt for vehicle count (`density >= 0`) and emergency vehicle (`0 = None`, `1 = Ambulance`, `2 = Firetruck`, `> 2 = Ambulance`).
  - Populate `data[i]` with `"density"`, `"ambulance"`, `"emergency"`, and `"emergency_type"`.
  - Call `controlfun(data, lanes)` and display selected lane and signal.

### R4. Agent 3: Green/Yellow Countdown Timer Engine (`main.py` & `gui.py`)
- `main.py`:
  - Load `green_options`, `default_green`, and `yellow_time` from `config.json`.
  - Prompt user for green cycle time after mode/lane selection (validating against `green_options`, falling back to `default_green`).
  - Initialize cameras, call `reset_control()`, and execute initial boot scan via `scan_all_lanes(camera, live=False)` and `controlfun`.
  - Main countdown loop:
    - For `remaining` from `green_time` down to 1: display GREEN status when `remaining > yellow_time`.
    - When `remaining == yellow_time`: display YELLOW status and spawn background `threading.Thread` calling `scan_all_lanes(camera, live=False)` and `controlfun(new_data, lanes)` to prepare `next_decision`.
    - Display switching countdown when `remaining < yellow_time`.
    - At countdown expiry (0): join scan thread (timeout=2), switch `active_lane = next_decision["lane_no"]`, print cycle summary, and repeat.
- `gui.py`:
  - Load timings from `config.json`.
  - Preserve the existing `Dashboard._log(self, msg)` method on `Dashboard`.
  - Standardize timer expiry checks to `time_left <= 0` everywhere in `_tick_timer`.
  - `SetupScreen`: Add "GREEN SIGNAL DURATION (SECONDS)" radio button group below lane count with options `[15, 30, 40, 50, 60]` defaulting to 30. Pass `green_time` into `on_start` with backward-compatible defaults.
  - `LaneCard.set_signal(signal, density=None, ambulance=None, emergency_type=None, time_left=None)`: Format countdown suffix `f" ({time_left}s)"` for GREEN and YELLOW; show `"Emergency: FIRETRUCK 🚒"`, `"Emergency: AMBULANCE 🚨"`, or `"Emergency: No"`.
  - `ManualDialog`:
    - Replace checkbox with 3-option selector (`None`, `Ambulance`, `Firetruck`) and populate `"emergency"` and `"emergency_type"`.
    - Handle window close ("X" button): bind `self.protocol("WM_DELETE_WINDOW", self._on_close)` so if closed without clicking Submit, pass existing `lane_data` (or zero-density defaults on boot) to `on_submit` so Manual Mode never hangs on Yellow.
  - `Dashboard`:
    - Decoupled `_video_loop` scheduled via `self.after(40, ...)` updating frames smoothly using `cam.read_frame()` with zero YOLO inference.
    - `_init_cameras`: run initial boot scan, call `reset_control()`, set `active_lane`, and start loops.
    - Timer Hold on Slow Scans: When `time_left <= 0`, if `self.scanning` is still `True` (`next_winner` not ready yet), hold active lane on `YELLOW (0s)` and switch immediately on the first tick after the background scan completes.
    - Prevent Yellow Freeze on Scan Failure: In `_bg_scan`, wrap scan and `controlfun` in a `try...except Exception as e:...finally:` block. On `except`, log `self._log(f"Scan error: {e}")`, set `self.next_lane_data = self.lane_data`, and set `self.next_winner = (self.active_lane + 1) % self.lanes`. In `finally`, ALWAYS set `self.scanning = False`.
    - Manual Mode (Mode 2) Cycle Integration: In Mode 2 (no cameras), open `ManualDialog` at startup to set initial `lane_data` and pick the initial GREEN lane. Automatically open `ManualDialog` again when `time_left == yellow_time` to collect `next_lane_data`, holding the transition at `YELLOW` until submitted or closed.
    - Video / Camera Modes (0 & 1): background scan at `time_left == yellow_time` calls `scan_all_lanes(self.cameras, live=True)`.

## Verification Resources
The team will create and run automated unit and integration tests (using `unittest.mock` so tests run without live network or `.pt` model files):
- Anti-starvation queueing, tie-breaking, and priority overrides in `control.py`.
- Frame stitching, Gemini request formatting, allowlist normalization, and local YOLO fallback in `ambdet.py` and `cvfile.py`.
- Thread safety, null-frame handling, and `live` frame selection in `cvfile.Cameraf` and `scan_all_lanes`.
- Data contract schema compliance between `scan_all_lanes` and `controlfun`.
- Video looping and thread-safe YOLO vehicle counting in `uafile.py` and `cvfile.py`.
- Automatic cleanup: All temporary test scripts and test directories (`tests/` or `test_temp.py`) must be deleted after tests pass.

## Acceptance Criteria

### Global Constraints & Contracts
- [ ] Each agent modifies ONLY its assigned files: Agent 1 (`config.json`, `uafile.py`, `ambdet.py`, `cvfile.py`), Agent 2 (`control.py`, `manual_io.py`), Agent 3 (`main.py`, `gui.py`).
- [ ] No new pip dependencies installed; imports use only Python standard library and pre-existing packages (`cv2`, `numpy`, `PIL`, `ultralytics`, `tkinter`).
- [ ] `config.json` contains valid JSON with exact required keys and defaults.
- [ ] Existing function signatures and return keys remain backward-compatible.
- [ ] All temporary test files and folders are cleaned up after verification.

### Vision & Emergency Detection (Agent 1)
- [ ] `uafile.uamodel` is thread-safe with `_yolo_lock`, counts `{"car", "motorcycle", "truck", "bus"}` into `density`, and returns the schema dict without calling `ambulance_detect`.
- [ ] `ambdet.detect_emergencies_batch` filters keys to requested `lane_ids`, normalizes Gemini outputs, enforces strict allowlist validation (`{"ambulance", "firetruck", "none"}`), prints a one-time missing key warning, and wraps `best.pt` inference in a lock.
- [ ] `ambdet._stitch_lanes` resizes frames to 480x360 with header bar and lane numbers, concatenating up to `vision_stitch_limit` valid frames.
- [ ] `cvfile.Cameraf` protects VideoCapture access with `self._lock` and auto-loops to frame 0 on EOF.
- [ ] `cvfile.scan_all_lanes(cameras, live=False)` handles `live=True` vs `live=False`, guards against `None` frames, and returns `(lane_data, frames)` matching the shared contract.

### Controller & Starvation Prevention (Agent 2)
- [ ] `control.controlfun` prioritizes ambulance (priority 2) over firetruck (priority 1) over non-emergency lanes.
- [ ] `control.controlfun` enforces active-lane cooldown and prioritizes starving lanes (`_wait_counts >= lanes` with traffic) over non-starving lanes.
- [ ] `control.controlfun` uses weighted density formula `density + (wait * 3)` during normal cycles and rotates on zero traffic.
- [ ] `control.reset_control` clears wait counts and last active lane.
- [ ] `manual_io.minput` correctly accepts and handles 0 (None), 1 (Ambulance), and 2 (Firetruck).

### Timing Engine & GUI (Agent 3)
- [ ] `main.py` CLI prompts for green duration from `green_options`, runs green countdown, triggers background scan during yellow time, and switches active lanes cleanly.
- [ ] `gui.py` video playback runs smoothly at ~25fps without blocking on YOLO inference.
- [ ] `gui.py` `LaneCard` displays green/yellow countdown timers and ambulance/firetruck badges.
- [ ] `gui.py` standardizes on `time_left <= 0`, holds on `YELLOW (0s)` if background scan is slow, and recovers cleanly without freezing if `_bg_scan` raises an exception.
- [ ] `gui.py` integrates Mode 2 (Manual) with automatic dialog prompt at yellow time and safe window close ("X") handling.

### Test Verification
- [ ] Automated unit and integration tests run and pass completely using `unittest.mock`.
- [ ] All temporary test files and folders are deleted after testing.
