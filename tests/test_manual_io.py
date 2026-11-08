from unittest.mock import patch
import pytest
import manual_io


@pytest.mark.unit
@pytest.mark.parametrize("code,expected_amb,expected_emerg,expected_type", [
    ("0", False, False, "none"),
    ("1", True, True, "ambulance"),
    ("2", False, True, "firetruck"),
    ("5", True, True, "ambulance"),  # > 2 treated as Ambulance
])
def test_minput_emergency_codes(code, expected_amb, expected_emerg, expected_type):
    """Verify emergency input mapping for 0, 1, 2, and >2."""
    # Inputs: lane 1 density '5', lane 1 emergency `code`
    inputs = ["5", code]
    with patch("builtins.input", side_effect=inputs):
        with patch("manual_io.controlfun") as mock_control:
            mock_control.return_value = {"lane_no": 0, "signal": "Green"}
            res = manual_io.minput(1)

    assert res == {"lane_no": 0, "signal": "Green"}
    data_arg = mock_control.call_args[0][0]
    assert data_arg[0]["density"] == 5
    assert data_arg[0]["ambulance"] is expected_amb
    assert data_arg[0]["emergency"] is expected_emerg
    assert data_arg[0]["emergency_type"] == expected_type


@pytest.mark.unit
def test_minput_retry_on_invalid_input():
    """Negative values or non-integers prompt user to retry without crashing."""
    # Inputs:
    # Lane 1: invalid 'bad', negative '-3', valid '10'
    # Lane 1 emerg: invalid 'foo', valid '0'
    inputs = ["bad", "-3", "10", "foo", "0"]
    with patch("builtins.input", side_effect=inputs):
        res = manual_io.minput(1)

    assert res["lane_no"] == 0
    assert res["signal"] == "Green"


@pytest.mark.unit
def test_minput_keyboard_interrupt_handled_gracefully():
    """KeyboardInterrupt should print message and return None without traceback."""
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        res = manual_io.minput(2)
        assert res is None
