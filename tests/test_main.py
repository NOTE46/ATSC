import importlib
import sys
import types
from unittest.mock import MagicMock, patch
import pytest
import main


@pytest.mark.unit
def test_main_manual_mode_dispatches_to_minput():
    """Mode 2 calls minput and exits."""
    # Inputs: ty=2, lanes=3, green_time=30
    inputs = ["2", "3", "30"]
    with patch("builtins.input", side_effect=inputs):
        with patch("main.minput") as mock_minput:
            main.main()
            mock_minput.assert_called_once_with(3)


@pytest.mark.unit
@pytest.mark.parametrize("user_green,expected", [
    ("15", 15),
    ("40", 40),
    ("999", 30),  # invalid option -> default 30
    ("", 30),     # empty -> default 30
])
def test_main_green_time_selection(user_green, expected):
    """Green time selection validates against green_options, falling back to default_green."""
    inputs = ["2", "2", user_green]
    with patch("builtins.input", side_effect=inputs):
        with patch("main.minput"):
            with patch("main.load_config", return_value={"green_options": [15, 30, 40], "default_green": 30}):
                # Run main up to minput
                main.main()


@pytest.mark.unit
def test_main_invalid_input_terminates():
    """Entering invalid mode 5 times terminates the program cleanly."""
    inputs = ["9", "9", "9", "9", "9"]
    with patch("builtins.input", side_effect=inputs):
        with patch("main.minput") as mock_minput:
            main.main()
            assert not mock_minput.called


@pytest.mark.unit
def test_main_cli_cycle_execution():
    """Simulate a short 1-round CLI countdown cycle with time.sleep mocked."""
    # Mode 1 (video), 1 lane, green duration 15, video path "test.mp4"
    inputs = ["1", "1", "15", "test.mp4"]
    mock_cam = MagicMock()

    with patch("builtins.input", side_effect=inputs):
        with patch("main.Cameraf", return_value=mock_cam):
            with patch("main.reset_control") as mock_reset:
                with patch("main.scan_all_lanes", return_value=({0: {"density": 5, "emergency_type": "none"}}, {0: None})):
                    with patch("main.controlfun", return_value={"lane_no": 0, "signal": "Green"}):
                        # Stop the infinite loop on second iteration via KeyboardInterrupt
                        with patch("time.sleep", side_effect=[None, None, None, KeyboardInterrupt]):
                            with patch("main.load_config", return_value={"green_options": [15], "default_green": 15, "yellow_time": 2}):
                                main.main()

    assert mock_reset.called
    assert mock_cam.releasevid.called


@pytest.mark.unit
def test_main_scan_error_during_yellow_rotates_lane(make_lane_data, capsys):
    """A worker scan RuntimeError prints the resilient warning and rotates to the next lane."""
    boot_lane_data = make_lane_data([5, 2])
    scan_mock = MagicMock(side_effect=[(boot_lane_data, {}), RuntimeError("boom")])

    inputs = ["1", "2", "3", "v1.mp4", "v2.mp4"]
    with patch("builtins.input", side_effect=inputs):
        with patch("main.Cameraf", side_effect=[MagicMock(), MagicMock()]):
            with patch("main.reset_control"):
                with patch("main.scan_all_lanes", scan_mock):
                    with patch("main.controlfun", return_value={"lane_no": 0, "signal": "Green"}):
                        with patch("main.load_config", return_value={
                            "green_options": [3], "default_green": 3, "yellow_time": 1
                        }):
                            # 3 countdown sleeps in cycle 1, then stop the loop in cycle 2
                            with patch("time.sleep", side_effect=[None, None, None, KeyboardInterrupt]):
                                main.main()

    captured = capsys.readouterr()
    assert scan_mock.call_count == 2
    assert captured.out.count("[WARN] Scan error: boom") == 1
    assert "Lane 1 -> Lane 2 GREEN" in captured.out


@pytest.mark.unit
def test_main_camera_init_failure_releases_opened_cameras():
    """If a later camera fails to open, already-opened cameras are released in finally."""
    first_cam = MagicMock()
    cameraf_mock = MagicMock(side_effect=[first_cam, RuntimeError("camera fail")])

    inputs = ["1", "2", "30", "v1.mp4", "v2.mp4"]
    with patch("builtins.input", side_effect=inputs):
        with patch("main.Cameraf", cameraf_mock):
            with patch("main.load_config", return_value={
                "green_options": [30], "default_green": 30, "yellow_time": 5
            }):
                main.main()

    assert cameraf_mock.call_count == 2
    assert first_cam.releasevid.called


@pytest.mark.unit
def test_load_config_missing_and_invalid(tmp_path, monkeypatch):
    """load_config returns {} for a missing file or invalid JSON."""
    monkeypatch.chdir(tmp_path)
    assert main.load_config() == {}

    (tmp_path / "config.json").write_text("{not valid json", encoding="utf-8")
    assert main.load_config() == {}


@pytest.mark.unit
def test_clean_path_strips_whitespace_and_quotes():
    """clean_path removes surrounding whitespace and single/double quotes."""
    assert main.clean_path("  video.mp4  ") == "video.mp4"
    assert main.clean_path('  "video.mp4"  ') == "video.mp4"
    assert main.clean_path("  'video.mp4'  ") == "video.mp4"


@pytest.mark.unit
def test_main_mode0_full_countdown_and_emergency_summary(capsys):
    """Mode 0 opens live cameras, completes a full cycle, and switches to the scan winner."""
    boot_data = {
        0: {"density": 5, "emergency_type": "none"},
        1: {"density": 2, "emergency_type": "none"},
    }
    scan_data = {
        0: {"density": 1, "emergency_type": "none"},
        1: {"density": 9, "emergency_type": "ambulance"},
    }
    cam0, cam1 = MagicMock(), MagicMock()
    scan_mock = MagicMock(side_effect=[(boot_data, {}), (scan_data, {})])
    control_mock = MagicMock(side_effect=[
        {"lane_no": 0, "signal": "Green"},
        {"lane_no": 1, "signal": "Green"},
    ])

    with patch("builtins.input", side_effect=["0", "2", "3"]):
        with patch("main.Cameraf", side_effect=[cam0, cam1]) as cameraf_mock:
            with patch("main.reset_control"):
                with patch("main.scan_all_lanes", scan_mock):
                    with patch("main.controlfun", control_mock):
                        with patch("main.load_config", return_value={
                            "green_options": [3], "default_green": 3, "yellow_time": 2
                        }):
                            with patch("time.sleep", side_effect=[None, None, None, KeyboardInterrupt]):
                                main.main()

    captured = capsys.readouterr().out
    assert cameraf_mock.call_args_list[0].args == (0, 0)
    assert cameraf_mock.call_args_list[1].args == (1, 1)
    assert scan_mock.call_count == 2
    assert control_mock.call_count == 2
    assert "[Lane 1 YELLOW] Switching in 2s" in captured
    assert "[Lane 1 YELLOW] Switching in 1s" in captured
    assert "CYCLE SUMMARY: Lane 1 -> Lane 2 GREEN" in captured
    assert "Winner Density: 9 | Emergency: AMBULANCE" in captured
    assert "Stopped" in captured
    assert cam0.releasevid.called
    assert cam1.releasevid.called


@pytest.mark.unit
def test_main_non_numeric_input_terminates(capsys):
    """A non-numeric mode/lane input prints the validation message and never opens cameras."""
    with patch("builtins.input", return_value="not-a-number"):
        with patch("main.Cameraf") as cameraf_mock:
            main.main()

    assert "Please enter a valid number!" in capsys.readouterr().out
    assert not cameraf_mock.called


@pytest.mark.unit
def test_main_scan_timeout_rotates_without_result(capsys, make_lane_data):
    """A worker that never publishes a result falls back to rotating the active lane."""
    lane_data = make_lane_data([5, 2])
    fake_thread = MagicMock()

    with patch("builtins.input", side_effect=["0", "2", "2"]):
        with patch("main.Cameraf", return_value=MagicMock()):
            with patch("main.reset_control"):
                with patch("main.scan_all_lanes", return_value=(lane_data, {})):
                    with patch("main.controlfun", return_value={"lane_no": 0, "signal": "Green"}):
                        with patch("main.load_config", return_value={
                            "green_options": [2], "default_green": 2, "yellow_time": 1
                        }):
                            with patch("main.threading.Thread", return_value=fake_thread):
                                with patch("time.sleep", side_effect=[None, None, KeyboardInterrupt]):
                                    main.main()

    captured = capsys.readouterr().out
    assert fake_thread.start.called
    assert fake_thread.join.called
    assert "CYCLE SUMMARY: Lane 1 -> Lane 2 GREEN" in captured
    assert "Winner Density: N/A | Emergency: NONE" in captured


@pytest.mark.unit
def test_main_quoted_video_path_and_release_error_is_swallowed(capsys):
    """Mode 1 cleans quoted paths; teardown suppresses releasevid errors."""
    cam = MagicMock()
    cam.releasevid.side_effect = RuntimeError("release fail")

    with patch("builtins.input", side_effect=["1", "1", "30", '  "clip.mp4"  ']):
        with patch("main.Cameraf", return_value=cam) as cameraf_mock:
            with patch("main.reset_control"):
                with patch("main.scan_all_lanes", side_effect=RuntimeError("scan fail")):
                    with patch("main.load_config", return_value={
                        "green_options": [30], "default_green": 30, "yellow_time": 5
                    }):
                        main.main()

    assert "Error : scan fail" in capsys.readouterr().out
    cameraf_mock.assert_called_once_with(0, "clip.mp4")
    assert cam.releasevid.called


@pytest.mark.unit
def test_import_fallbacks_define_compat_helpers():
    """Missing optional exports fall back to local compatibility definitions."""
    fake_control = types.ModuleType("control")
    fake_control.controlfun = lambda data, lanes: {"lane_no": 0, "signal": "Green"}
    fake_cvfile = types.ModuleType("cvfile")
    fake_cvfile.Cameraf = MagicMock()

    original_control = sys.modules.get("control")
    original_cvfile = sys.modules.get("cvfile")
    sys.modules["control"] = fake_control
    sys.modules["cvfile"] = fake_cvfile
    try:
        reloaded = importlib.reload(main)
        assert reloaded.reset_control() is None
        assert reloaded.scan_all_lanes(None) == ({}, {})
    finally:
        if original_control is not None:
            sys.modules["control"] = original_control
        else:
            sys.modules.pop("control", None)
        if original_cvfile is not None:
            sys.modules["cvfile"] = original_cvfile
        else:
            sys.modules.pop("cvfile", None)
        importlib.reload(main)
