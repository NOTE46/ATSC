## 2026-11-01T02:41:14Z
You are Worker M2 (teamwork_worker).
Your working directory is: c:\python_code\ATSC\.agents\teamwork\worker_m2_1\
Read c:\python_code\ATSC\.agents\teamwork\ORIGINAL_REQUEST.md before starting work.
Read c:\python_code\ATSC\PROJECT.md and c:\python_code\ATSC\.agents\teamwork\teamwork_explorer_survey_2\handoff.md for architecture, contracts, and implementation blueprints.

DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Strict File Ownership:
You ONLY edit:
- c:\python_code\ATSC\control.py
- c:\python_code\ATSC\manual_io.py
You MUST NOT edit any other application source files!

Requirements to Implement:
1. control.py:
   - Replace stateless greedy loop with a 3-tier priority + anti-starvation queue while preserving controlfun(data, lanes) signature and return format {"lane_no": int, "signal": "Green"}.
   - Maintain module-level state _wait_counts = {} and _last_lane = None. Add thread safety lock _control_lock = threading.Lock() around state modifications.
   - Implement reset_control() to clear _wait_counts and reset _last_lane = None.
   - Helper _load_priorities() reading "emergency_priority" from config.json (fallback {"ambulance": 2, "firetruck": 1, "none": 0}).
   - controlfun(data, lanes) decision logic:
     - Tier 1 (Emergency Override): Lanes with priority > 0; winner selected by highest (lane_prio, density, wait_count).
     - Tier 2 (Anti-Starvation Queue): When no emergency, apply cooldown (_last_lane excluded if other lanes have density > 0); starving lanes with _wait_counts[i] >= lanes and density > 0 selected by highest (_wait_counts[i], density).
     - Tier 3 (Weighted Density Score): Winner selected by highest (density + (_wait_counts[i] * 3), _wait_counts[i]). If all densities are 0 and _last_lane is not None, rotate to (_last_lane + 1) % lanes.
     - Counter updates: reset winner wait count to 0, record _last_lane = winner, and increment _wait_counts[i] += 1 for all other lanes with density > 0.
2. manual_io.py:
   - Update minput(lanes) to prompt for vehicle count (density >= 0) and emergency vehicle (0 = None, 1 = Ambulance, 2 = Firetruck, > 2 = Ambulance).
   - Populate data[i] with "density", "ambulance", "emergency", and "emergency_type".
   - Call controlfun(data, lanes) and display selected lane and signal.

Verification:
Write a temporary test script (e.g. tests/test_m2.py or test_temp_m2.py) using unittest.mock to thoroughly verify:
- Tier 1 priority override (ambulance 2 > firetruck 1 > none 0, tie-breaking by density and wait_count)
- Tier 2 active-lane cooldown and anti-starvation queueing (_wait_counts >= lanes with traffic)
- Tier 3 weighted density scoring (density + wait*3) and zero-traffic fair rotation
- reset_control() clearing internal state
- manual_io.minput prompt parsing, schema completeness, and controlfun invocation
Execute the tests, document results in your handoff.md, and DELETE all temporary test files/folders after testing so the repository stays clean.

Deliverable:
Write your completion report to c:\python_code\ATSC\.agents\teamwork\worker_m2_1\handoff.md and report back with send_message.
