# Project: Automated Traffic Signal Controller (ATSC) Upgrade

## Architecture
ATSC is an intelligent, multi-lane traffic signal controller that balances vehicle density, emergency vehicle preemption (Ambulances and Firetrucks), and anti-starvation fair queueing. It supports live video feeds, pre-recorded video files, and manual entry.

### Component Boundaries & Strict File Ownership
1. **Vision & Capture Backend (Agent 1)**:
   - Files: `config.json`, `uafile.py`, `ambdet.py`, `cvfile.py`
   - Responsibilities: Camera capture thread-safety, frame auto-looping, vehicle counting (YOLOv8n), 2-lane composite image stitching, Gemini Vision API client, batch emergency detection, local YOLO fallback.
2. **Emergency Priority & Anti-Starvation Controller (Agent 2)**:
   - Files: `control.py`, `manual_io.py`
   - Responsibilities: 3-tier priority arbitration, active-lane cooldown, anti-starvation queueing, weighted density scoring, zero-traffic rotation, session reset, CLI manual input handling.
3. **Green/Yellow Countdown Timer Engine & GUI (Agent 3)**:
   - Files: `main.py`, `gui.py`
   - Responsibilities: CLI & GUI countdown engines, video loop decoupling (40ms, zero YOLO), yellow light transition and background scan trigger, slow-scan hold, yellow freeze prevention, manual dialog lifecycle.
4. **E2E Testing Track**:
   - Scope: Comprehensive opaque-box test suite (`tests/` or `test_temp.py`) with `unittest.mock` for zero-hardware automated verification. Temporary files cleaned after verification.

---

## Feature Inventory
| # | Feature | Description | Milestone | Source | Status |
|---|---------|-------------|-----------|--------|--------|
| 1 | Configuration Schema | Complete `config.json` with `green_options`, `default_green`, `yellow_time`, `frame_skip`, `vehicle_model`, `ambulance_model`, `emergency_detector`: "vision", `vision_provider`: "gemini", `gemini_model`: "gemini-2.5-flash", `vision_stitch_limit`: 2, `emergency_priority`, `roi_points`: {} | M1 | R1, R2 | DONE |
| 2 | Thread-Safe Vehicle Counting | `uafile.uamodel` with `_yolo_lock`, counting `{"car", "motorcycle", "truck", "bus"}` with conf=0.4 | M1 | R2 | DONE |
| 3 | Decoupled uamodel Schema | `uafile.uamodel` returns contract schema without calling `ambulance_detect` | M1 | R2 | DONE |
| 4 | Lazy Emergency Model Loading | `ambdet._get_yolo_model()` lazy-loads `Model/best.pt` under lock only on local mode/fallback | M1 | R2 | DONE |
| 5 | Lock-Protected Local Inference | `ambdet.ambulance_detect(frame)` runs inference under lock | M1 | R2 | DONE |
| 6 | Missing API Key Warning | One-time console warning if `GEMINI_API_KEY` missing before fallback to local YOLO | M1 | R2 | DONE |
| 7 | 2-Lane Image Stitching | `ambdet._stitch_lanes` resizes to (480, 360), adds solid black header bar with "LANE {id}", horizontally concatenates | M1 | R2 | DONE |
| 8 | Gemini Vision Client | `ambdet._call_gemini_vision` sends base64 POST via urllib, timeout=4, temp=0.0, json schema, key filtering, allowlist normalization | M1 | R2 | DONE |
| 9 | Batch Emergency Detection | `ambdet.detect_emergencies_batch` chunks by stitch limit, calls vision or falls back to local YOLO | M1 | R2 | DONE |
| 10 | VideoCapture Mutex Lock | `cvfile.Cameraf` wraps read, grab, set in `self._lock`, maintains `last_frame` | M1 | R2 | DONE |
| 11 | Video Auto-Looping | `cvfile.Cameraf.read_frame` seeks to frame 0 on EOF | M1 | R2 | DONE |
| 12 | Video Grab & Single-Lane Fallback | `cvfile.Cameraf.cvfun` grabs `frame_skip` frames, auto-loops, runs uamodel and single-lane fallback | M1 | R2 | DONE |
| 13 | Multi-Lane Scan Engine | `cvfile.scan_all_lanes` supports `live=True` vs `live=False`, Null-Frame Guard, returns `(lane_data, frames)` | M1 | R2 | DONE |
| 14 | Controller State Management | `control.py` maintains `_wait_counts = {}` and `_last_lane = None` | M2 | R3 | DONE |
| 15 | Session Reset Function | `control.reset_control()` clears `_wait_counts` and sets `_last_lane = None` | M2 | R1, R3 | DONE |
| 16 | Priority Configuration Loader | `control._load_priorities()` loads `emergency_priority` from config with fallback | M2 | R3 | DONE |
| 17 | Tier 1: Emergency Override | Highest `(lane_prio, density, wait_count)` wins; ambulance (2) > firetruck (1) > none (0) | M2 | R3 | DONE |
| 18 | Tier 2: Anti-Starvation Queue | Active-lane cooldown; starving lanes (`_wait_counts >= lanes` with density > 0) prioritized by `(wait_count, density)` | M2 | R3 | DONE |
| 19 | Tier 3: Weighted Density & Rotation | Highest `(density + (wait_count * 3), wait_count)`; zero traffic rotation `(_last_lane + 1) % lanes` | M2 | R3 | DONE |
| 20 | State Counter Updates | Winner wait count reset to 0, `_last_lane = winner`, wait count incremented for non-winners with density > 0 | M2 | R3 | DONE |
| 21 | Manual CLI Input Schema | `manual_io.minput` prompts for density and emergency vehicle (0=None, 1=Ambulance, 2=Firetruck, >2=Ambulance) | M2 | R3 | DONE |
| 22 | Manual CLI Dispatch | `manual_io.minput` populates shared contract schema and calls `controlfun` | M2 | R3 | DONE |
| 23 | CLI Config & Duration Prompt | `main.py` loads timing from config, prompts for green duration with validation & default fallback | M3 | R4 | DONE |
| 24 | CLI Boot Scan & Countdown Loop | `main.py` boot scan via `scan_all_lanes` + `controlfun`, countdown loop, background scan at yellow time, summary print | M3 | R4 | DONE |
| 25 | Preserved Dashboard._log | `gui.py` preserves `Dashboard._log(self, msg)` verbatim | M3 | R4 | DONE |
| 26 | Standardized Timer Expiry | `gui.py` checks `time_left <= 0` everywhere in `_tick_timer` | M3 | R4 | DONE |
| 27 | SetupScreen Duration Selector | `gui.py` SetupScreen adds radio group `[15, 30, 40, 50, 60]` defaulting to 30, passes to `on_start` | M3 | R4 | DONE |
| 28 | LaneCard Countdown & Badges | `gui.py` LaneCard formats countdown suffix `f" ({time_left}s)"` and badges (`FIRETRUCK 🚒`, `AMBULANCE 🚨`, `No`) | M3 | R4 | DONE |
| 29 | ManualDialog 3-Option & Close Safety | `gui.py` ManualDialog 3-option selector, full schema return, and `WM_DELETE_WINDOW` handler preventing yellow freeze | M3 | R4 | DONE |
| 30 | Decoupled Video Loop | `gui.py` Dashboard `_video_loop` at 40ms using `cam.read_frame()` with zero YOLO calls | M3 | R4 | DONE |
| 31 | Dashboard Boot Scan | `gui.py` Dashboard `_init_cameras` boot scan calling `reset_control()`, setting `active_lane`, starting loops | M3 | R4 | DONE |
| 32 | Timer Hold on Slow Scans | `gui.py` Dashboard holds on `YELLOW (0s)` while `scanning=True`, switching immediately upon completion | M3 | R4 | DONE |
| 33 | Yellow Freeze Prevention | `gui.py` Dashboard `_bg_scan` wrapped in `try...except...finally` ensuring `scanning=False` and fallback rotation | M3 | R4 | DONE |
| 34 | Mode 2 Cycle Integration | `gui.py` Dashboard Mode 2 opens ManualDialog at startup and yellow time, holding on yellow until submitted/closed | M3 | R4 | DONE |
| 35 | Video/Camera Mode Live Scan | `gui.py` Dashboard Mode 0/1 background scan calls `scan_all_lanes(self.cameras, live=True)` | M3 | R4 | DONE |
| 36 | 4-Tier Opaque-Box Test Suite | Comprehensive unit/mock test suite covering Tiers 1-4 | Test Track | R1, R2, R3, R4 | DONE |
| 37 | Full E2E & Adversarial Pass | 100% pass on all test tiers, Tier 5 adversarial checks, clean workspace | Final Milestone | R1, R2, R3, R4 | DONE |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Agent 1: Vision, 2-Lane Stitcher & Capture Backend | `config.json`, `uafile.py`, `ambdet.py`, `cvfile.py` | None | DONE |
| M2 | Agent 2: Emergency Priority & Anti-Starvation Controller | `control.py`, `manual_io.py` | None | DONE |
| M3 | Agent 3: Green/Yellow Countdown Timer Engine & GUI | `main.py`, `gui.py` | Interface Contracts | DONE |
| M_TEST | Parallel E2E Testing Track | Test suite design, `TEST_INFRA.md`, `TEST_READY.md` | None (opaque-box) | DONE |
| M_FINAL | Final Integration & Adversarial Hardening | Run 100% test suite, Tier 5 adversarial checks, delete temp tests | M1, M2, M3, M_TEST | DONE |

---

## Interface Contracts

### 1. `cvfile.scan_all_lanes(cameras, live=False) -> (lane_data, frames)`
- **Input**:
  - `cameras`: dictionary `{i: Cameraf}` or list of `Cameraf` instances.
  - `live`: `bool`. If `True`, use cached `cam.last_frame.copy()` (fallback `cam.read_frame()`). If `False`, call `cam.read_frame()` directly.
- **Output**: `(lane_data, frames)`
  - `lane_data`: `{i: {"density": int, "ambulance": bool, "emergency": bool, "emergency_type": str}}`
    - `density`: non-negative integer count of vehicles (`car`, `motorcycle`, `truck`, `bus`).
    - `ambulance`: boolean (`True` if `emergency_type == "ambulance"`).
    - `emergency`: boolean (`True` if `emergency_type in ("ambulance", "firetruck")`).
    - `emergency_type`: string strictly in `{"ambulance", "firetruck", "none"}`.
  - `frames`: `{i: numpy_bgr_frame}` (or empty/None if camera unavailable).
  - Null-Frame Guard: If camera frame is `None`, default `lane_data[i] = {"density": 0, "ambulance": False, "emergency": False, "emergency_type": "none"}` and exclude from batch emergency detection.

### 2. `control.controlfun(data, lanes) -> {"lane_no": int, "signal": "Green"}`
- **Input**:
  - `data`: `lane_data` dictionary formatted per contract above.
  - `lanes`: integer total number of lanes.
- **Output**: `{"lane_no": int, "signal": "Green"}`
  - `lane_no`: 0-indexed winner lane (`0 <= lane_no < lanes`).
  - `signal`: string `"Green"`.

### 3. `control.reset_control() -> None`
- Resets module-level `_wait_counts = {}` and `_last_lane = None`.

---

## Code Layout
- `c:\python_code\ATSC\config.json`: System configuration (Agent 1)
- `c:\python_code\ATSC\uafile.py`: Vehicle density YOLO counter (Agent 1)
- `c:\python_code\ATSC\ambdet.py`: 2-lane stitcher, Gemini vision client, local YOLO fallback (Agent 1)
- `c:\python_code\ATSC\cvfile.py`: VideoCapture wrapper and multi-lane scanner (Agent 1)
- `c:\python_code\ATSC\control.py`: 3-tier priority and anti-starvation controller (Agent 2)
- `c:\python_code\ATSC\manual_io.py`: Manual CLI traffic entry (Agent 2)
- `c:\python_code\ATSC\main.py`: CLI execution loop and countdown engine (Agent 3)
- `c:\python_code\ATSC\gui.py`: Tkinter dashboard and countdown engine (Agent 3)
- `c:\python_code\ATSC\Model\yolov8n.pt`: COCO vehicle model (Read-only)
- `c:\python_code\ATSC\Model\best.pt`: Local ambulance YOLO model (Read-only)
