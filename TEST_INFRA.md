# E2E Test Infra: Automated Traffic Signal Controller (ATSC)

## Test Philosophy
- Opaque-box, requirement-driven testing based strictly on `ORIGINAL_REQUEST.md`.
- No live hardware or GPU required: all tests utilize Python `unittest` and `unittest.mock` to mock OpenCV VideoCapture, Ultralytics YOLO models, and Gemini Vision network requests.
- Clean Workspace: Test scripts run in a temporary test directory (`tests/` or `test_temp.py`) and are automatically deleted upon test completion, leaving the repository completely clean.
- Methodology: Category-Partition, Boundary Value Analysis (BVA), Pairwise Combinatorial Testing, and Real-World Traffic Workload Testing.

## Feature Inventory & Test Mapping
| # | Feature | Requirement Source | Tier 1 (Unit/Isolation) | Tier 2 (Boundary/Edge) | Tier 3 (Cross-Module) |
|---|---------|-------------------|:-----------------------:|:----------------------:|:---------------------:|
| 1 | Config Schema & Validation | R1, R2 | 5 tests | 5 tests | ✓ |
| 2 | Vehicle Density Counting (uafile) | R2 | 5 tests | 5 tests | ✓ |
| 3 | Stitching & Gemini Vision Client (ambdet) | R2 | 5 tests | 5 tests | ✓ |
| 4 | Batch Emergency Detection & Fallback (ambdet) | R2 | 5 tests | 5 tests | ✓ |
| 5 | VideoCapture Thread Safety & EOF Looping (cvfile) | R2 | 5 tests | 5 tests | ✓ |
| 6 | Multi-Lane Scan Engine (cvfile) | R1, R2 | 5 tests | 5 tests | ✓ |
| 7 | 3-Tier Priority Controller (control) | R3 | 5 tests | 5 tests | ✓ |
| 8 | Anti-Starvation Queueing & Cooldown (control) | R3 | 5 tests | 5 tests | ✓ |
| 9 | Manual CLI Input & Contract Schema (manual_io) | R3 | 5 tests | 5 tests | ✓ |
| 10 | CLI Countdown Timer Engine (main) | R4 | 5 tests | 5 tests | ✓ |
| 11 | GUI Countdown & Video Decoupling (gui) | R4 | 5 tests | 5 tests | ✓ |
| 12 | GUI Slow-Scan Hold & Yellow Freeze Prevention (gui) | R4 | 5 tests | 5 tests | ✓ |

## Test Architecture
- **Runner**: `python -m unittest discover -s tests -p "test_*.py"` or running test suites programmatically.
- **Mocks**:
  - `cv2.VideoCapture`: mock frame reading, grab, retrieve, and EOF looping.
  - `ultralytics.YOLO`: mock inference results returning boxes with labels and confidence.
  - `urllib.request.urlopen`: mock HTTP responses for Gemini Vision API.
  - `tkinter`: headless/mock Tkinter widgets for GUI verification.
- **Directory Layout**:
  - `c:\python_code\ATSC\tests\test_tier1_features.py`
  - `c:\python_code\ATSC\tests\test_tier2_boundaries.py`
  - `c:\python_code\ATSC\tests\test_tier3_combinations.py`
  - `c:\python_code\ATSC\tests\test_tier4_workloads.py`

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | High-Traffic Ambulance Rush Hour | Multi-lane scan + Tier 1 Ambulance Override + Countdown switch | High |
| 2 | Firetruck vs Ambulance Dual Emergency | Priority tie-breaking (Ambulance 2 > Firetruck 1) + Wait-count update | High |
| 3 | Heavy Congestion Starvation Scenario | Dominant lane vs Starving lane + Cooldown + Tier 2 preemption | High |
| 4 | Network Outage & Missing API Key | Gemini failure/timeout -> Local YOLO fallback -> Clean controller arbitration | High |
| 5 | Slow Scan Yellow Light Hold & Recovery | Background scan latency > yellow_time -> Hold on YELLOW (0s) -> Switch cleanly | High |
| 6 | Manual Mode Dialog Close & Cycle | Mode 2 startup prompt -> WM_DELETE_WINDOW close -> Yellow cycle repeat | Medium |

## Coverage Thresholds
- Tier 1: ≥5 test cases per feature area (≥60 tests total)
- Tier 2: ≥5 boundary/edge test cases per feature area (≥60 tests total)
- Tier 3: Pairwise coverage of module interactions (≥15 interaction tests)
- Tier 4: ≥6 realistic end-to-end application scenarios
- Tier 5 (Adversarial): Challenger-generated stress tests and coverage hardening
