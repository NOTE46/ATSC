from unittest.mock import MagicMock, patch
import pytest
import gui


@pytest.mark.unit
def test_bg_scan_success():
    """_bg_scan updates next_winner and next_lane_data and clears scanning flag."""
    dash = object.__new__(gui.Dashboard)
    dash.cameras = {}
    dash.lanes = 2
    dash.active_lane = 0
    dash.lane_data = {}
    dash.scanning = True
    dash.next_winner = None
    dash.next_lane_data = None
    dash._log = MagicMock()

    mock_lane_data = {
        0: {"density": 1, "emergency_type": "none"},
        1: {"density": 10, "emergency_type": "none"},
    }
    with patch("gui.scan_all_lanes", return_value=(mock_lane_data, {})):
        with patch("gui.controlfun", return_value={"lane_no": 1, "signal": "Green"}):
            dash._bg_scan()

    assert dash.next_winner == 1
    assert dash.next_lane_data == mock_lane_data
    assert dash.scanning is False


@pytest.mark.unit
def test_bg_scan_exception_prevent_yellow_freeze():
    """If scan raises exception, log error, fall back to next lane rotation, and clear scanning."""
    dash = object.__new__(gui.Dashboard)
    dash.cameras = {}
    dash.lanes = 3
    dash.active_lane = 1
    dash.lane_data = {0: {"density": 2}, 1: {"density": 3}, 2: {"density": 0}}
    dash.scanning = True
    dash.next_winner = None
    dash.next_lane_data = None
    dash._log = MagicMock()

    with patch("gui.scan_all_lanes", side_effect=RuntimeError("Camera disconnected")):
        dash._bg_scan()

    assert dash.scanning is False
    assert dash.next_winner == 2  # (1 + 1) % 3
    assert dash.next_lane_data == dash.lane_data
    assert dash._log.called


@pytest.mark.unit
def test_tick_timer_holds_on_yellow_while_scanning():
    """When time_left <= 0 and scanning is True, hold on YELLOW (0s) and reschedule in 200ms."""
    dash = object.__new__(gui.Dashboard)
    dash.running = True
    dash.time_left = 0
    dash.scanning = True
    dash.active_lane = 0
    dash.lane_data = {0: {"density": 5, "ambulance": False, "emergency_type": "none"}}
    dash.cards = {0: MagicMock()}
    dash.status_var = MagicMock()
    dash.after = MagicMock()

    dash._tick_timer()

    assert dash.current_signal == "YELLOW"
    dash.cards[0].set_signal.assert_called_once()
    assert dash.cards[0].set_signal.call_args[1]["time_left"] == 0
    dash.after.assert_called_once_with(200, dash._tick_timer)


@pytest.mark.unit
def test_tick_timer_switches_when_scan_finished():
    """When time_left <= 0 and scanning is False, switch active lane to next_winner."""
    dash = object.__new__(gui.Dashboard)
    dash.running = True
    dash.time_left = 0
    dash.scanning = False
    dash.active_lane = 0
    dash.lanes = 2
    dash.green_time = 30
    dash.next_winner = 1
    dash.next_lane_data = {0: {"density": 0}, 1: {"density": 8}}
    dash.lane_data = {}
    dash.cards = {0: MagicMock(), 1: MagicMock()}
    dash.status_var = MagicMock()
    dash.after = MagicMock()
    dash._log = MagicMock()

    dash._tick_timer()

    assert dash.active_lane == 1
    assert dash.time_left == 30
    assert dash.current_signal == "GREEN"
    assert dash.next_winner is None


@pytest.mark.unit
def test_manual_dialog_close_safeguard():
    """Closing ManualDialog ('X' button) sends fallback data so manual mode never hangs."""
    dlg = object.__new__(gui.ManualDialog)
    dlg.lanes = 2
    dlg.initial_data = {0: {"density": 4, "emergency_type": "none"}, 1: {"density": 2, "emergency_type": "none"}}
    dlg.on_submit = MagicMock()
    dlg.destroy = MagicMock()

    dlg._on_close()

    assert dlg.destroy.called
    dlg.on_submit.assert_called_once_with(dlg.initial_data)
