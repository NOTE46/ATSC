from unittest.mock import MagicMock, patch
import numpy as np
import pytest
import cvfile
import control
import ambdet


@pytest.mark.integration
def test_scan_all_lanes_feeds_controlfun_directly():
    """End-to-end integration: cameras -> scan_all_lanes -> controlfun -> green light decision."""
    frame0 = np.zeros((480, 640, 3), dtype=np.uint8)
    frame1 = np.ones((480, 640, 3), dtype=np.uint8)

    cam0 = MagicMock()
    cam0.lane_no = 0
    cam0.last_frame = frame0
    cam0.read_frame.return_value = frame0

    cam1 = MagicMock()
    cam1.lane_no = 1
    cam1.last_frame = frame1
    cam1.read_frame.return_value = frame1

    cameras = {0: cam0, 1: cam1}

    # Simulate lane 0 density 3, lane 1 density 8
    def mock_uamodel(frame):
        return {
            "density": 8 if frame[0, 0, 0] == 1 else 3,
            "ambulance": False,
            "emergency": False,
            "emergency_type": "none",
        }

    with patch("cvfile.uamodel", side_effect=mock_uamodel):
        with patch("cvfile.detect_emergencies_batch", return_value={
            0: {"ambulance": False, "emergency": False, "emergency_type": "none"},
            1: {"ambulance": False, "emergency": False, "emergency_type": "none"},
        }):
            lane_data, frames = cvfile.scan_all_lanes(cameras, live=False)

    decision = control.controlfun(lane_data, 2)
    assert decision["lane_no"] == 1
    assert decision["signal"] == "Green"


@pytest.mark.integration
def test_gemini_outage_local_fallback_to_controller(fake_frame, monkeypatch):
    """Integration: Gemini network error triggers local fallback, which correctly alerts controller."""
    monkeypatch.setenv("GEMINI_API_KEY", "mock_key")
    cam0 = MagicMock()
    cam0.last_frame = fake_frame.copy()
    cam0.read_frame.return_value = fake_frame.copy()

    cameras = {0: cam0}

    # Network outage causes urllib error -> triggers fallback to ambulance_detect
    with patch("cvfile.uamodel", return_value={"density": 2, "ambulance": False, "emergency": False, "emergency_type": "none"}):
        with patch("urllib.request.urlopen", side_effect=ConnectionError("Cloud unreachable")):
            with patch.object(ambdet, "ambulance_detect", return_value=True):
                lane_data, _ = cvfile.scan_all_lanes(cameras, live=False)

    assert lane_data[0]["emergency"] is True
    assert lane_data[0]["emergency_type"] == "ambulance"

    decision = control.controlfun(lane_data, 1)
    assert decision["lane_no"] == 0
    assert decision["signal"] == "Green"


@pytest.mark.scenario
def test_multi_cycle_traffic_and_emergency_rush(fake_frame):
    """
    Scenario:
    Round 1: Normal traffic -> Highest density wins (Lane 1).
    Round 2: Cooldown & balanced traffic -> Lane 0 wins.
    Round 3: Sudden Ambulance in Lane 2 -> Preempts everyone immediately.
    """
    lanes = 3
    # Round 1: Lane 0: 5, Lane 1: 15, Lane 2: 2
    r1_data = {
        0: {"density": 5, "ambulance": False, "emergency": False, "emergency_type": "none"},
        1: {"density": 15, "ambulance": False, "emergency": False, "emergency_type": "none"},
        2: {"density": 2, "ambulance": False, "emergency": False, "emergency_type": "none"},
    }
    d1 = control.controlfun(r1_data, lanes)
    assert d1["lane_no"] == 1

    # Round 2: Lane 1 cooled down, Lane 0 (density 5) vs Lane 2 (density 2)
    r2_data = {
        0: {"density": 5, "ambulance": False, "emergency": False, "emergency_type": "none"},
        1: {"density": 10, "ambulance": False, "emergency": False, "emergency_type": "none"},
        2: {"density": 2, "ambulance": False, "emergency": False, "emergency_type": "none"},
    }
    d2 = control.controlfun(r2_data, lanes)
    assert d2["lane_no"] == 0

    # Round 3: Ambulance rushes into Lane 2
    r3_data = {
        0: {"density": 20, "ambulance": False, "emergency": False, "emergency_type": "none"},
        1: {"density": 20, "ambulance": False, "emergency": False, "emergency_type": "none"},
        2: {"density": 1, "ambulance": True, "emergency": True, "emergency_type": "ambulance"},
    }
    d3 = control.controlfun(r3_data, lanes)
    assert d3["lane_no"] == 2


@pytest.mark.scenario
def test_dual_emergency_tiebreaking_scenario():
    """
    Scenario: Ambulance in Lane 0, Firetruck in Lane 1, heavy traffic in Lane 2.
    Ambulance (tier 1 weight 2) must preempt Firetruck (tier 1 weight 1).
    """
    data = {
        0: {"density": 1, "ambulance": True, "emergency": True, "emergency_type": "ambulance"},
        1: {"density": 10, "ambulance": False, "emergency": True, "emergency_type": "firetruck"},
        2: {"density": 50, "ambulance": False, "emergency": False, "emergency_type": "none"},
    }
    res = control.controlfun(data, 3)
    assert res["lane_no"] == 0
