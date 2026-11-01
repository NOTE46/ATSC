## 2026-11-01T02:41:00Z
You are Worker M1 (teamwork_worker).
Your working directory is: c:\python_code\ATSC\.agents\teamwork\worker_m1_1\
Read c:\python_code\ATSC\.agents\teamwork\ORIGINAL_REQUEST.md before starting work.
Read c:\python_code\ATSC\PROJECT.md and c:\python_code\ATSC\.agents\teamwork\teamwork_explorer_survey_1\handoff.md for architecture, contracts, and implementation blueprints.

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Strict File Ownership:
You ONLY edit:
- c:\python_code\ATSC\config.json
- c:\python_code\ATSC\uafile.py
- c:\python_code\ATSC\ambdet.py
- c:\python_code\ATSC\cvfile.py
You MUST NOT edit any other application source files!

Requirements to Implement:
1. config.json:
   - Ensure valid JSON with: "green_options": [15, 30, 40, 50, 60], "default_green": 30, "yellow_time": 5, "frame_skip": 5, "vehicle_model": "Model/yolov8n.pt", "ambulance_model": "Model/best.pt", "emergency_detector": "vision", "vision_provider": "gemini", "gemini_model": "gemini-2.5-flash", "vision_stitch_limit": 2, "emergency_priority": {"ambulance": 2, "firetruck": 1, "none": 0}, and leave "roi_points": {}.
2. uafile.py:
   - Thread-safe vehicle counter uamodel(frame).
   - Load "vehicle_model" from config.json (fallback "Model/yolov8n.pt").
   - Module-level _yolo_lock = threading.Lock(). Wrap model(frame, conf=0.4, verbose=False) under this lock.
   - Count bounding boxes with class in {"car", "motorcycle", "truck", "bus"} into density.
   - Do NOT call ambulance_detect inside uafile.py.
   - Return {"density": density, "ambulance": False, "emergency": False, "emergency_type": "none"}.
3. ambdet.py:
   - Lazy-load Model/best.pt via _get_yolo_model() with threading.Lock().
   - Wrap model(frame, conf=0.45, verbose=False) under the lock.
   - Preserve ambulance_detect(frame): returns True if 'ambulance' detected, else False.
   - One-time console warning if GEMINI_API_KEY is missing before fallback to local YOLO.
   - Implement _stitch_lanes(lane_pairs): accept up to vision_stitch_limit pairs (lane_id, frame) where frame is not None, resize to (480, 360), draw solid black header bar (0, 0) to (480, 32) with white text "LANE {lane_id}", horizontally concatenate with cv2.hconcat.
   - Implement _call_gemini_vision(stitched_bgr, lane_ids, model_name): read GEMINI_API_KEY, encode JPEG base64, urllib.request.urlopen (timeout=4) with json response and temperature 0.0. Parse JSON, filter keys to int(k) in lane_ids, default missing to "none". Strict allowlist normalization {"ambulance", "firetruck", "none"}.
   - Implement detect_emergencies_batch(frames_dict): chunk by vision_stitch_limit, call _stitch_lanes and _call_gemini_vision if emergency_detector == "vision", fall back to per-lane ambulance_detect(f) on any exception or if detector == "yolo". Populate lane dict with {"ambulance": is_emerg, "emergency": is_emerg, "emergency_type": etype} where is_emerg = etype in ("ambulance", "firetruck").
4. cvfile.py:
   - Load frame_skip from config.json (default 5).
   - Cameraf.__init__(self, lane_no, source): add self.last_frame = None and self._lock = threading.Lock().
   - Wrap all self.vid.read(), grab(), set() inside with self._lock:.
   - Cameraf.read_frame(self): read, auto-loop to frame 0 via self.vid.set(cv.CAP_PROP_POS_FRAMES, 0) if EOF, store self.last_frame, return frame.
   - Cameraf.cvfun(self): grab FRAME_S frames, retrieve (or loop to 0), update self.last_frame, run uamodel(frame), check ambulance_detect(frame) for single-lane fallback.
   - Implement scan_all_lanes(cameras, live=False): live=True uses cam.last_frame.copy() (fallback cam.read_frame()), live=False calls cam.read_frame(). Null-Frame Guard: if frame is None, default lane_data to density 0 and emergency false/"none", exclude from detect_emergencies_batch. Run uamodel on valid frames, call detect_emergencies_batch, return (lane_data, frames).

Verification:
Write a temporary test script (e.g. tests/test_m1.py or test_temp_m1.py) using unittest.mock to thoroughly verify:
- config.json schema and keys
- uafile.uamodel thread safety, class counts, return schema
- ambdet lazy loading, stitcher dimensions, gemini mock call, allowlist normalization, local fallback
- cvfile.Cameraf lock, auto-looping, scan_all_lanes live/non-live, null-frame guard
Execute the tests, document results in your handoff.md, and DELETE all temporary test files/folders after testing so the repository stays clean.

Deliverable:
Write your completion report to c:\python_code\ATSC\.agents\teamwork\worker_m1_1\handoff.md and report back with send_message.
