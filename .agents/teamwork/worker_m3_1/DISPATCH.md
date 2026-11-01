## 2026-11-01T02:41:31Z
You are Worker M3 (teamwork_worker).
Your working directory is: c:\python_code\ATSC\.agents\teamwork\worker_m3_1\
Read c:\python_code\ATSC\.agents\teamwork\ORIGINAL_REQUEST.md before starting work.
Read c:\python_code\ATSC\PROJECT.md and c:\python_code\ATSC\.agents\teamwork\teamwork_explorer_survey_3\handoff.md for architecture, contracts, and implementation blueprints.

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Strict File Ownership:
You ONLY edit:
- c:\python_code\ATSC\main.py
- c:\python_code\ATSC\gui.py
You MUST NOT edit any other application source files!

Requirements to Implement:
1. main.py:
   - Load green_options, default_green, and yellow_time from config.json.
   - Prompt user for green cycle time after mode/lane selection (validating against green_options, falling back to default_green).
   - Initialize cameras, call reset_control(), and execute initial boot scan via scan_all_lanes(camera, live=False) and controlfun.
   - Main countdown loop:
     - For remaining from green_time down to 1: display GREEN status when remaining > yellow_time.
     - When remaining == yellow_time: display YELLOW status and spawn background threading.Thread calling scan_all_lanes(camera, live=False) and controlfun(new_data, lanes) to prepare next_decision.
     - Display switching countdown when remaining < yellow_time.
     - At countdown expiry (0): join scan thread (timeout=2), switch active_lane = next_decision["lane_no"], print cycle summary, and repeat.
2. gui.py:
   - Load timings from config.json.
   - Preserve existing Dashboard._log(self, msg) method on Dashboard.
   - Standardize timer expiry checks to time_left <= 0 everywhere in _tick_timer.
   - SetupScreen: Add "GREEN SIGNAL DURATION (SECONDS)" radio button group below lane count with options [15, 30, 40, 50, 60] defaulting to 30. Pass green_time into on_start with backward-compatible defaults.
   - LaneCard.set_signal(signal, density=None, ambulance=None, emergency_type=None, time_left=None): Format countdown suffix f" ({time_left}s)" for GREEN and YELLOW; show "Emergency: FIRETRUCK 🚒", "Emergency: AMBULANCE 🚨", or "Emergency: No".
   - ManualDialog: Replace checkbox with 3-option selector (None, Ambulance, Firetruck) and populate "emergency" and "emergency_type". Handle window close ("X" button): bind self.protocol("WM_DELETE_WINDOW", self._on_close) so if closed without clicking Submit, pass existing lane_data (or zero-density defaults on boot) to on_submit so Manual Mode never hangs on Yellow.
   - Dashboard:
     - Decoupled _video_loop scheduled via self.after(40, ...) updating frames smoothly using cam.read_frame() with zero YOLO inference.
     - _init_cameras: run initial boot scan, call reset_control(), set active_lane, and start loops.
     - Timer Hold on Slow Scans: When time_left <= 0, if self.scanning is still True (next_winner not ready yet), hold active lane on YELLOW (0s) and switch immediately on the first tick after the background scan completes.
     - Prevent Yellow Freeze on Scan Failure: In _bg_scan, wrap scan and controlfun in try...except Exception as e:...finally: block. On except, log self._log(f"Scan error: {e}"), set self.next_lane_data = self.lane_data, and set self.next_winner = (self.active_lane + 1) % self.lanes. In finally, ALWAYS set self.scanning = False.
     - Manual Mode (Mode 2) Cycle Integration: In Mode 2 (no cameras), open ManualDialog at startup to set initial lane_data and pick the initial GREEN lane. Automatically open ManualDialog again when time_left == yellow_time to collect next_lane_data, holding transition at YELLOW until submitted or closed.
     - Video / Camera Modes (0 & 1): background scan at time_left == yellow_time calls scan_all_lanes(self.cameras, live=True).

Verification:
Write a temporary test script (e.g. tests/test_m3.py or test_temp_m3.py) using unittest.mock to thoroughly verify:
- main.py duration prompt validation, boot scan, countdown loop, and thread scan joining
- gui.py SetupScreen green duration selector
- gui.py LaneCard timer formatting and emergency badges
- gui.py ManualDialog 3-option selector and WM_DELETE_WINDOW fallback
- gui.py Dashboard decoupled video loop, slow scan YELLOW (0s) hold, yellow freeze prevention on exception, and Mode 2 integration
Execute the tests, document results in your handoff.md, and DELETE all temporary test files/folders after testing so the repository stays clean.

Deliverable:
Write your completion report to c:\python_code\ATSC\.agents\teamwork\worker_m3_1\handoff.md and report back with send_message.
