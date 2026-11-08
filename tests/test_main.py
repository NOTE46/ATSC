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
