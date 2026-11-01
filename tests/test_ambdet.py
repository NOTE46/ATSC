import json
import os
from unittest.mock import MagicMock, patch
import numpy as np
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

    with patch.object(ambdet, "ambulance_detect", return_value=False):
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
    """When Gemini call raises an exception/timeout, fall back to local ambulance_detect."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock_key")
    frames_dict = {0: fake_frame}

    with patch("urllib.request.urlopen", side_effect=TimeoutError("Network timeout")):
        with patch.object(ambdet, "ambulance_detect", return_value=True):
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
            with patch.object(ambdet, "ambulance_detect", return_value=False):
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
