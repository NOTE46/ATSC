import json
from pathlib import Path
import pytest


@pytest.mark.unit
def test_config_json_exists_and_valid():
    """Verify config.json exists and contains parseable JSON."""
    config_path = Path("config.json")
    assert config_path.exists(), "config.json does not exist"
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    assert isinstance(cfg, dict)


@pytest.mark.unit
def test_config_required_keys_and_types():
    """Ensure all required keys are present with valid types."""
    with open("config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    assert isinstance(cfg.get("green_options"), list)
    assert isinstance(cfg.get("default_green"), int)
    assert isinstance(cfg.get("yellow_time"), int)
    assert isinstance(cfg.get("frame_skip"), int)
    assert isinstance(cfg.get("vehicle_model"), str)
    assert cfg.get("vehicle_model") == "Model/yolo26n.pt"
    assert isinstance(cfg.get("ambulance_model"), str)
    assert isinstance(cfg.get("emergency_detector"), str)
    assert isinstance(cfg.get("vision_provider"), str)
    assert isinstance(cfg.get("gemini_model"), str)
    assert isinstance(cfg.get("vision_model"), str)
    assert isinstance(cfg.get("vision_models"), dict)
    assert isinstance(cfg.get("vision_stitch_limit"), int)
    assert isinstance(cfg.get("emergency_priority"), dict)
    assert isinstance(cfg.get("roi_points"), dict)


@pytest.mark.unit
def test_config_timing_rules():
    """Check timing integrity: default_green in options, and yellow_time < min(green_options)."""
    with open("config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    green_opts = cfg["green_options"]
    default_green = cfg["default_green"]
    yellow_time = cfg["yellow_time"]

    assert len(green_opts) > 0
    assert default_green in green_opts
    assert yellow_time < min(green_opts)
    assert yellow_time > 0


@pytest.mark.unit
def test_config_emergency_priorities():
    """Verify priority hierarchy: ambulance > firetruck > none."""
    with open("config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    prio = cfg["emergency_priority"]
    assert prio.get("ambulance", 0) > prio.get("firetruck", 0)
    assert prio.get("firetruck", 0) > prio.get("none", -1)


@pytest.mark.unit
def test_config_stitch_limit():
    """Verify vision_stitch_limit is at least 1."""
    with open("config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    assert cfg.get("vision_stitch_limit", 0) >= 1


@pytest.mark.unit
def test_config_vision_models():
    """Verify vision_models has required providers with lists and vision_model matches active provider."""
    with open("config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    v_models = cfg.get("vision_models", {})
    assert "gemini" in v_models and isinstance(v_models["gemini"], list) and len(v_models["gemini"]) > 0
    assert "groq" in v_models and isinstance(v_models["groq"], list) and len(v_models["groq"]) > 0
    assert "openrouter" in v_models and isinstance(v_models["openrouter"], list) and len(v_models["openrouter"]) > 0

    active_provider = cfg.get("vision_provider", "gemini")
    active_model = cfg.get("vision_model")
    assert active_model in v_models[active_provider]

