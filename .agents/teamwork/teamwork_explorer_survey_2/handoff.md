# Agent 2 Domain Survey Report: Emergency Priority & Anti-Starvation Controller

**Survey Agent**: Survey Explorer 2 (`teamwork_explorer_survey_2`)  
**Target Files**: `control.py`, `manual_io.py`  
**Related Files**: `config.json`, `main.py`, `gui.py`, `cvfile.py`  
**Timestamp**: 2026-11-01T02:35:00Z  

---

## 1. Observation

### 1.1 Existing Implementation: `control.py`
The existing `c:\python_code\ATSC\control.py` contains 18 lines:
```python
def controlfun(data,lanes):

    maxi=0
    dlane=0
    for i in range(lanes):
        
        if(data[i]["ambulance"]):
            return {
                "lane_no":i,
                "signal":"Green" 
            }
        elif(maxi<data[i]["density"]):
            maxi = data[i]["density"]
            dlane=i
    return {
         "lane_no":dlane,
         "signal":"Green" 
        }
```

#### Key Observations in `control.py`:
1. **Stateless Greedy Logic**: The controller does not track any historical state between calls. There is no `_wait_counts` dictionary and no `_last_lane` tracking.
2. **Missing `reset_control()`**: Required by R1 (`control.reset_control()` resets internal wait-count and last-lane state when a session restarts) and called by `main.py` and `gui.py` during session initialization. It currently does not exist.
3. **No Multi-Tier Priority**:
   - It only evaluates `data[i]["ambulance"]` as a boolean.
   - It terminates immediately on the *first* lane where `data[i]["ambulance"]` is True (lines 7-11), ignoring subsequent lanes that might also have an ambulance or higher density.
   - It has no concept of fire trucks, emergency priority weights, or reading `emergency_priority` from `config.json`.
4. **No Starvation Prevention / Cooldown**:
   - If one lane continuously has the highest density, that lane is selected indefinitely (`dlane = i`). Low-density lanes will starve indefinitely.
   - There is no active-lane cooldown.
   - If all lanes have density 0, it always returns `lane_no: 0`, failing to rotate traffic fairly.
5. **Data Structure Dependency**:
   - Accesses `data[i]["ambulance"]` and `data[i]["density"]` directly using integer keys `i`. If `i` is missing or keys are strings, it raises `KeyError`.

---

### 1.2 Existing Implementation: `manual_io.py`
The existing `c:\python_code\ATSC\manual_io.py` contains 42 lines:
```python
from control import controlfun

def minput(lanes):
    
    data={}
    print(f"Number of lanes:{lanes}")

    try:

        for i in range(lanes):
            data[i]={"density":0,"ambulance":False}

            while True:
                data[i]["density"]=int(input(f"Enter no of vehicles in lane {i+1}:"))
                if data[i]["density"] < 0:
                    print("Incorrect input (Enter positive value)")
                    continue
                break
            while True:
                amb=int(input(f"Enter no of ambulance (0 if none):"))
                if amb < 0:
                    print("Invalid (Enter positive value)")
                    continue
                elif amb==0:
                    data[i]["ambulance"]=False
                else:
                    data[i]["ambulance"]=True
                break
            
    except Exception as e:
        print(f"{e}, Program Terminated")
        return

    result=controlfun(data,lanes)

    print(f"Lane no:{result['lane_no']+1}\nSignal:{result['signal']}")
```

#### Key Observations in `manual_io.py`:
1. **Emergency Prompt Limitation**:
   - Lines 20-28 only ask for `no of ambulance (0 if none)`.
   - R3 requires: prompt for emergency vehicle (`0 = None`, `1 = Ambulance`, `2 = Firetruck`, `> 2 = Ambulance`).
2. **Incomplete Schema Population**:
   - Only populates `data[i]["density"]` and `data[i]["ambulance"]`.
   - Lacks `"emergency"` (bool) and `"emergency_type"` (str: `"ambulance"`, `"firetruck"`, or `"none"`), violating the shared data contract in R1.
3. **Execution Flow**:
   - Reads inputs per lane, populates `data`, invokes `controlfun(data, lanes)`, and prints `Lane no: {result['lane_no']+1}` and `Signal: {result['signal']}`.

---

### 1.3 Callers & Dependencies across Repository
- **`config.json`**:
  ```json
  "emergency_priority": {
    "ambulance": 2,
    "firetruck": 1,
    "none": 0
  }
  ```
- **`main.py`**:
  - Line 2: `from control import controlfun`
  - Line 4: `from manual_io import minput`
  - Line 47: `minput(lanes)` in mode 2 (manual mode).
  - Line 64: `results = controlfun(lane_data, lanes)` in main execution loop.
  - R4 Requirement: `main.py` will call `reset_control()` at session startup.
- **`gui.py`**:
  - Line 9: `from control import controlfun`
  - Line 408: `result = controlfun(data, self.lanes)` in `_run_manual(self, data)`.
  - Line 467: `result = controlfun(lane_data, self.lanes)` in `_run_loop(self)`.
  - R4 Requirement: `gui.py` will call `reset_control()` in `_init_cameras`.
- **Shared Data Contract (R1)**:
  - Input `lane_data = {i: {"density": int, "ambulance": bool, "emergency": bool, "emergency_type": str}}`.
  - Output: `{"lane_no": int, "signal": "Green"}` where `lane_no` is 0-indexed integer (`0 <= lane_no < lanes`).

---

## 2. Logic Chain

### 2.1 State Management & Reset Lifecycle
- **State Variables**:
  - Module-level `_wait_counts = {}` maps lane index `int` to wait counter `int >= 0`.
  - Module-level `_last_lane = None` tracks the integer index of the lane that received the green signal in the previous cycle (`None` before the first cycle or after reset).
- **Reset Functionality**:
  - `reset_control()` resets `_wait_counts.clear()` (or `_wait_counts = {}`) and `_last_lane = None`.
  - Must use `global _wait_counts, _last_lane`.

### 2.2 Priority Configuration Loading
- Helper `_load_priorities()` reads `"emergency_priority"` from `config.json`.
- Location resolved robustly via `Path(__file__).resolve().parent / "config.json"`.
- Default fallback if file is missing, invalid JSON, or missing key:
  `{"ambulance": 2, "firetruck": 1, "none": 0}`.
- Lane priority resolution for lane `i`:
  - If `emergency_type` is present in `lane_info`: normalize `etype = str(lane_info["emergency_type"]).strip().lower()`. If `etype in priorities and etype != "none"`, prio = `priorities[etype]`.
  - Backward-compatibility fallback: if `etype == "none"` or missing, but `lane_info.get("ambulance")` is True, prio = `priorities.get("ambulance", 2)`.
  - If neither, prio = `priorities.get("none", 0)`.

### 2.3 3-Tier Decision Engine Architecture
```
                   ┌────────────────────────────────────────┐
                   │    controlfun(data, lanes) invoked     │
                   └───────────────────┬────────────────────┘
                                       │
                                       ▼
                       Does any lane have lane_prio > 0?
                                  /         \
                            YES  /           \  NO
                                ▼             ▼
     ┌────────────────────────────┐    ┌──────────────────────────────────┐
     │ TIER 1: EMERGENCY OVERRIDE │    │   Does any candidate lane have   │
     │ Winner: highest            │    │ wait_count >= lanes & density >0?│
     │ (lane_prio, density, wait) │    │ (cooldown: exclude _last_lane    │
     └─────────────┬──────────────┘    │  if other lanes have traffic)    │
                   │                   └──────────────┬───────────────────┘
                   │                             /         \
                   │                       YES  /           \  NO
                   │                           ▼             ▼
                   │               ┌──────────────────────┐  ┌─────────────────────────┐
                   │               │ TIER 2: ANTI-        │  │ TIER 3: WEIGHTED        │
                   │               │ STARVATION QUEUE     │  │ DENSITY SCORE           │
                   │               │ Winner: highest      │  │ If all densities == 0:  │
                   │               │ (wait_count, density)│  │   rotate (_last+1)%lanes│
                   │               └──────────┬───────────┘  │ Else: highest           │
                   │                          │              │ (density+wait*3, wait)  │
                   │                          │              └────────────┬────────────┘
                   │                          │                           │
                   ▼                          ▼                           ▼
     ┌─────────────────────────────────────────────────────────────────────────────────┐
     │ COUNTER & STATE UPDATE LIFECYCLE:                                               │
     │ 1. Winner wait count set to 0: _wait_counts[winner] = 0                         │
     │ 2. _last_lane recorded as winner: _last_lane = winner                           │
     │ 3. All other lanes i != winner with density > 0 incremented: _wait_counts[i]+=1 │
     │ 4. Return: {"lane_no": winner, "signal": "Green"}                               │
     └─────────────────────────────────────────────────────────────────────────────────┘
```

#### Tier 1: Emergency Override
- Triggers when `any(lane_prio[i] > 0 for i in range(lanes))`.
- Candidates: all lanes with `lane_prio[i] > 0`.
- Selection key: `(lane_prio[i], density[i], wait_counts[i])`.
- Tie-breaker: lowest lane index `-i` (or first encountered in `0..lanes-1`).
- Emergency vehicles bypass active-lane cooldown.

#### Tier 2: Anti-Starvation Queue
- Triggers when no emergency exists.
- Active-lane Cooldown:
  - If `_last_lane is not None` and `any(density[j] > 0 for j in range(lanes) if j != _last_lane)`:
    `_last_lane` is excluded from candidate consideration.
- Starving lanes condition:
  - Eligible candidate lane `i` where `_wait_counts[i] >= lanes` and `density[i] > 0`.
- Selection key: `(_wait_counts[i], density[i])`.
- Tie-breaker: lowest lane index `-i`.

#### Tier 3: Weighted Density Score
- Triggers when no emergency and no starving lanes.
- Zero Traffic Case:
  - If `all(density[i] == 0 for i in range(lanes))`:
    - If `_last_lane is not None`: winner is `(_last_lane + 1) % lanes`.
    - If `_last_lane is None`: winner is `0`.
- Normal Case (traffic exists):
  - Candidates: eligible lanes (applying active-lane cooldown if other lanes have traffic).
  - Score formula: `score = density[i] + (_wait_counts[i] * 3)`.
  - Selection key: `(score, _wait_counts[i])`.
  - Tie-breaker: lowest lane index `-i`.

#### Counter & State Updates
- Winner wait count reset: `_wait_counts[winner] = 0`.
- Last lane recorded: `_last_lane = winner`.
- Waiting lane increments: For each `i in range(lanes)` where `i != winner`:
  - If `density[i] > 0`: `_wait_counts[i] += 1`.
  - If `density[i] == 0`: `_wait_counts[i]` remains unchanged (does NOT increment).

---

### 2.4 `manual_io.py` Protocol and Contract Compliance
1. Prompt for vehicle count:
   - Accept integer `density >= 0`. Re-prompt on `< 0` or invalid integer.
2. Prompt for emergency vehicle:
   - Accept integer code:
     - `0`: None -> `ambulance = False, emergency = False, emergency_type = "none"`
     - `1`: Ambulance -> `ambulance = True, emergency = True, emergency_type = "ambulance"`
     - `2`: Firetruck -> `ambulance = False, emergency = True, emergency_type = "firetruck"`
     - `> 2`: Ambulance -> `ambulance = True, emergency = True, emergency_type = "ambulance"`
     - `< 0`: Invalid, print warning and re-prompt.
3. Construct `data[i]`:
   ```python
   data[i] = {
       "density": density,
       "ambulance": ambulance,
       "emergency": emergency,
       "emergency_type": emergency_type
   }
   ```
4. Invoke `result = controlfun(data, lanes)`.
5. Display output:
   `print(f"Lane no:{result['lane_no']+1}\nSignal:{result['signal']}")`.

---

## 3. Caveats

1. **Cooldown Scope Across Tiers**:
   - In R3, cooldown is described under Tier 2:
     `Tier 2 (Anti-Starvation Queue): When no emergency, apply cooldown (_last_lane excluded if other lanes have density > 0); starving lanes with _wait_counts[i] >= lanes and density > 0 selected by highest (_wait_counts[i], density).`
   - If cooldown is applied to the candidate pool for all non-emergency selections (both Tier 2 and Tier 3), `_last_lane` cannot repeat immediately when other lanes have waiting traffic. This aligns with Acceptance Criterion line 132 (`control.controlfun enforces active-lane cooldown and prioritizes starving lanes`).
   - If other lanes have NO traffic (`density == 0`), `_last_lane` is NOT excluded, allowing the same lane to proceed if only it has traffic.
   - If ALL lanes have 0 traffic, zero-traffic rotation `(_last_lane + 1) % lanes` triggers.
2. **Missing Keys and Legacy Inputs**:
   - `data` might be passed with string keys (e.g., `data["0"]`) or missing fields. The implementation should safely inspect `data.get(i) or data.get(str(i), {})` and provide fallback defaults (`density=0, ambulance=False, emergency=False, emergency_type="none"`).
3. **Thread Safety**:
   - Because `controlfun` is called from background scan threads in `main.py` and `gui.py`, modifying module-level `_wait_counts` and `_last_lane` should be protected by a `threading.Lock()` (`_control_lock = threading.Lock()`) to prevent race conditions during state updates.
4. **Lane Index Offsets**:
   - `controlfun` must return 0-indexed integer `result["lane_no"]` (e.g. `0, 1, 2, ...`).
   - `manual_io.py` displays 1-indexed lane numbers to the user: `result["lane_no"] + 1`. This preserves compatibility with CLI expectations.

---

## 4. Conclusion & Implementation Recommendations

Agent 2's domain (`control.py` and `manual_io.py`) is completely decoupled from heavy dependencies (no OpenCV, YOLO, or Tkinter). The current code is minimal and requires an upgrade to support the 3-tier priority structure, anti-starvation queueing, and contract-compliant manual input.

### 4.1 Proposed Implementation: `control.py`

```python
import json
import threading
from pathlib import Path

# Module-level state tracking
_wait_counts = {}
_last_lane = None
_control_lock = threading.Lock()


def _load_priorities():
    """Read emergency_priority from config.json with fallback."""
    cfg_path = Path(__file__).resolve().parent / "config.json"
    default_prio = {"ambulance": 2, "firetruck": 1, "none": 0}
    if not cfg_path.exists():
        return default_prio
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("emergency_priority", default_prio)
    except Exception:
        return default_prio


def reset_control():
    """Reset wait counts and last active lane."""
    global _wait_counts, _last_lane
    with _control_lock:
        _wait_counts.clear()
        _last_lane = None


def controlfun(data, lanes):
    """
    Select active green lane using 3-tier priority controller:
    - Tier 1: Emergency Override (ambulance > firetruck > none)
    - Tier 2: Anti-Starvation Queue (cooldown & wait_counts >= lanes)
    - Tier 3: Weighted Density Score (density + wait*3 or rotation)
    """
    global _wait_counts, _last_lane

    with _control_lock:
        # Ensure all lanes exist in _wait_counts
        for i in range(lanes):
            if i not in _wait_counts:
                _wait_counts[i] = 0

        priorities = _load_priorities()

        # Extract normalized lane attributes
        densities = {}
        lane_prios = {}

        for i in range(lanes):
            lane_info = data.get(i)
            if lane_info is None and str(i) in data:
                lane_info = data[str(i)]
            if not isinstance(lane_info, dict):
                lane_info = {}

            densities[i] = int(lane_info.get("density", 0))

            # Determine emergency priority
            etype = str(lane_info.get("emergency_type", "")).strip().lower()
            if etype in priorities and etype != "none":
                lane_prios[i] = priorities[etype]
            elif lane_info.get("ambulance"):
                lane_prios[i] = priorities.get("ambulance", 2)
            elif lane_info.get("emergency"):
                lane_prios[i] = priorities.get("ambulance", 2)
            elif etype == "none":
                lane_prios[i] = priorities.get("none", 0)
            else:
                lane_prios[i] = 0

        winner = None

        # Tier 1: Emergency Override
        emergency_lanes = [i for i in range(lanes) if lane_prios[i] > 0]
        if emergency_lanes:
            # Winner selected by highest (lane_prio, density, wait_count)
            # Tie-breaker: lowest lane index (-i)
            winner = max(
                emergency_lanes,
                key=lambda i: (lane_prios[i], densities[i], _wait_counts.get(i, 0), -i)
            )

        # Tier 2 & Tier 3: Non-Emergency
        if winner is None:
            # Check if other lanes have traffic
            other_traffic = any(
                densities[j] > 0 for j in range(lanes) if j != _last_lane
            )

            # Apply cooldown: _last_lane excluded if other lanes have density > 0
            if _last_lane is not None and other_traffic:
                candidate_lanes = [i for i in range(lanes) if i != _last_lane]
            else:
                candidate_lanes = list(range(lanes))

            # Tier 2: Anti-Starvation Queue
            starving_lanes = [
                i for i in candidate_lanes
                if _wait_counts.get(i, 0) >= lanes and densities[i] > 0
            ]
            if starving_lanes:
                # Winner selected by highest (wait_count, density)
                winner = max(
                    starving_lanes,
                    key=lambda i: (_wait_counts.get(i, 0), densities[i], -i)
                )

        # Tier 3: Weighted Density Score
        if winner is None:
            all_zero = all(densities[i] == 0 for i in range(lanes))
            if all_zero:
                if _last_lane is not None:
                    winner = (_last_lane + 1) % lanes
                else:
                    winner = 0
            else:
                # Winner selected by highest (density + wait * 3, wait)
                winner = max(
                    candidate_lanes,
                    key=lambda i: (
                        densities[i] + (_wait_counts.get(i, 0) * 3),
                        _wait_counts.get(i, 0),
                        -i
                    )
                )

        # Counter Updates
        _wait_counts[winner] = 0
        _last_lane = winner
        for i in range(lanes):
            if i != winner and densities[i] > 0:
                _wait_counts[i] = _wait_counts.get(i, 0) + 1

        return {
            "lane_no": winner,
            "signal": "Green"
        }
```

---

### 4.2 Proposed Implementation: `manual_io.py`

```python
from control import controlfun


def minput(lanes):
    """
    Prompt for vehicle count and emergency vehicle per lane,
    invoke controlfun, and display the selected green lane.
    """
    data = {}
    print(f"Number of lanes: {lanes}")

    try:
        for i in range(lanes):
            # Prompt for vehicle density
            while True:
                try:
                    val = int(input(f"Enter no of vehicles in lane {i + 1}: "))
                    if val < 0:
                        print("Incorrect input (Enter positive value)")
                        continue
                    density = val
                    break
                except ValueError:
                    print("Invalid input (Enter an integer)")

            # Prompt for emergency vehicle
            while True:
                try:
                    prompt = (
                        f"Enter emergency vehicle in lane {i + 1} "
                        "(0=None, 1=Ambulance, 2=Firetruck, >2=Ambulance): "
                    )
                    ev = int(input(prompt))
                    if ev < 0:
                        print("Invalid (Enter positive value)")
                        continue
                    if ev == 0:
                        ambulance = False
                        emergency = False
                        emergency_type = "none"
                    elif ev == 2:
                        ambulance = False
                        emergency = True
                        emergency_type = "firetruck"
                    else:  # ev == 1 or ev > 2
                        ambulance = True
                        emergency = True
                        emergency_type = "ambulance"
                    break
                except ValueError:
                    print("Invalid input (Enter an integer)")

            data[i] = {
                "density": density,
                "ambulance": ambulance,
                "emergency": emergency,
                "emergency_type": emergency_type,
            }

    except Exception as e:
        print(f"{e}, Program Terminated")
        return

    result = controlfun(data, lanes)
    print(f"Lane no:{result['lane_no'] + 1}\nSignal:{result['signal']}")
```

---

## 5. Verification Method

To independently verify Agent 2's implementation when constructed:

### 5.1 Verification Test Cases
Create a temporary test script (e.g. `tests/test_control_manual.py`) and run via standard library `unittest`:

1. **`test_emergency_override`**:
   - Lane 0: density=20, emergency_type="none".
   - Lane 1: density=2, emergency_type="ambulance".
   - Winner must be Lane 1 (`lane_no: 1`).
2. **`test_ambulance_over_firetruck`**:
   - Lane 0: emergency_type="firetruck" (prio 1).
   - Lane 1: emergency_type="ambulance" (prio 2).
   - Winner must be Lane 1 (`lane_no: 1`).
3. **`test_emergency_tie_breaker`**:
   - Lane 0: prio 2, density 5, wait 0.
   - Lane 1: prio 2, density 10, wait 0.
   - Winner must be Lane 1 (`lane_no: 1` due to higher density).
4. **`test_active_lane_cooldown`**:
   - Initial run selects Lane 0 (`_last_lane = 0`).
   - Next run: Lane 0 has density 10, Lane 1 has density 2.
   - Cooldown excludes Lane 0; winner must be Lane 1.
5. **`test_anti_starvation_queue`**:
   - Lane 0 has density 50, wait_count 0.
   - Lane 1 has density 5, wait_count 4 (where lanes = 3, so `wait_count >= lanes`).
   - Winner must be Lane 1 (starvation override).
6. **`test_weighted_density`**:
   - Lane 1: density 2, wait_count 2 (score = 2 + 6 = 8).
   - Lane 2: density 6, wait_count 0 (score = 6 + 0 = 6).
   - Winner must be Lane 1.
7. **`test_zero_traffic_rotation`**:
   - Cycle 1: all densities 0, `_last_lane = None` -> winner 0.
   - Cycle 2: all densities 0, `_last_lane = 0` -> winner 1.
   - Cycle 3: all densities 0, `_last_lane = 1` -> winner 2.
8. **`test_reset_control`**:
   - Call `reset_control()`; verify `_wait_counts == {}` and `_last_lane is None`.
9. **`test_manual_minput_mocked`**:
   - Mock `builtins.input` with side effects for densities and emergency codes `[0, 1, 2, 3]`.
   - Verify `data` dict passed to `controlfun` matches the schema:
     `{"density": int, "ambulance": bool, "emergency": bool, "emergency_type": str}`.

### 5.2 Verification Commands
```powershell
python -m unittest tests/test_control_manual.py
Remove-Item -Recurse -Force tests
```

### 5.3 Invalidation Conditions
- Any change to the signature of `controlfun(data, lanes)`.
- Returning a lane number that is not 0-indexed or signal not `"Green"`.
- Modifying files outside Agent 2's strict ownership (`control.py`, `manual_io.py`).
