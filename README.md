# ATSC: Automated Traffic Signal Controller

![tests](https://github.com/NOTE46/ATSC/actions/workflows/tests.yml/badge.svg)
![lint](https://github.com/NOTE46/ATSC/actions/workflows/lint.yml/badge.svg)
![python](https://img.shields.io/badge/python-3.13-blue)

ATSC decides which lane of an intersection gets the green light. It counts vehicles in each lane with YOLOv8, checks for ambulances and fire trucks with a vision AI (or a local model), and picks the next lane with a fair priority queue, so emergency vehicles go first and no lane waits forever.

## Features

- **Green/yellow countdown.** Pick a green time of 15, 30, 40, 50 or 60 seconds, followed by a 5-second yellow. Detection runs once per cycle, at the start of yellow, so video plays smoothly the rest of the time and the AI sits idle.
- **4-point polygon ROI per lane.** Click four corners on the video to outline the incoming lane. Everything outside the polygon is blacked out and cropped away before detection, so outgoing traffic is not counted.
- **Emergency vehicle detection with a choice of engine.**
  - Cloud vision: Gemini, Groq or OpenRouter. Two lanes are stitched into one labeled image per request, which halves the number of API calls.
  - Local YOLO: any `.pt` model in `Model/`. Drop in a new file and click **Refresh**.
  - If a cloud call fails or its key is missing, ATSC falls back to the local model.
- **3-tier controller.**
  1. Emergency override: ambulance, then fire truck. Ties are broken by vehicle count, then wait time.
  2. Anti-starvation: a lane with traffic that has waited as many cycles as there are lanes gets the next green.
  3. Weighted density: score = `density + 3 x wait_count`. The current lane cannot win twice in a row while other lanes have traffic. If every lane is empty, the signal rotates.
- **Three input modes.** Video files, live webcams, or manual numbers for testing the controller without any video.
- **Tkinter dashboard** with live video, a countdown per lane, emergency badges and a log bar, plus a **terminal version** (`main.py`).

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
YOLOv8n vehicle count              stitch 2 lanes per image ->
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
├── gui.py              Tkinter dashboard, ROI editor, setup screen
├── main.py             terminal version
├── cvfile.py           camera wrapper, ROI mask/crop, scan_all_lanes()
├── uafile.py           YOLOv8n vehicle counter
├── ambdet.py           emergency detection (Gemini/Groq/OpenRouter/local), .env loader
├── control.py          3-tier priority and anti-starvation controller
├── manual_io.py        manual input mode (terminal)
├── config.json         timings, models, priorities, saved ROIs
├── .env.example        template for API keys
├── requirements.txt    runtime dependencies
├── requirements-dev.txt  pytest and coverage
├── Model/              yolov8n.pt (vehicle counting) + emergency .pt models
├── tests/              pytest suite (headless, everything mocked)
└── .github/workflows/  CI: tests and lint
```

## Installation

Requires Python 3.13 (3.11+ should work). Tkinter ships with Python on Windows and macOS. On Linux, install it with `sudo apt install python3-tk`.

```powershell
git clone https://github.com/NOTE46/ATSC.git
cd ATSC
python -m venv venv
.\venv\Scripts\Activate.ps1      # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
```

**Model weights.** Put these in `Model/`:

- `yolov8n.pt` for vehicle counting
- `best.pt`, or any custom `.pt` model, for local emergency detection

**API keys (optional).** Copy the template and fill in only the providers you use:

```powershell
copy .env.example .env
```

```
GEMINI_API_KEY=...
GROQ_API_KEY=...
OPENROUTER_API_KEY=...
```

`.env` is read at startup and is ignored by git. A real environment variable overrides the file. With no key set, ATSC prints one warning and uses the local model.

> **Privacy:** cloud detection sends stitched lane images to a third party. Free tiers may log requests, and some ask you not to upload faces or personal data. Use test clips for those, not real footage of people.

## Usage

### Dashboard

```powershell
python gui.py
```

1. Choose the input mode: Video files, Live camera, or Manual.
2. Choose the number of lanes and the green duration.
3. Choose the **Emergency Detection Engine** (Gemini, Groq, OpenRouter or Local YOLO) and a model. The model box is editable, so you can type any model name your provider supports.
4. Draw the ROI for each lane (see below), then watch the cycle run.

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
| `emergency_priority` | priority weights (ambulance 2, firetruck 1) |
| `roi_points` | saved polygons (written by the GUI) |

Provider model names change over time. If a call fails with HTTP 400 or 404, check the name on the provider's model page, or type a different one in the GUI.

## Testing

```powershell
pip install -r requirements-dev.txt
python -m pytest --cov=. --cov-report=term-missing
ruff check . --select E9,F --exclude venv,.venv
```

The suite runs without a display, a GPU, model files, a network or API keys, because YOLO, OpenCV capture and all HTTP calls are mocked. GitHub Actions runs the tests and the linter on every push and pull request. Mocked tests prove the logic and data formats, not that a real provider accepts a request, so see [docs/MANUAL_TESTS.md](docs/MANUAL_TESTS.md) for the checks to run by hand.

## Known limitations

- Detection happens once per cycle, so an emergency vehicle that arrives right after the scan is not seen until the next one.
- The GUI window can resize while running. A redesign is planned.
- Two lanes using video files with the same file name share one saved ROI.
- Local emergency detection only knows the classes its `.pt` model was trained on.

## License

MIT. See [LICENSE](LICENSE).
