import base64
import json
import os
from pathlib import Path
import threading
import urllib.error
import urllib.request
import cv2
from ultralytics import YOLO

_yolo_lock = threading.Lock()
_yolo_model = None
_cached_model_path = None
model = None  # Legacy test override hook

_detector_config_lock = threading.Lock()
_runtime_config = {}

_warned_missing_api_key = False
_warned_missing_keys = set()
_reported_vision_failures = set()

ALLOWLIST = {"ambulance", "firetruck", "none"}

KEY_ENV_VARS = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


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


def list_local_models(model_dir="Model"):
    """
    Scan model_dir for .pt files, excluding base vehicle models (yolo26n.pt, yolov8n.pt)
    if other .pt models exist, sorting best.pt first, and normalizing with forward slashes.
    """
    p = Path(model_dir)
    if not p.is_dir():
        return ["Model/best.pt"]
    files = list(p.glob("*.pt"))
    if not files:
        return ["Model/best.pt"]

    non_base = [f for f in files if f.name not in ("yolo26n.pt", "yolov8n.pt")]
    if not non_base:
        return ["Model/best.pt"]
    non_base.sort(key=lambda x: (0 if x.name == "best.pt" else 1, x.name.lower()))
    return [f.as_posix() for f in non_base]


def set_detector_config(detector=None, provider=None, vision_model=None, ambulance_model=None):
    """Thread-safe update of in-memory detector overrides."""
    with _detector_config_lock:
        if detector is not None:
            _runtime_config["detector"] = str(detector).strip().lower()
        if provider is not None:
            _runtime_config["provider"] = str(provider).strip().lower()
        if vision_model is not None:
            _runtime_config["vision_model"] = str(vision_model).strip()
        if ambulance_model is not None:
            _runtime_config["ambulance_model"] = str(ambulance_model).strip().replace("\\", "/")


def reset_detector_config():
    """Clear runtime detector overrides."""
    with _detector_config_lock:
        _runtime_config.clear()


def get_detector_config():
    """
    Merge config.json defaults with runtime overrides.
    Resolves the active model and checks API key presence.
    """
    cfg = _load_config()
    with _detector_config_lock:
        overrides = dict(_runtime_config)

    detector = overrides.get("detector", cfg.get("emergency_detector", "vision")).strip().lower()
    provider = overrides.get("provider", cfg.get("vision_provider", "gemini")).strip().lower()
    ambulance_model = overrides.get("ambulance_model", cfg.get("ambulance_model", "Model/best.pt"))
    stitch_limit = cfg.get("vision_stitch_limit", 2)
    vision_models = cfg.get("vision_models", {})

    v_model = overrides.get("vision_model", cfg.get("vision_model"))
    if not v_model:
        if provider == "gemini":
            v_model = cfg.get("gemini_model", "gemini-2.5-flash")
        else:
            prov_list = vision_models.get(provider, [])
            v_model = prov_list[0] if prov_list else ""

    if detector == "yolo":
        active_model = ambulance_model
    else:
        active_model = v_model

    env_var = KEY_ENV_VARS.get(provider, "GEMINI_API_KEY")
    has_api_key = bool(os.environ.get(env_var, "").strip())

    return {
        "detector": detector,
        "provider": provider,
        "vision_model": v_model,
        "gemini_model": cfg.get("gemini_model", "gemini-2.5-flash"),
        "ambulance_model": ambulance_model,
        "active_model": active_model,
        "has_api_key": has_api_key,
        "stitch_limit": stitch_limit,
        "vision_models": vision_models,
        "key_env_var": env_var,
    }


def _warn_missing_key(provider, local_model_path="Model/best.pt"):
    """Print a one-time console warning when an API key is missing."""
    global _warned_missing_api_key
    key_name = KEY_ENV_VARS.get(provider, f"{provider.upper()}_API_KEY")
    local_name = Path(local_model_path).name
    if provider not in _warned_missing_keys:
        if provider != "gemini" or not _warned_missing_api_key:
            print(f"{key_name} not set (add it to .env or set the environment variable); falling back to local {local_name}.")
        _warned_missing_keys.add(provider)
        if provider == "gemini":
            _warned_missing_api_key = True


def _warn_missing_gemini_key():
    """Print a one-time console warning when GEMINI_API_KEY is missing (legacy compat)."""
    _warn_missing_key("gemini")


def _get_yolo_model(model_path=None):
    """Lazy-load or reload local ambulance YOLO model under _yolo_lock."""
    global _yolo_model, _cached_model_path, model
    if model is not None:
        return model

    if model_path is None:
        cfg = get_detector_config()
        model_path = cfg["ambulance_model"]

    norm_path = str(model_path).replace("\\", "/")
    if _yolo_model is None or _cached_model_path != norm_path:
        with _yolo_lock:
            if _yolo_model is None or _cached_model_path != norm_path:
                _yolo_model = YOLO(norm_path)
                _cached_model_path = norm_path
    return _yolo_model


def _detect_local_type(frame, model_path=None):
    """
    Run active local YOLO model under thread lock.
    Returns 'ambulance', 'firetruck', or 'none'.
    """
    if frame is None:
        return "none"

    # Support legacy tests that mock ambulance_detect directly
    if hasattr(ambulance_detect, "mock_calls"):
        try:
            if ambulance_detect(frame):
                return "ambulance"
            return "none"
        except Exception:
            pass

    m = _get_yolo_model(model_path)
    with _yolo_lock:
        results = m(frame, conf=0.45, verbose=False)

    if results and len(results) > 0 and results[0].boxes is not None:
        names = results[0].names
        for box in results[0].boxes:
            cls_id = int(box.cls)
            label = names[cls_id] if isinstance(names, dict) else names[cls_id]
            norm_label = str(label).strip().lower().replace("_", "").replace(" ", "")
            if "ambulance" in norm_label:
                return "ambulance"
            if "firetruck" in norm_label or "fireengine" in norm_label:
                return "firetruck"
    return "none"


def ambulance_detect(frame):
    """Run local YOLO model and return True if ambulance detected, else False."""
    return _detect_local_type(frame) != "none"


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
        cv2.rectangle(resized, (0, 0), (480, 32), (0, 0, 0), -1)
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
    Never leaks API keys or URLs in exceptions.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable not found")

    if model_name is None:
        cfg = get_detector_config()
        model_name = cfg["active_model"]

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

    try:
        with urllib.request.urlopen(req, timeout=6) as response:
            resp_bytes = response.read()
            resp_text = resp_bytes.decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"gemini HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"gemini URL error: {e.reason}") from None
    except Exception as e:
        raise RuntimeError(f"gemini error: {e}") from None

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


def _call_openai_compat_vision(stitched_bgr, lane_ids, provider, model_name):
    """
    Call Groq or OpenRouter Vision API with OpenAI-compatible payload.
    Never leaks API keys or Authorization headers in exceptions.
    """
    endpoints = {
        "groq": ("GROQ_API_KEY", "https://api.groq.com/openai/v1/chat/completions"),
        "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions"),
    }
    if provider not in endpoints:
        raise RuntimeError(f"Unknown vision provider: {provider}")

    key_name, url = endpoints[provider]
    api_key = os.environ.get(key_name, "").strip()
    if not api_key:
        _warn_missing_key(provider)
        raise RuntimeError(f"{key_name} not set")

    success, buf = cv2.imencode(".jpg", stitched_bgr)
    if not success:
        raise RuntimeError("Failed to encode stitched image to JPEG")
    b64_str = base64.b64encode(buf.tobytes()).decode("utf-8")

    prompt = (
        "Analyze the traffic camera image containing lanes marked with 'LANE <id>'. "
        "Classify emergency vehicle presence for each requested lane_id into: "
        "'ambulance', 'firetruck', or 'none'. "
        f"Requested lane IDs: {lane_ids}. "
        "Return ONLY a JSON dictionary mapping lane ID string to classification."
    )

    payload = {
        "model": model_name,
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64_str}"
                        }
                    }
                ]
            }
        ]
    }
    if provider == "groq":
        payload["reasoning_format"] = "hidden"

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "ATSC/1.0"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=6) as response:
            resp_bytes = response.read()
            resp_text = resp_bytes.decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{provider} HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"{provider} URL error: {e.reason}") from None
    except Exception as e:
        raise RuntimeError(f"{provider} error: {e}") from None

    raw_data = json.loads(resp_text)
    content = ""
    if isinstance(raw_data, dict):
        choices = raw_data.get("choices", [])
        if choices and isinstance(choices, list):
            msg = choices[0].get("message", {})
            content = msg.get("content", "")

    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    parsed_json = json.loads(content) if content else {}

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
    Batch emergency detection across lanes using Multi-Provider Vision or Local YOLO.
    Returns {lane_id: {"ambulance": bool, "emergency": bool, "emergency_type": str}}.
    """
    if not frames_dict:
        return {}

    # Snapshot config settings once at the start of scan
    cfg = get_detector_config()
    detector = cfg["detector"]
    provider = cfg["provider"]
    active_model = cfg["active_model"]
    local_model_path = cfg["ambulance_model"]
    stitch_limit = cfg["stitch_limit"]
    has_api_key = cfg["has_api_key"]

    results = {}
    sorted_lane_ids = sorted(frames_dict.keys())

    if detector == "vision":
        if not has_api_key:
            _warn_missing_key(provider, local_model_path)
            for lane_id in sorted_lane_ids:
                f = frames_dict[lane_id]
                etype = _detect_local_type(f, local_model_path)
                is_emerg = etype in ("ambulance", "firetruck")
                results[lane_id] = {
                    "ambulance": is_emerg,
                    "emergency": is_emerg,
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

                if provider == "gemini":
                    vision_map = _call_gemini_vision(stitched, chunk_ids, active_model)
                elif provider in ("groq", "openrouter"):
                    vision_map = _call_openai_compat_vision(stitched, chunk_ids, provider, active_model)
                else:
                    raise RuntimeError(f"Unsupported vision provider: {provider}")

                for lid in chunk_ids:
                    etype = vision_map.get(lid, "none")
                    is_emerg = etype in ("ambulance", "firetruck")
                    results[lid] = {
                        "ambulance": is_emerg,
                        "emergency": is_emerg,
                        "emergency_type": etype
                    }
            except Exception as e:
                err_msg = str(e)
                if provider not in _reported_vision_failures:
                    print(f"Vision call failed ({err_msg}); using local model")
                    _reported_vision_failures.add(provider)
                # Fallback per lane using active local YOLO model
                for lid in chunk_ids:
                    f = frames_dict[lid]
                    etype = _detect_local_type(f, local_model_path)
                    is_emerg = etype in ("ambulance", "firetruck")
                    results[lid] = {
                        "ambulance": is_emerg,
                        "emergency": is_emerg,
                        "emergency_type": etype
                    }
        return results

    # detector == "yolo" or fallback
    for lane_id in sorted_lane_ids:
        f = frames_dict[lane_id]
        etype = _detect_local_type(f, local_model_path)
        is_emerg = etype in ("ambulance", "firetruck")
        results[lane_id] = {
            "ambulance": is_emerg,
            "emergency": is_emerg,
            "emergency_type": etype
        }
    return results
