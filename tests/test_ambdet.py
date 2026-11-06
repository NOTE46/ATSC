import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error
import pytest
import ambdet


@pytest.mark.unit
def test_stitch_lanes_single_frame(fake_frame):
    """Single frame stitching returns 480x360 image with header bar."""
    stitched = ambdet._stitch_lanes([(0, fake_frame)])
    assert stitched is not None
    assert stitched.shape == (360, 480, 3)


@pytest.mark.unit
def test_stitch_lanes_two_frames(fake_frame):
    """Two frame stitching returns (360, 960, 3) image (480*2 wide)."""
    f1 = fake_frame.copy()
    f2 = fake_frame.copy()
    stitched = ambdet._stitch_lanes([(0, f1), (1, f2)])
    assert stitched is not None
    assert stitched.shape == (360, 960, 3)


@pytest.mark.unit
def test_stitch_lanes_empty_or_none():
    """Empty list or all-None frames return None."""
    assert ambdet._stitch_lanes([]) is None
    assert ambdet._stitch_lanes([(0, None), (1, None)]) is None


@pytest.mark.unit
def test_call_gemini_vision_success(fake_frame, monkeypatch):
    """Mock Gemini API response and verify correct parsing and allowlist normalization."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock_key")
    stitched = ambdet._stitch_lanes([(0, fake_frame), (1, fake_frame)])

    mock_response = MagicMock()
    mock_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": json.dumps({"0": " Fire Truck ", "1": "AMBULANCE", "99": "ambulance"})}
                    ]
                }
            }
        ]
    }
    mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        result = ambdet._call_gemini_vision(stitched, [0, 1])

    # 0 -> firetruck, 1 -> ambulance, 99 ignored because not in requested lane_ids
    assert result[0] == "firetruck"
    assert result[1] == "ambulance"
    assert 99 not in result


@pytest.mark.unit
@pytest.mark.parametrize("raw_label,expected", [
    ("ambulance", "ambulance"),
    ("AMBULANCE", "ambulance"),
    (" Fire Truck ", "firetruck"),
    ("police", "none"),
    ("unknown_vehicle", "none"),
    ("", "none"),
])
def test_call_gemini_vision_label_normalization(fake_frame, monkeypatch, raw_label, expected):
    """Normalize labels and enforce strict allowlist validation."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock_key")
    stitched = ambdet._stitch_lanes([(0, fake_frame)])

    mock_response = MagicMock()
    mock_payload = {"0": raw_label}
    mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        result = ambdet._call_gemini_vision(stitched, [0])

    assert result[0] == expected


@pytest.mark.unit
def test_call_gemini_vision_missing_lane_defaults_to_none(fake_frame, monkeypatch):
    """If Gemini response misses a requested lane, default it to 'none'."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock_key")
    stitched = ambdet._stitch_lanes([(0, fake_frame), (1, fake_frame)])

    mock_response = MagicMock()
    mock_payload = {"0": "ambulance"}  # Lane 1 missing
    mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        result = ambdet._call_gemini_vision(stitched, [0, 1])

    assert result[0] == "ambulance"
    assert result[1] == "none"


@pytest.mark.unit
def test_missing_api_key_prints_warning_once_and_falls_back(fake_frame, capsys, monkeypatch):
    """Missing GEMINI_API_KEY prints one-time warning and falls back to local YOLO."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    frames_dict = {0: fake_frame, 1: fake_frame}

    with patch.object(ambdet, "_detect_local_type", return_value="none"):
        res1 = ambdet.detect_emergencies_batch(frames_dict)
        captured = capsys.readouterr()
        assert "GEMINI_API_KEY not set" in captured.out

        # Second call: warning should NOT be printed again
        res2 = ambdet.detect_emergencies_batch(frames_dict)
        captured2 = capsys.readouterr()
        assert "GEMINI_API_KEY not set" not in captured2.out

    assert res1[0]["emergency_type"] == "none"
    assert res2[1]["emergency_type"] == "none"


@pytest.mark.unit
def test_gemini_timeout_falls_back_to_local_yolo(fake_frame, monkeypatch):
    """When Gemini call raises an exception/timeout, fall back to local _detect_local_type."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock_key")
    frames_dict = {0: fake_frame}

    with patch("urllib.request.urlopen", side_effect=TimeoutError("Network timeout")):
        with patch.object(ambdet, "_detect_local_type", return_value="ambulance"):
            res = ambdet.detect_emergencies_batch(frames_dict)

    assert res[0]["emergency"] is True
    assert res[0]["emergency_type"] == "ambulance"


@pytest.mark.unit
def test_detector_yolo_mode_never_calls_gemini(fake_frame, monkeypatch):
    """If emergency_detector == 'yolo', Gemini is never called."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock_key")
    frames_dict = {0: fake_frame}

    with patch.object(ambdet, "_load_config", return_value={"emergency_detector": "yolo"}):
        with patch("urllib.request.urlopen") as mock_url:
            with patch.object(ambdet, "_detect_local_type", return_value="none"):
                res = ambdet.detect_emergencies_batch(frames_dict)
                assert not mock_url.called

    assert res[0]["emergency"] is False


@pytest.mark.unit
def test_load_env_logic(tmp_path, monkeypatch):
    """Verify _load_env parses variables without overriding existing environment."""
    env_file = tmp_path / ".env"
    env_file.write_text("""
    # Comment line
    TEST_VAR_A=hello_world
    TEST_VAR_B="quoted value"
    TEST_VAR_C='single quotes'
    EXISTING_VAR=file_val
    EMPTY_VAR=
    """, encoding="utf-8")

    monkeypatch.setenv("EXISTING_VAR", "system_val")
    monkeypatch.delenv("TEST_VAR_A", raising=False)
    monkeypatch.delenv("TEST_VAR_B", raising=False)
    monkeypatch.delenv("TEST_VAR_C", raising=False)

    ambdet._load_env(env_file)

    assert os.environ.get("TEST_VAR_A") == "hello_world"
    assert os.environ.get("TEST_VAR_B") == "quoted value"
    assert os.environ.get("TEST_VAR_C") == "single quotes"
    assert os.environ.get("EXISTING_VAR") == "system_val"
    assert os.environ.get("EMPTY_VAR") is None


@pytest.mark.unit
def test_openai_compat_vision_groq_and_openrouter(fake_frame, monkeypatch):
    """Test Groq and OpenRouter request payloads, markdown stripping, allowlist filtering."""
    monkeypatch.setenv("GROQ_API_KEY", "mock_groq_key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "mock_openrouter_key")
    stitched = ambdet._stitch_lanes([(0, fake_frame), (1, fake_frame)])

    captured_requests = []

    def mock_urlopen(req, timeout=6):
        captured_requests.append(req)
        mock_resp = MagicMock()
        payload = {
            "choices": [
                {
                    "message": {
                        "content": "```json\n{\"0\": \"ambulance\", \"1\": \" FIRE TRUCK \", \"99\": \"none\"}\n```"
                    }
                }
            ]
        }
        mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        # 1. Groq call
        res_groq = ambdet._call_openai_compat_vision(stitched, [0, 1], "groq", "qwen/qwen3.8-27b")
        assert res_groq[0] == "ambulance"
        assert res_groq[1] == "firetruck"
        assert 99 not in res_groq

        req_groq = captured_requests[-1]
        assert req_groq.headers["Authorization"] == "Bearer mock_groq_key"
        body_groq = json.loads(req_groq.data.decode("utf-8"))
        assert body_groq["model"] == "qwen/qwen3.8-27b"
        assert body_groq["reasoning_format"] == "hidden"

        # 2. OpenRouter call
        res_or = ambdet._call_openai_compat_vision(stitched, [0, 1], "openrouter", "google/gemma-4-26b-a4b-it:free")
        assert res_or[0] == "ambulance"
        assert res_or[1] == "firetruck"

        req_or = captured_requests[-1]
        assert req_or.headers["Authorization"] == "Bearer mock_openrouter_key"
        body_or = json.loads(req_or.data.decode("utf-8"))
        assert body_or["model"] == "google/gemma-4-26b-a4b-it:free"
        assert "reasoning_format" not in body_or


@pytest.mark.unit
def test_openai_compat_vision_missing_key_warns_and_raises(fake_frame, capsys, monkeypatch):
    """Missing key in OpenAI compat vision triggers one-time warning and raises RuntimeError."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    stitched = ambdet._stitch_lanes([(0, fake_frame)])

    with pytest.raises(RuntimeError) as exc_info:
        ambdet._call_openai_compat_vision(stitched, [0], "groq", "qwen/qwen3.8-27b")
    assert "GROQ_API_KEY not set" in str(exc_info.value)

    captured = capsys.readouterr()
    assert "GROQ_API_KEY not set" in captured.out


@pytest.mark.unit
def test_security_sanitized_exceptions_never_leak_api_keys(fake_frame, monkeypatch):
    """Sanitized HTTPError / URLError exceptions in Gemini, Groq, OpenRouter never contain API keys."""
    secret_gemini = "AIzaSySecretGeminiKey12345"
    secret_groq = "gsk_secret_groq_key_99999"
    secret_or = "sk-or-v1-secret_openrouter_key_77777"

    monkeypatch.setenv("GEMINI_API_KEY", secret_gemini)
    monkeypatch.setenv("GROQ_API_KEY", secret_groq)
    monkeypatch.setenv("OPENROUTER_API_KEY", secret_or)

    stitched = ambdet._stitch_lanes([(0, fake_frame)])

    # Gemini HTTP 400
    http_err_gemini = urllib.error.HTTPError(
        url=f"https://generativelanguage.googleapis.com/v1beta/models/test:generateContent?key={secret_gemini}",
        code=400,
        msg="Bad Request",
        hdrs={},
        fp=None
    )
    with patch("urllib.request.urlopen", side_effect=http_err_gemini):
        with pytest.raises(RuntimeError) as exc:
            ambdet._call_gemini_vision(stitched, [0])
        err_msg = str(exc.value)
        assert secret_gemini not in err_msg
        assert "?key=" not in err_msg
        assert err_msg == "gemini HTTP 400"

    # Groq HTTP 401
    http_err_groq = urllib.error.HTTPError(
        url="https://api.groq.com/openai/v1/chat/completions",
        code=401,
        msg="Unauthorized",
        hdrs={"Authorization": f"Bearer {secret_groq}"},
        fp=None
    )
    with patch("urllib.request.urlopen", side_effect=http_err_groq):
        with pytest.raises(RuntimeError) as exc:
            ambdet._call_openai_compat_vision(stitched, [0], "groq", "test-model")
        err_msg = str(exc.value)
        assert secret_groq not in err_msg
        assert "Bearer" not in err_msg
        assert err_msg == "groq HTTP 401"

    # OpenRouter URLError
    url_err_or = urllib.error.URLError(reason="Connection refused")
    with patch("urllib.request.urlopen", side_effect=url_err_or):
        with pytest.raises(RuntimeError) as exc:
            ambdet._call_openai_compat_vision(stitched, [0], "openrouter", "test-model")
        err_msg = str(exc.value)
        assert secret_or not in err_msg
        assert err_msg == "openrouter URL error: Connection refused"


@pytest.mark.unit
def test_list_local_models_discovery_and_ordering(tmp_path):
    """list_local_models discovers .pt files, excludes yolov8n.pt if other models exist, and puts best.pt first."""
    # 1. Multiple models including best.pt and yolov8n.pt
    (tmp_path / "custom_b.pt").touch()
    (tmp_path / "custom_a.pt").touch()
    (tmp_path / "yolov8n.pt").touch()
    (tmp_path / "best.pt").touch()

    found = ambdet.list_local_models(tmp_path)
    # best.pt must be first
    assert Path(found[0]).name == "best.pt"
    # yolov8n.pt must be excluded because other .pt files exist
    names = [Path(p).name for p in found]
    assert "yolov8n.pt" not in names
    assert "custom_a.pt" in names
    assert "custom_b.pt" in names
    for p in found:
        assert "\\" not in p  # normalized with forward slashes

    # 2. Only yolov8n.pt exists
    only_yolo_dir = tmp_path / "only_yolo"
    only_yolo_dir.mkdir()
    (only_yolo_dir / "yolov8n.pt").touch()
    found_yolo = ambdet.list_local_models(only_yolo_dir)
    assert len(found_yolo) == 1
    assert Path(found_yolo[0]).name == "yolov8n.pt"

    # 3. Empty directory or non-existent
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert ambdet.list_local_models(empty_dir) == ["Model/best.pt"]
    assert ambdet.list_local_models(tmp_path / "does_not_exist") == ["Model/best.pt"]


@pytest.mark.unit
def test_set_and_get_detector_config_runtime_overrides(monkeypatch):
    """Runtime config overrides merge with config.json defaults and resolve active model."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "mock_groq")

    # Default config
    cfg = ambdet.get_detector_config()
    assert cfg["detector"] == "vision"
    assert cfg["provider"] == "gemini"
    assert cfg["has_api_key"] is False  # GEMINI_API_KEY is not set

    # Set to Groq
    ambdet.set_detector_config(detector="vision", provider="groq", vision_model="qwen/qwen3.8-27b")
    cfg_groq = ambdet.get_detector_config()
    assert cfg_groq["detector"] == "vision"
    assert cfg_groq["provider"] == "groq"
    assert cfg_groq["active_model"] == "qwen/qwen3.8-27b"
    assert cfg_groq["has_api_key"] is True  # GROQ_API_KEY is set

    # Set to YOLO
    ambdet.set_detector_config(detector="yolo", ambulance_model="Model/custom_best.pt")
    cfg_yolo = ambdet.get_detector_config()
    assert cfg_yolo["detector"] == "yolo"
    assert cfg_yolo["ambulance_model"] == "Model/custom_best.pt"
    assert cfg_yolo["active_model"] == "Model/custom_best.pt"

    # Reset
    ambdet.reset_detector_config()
    cfg_reset = ambdet.get_detector_config()
    assert cfg_reset["detector"] == "vision"
    assert cfg_reset["provider"] == "gemini"


@pytest.mark.unit
def test_get_yolo_model_reloads_on_path_change():
    """_get_yolo_model re-instantiates YOLO when model_path changes."""
    mock_instance_a = MagicMock()
    mock_instance_b = MagicMock()

    with patch("ambdet.YOLO", side_effect=[mock_instance_a, mock_instance_b]) as mock_yolo_cls:
        # First call with path A
        m1 = ambdet._get_yolo_model("Model/model_a.pt")
        assert m1 is mock_instance_a
        assert mock_yolo_cls.call_count == 1

        # Second call with same path -> cached
        m2 = ambdet._get_yolo_model("Model/model_a.pt")
        assert m2 is mock_instance_a
        assert mock_yolo_cls.call_count == 1

        # Third call with path B -> reloads
        m3 = ambdet._get_yolo_model("Model/model_b.pt")
        assert m3 is mock_instance_b
        assert mock_yolo_cls.call_count == 2


@pytest.mark.unit
@pytest.mark.parametrize("class_name,expected", [
    ("ambulance", "ambulance"),
    ("AMBULANCE", "ambulance"),
    ("emergency_ambulance", "ambulance"),
    ("firetruck", "firetruck"),
    ("FIRE_TRUCK", "firetruck"),
    ("fireengine", "firetruck"),
    ("car", "none"),
    ("truck", "none"),
    ("bus", "none"),
    ("motorcycle", "none"),
])
def test_detect_local_type_classes(fake_frame, class_name, expected):
    """_detect_local_type correctly normalizes classes to ambulance, firetruck, or none."""
    mock_res = MagicMock()
    mock_box = MagicMock()
    mock_box.cls = 0
    mock_res.boxes = [mock_box]
    mock_res.names = {0: class_name}

    mock_m = MagicMock()
    mock_m.return_value = [mock_res]

    with patch.object(ambdet, "_get_yolo_model", return_value=mock_m):
        res = ambdet._detect_local_type(fake_frame)
        assert res == expected


@pytest.mark.unit
def test_detect_emergencies_batch_provider_routing_and_failure_log(fake_frame, capsys, monkeypatch):
    """detect_emergencies_batch routes to Groq/OpenRouter and logs single-line failure on error."""
    monkeypatch.setenv("GROQ_API_KEY", "mock_key")
    ambdet.set_detector_config(detector="vision", provider="groq", vision_model="qwen/qwen3.8-27b")

    frames_dict = {0: fake_frame}

    # 1. Successful Groq routing
    with patch.object(ambdet, "_call_openai_compat_vision", return_value={0: "firetruck"}):
        res = ambdet.detect_emergencies_batch(frames_dict)
        assert res[0]["emergency_type"] == "firetruck"
        assert res[0]["emergency"] is True

    # 2. Failure fallback and single-line logging
    with patch.object(ambdet, "_call_openai_compat_vision", side_effect=RuntimeError("groq HTTP 500")):
        with patch.object(ambdet, "_detect_local_type", return_value="ambulance"):
            res_fail = ambdet.detect_emergencies_batch(frames_dict)
            assert res_fail[0]["emergency_type"] == "ambulance"
            captured = capsys.readouterr()
            assert "Vision call failed (groq HTTP 500); using local model" in captured.out
