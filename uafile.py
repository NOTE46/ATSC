import json
import threading
from pathlib import Path
from ultralytics import YOLO

# Module-level lock for thread-safe YOLO inference
_yolo_lock = threading.Lock()
_vehicle_model = None
model = None

TARGET_CLASSES = {"car", "motorcycle", "truck", "bus"}


def _get_vehicle_model():
    """Lazy-load the vehicle YOLO model under _yolo_lock."""
    global _vehicle_model, model
    if model is not None:
        return model
    if _vehicle_model is None:
        with _yolo_lock:
            if _vehicle_model is None:
                model_path = "Model/yolo26n.pt"
                config_path = Path("config.json")
                if config_path.exists():
                    try:
                        with open(config_path, "r", encoding="utf-8") as f:
                            cfg = json.load(f)
                            model_path = cfg.get("vehicle_model", model_path)
                    except Exception:
                        pass
                _vehicle_model = YOLO(model_path)
    return _vehicle_model


def uamodel(frame):
    """
    Thread-safe vehicle counter using YOLO26n.
    Counts bounding boxes with class in {'car', 'motorcycle', 'truck', 'bus'}.
    Returns a dictionary conforming to the ATSC shared data contract.
    """
    if frame is None:
        return {
            "density": 0,
            "ambulance": False,
            "emergency": False,
            "emergency_type": "none"
        }

    m = _get_vehicle_model()

    with _yolo_lock:
        results = m(frame, conf=0.4, verbose=False)

    density = 0
    if results and len(results) > 0 and results[0].boxes is not None:
        names = results[0].names
        for box in results[0].boxes:
            cls_id = int(box.cls)
            label = names[cls_id] if isinstance(names, dict) else names[cls_id]
            if label in TARGET_CLASSES:
                density += 1

    return {
        "density": density,
        "ambulance": False,
        "emergency": False,
        "emergency_type": "none"
    }
    