import base64
import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path
import cv2
from ultralytics import YOLO

_yolo_lock = threading.Lock()
_yolo_model = None
model = None
_warned_missing_api_key = False

ALLOWLIST = {"ambulance", "firetruck", "none"}


def _load_env(env_path=None):
    """Load key-value pairs from .env into os.environ without overwriting existing vars."""
    if env_path is None:
        env_path = Path(__file__).resolve().parent / ".env"
    else:
        env_path = Path(env_path)
    if not env_path.is_file():
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
                    v = v[1:-1]
                if k and v:
                    os.environ.setdefault(k, v)
    except Exception:
        pass


_load_env()


def _warn_missing_gemini_key():
    """Print a one-time console warning when GEMINI_API_KEY is missing."""
    global _warned_missing_api_key
    if not _warned_missing_api_key:
        print("GEMINI_API_KEY not set (add it to .env or set the environment variable); falling back to local best.pt.")
        _warned_missing_api_key = True


def _load_config():
    """Helper to load config.json safely."""
    config_path = Path("config.json")
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _get_yolo_model():
    """Lazy-load the local ambulance YOLO model under _yolo_lock."""
    global _yolo_model, model
    if model is not None:
        return model
    if _yolo_model is None:
        with _yolo_lock:
            if _yolo_model is None:
                cfg = _load_config()
                model_path = cfg.get("ambulance_model", "Model/best.pt")
                _yolo_model = YOLO(model_path)
    return _yolo_model


def ambulance_detect(frame):
    """
    Run local YOLO model under thread lock to detect ambulances.
    Returns True if 'ambulance' detected, else False.
    """
    if frame is None:
        return False

    m = _get_yolo_model()
    with _yolo_lock:
        results = m(frame, conf=0.45, verbose=False)

    if results and len(results) > 0 and results[0].boxes is not None:
        names = results[0].names
        for box in results[0].boxes:
            cls_id = int(box.cls)
            label = names[cls_id] if isinstance(names, dict) else names[cls_id]
            if label == "ambulance":
                return True
    return False


def _stitch_lanes(lane_pairs):
    """
    Accept up to vision_stitch_limit pairs (lane_id, frame) where frame is not None,
    resize to (480, 360), draw solid black header bar (0, 0) to (480, 32) with white
    text 'LANE {lane_id}', and horizontally concatenate with cv2.hconcat.
    """
    cfg = _load_config()
    stitch_limit = cfg.get("vision_stitch_limit", 2)

    valid_pairs = [(lid, f) for lid, f in lane_pairs if f is not None][:stitch_limit]
    if not valid_pairs:
        return None

    processed = []
    for lane_id, frame in valid_pairs:
        resized = cv2.resize(frame, (480, 360))
        # Solid black header bar (0, 0) to (480, 32)
        cv2.rectangle(resized, (0, 0), (480, 32), (0, 0, 0), -1)
        # White text "LANE {lane_id}"
        cv2.putText(
            resized,
            f"LANE {lane_id}",
            (10, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )
        processed.append(resized)

    if len(processed) == 1:
        return processed[0]
    return cv2.hconcat(processed)


def _call_gemini_vision(stitched_bgr, lane_ids, model_name=None):
    """
    Call Gemini Vision API on the stitched image for the requested lane IDs.
    Normalizes labels and validates strictly against ALLOWLIST.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable not found")

    if model_name is None:
        cfg = _load_config()
        model_name = cfg.get("gemini_model", "gemini-2.5-flash")

    success, buf = cv2.imencode(".jpg", stitched_bgr)
    if not success:
        raise RuntimeError("Failed to encode stitched image to JPEG")
    b64_image = base64.b64encode(buf.tobytes()).decode("utf-8")

    prompt = (
        "Analyze the traffic camera image containing lanes marked with 'LANE <id>'. "
        "Classify emergency vehicle presence for each requested lane_id into: "
        "'ambulance', 'firetruck', or 'none'. "
        f"Requested lane IDs: {lane_ids}. "
        "Return ONLY a JSON dictionary mapping lane ID string to classification."
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": b64_image
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.0
        }
    }

    req_data = json.dumps(payload).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=4) as response:
        resp_bytes = response.read()
        resp_text = resp_bytes.decode("utf-8")

    raw_data = json.loads(resp_text)
    parsed_json = {}
    if isinstance(raw_data, dict) and "candidates" in raw_data:
        candidates = raw_data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                text_val = parts[0].get("text", "").strip()
                if text_val.startswith("```"):
                    lines = text_val.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    text_val = "\n".join(lines).strip()
                parsed_json = json.loads(text_val)
    elif isinstance(raw_data, dict):
        parsed_json = raw_data

    # Filter keys to int(k) in lane_ids and normalize labels
    extracted = {}
    if isinstance(parsed_json, dict):
        for k, v in parsed_json.items():
            try:
                ik = int(k)
                if ik in lane_ids:
                    norm_v = str(v).strip().lower().replace(" ", "")
                    if norm_v not in ALLOWLIST:
                        norm_v = "none"
                    extracted[ik] = norm_v
            except (ValueError, TypeError):
                continue

    result = {}
    for lid in lane_ids:
        result[lid] = extracted.get(lid, "none")

    return result


def detect_emergencies_batch(frames_dict):
    """
    Batch emergency detection across lanes using Gemini Vision with local YOLO fallback.
    Returns {lane_id: {"ambulance": bool, "emergency": bool, "emergency_type": str}}.
    """
    if not frames_dict:
        return {}

    cfg = _load_config()
    detector = cfg.get("emergency_detector", "vision")
    stitch_limit = cfg.get("vision_stitch_limit", 2)
    model_name = cfg.get("gemini_model", "gemini-2.5-flash")

    results = {}
    sorted_lane_ids = sorted(frames_dict.keys())

    if detector == "vision":
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            _warn_missing_gemini_key()
            for lane_id in sorted_lane_ids:
                f = frames_dict[lane_id]
                is_amb = ambulance_detect(f)
                etype = "ambulance" if is_amb else "none"
                results[lane_id] = {
                    "ambulance": is_amb,
                    "emergency": is_amb,
                    "emergency_type": etype
                }
            return results

        for i in range(0, len(sorted_lane_ids), stitch_limit):
            chunk_ids = sorted_lane_ids[i:i + stitch_limit]
            chunk_pairs = [(lid, frames_dict[lid]) for lid in chunk_ids if frames_dict[lid] is not None]
            try:
                stitched = _stitch_lanes(chunk_pairs)
                if stitched is None:
                    raise ValueError("No valid frames to stitch")
                vision_map = _call_gemini_vision(stitched, chunk_ids, model_name)
                for lid in chunk_ids:
                    etype = vision_map.get(lid, "none")
                    is_emerg = etype in ("ambulance", "firetruck")
                    results[lid] = {
                        "ambulance": is_emerg,
                        "emergency": is_emerg,
                        "emergency_type": etype
                    }
            except Exception:
                # Fallback to per-lane ambulance_detect on any exception
                for lid in chunk_ids:
                    f = frames_dict[lid]
                    is_amb = ambulance_detect(f)
                    etype = "ambulance" if is_amb else "none"
                    results[lid] = {
                        "ambulance": is_amb,
                        "emergency": is_amb,
                        "emergency_type": etype
                    }
        return results

    # detector == "yolo" or fallback
    for lane_id in sorted_lane_ids:
        f = frames_dict[lane_id]
        is_amb = ambulance_detect(f)
        etype = "ambulance" if is_amb else "none"
        results[lane_id] = {
            "ambulance": is_amb,
            "emergency": is_amb,
            "emergency_type": etype
        }
    return results
        
    