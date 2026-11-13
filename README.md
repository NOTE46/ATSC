# ATSC: Automated Traffic Signal Controller

![tests](https://github.com/NOTE46/ATSC/actions/workflows/tests.yml/badge.svg)
![lint](https://github.com/NOTE46/ATSC/actions/workflows/lint.yml/badge.svg)
![python](https://img.shields.io/badge/python-3.13-blue)

ATSC decides which lane of an intersection gets the green light. It counts vehicles in each lane with YOLO26n, checks for ambulances and fire trucks with a vision AI (or a local model), and picks the next lane with a fair priority queue, so emergency vehicles go first and no lane waits forever.

## Features

- **Green/yellow countdown.** Pick a green time of 15, 30, 40, 50 or 60 seconds, followed by a 5-second yellow. Detection runs once per cycle, at the start of yellow, so video plays smoothly the rest of the time and the AI sits idle.
- **4-point polygon ROI per lane.** Click four corners on the video to outline the incoming lane. Everything outside the polygon is blacked out and cropped away before detection, so outgoing traffic is not counted.
- **Emergency vehicle detection with a choice of engine.**
  - Cloud vision: Gemini, Groq or OpenRouter. Two lanes are stitched into one labeled image per request, which halves the number of API calls.
  - Local YOLO: any `.pt` model in `Model/`. Drop in a new file and click **Refresh**.
  - If a cloud call fails or its key is missing, ATSC falls back to the local model.
- **3-tier controller.**
  1. Emergency override: ambulance, then fire truck. Ties are broken by vehicle count, then wait time.
  2. Anti-starvation: a lane with traffic that reaches the wait threshold (default `3` cycles; falls back to the lane count if unset) gets the next green.
  3. Weighted density: score = `density + 3 x wait_count`. The current lane cannot win twice in a row while other lanes have traffic. If every lane is empty, the signal rotates.
- **Three input modes.** Video files, live webcams, or manual numbers for testing the controller without any video.
- **Tkinter dashboard** with live 16:9 letterboxed video, per-lane countdowns, emergency badges, Dark/Light themes, an in-app Settings dialog, keyboard shortcuts (`Space` / `Esc`), and a log bar, plus a **terminal version** (`main.py`).

## How it works

```
Cameras / video files
        |
        v
cvfile.py        read frames, apply the 4-point ROI mask and crop
        |
        +--------------------------------+
        v                                v
uafile.py                          ambdet.py
YOLO26n vehicle count                stitch 2 lanes per image ->
(car, motorcycle, truck, bus)      Gemini / Groq / OpenRouter
                                   or local .pt model
        |                                |
        +---------------+----------------+
                        v
                 lane_data (shared contract)
                        |
                        v
                  control.py
          emergency > starving lane > weighted density
                        |
                        v
             gui.py / main.py: green / yellow timer
```

**Timeline of one cycle** (30s green example):

```
0s ------------- 25s ---- 30s
GREEN (AI idle)   YELLOW   next lane turns GREEN
                  scan runs here
```

At startup there is one boot scan to choose the first green lane.

**Decision log.** `control.py` appends one CSV row per controller decision (`timestamp`, `lanes`, `winner_lane`, `tier`, `densities`, `emergencies`, `wait_counts`) to `decisions.csv` next to `control.py`. The file is gitignored, capped at 1 MB, and then rotated to `decisions.csv.1` (one backup only; the older backup is overwritten). Rows record what the controller decided, and boot and manual-mode decisions are logged too.

**Shared data contract**

```python
lane_data = {
    lane_id: {
        "density": int,                # vehicles in the ROI
        "ambulance": bool,             # legacy flag, True for any emergency
        "emergency": bool,
        "emergency_type": "ambulance" | "firetruck" | "none",
    }
}
```

## Project structure

```
ATSC/
├── gui.py                Tkinter dashboard, ROI editor, setup screen, settings dialog
├── main.py               terminal version
├── cvfile.py             camera wrapper, ROI mask/crop, scan_all_lanes()
├── uafile.py             YOLO26n vehicle counter
├── ambdet.py             emergency detection (Gemini/Groq/OpenRouter/local), .env loader
├── control.py            3-tier priority and anti-starvation controller
├── manual_io.py          manual input mode (terminal)
├── config.json           timings, models, priorities, saved ROIs
├── .env.example          template for API keys
├── requirements.txt      runtime dependencies
├── requirements-dev.txt  pytest and coverage
├── Model/                yolo26n.pt (vehicle counting) + emergency .pt models
├── tests/                pytest suite (headless, everything mocked)
└── .github/workflows/    CI: tests and lint
```

## Installation

Requires Python 3.13 (3.11+ should work). Tkinter ships with Python on Windows and macOS. On Linux, install it with `sudo apt install python3-tk`.

```powershell
git clone [https://github.com/NOTE46/ATSC.git](https://github.com/NOTE46/ATSC.git)
cd ATSC
python -m venv venv
.\venv\Scripts\Activate.ps1      # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
```

**Windows CUDA (optional).** The default PyPI wheel is CPU-only on Windows. A GPU is optional and only speeds up local YOLO inference (vehicle counting and the local emergency model). After installing `requirements.txt`, Windows users with an NVIDIA GPU can install the CUDA build (`cu128`; use `cu126` or `cu130` for other CUDA versions):

```bash
pip install torch==2.11.0 --index-url [https://download.pytorch.org/whl/cu128](https://download.pytorch.org/whl/cu128) --force-reinstall --no-deps
```

Verify with:

```bash
python -c "import torch; print(torch.cuda.is_available())"
```

**Model weights.** Put these in `Model/`:

- `yolo26n.pt` for vehicle counting
- `best.pt`, or any custom `.pt` model, for local emergency detection

**API keys (optional).** Copy the template and fill in only the providers you use:

```powershell
copy .env.example .env
```

```
GEMINI_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=
```

`.env` is read at startup and is ignored by git. A real environment variable overrides the file. You can also paste session-only keys inside the GUI **Settings (`⚙`)** dialog without writing them to disk. With no key set, ATSC prints one warning and uses the local model.

> **Privacy:** cloud detection sends stitched lane images to a third party. Free tiers may log requests, and some ask you not to upload faces or personal data. Use test clips for those, not real footage of people.

## Usage

### Dashboard

```powershell
python gui.py
```

1. Choose the input mode: Live Camera, Video Files, or Manual Input.
2. Choose the number of lanes (1–4) and the green duration.
3. Choose the **Detector** (Gemini, Groq, OpenRouter, or Local YOLO) and a model. The model box is editable, so you can type any model name your provider supports.
4. Click **Settings (`⚙`)** anytime to switch between Dark and Light themes, adjust yellow duration or starvation threshold, or set a session-only API key.
5. Draw the ROI for each lane (see below), then watch the cycle run. Press `Space` to pause/resume the countdown, or `Esc` to cancel an active ROI edit or stop the controller.

**Drawing an ROI.** On first run, the first lane without a saved polygon opens in edit mode. Click four corners around the incoming lane. Use **Edit ROI** to redraw (press `Esc` to cancel), **Clear** to go back to the full frame, or **Skip ROI** to start without one. Polygons are saved in `config.json` under `roi_points`, keyed by webcam index or video file name, and load automatically next time.

### Terminal

```powershell
python main.py
```

Pick the input type (0 camera, 1 video, 2 manual), the number of lanes and the green time. Pasted video paths with surrounding quotes are accepted.

## Configuration

Edit `config.json`:

| Key | Meaning |
| --- | --- |
| `green_options`, `default_green` | selectable green durations and the default |
| `yellow_time` | yellow phase length in seconds (the scan runs here) |
| `frame_skip` | frames skipped between reads |
| `vehicle_model` | path to the vehicle counting model |
| `emergency_detector` | `vision` (cloud) or `yolo` (local) |
| `vision_provider`, `vision_model` | provider and the active model |
| `vision_models` | model names offered per provider in the GUI |
| `ambulance_model` | local emergency model |
| `vision_stitch_limit` | lanes stitched per cloud request (default 2) |
| `starvation_threshold` | consecutive decisions a lane with traffic can be skipped before Tier 2 anti-starvation picks it (default 3; missing, null, or below 1 falls back to the number of lanes) |
| `emergency_priority` | priority weights (ambulance 2, firetruck 1) |
| `roi_points` | saved polygons (written by the GUI) |

Provider model names change over time. If a call fails with HTTP 400 or 404, check the name on the provider's model page, or type a different one in the GUI.

## Testing

```powershell
pip install -r requirements-dev.txt
python -m pytest --cov=. --cov-report=term-missing
ruff check . --select E9,F --exclude venv,.venv
```

The suite runs without a display, a GPU, model files, a network or API keys, because YOLO, OpenCV capture and all HTTP calls are mocked. GitHub Actions runs the tests and the linter on every push and pull request.

Mocked tests verify the controller logic and data formats; when testing by hand before a release, verify:
- Real cloud API response with an active key in `.env` or Settings, and graceful fallback to local YOLO when the key is removed.
- 4-point ROI placement, persistence across restarts, and Settings save preserving `roi_points`.
- Windowed vs. fullscreen layout and 100% / 125% / 150% display scaling without clipping or overlap.
- `Space` pause/resume and `Esc` ROI-cancel / stop confirmation.

## License

MIT. See [LICENSE](LICENSE).
