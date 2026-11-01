# Handoff Report: Milestone 1 (M1) — Vision & Detection Engine Overhaul

**Author**: Worker M1 (`teamwork_worker`)  
**Working Directory**: `c:\python_code\ATSC\.agents\teamwork\worker_m1_1`  
**Target Files Modified**:
- `c:\python_code\ATSC\config.json`
- `c:\python_code\ATSC\uafile.py`
- `c:\python_code\ATSC\ambdet.py`
- `c:\python_code\ATSC\cvfile.py`  
**Date**: 2026-11-01  
**Handoff Type**: Hard (Task Complete)

---

## 1. Observation

1. **Pre-existing Codebase State**:
   - `config.json` contained `"emergency_detector": "yolo"` and lacked `"gemini_model"`.
   - `uafile.py` loaded `Model/yolov8n.pt` eagerly at import time, lacked thread locking around inference (`results = model(frame)`), omitted class `'bus'` from detection, called `ambulance_detect(frame)` directly if a truck was found, and returned only `{"density": density, "ambulance": bool}`.
   - `ambdet.py` loaded `Model/best.pt` eagerly at import time without thread locks, lacked Gemini vision API client capabilities, lacked image stitching routines, and lacked batch multi-lane emergency detection.
   - `cvfile.py` hardcoded `FRAME_S = 5`, lacked mutex locking across `cv.VideoCapture` operations, did not rewind to frame 0 on EOF, lacked `last_frame` caching, and had no `scan_all_lanes` implementation.

2. **Executed Commands and Tool Results**:
   - Updated `config.json`:
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
   - Executed test suite (`test_temp_m1.py` with 20 unit and integration tests):
     ```
     Command: python -m unittest test_temp_m1.py
     Output:
     ....................
     ----------------------------------------------------------------------
     Ran 20 tests in 0.017s

     OK
     Warning: GEMINI_API_KEY environment variable not found. Falling back to local YOLO.
     ```
   - Executed live model inference on local PyTorch weights (`Model/yolov8n.pt` and `Model/best.pt`):
     ```
     Command: python -c "import numpy as np, uafile, ambdet; img = np.zeros((360, 480, 3), dtype=np.uint8); res1 = uafile.uamodel(img); print('uamodel result:', res1); res2 = ambdet.ambulance_detect(img); print('ambulance_detect result:', res2)"
     Output:
     uamodel result: {'density': 0, 'ambulance': False, 'emergency': False, 'emergency_type': 'none'}
     ambulance_detect result: False
     ```
   - Executed multi-scan warning test:
     ```
     Command: python -c "import numpy as np, cvfile; from unittest.mock import MagicMock; cam0 = MagicMock(); cam0.read_frame.return_value = np.zeros((360, 480, 3), dtype=np.uint8); cvfile.scan_all_lanes([cam0], live=False); print('First call done.'); cvfile.scan_all_lanes([cam0], live=False); print('Second call done.')"
     Output:
     Warning: GEMINI_API_KEY environment variable not found. Falling back to local YOLO.
     First call done.
     Second call done.
     ```
   - Removed temporary test file `test_temp_m1.py` and confirmed clean workspace via `git status --short`.

---

## 2. Logic Chain

1. **Configuration Correctness**:
   - `config.json` was updated to set `"emergency_detector": "vision"` and `"gemini_model": "gemini-2.5-flash"` while maintaining `"roi_points": {}` and the full schema. This allows `ambdet.py` and `control.py` to discover the active vision provider and emergency priorities dynamically.

2. **Thread Safety & Vehicle Density Counting (`uafile.py`)**:
   - Ultralytics `YOLO` C++ bindings/PyTorch backends are not thread-safe under concurrent forward passes across multiple threads (e.g. GUI rendering and background scan thread).
   - Introduced a module-level `_yolo_lock = threading.Lock()` and wrapped `model(frame, conf=0.4, verbose=False)` inside `with _yolo_lock:`.
   - Replaced vehicle counting to check `TARGET_CLASSES = {"car", "motorcycle", "truck", "bus"}` and decoupled it from `ambulance_detect`.
   - Returned contract schema: `{"density": density, "ambulance": False, "emergency": False, "emergency_type": "none"}`.

3. **Batch Emergency Detection & Cloud/Local Fallback (`ambdet.py`)**:
   - Implemented `_get_yolo_model()` with double-checked locking under `_yolo_lock` so `Model/best.pt` is only loaded into memory if local mode or fallback is triggered.
   - Wrapped `ambulance_detect(frame)` inference with `conf=0.45, verbose=False` inside `with _yolo_lock:`.
   - Implemented `_stitch_lanes(lane_pairs)` to resize valid frames to (480, 360), apply solid black header bar with white `LANE {lane_id}` text, and concatenate up to `vision_stitch_limit` (2) frames horizontally with `cv2.hconcat`.
   - Implemented `_call_gemini_vision(stitched_bgr, lane_ids, model_name)` using standard library `urllib.request`, JSON response format, `temperature: 0.0`, key filtering to requested `lane_ids`, and strict allowlist normalization (`val = str(val).strip().lower().replace(" ", "")` in `{"ambulance", "firetruck", "none"}`).
   - Implemented `detect_emergencies_batch(frames_dict)` to chunk frames by `vision_stitch_limit`, perform Gemini Vision classification, emit a one-time console warning if `GEMINI_API_KEY` is absent, and seamlessly fall back to local `ambulance_detect` on any exception or if detector is `"yolo"`.
   - Populated return dictionary with `{"ambulance": is_emerg, "emergency": is_emerg, "emergency_type": etype}` where `is_emerg = etype in ("ambulance", "firetruck")`, preserving backward compatibility for legacy callers while providing 3-tier emergency flags.

4. **VideoCapture Mutex & Multi-Lane Scanning (`cvfile.py`)**:
   - Added `self.last_frame = None` and `self._lock = threading.Lock()` to `Cameraf`.
   - Protected all `read()`, `grab()`, and `set()` operations under `with self._lock:`.
   - Implemented auto-looping on EOF via `self.vid.set(cv.CAP_PROP_POS_FRAMES, 0)` in both `read_frame()` and `cvfun()`.
   - Implemented `scan_all_lanes(cameras, live=False)`:
     - For `live=True`: accesses `cam.last_frame.copy()` (falling back to `cam.read_frame()`).
     - For `live=False`: calls `cam.read_frame()`.
     - Null-Frame Guard: if `frame is None`, defaults `lane_data` to `{"density": 0, "ambulance": False, "emergency": False, "emergency_type": "none"}` and excludes the lane from `detect_emergencies_batch`.
     - Calls `uamodel(frame)` on valid frames, invokes `detect_emergencies_batch(valid_frames)`, and returns `(lane_data, frames)`.

---

## 3. Caveats

- **API Key in Testing**: Tests mock Gemini API calls and verify the one-time warning on missing key. In production with a live key, network latency is capped at 4 seconds (`timeout=4`) before fallback.
- **Local Model Limitations**: `Model/best.pt` only detects ambulances. Firetruck detection is handled via Gemini Vision (or manual input). This is by design per the architecture specification.
- **Strict File Ownership**: Worker M1 only modified `config.json`, `uafile.py`, `ambdet.py`, and `cvfile.py`. No other files were edited.

---

## 4. Conclusion

Milestone 1 is fully implemented, verified, and strictly compliant with all requirements:
1. `config.json` contains complete schema with `emergency_detector: "vision"` and `gemini_model: "gemini-2.5-flash"`.
2. `uafile.py` provides thread-safe, decoupled vehicle counting under `_yolo_lock` returning the shared contract schema.
3. `ambdet.py` delivers lazy YOLO loading, 2-lane horizontal stitching, Gemini Vision client with allowlist normalization, one-time console warning, and local fallback.
4. `cvfile.py` provides thread-safe `Cameraf` with auto-looping on EOF and `scan_all_lanes` with live caching and Null-Frame Guard.
5. All 20 automated tests passed, live inference was verified on local model weights, and all temporary test files were cleaned up.

---

## 5. Verification Method

To independently verify the implementation:

1. **Verify Module Imports and Configuration**:
   ```powershell
   python -c "import json, uafile, ambdet, cvfile; cfg = json.load(open('config.json')); assert cfg['emergency_detector'] == 'vision'; assert cfg['gemini_model'] == 'gemini-2.5-flash'; print('Config and imports valid')"
   ```

2. **Verify Thread Safety and Return Schemas**:
   ```powershell
   python -c "import numpy as np, uafile, ambdet; img = np.zeros((360, 480, 3), dtype=np.uint8); res1 = uafile.uamodel(img); assert 'density' in res1 and 'emergency_type' in res1; res2 = ambdet.ambulance_detect(img); assert isinstance(res2, bool); print('Inference test passed')"
   ```

3. **Verify Scanner and Fallback**:
   ```powershell
   python -c "import numpy as np, cvfile; from unittest.mock import MagicMock; cam = MagicMock(); cam.read_frame.return_value = np.zeros((360, 480, 3), dtype=np.uint8); data, frames = cvfile.scan_all_lanes([cam], live=False); assert data[0]['emergency_type'] == 'none'; print('Scanner test passed')"
   ```

4. **Verify Clean Workspace**:
   ```powershell
   git status --short
   ```
   Assert that no temporary test files remain in the root or `.agents/teamwork/` directories.
