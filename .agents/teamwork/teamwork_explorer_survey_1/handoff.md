# Comprehensive Survey Report: Agent 1 Domain (Vision, 2-Lane Stitcher & Capture Backend)

**Author**: Survey Explorer 1 (`teamwork_explorer`)  
**Target Files**: `config.json`, `uafile.py`, `ambdet.py`, `cvfile.py`, `Model/`  
**Working Directory**: `c:\python_code\ATSC\.agents\teamwork\teamwork_explorer_survey_1`  
**Date**: 2026-11-01  

---

## 1. Observations

### 1.1 `Model/` Directory
- **Files**:
  - `c:\python_code\ATSC\Model\best.pt` (Size: 6,249,258 bytes).
  - `c:\python_code\ATSC\Model\yolov8n.pt` (Size: 6,549,796 bytes).
- **Inspected Attributes via Python**:
  - `yolov8n.pt` contains 80 standard COCO classes, specifically including:
    - Class 2: `'car'`
    - Class 3: `'motorcycle'`
    - Class 5: `'bus'`
    - Class 7: `'truck'`
  - `best.pt` contains custom classes:
    - `{0: 'ambulance'}` (Note: local YOLO model detects ambulances only; it has **no** firetruck class).

---

### 1.2 `config.json`
- **Path**: `c:\python_code\ATSC\config.json` (17 lines)
- **Current Content**:
```json
{
  "green_options": [15, 30, 40, 50, 60],
  "default_green": 30,
  "yellow_time": 5,
  "frame_skip": 5,
  "vehicle_model": "Model/yolov8n.pt",
  "ambulance_model": "Model/best.pt",
  "emergency_detector": "yolo",
  "vision_provider": "gemini",
  "vision_stitch_limit": 2,
  "emergency_priority": {
    "ambulance": 2,
    "firetruck": 1,
    "none": 0
  },
  "roi_points": {}
}
```
- **Discrepancies against R2 Requirements**:
  1. `"emergency_detector"` is currently set to `"yolo"`. R2 requirement: `"emergency_detector": "vision"`.
  2. `"gemini_model"` key is **missing entirely**. R2 requirement: `"gemini_model": "gemini-2.5-flash"`.
  3. `"roi_points": {}` is present and must remain untouched per R1 constraint.

---

### 1.3 `uafile.py`
- **Path**: `c:\python_code\ATSC\uafile.py` (48 lines)
- **Current Imports & Globals** (Lines 1–8):
```python
1: from ultralytics import YOLO
2: from collections import defaultdict
3: from ambdet import ambulance_detect
4: from pathlib import Path
...
7: model_path=Path("Model")/"yolov8n.pt"
8: model = YOLO(model_path)
```
- **Current Function Signature**: `def uamodel(frame):` (Lines 11–47)
- **Observations**:
  1. **Eager Global Model Load**: Model is instantiated at module import time (`model = YOLO(model_path)`) using a hardcoded path (`Path("Model")/"yolov8n.pt"`), ignoring `config.json`.
  2. **No Thread Lock**: Inference `results=model(frame)` (Line 17) runs without synchronization locks. Concurrent execution across background scan threads and video loops causes race conditions in Ultralytics PyTorch backends.
  3. **Missing Target Class**: Current detection loop (Lines 24–36) checks `car`, `motorcycle`, and `truck`, but **omits `bus`**.
  4. **Tight Coupling with Emergency Detection**: Lines 38–41 call `ambulance_detect(frame)` directly if a truck is detected. This tightly couples vehicle density counting with emergency detection and forces local YOLO inference on every truck detection.
  5. **Incompatible Return Schema**: Returns `{"density": density, "ambulance": vehiclecount["ambulance"] > 0}` (Lines 44–47). It lacks the R2 contract keys: `"emergency": False, "emergency_type": "none"`.
  6. **Default Parameters**: `model(frame)` defaults to `conf=0.25` and `verbose=True` (emitting verbose console output).

---

### 1.4 `ambdet.py`
- **Path**: `c:\python_code\ATSC\ambdet.py` (19 lines)
- **Current Imports & Globals** (Lines 1–5):
```python
1: from ultralytics import YOLO
2: from pathlib import Path
...
4: model_v=Path("Model")/"best.pt"
5: model=YOLO(model_v)
```
- **Current Function Signature**: `def ambulance_detect(frame):` (Lines 7–17)
```python
7: def ambulance_detect(frame):
8: 
9:     results=model(frame)
10: 
11:     for box in results[0].boxes:
12:         label=results[0].names[int(box.cls)]
13: 
14:         if label == 'ambulance':
15:             return True
16:     
17:     return False
```
- **Observations**:
  1. **Eager Load on Import**: `best.pt` is loaded immediately on module import, incurring startup latency even if `emergency_detector` is set to `"vision"`.
  2. **No Inference Lock**: Inference `model(frame)` lacks synchronization.
  3. **Missing Functions**: None of the required vision functions exist:
     - Missing `_get_yolo_model()` lazy loader.
     - Missing `_stitch_lanes(lane_pairs)`.
     - Missing `_call_gemini_vision(stitched_bgr, lane_ids, model_name)`.
     - Missing `detect_emergencies_batch(frames_dict)`.
     - Missing one-time console warning when `GEMINI_API_KEY` is absent.

---

### 1.5 `cvfile.py`
- **Path**: `c:\python_code\ATSC\cvfile.py` (36 lines)
- **Current Imports & Class Structure**:
```python
1: import cv2 as cv
2: from uafile import uamodel
...
4: FRAME_S=5
...
6: class Cameraf:
7:     def __init__(self,lane_no,source):
8:         self.lane_no=lane_no
9:         self.vid=cv.VideoCapture(source)
...
14:    def cvfun(self):
...
28:    def releasevid(self):
```
- **Observations**:
  1. **Hardcoded Frame Skip**: `FRAME_S = 5` is hardcoded instead of dynamically reading `frame_skip` from `config.json`.
  2. **Missing Thread Lock on VideoCapture**: `cv.VideoCapture` instances in OpenCV are not thread-safe. Concurrent access (`read()` in GUI video loop while `grab()` in scan loop) crashes OpenCV or corrupts frame buffers.
  3. **Missing `last_frame` Attribute**: `Cameraf` lacks `self.last_frame` cache required for non-blocking `live=True` scans.
  4. **Missing `read_frame(self)` Method**: Does not exist on `Cameraf`.
  5. **No EOF Auto-Looping**: In `cvfun(self)` (Lines 19–23), if `retrieve()` fails on EOF, it prints a failure and returns `{"density": 0, "ambulance": False}` without rewinding `cv.CAP_PROP_POS_FRAMES` to 0.
  6. **Missing Module-Level Function**: `scan_all_lanes(cameras, live=False)` is **completely absent**.
  7. **Callers in Codebase**:
     - `main.py`: Imports `Cameraf` from `cvfile`. Currently calls `camera[i].cvfun()` in a loop. Needs `scan_all_lanes(cameras, live=False)`.
     - `gui.py`: Imports `Cameraf` from `cvfile`. In `_grab_raw_frame` (Lines 491–497), it directly called `cam.vid.read()` and `cam.vid.set(cv2.CAP_PROP_POS_FRAMES, 0)`. Agent 3 will refactor this to use `cam.read_frame()`, while background scan will call `scan_all_lanes(cameras, live=True)`.

---

## 2. Logic Chain

1. **Config Incompleteness**:
   - *Observation*: `config.json` lacks `"gemini_model"` and has `"emergency_detector": "yolo"`.
   - *Deduction*: If `emergency_detector` remains `"yolo"`, the system will bypass Gemini Vision by default. If `gemini_model` is missing, `_call_gemini_vision` will lack a configured model endpoint.
   - *Action*: Update `config.json` to include `"gemini_model": "gemini-2.5-flash"` and `"emergency_detector": "vision"`.

2. **Thread Safety in YOLO Inference (`uafile.py` & `ambdet.py`)**:
   - *Observation*: Ultralytics `YOLO` C++ bindings/PyTorch backends are not thread-safe for simultaneous forward passes.
   - *Deduction*: When GUI runs video playback and background threads run scans, concurrent calls to `uamodel` and `ambulance_detect` cause race conditions.
   - *Action*: Introduce module-level `threading.Lock()` instances: `_yolo_lock` in `uafile.py` and `_yolo_lock` in `ambdet.py`. Serialize all model execution calls under `with _yolo_lock:`.

3. **Decoupling Vehicle Counting from Emergency Detection (`uafile.py`)**:
   - *Observation*: `uafile.py` currently invokes `ambulance_detect(frame)`.
   - *Deduction*: Calling emergency detection inside `uafile` duplicates work because `detect_emergencies_batch` in `ambdet.py` processes emergency classification across all lanes in batched chunks.
   - *Action*: Remove `ambulance_detect` from `uafile.py`. `uamodel` will count classes in `{"car", "motorcycle", "truck", "bus"}` with `conf=0.4, verbose=False` and return `{"density": density, "ambulance": False, "emergency": False, "emergency_type": "none"}`.

4. **Lazy Loading of Secondary Emergency Model (`ambdet.py`)**:
   - *Observation*: `Model/best.pt` is 6.2MB. Loading it on import delays startup by 1–2 seconds.
   - *Deduction*: In production with `emergency_detector: "vision"`, local YOLO is only a fallback when `GEMINI_API_KEY` is missing or when network calls fail.
   - *Action*: Implement `_get_yolo_model()` using double-checked locking so `best.pt` is only loaded into memory when local fallback is actually invoked.

5. **2-Lane Horizon Stitching & Gemini Vision Pipeline (`ambdet.py`)**:
   - *Observation*: Sending individual frames per lane to Gemini doubles API latency and request count.
   - *Deduction*: Stitching 2 lanes into a single horizontal composite image of 960x360 with clear header annotations allows a single Gemini Vision call to classify multiple lanes simultaneously with temperature=0.0 and JSON schema enforcement.
   - *Action*:
     - `_stitch_lanes(lane_pairs)`: Resizes each valid frame to (480, 360), draws black banner `(0, 0)` to `(480, 32)`, writes `"LANE {lane_id}"` in white text, and horizontally concatenates up to `vision_stitch_limit` frames.
     - `_call_gemini_vision(stitched_bgr, lane_ids, model_name)`: Sends base64 JPEG via `urllib.request.urlopen` with timeout=4s and JSON response schema. Parses response, discards extraneous keys, validates against allowlist `{"ambulance", "firetruck", "none"}`, and normalizes casing/whitespace.
     - Fallback: Any exception in Gemini call triggers fallback to local `ambulance_detect(f)` for that batch slice.

6. **VideoCapture Thread Safety & Auto-Looping (`cvfile.py`)**:
   - *Observation*: Video files end (EOF). Concurrently calling `read()` and `grab()` without locks leads to corrupt frames or exceptions.
   - *Deduction*: `Cameraf` needs an internal lock protecting all `VideoCapture` operations. On EOF (`ret == False`), it must seek to frame 0 (`cv.CAP_PROP_POS_FRAMES, 0`) and read again to seamlessly loop video inputs.
   - *Action*:
     - Implement `self._lock = threading.Lock()` and `self.last_frame = None`.
     - Implement `read_frame(self)`: thread-safe read with EOF rewind to 0, updating `self.last_frame`.
     - Implement `cvfun(self)`: thread-safe grab/retrieve with EOF rewind, updating `self.last_frame`, returning full contract schema with single-lane `ambulance_detect` fallback.
     - Implement `scan_all_lanes(cameras, live=False)`: handles `live=True` (reading cached `last_frame.copy()`) vs `live=False` (calling `read_frame()`), null-frame guard defaulting to 0 density, runs `uamodel` on valid frames, batches emergency detection via `detect_emergencies_batch`, and returns `(lane_data, frames)`.

---

## 3. Potential Breaking Changes & Mitigations

| Area | Potential Risk | Mitigation |
|---|---|---|
| **Return Schema of `uamodel`** | Callers expecting only `{"density", "ambulance"}` might break if schema changes. | Maintain `density` and `ambulance` as primary keys, while adding `emergency` and `emergency_type`. All legacy callers checking `data["ambulance"]` remain 100% backward-compatible. |
| **`ambulance_detect` removal from `uafile`** | Callers calling `uamodel` standalone without `scan_all_lanes` might not detect ambulances. | For single-lane camera calls, `Cameraf.cvfun` checks `ambulance_detect(frame)` directly as a single-lane fallback. For multi-lane controller cycles, `scan_all_lanes` merges `detect_emergencies_batch`. |
| **Missing `GEMINI_API_KEY` in environment** | If `emergency_detector: "vision"` but no API key is provided, system could crash or hang. | Implement graceful fallback: print a one-time console warning `Warning: GEMINI_API_KEY environment variable not found. Falling back to local YOLO.` and immediately fall back to `ambulance_detect(f)`. |
| **Network Timeout on Gemini API** | Slow networks could stall the traffic light controller countdown. | Enforce `timeout=4` on `urllib.request.urlopen`. Catch `urllib.error.URLError`, `http.client.HTTPException`, `TimeoutError`, and `json.JSONDecodeError` inside `detect_emergencies_batch` and seamlessly fall back to local YOLO. |
| **VideoCapture EOF on Video Files** | Mode 1 (Video Files) stops when reaching video end. | Both `read_frame()` and `cvfun()` detect `ret == False`, set `CAP_PROP_POS_FRAMES = 0`, and re-read frame 0, ensuring infinite seamless looping. |
| **Null Frames / Disconnected Cameras** | Camera index invalid or file missing returns `None` frame. | `scan_all_lanes` implements Null-Frame Guard: if `frame is None`, defaults `lane_data[i]` to `{"density": 0, "ambulance": False, "emergency": False, "emergency_type": "none"}` and excludes that lane from `detect_emergencies_batch` so the stitcher never receives `None`. |
| **Allowlist Normalization** | Gemini might return `"Ambulance"`, `"Fire Truck"`, `"none."`, or markdown-wrapped JSON. | Strict normalization: `val = str(val).strip().lower().replace(" ", "")`. Any value outside `{"ambulance", "firetruck", "none"}` strictly defaults to `"none"`. |

---

## 4. Implementation Blueprint & Recommendations

### 4.1 `config.json`
Update to:
```json
{
  "green_options": [15, 30, 40, 50, 60],
  "default_green": 30,
  "yellow_time": 5,
  "frame_skip": 5,
  "vehicle_model": "Model/yolov8n.pt",
  "ambulance_model": "Model/best.pt",
  "emergency_detector": "vision",
  "vision_provider": "gemini",
  "gemini_model": "gemini-2.5-flash",
  "vision_stitch_limit": 2,
  "emergency_priority": {
    "ambulance": 2,
    "firetruck": 1,
    "none": 0
  },
  "roi_points": {}
}
```

### 4.2 `uafile.py`
Key architecture:
- Module-level `_yolo_lock = threading.Lock()`.
- Lazy loader `_get_vehicle_model()` reading `"vehicle_model"` from `config.json` with fallback to `"Model/yolov8n.pt"`.
- Target classes: `TARGET_CLASSES = {"car", "motorcycle", "truck", "bus"}`.
- `uamodel(frame)`:
  - If `frame is None`: return `{"density": 0, "ambulance": False, "emergency": False, "emergency_type": "none"}`.
  - Execute `results = model(frame, conf=0.4, verbose=False)` inside `with _yolo_lock:`.
  - Iterate boxes: count if `label in TARGET_CLASSES`.
  - Return `{"density": density, "ambulance": False, "emergency": False, "emergency_type": "none"}`.

### 4.3 `ambdet.py`
Key architecture:
- Module-level `_yolo_model = None`, `_yolo_lock = threading.Lock()`, `_warned_missing_api_key = False`.
- `_get_yolo_model()`: Lazy loads `config["ambulance_model"]` (`"Model/best.pt"`) under `_yolo_lock`.
- `ambulance_detect(frame)`:
  - Runs `model(frame, conf=0.45, verbose=False)` inside `with _yolo_lock:`.
  - Returns `True` if `'ambulance'` in box labels, else `False`.
- `_stitch_lanes(lane_pairs)`:
  - Takes up to `vision_stitch_limit` pairs of `(lane_id, frame)` where `frame is not None`.
  - Resizes each to `(480, 360)`.
  - Draws solid black header bar: `cv2.rectangle(resized, (0, 0), (480, 32), (0, 0, 0), -1)`.
  - Draws text: `cv2.putText(resized, f"LANE {lane_id}", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)`.
  - Returns `cv2.hconcat(processed_frames)`.
- `_call_gemini_vision(stitched_bgr, lane_ids, model_name)`:
  - Reads `os.environ.get("GEMINI_API_KEY")`. Raises `RuntimeError` if missing.
  - Encodes to JPEG base64.
  - Constructs REST payload with prompt, base64 image, and generationConfig `{"responseMimeType": "application/json", "temperature": 0.0}`.
  - Sends POST request via `urllib.request.urlopen(req, timeout=4)`.
  - Parses JSON response, maps only requested `lane_ids` (defaulting missing to `"none"`), normalizes labels with `str(val).strip().lower().replace(" ", "")`, and enforces strict allowlist `{"ambulance", "firetruck", "none"}`.
- `detect_emergencies_batch(frames_dict)`:
  - Reads `config.json`.
  - Slices valid frames into chunks of size `vision_stitch_limit`.
  - If `emergency_detector == "vision"` and API key present: stitches and calls Gemini.
  - On missing API key: displays one-time console warning and falls back to `ambulance_detect(f)`.
  - On any exception in vision call: falls back to `ambulance_detect(f)` for that chunk.
  - Maps results to `{lane_id: {"ambulance": is_emerg, "emergency": is_emerg, "emergency_type": etype}}` where `is_emerg = etype in ("ambulance", "firetruck")`.

### 4.4 `cvfile.py`
Key architecture:
- Loads `frame_skip` from `config.json` (fallback to 5).
- `Cameraf.__init__(self, lane_no, source)`:
  - `self.last_frame = None`
  - `self._lock = threading.Lock()`
  - `self.frame_skip = frame_skip`
  - `self.vid = cv.VideoCapture(source)`
- `Cameraf.read_frame(self)`:
  - Wrapped in `with self._lock:`.
  - Auto-loops on EOF: `if not ret: self.vid.set(cv.CAP_PROP_POS_FRAMES, 0); ret, frame = self.vid.read()`.
  - Stores and returns `self.last_frame = frame`.
- `Cameraf.cvfun(self)`:
  - Wrapped in `with self._lock:`.
  - Grabs `self.frame_skip` frames, retrieves (or rewinds to 0 on EOF).
  - Updates `self.last_frame`.
  - Runs `uamodel(frame)`, checks `ambulance_detect(frame)` for single-lane fallback.
- `Cameraf.releasevid(self)`:
  - Wrapped in `with self._lock:`.
- `scan_all_lanes(cameras, live=False)`:
  - Iterates over cameras (dict or list).
  - If `live=True`: uses `cam.last_frame.copy()` if available, else `cam.read_frame()`.
  - If `live=False`: calls `cam.read_frame()`.
  - Null-frame guard: if `frame is None`, assigns zero-density schema and excludes from emergency batch.
  - Calls `uamodel(frame)` on valid frames.
  - Calls `detect_emergencies_batch(valid_frames)` to populate emergency status.
  - Returns `(lane_data, frames)`.

---

## 5. Caveats

1. **Polygon ROI Points**:
   Per requirements R1 and R2, Polygon ROI selection is intentionally deferred for this pass (`"roi_points": {}` remains unchanged). Full frames are passed to inference.
2. **Local YOLO Model Scope**:
   `Model/best.pt` only detects `'ambulance'`, not `'firetruck'`. Firetruck detection is exclusively supported through Gemini Vision (or manual input). When in local fallback mode, any emergency detected by YOLO is marked as `'ambulance'`.
3. **External Network and API Keys in Testing**:
   Automated unit and integration testing must run in CI/offline environments without real network access or Gemini API keys. All network calls (`urllib.request.urlopen`) and heavy YOLO model loads must be verified with `unittest.mock`.

---

## 6. Conclusion

The Agent 1 subsystem can be implemented with full backward compatibility, robust thread safety, and zero additional pip dependencies. The proposed design:
1. Fixes `config.json` defaults and schema.
2. Eliminates race conditions across Ultralytics and OpenCV via `_yolo_lock` and `Cameraf._lock`.
3. Implements the 2-lane stitcher and Gemini Vision client with robust fallback to local YOLO.
4. Provides `scan_all_lanes` matching the exact shared data contract required by Agent 2 (`control.py`) and Agent 3 (`main.py`, `gui.py`).

---

## 7. Verification Method

### 7.1 Automated Mock Tests
Verification can be executed via `python -m unittest` with mocked dependencies:
1. **Config Verification**: Load `config.json` and assert all required keys and types exist (`green_options`, `default_green`, `yellow_time`, `frame_skip`, `vehicle_model`, `ambulance_model`, `emergency_detector == "vision"`, `gemini_model == "gemini-2.5-flash"`, `vision_stitch_limit == 2`, `emergency_priority`, `roi_points`).
2. **Thread-Safe Vehicle Counting (`uafile.py`)**:
   - Mock `ultralytics.YOLO`.
   - Pass fake frame with detected boxes for `car`, `motorcycle`, `bus`, `truck`, and ignored class (e.g. `person`).
   - Verify `density == 4`.
   - Verify return dict matches `{"density": 4, "ambulance": False, "emergency": False, "emergency_type": "none"}`.
   - Verify `_yolo_lock` was acquired during inference.
3. **Stitching & Allowlist Normalization (`ambdet.py`)**:
   - Test `_stitch_lanes`: Pass two dummy frames `(360, 480, 3)`. Verify output shape is `(360, 960, 3)`.
   - Test `_call_gemini_vision`: Mock `urllib.request.urlopen`. Return JSON response `{"0": "ambulance", "1": "FIRE TRUCK ", "2": "unknown_vehicle"}`.
   - Verify output mapping: `{0: "ambulance", 1: "firetruck", 2: "none"}`.
   - Verify `detect_emergencies_batch`: Mock failure in `_call_gemini_vision`, assert that `ambulance_detect` is called as fallback for all lanes.
   - Verify missing `GEMINI_API_KEY`: Ensure one-time console warning is emitted and local YOLO is called.
4. **VideoCapture Locking & Scan Backend (`cvfile.py`)**:
   - Mock `cv.VideoCapture`.
   - Test `read_frame()` with EOF: Mock first `read()` returning `(False, None)`, verify `set(CAP_PROP_POS_FRAMES, 0)` is called, followed by second `read()`.
   - Test `scan_all_lanes(cameras, live=True)` vs `scan_all_lanes(cameras, live=False)`.
   - Test Null-Frame Guard: Pass a camera returning `None`. Verify density is 0, emergency is False, and stitcher is not passed `None`.
   - Verify return schema is `(lane_data, frames)` where `lane_data` has `density`, `ambulance`, `emergency`, `emergency_type`.

### 7.2 Workspace Cleanup Verification
Ensure that any test script created (e.g. `test_temp_agent1.py` or `tests/`) is removed immediately after execution so the workspace stays clean.
