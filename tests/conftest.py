import sys
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np
import pytest

# Ensure the project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 1. Stub ultralytics before application imports
mock_ultralytics = MagicMock()
mock_yolo_cls = MagicMock()

def _default_yolo_call(frame, *args, **kwargs):
    res = MagicMock()
    res.boxes = []
    res.names = {0: "car", 1: "motorcycle", 2: "truck", 3: "bus", 4: "ambulance"}
    return [res]

default_instance = MagicMock()
default_instance.side_effect = _default_yolo_call
mock_yolo_cls.return_value = default_instance
mock_ultralytics.YOLO = mock_yolo_cls
sys.modules["ultralytics"] = mock_ultralytics

# 2. Stub torch if not installed
if "torch" not in sys.modules:
    sys.modules["torch"] = MagicMock()

# 3. Stub tkinter and PIL.ImageTk for headless environments
try:
    import tkinter  # noqa: F401
except ImportError:
    tk_mock = MagicMock()
    sys.modules["tkinter"] = tk_mock
    sys.modules["tkinter.ttk"] = MagicMock()
    sys.modules["tkinter.filedialog"] = MagicMock()
    sys.modules["tkinter.messagebox"] = MagicMock()

try:
    from PIL import ImageTk  # noqa: F401
except ImportError:
    if "PIL" not in sys.modules:
        sys.modules["PIL"] = MagicMock()
    sys.modules["PIL.ImageTk"] = MagicMock()

import control
import ambdet


@pytest.fixture(autouse=True)
def reset_controller_state(monkeypatch, tmp_path):
    """Reset controller state and isolate the decision log before and after every test."""
    monkeypatch.setattr(control, "DECISION_LOG_PATH", tmp_path / "decisions.csv")
    control.reset_control()
    yield
    control.reset_control()


@pytest.fixture(autouse=True)
def reset_ambdet_env_and_warning(monkeypatch):
    """Reset ambdet's one-time warning flags, detector overrides, and remove cloud API keys by default."""
    ambdet._warned_missing_api_key = False
    ambdet._warned_missing_keys.clear()
    ambdet._reported_vision_failures.clear()
    ambdet.reset_detector_config()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    yield
    ambdet._warned_missing_api_key = False
    ambdet._warned_missing_keys.clear()
    ambdet._reported_vision_failures.clear()
    ambdet.reset_detector_config()


@pytest.fixture
def fake_frame():
    """Return a standard 480x640 3-channel dummy BGR frame."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture
def fake_camera(fake_frame):
    """Return a mock Cameraf instance."""
    cam = MagicMock()
    cam.lane_no = 0
    cam.last_frame = fake_frame.copy()
    cam.read_frame.return_value = fake_frame.copy()
    cam.cvfun.return_value = {
        "density": 3,
        "ambulance": False,
        "emergency": False,
        "emergency_type": "none",
    }
    return cam


@pytest.fixture
def make_lane_data():
    """Factory fixture to generate shared contract lane_data."""
    def _create(densities, emergencies=None):
        if emergencies is None:
            emergencies = ["none"] * len(densities)
        data = {}
        for i, (d, em) in enumerate(zip(densities, emergencies)):
            is_amb = em == "ambulance"
            is_emerg = em in ("ambulance", "firetruck")
            data[i] = {
                "density": int(d),
                "ambulance": is_amb,
                "emergency": is_emerg,
                "emergency_type": str(em).lower(),
            }
        return data
    return _create
