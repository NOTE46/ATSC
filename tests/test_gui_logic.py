import json
import os
import tkinter as tk
from unittest.mock import MagicMock, patch
import numpy as np
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


@pytest.mark.unit
def test_setupscreen_detector_configuration():
    """SetupScreen configures detector via set_detector_config on start."""
    screen = object.__new__(gui.SetupScreen)
    screen.mode_var = MagicMock()
    screen.mode_var.get.return_value = 0
    screen.lane_var = MagicMock()
    screen.lane_var.get.return_value = 2
    screen.green_var = MagicMock()
    screen.green_var.get.return_value = 30
    screen.on_start = MagicMock()

    screen.provider_var = MagicMock()
    screen.provider_var.get.return_value = "groq"
    screen.model_combo = MagicMock()
    screen.model_combo.get.return_value = "qwen/qwen3.8-27b"
    screen.btn_refresh_models = MagicMock()

    with patch("gui.set_detector_config") as mock_set_det:
        screen._start()
        mock_set_det.assert_called_once_with(
            detector="vision", provider="groq", vision_model="qwen/qwen3.8-27b"
        )
        screen.on_start.assert_called_once_with(0, 2, [], 30)

    # Test Local YOLO choice
    screen.provider_var.get.return_value = "yolo"
    screen.model_combo.get.return_value = "Model/custom.pt"
    with patch("gui.set_detector_config") as mock_set_det2:
        screen._start()
        mock_set_det2.assert_called_once_with(
            detector="yolo", ambulance_model="Model/custom.pt"
        )


@pytest.mark.unit
def test_dashboard_startup_logs_detector_status(monkeypatch):
    """Dashboard logs detector provider and model, including fallback indicator when key is missing."""
    dash = object.__new__(gui.Dashboard)
    dash.running = True
    dash.active_lane = 0
    dash.green_time = 30
    dash.time_left = 30
    dash.lanes = 1
    dash.lane_data = {0: {"density": 3, "emergency_type": "none"}}
    dash.cards = {0: MagicMock()}
    dash.status_var = MagicMock()
    dash._log = MagicMock()
    dash._video_loop = MagicMock()
    dash.after = MagicMock()
    dash.cameras = {}

    with patch("gui.scan_all_lanes", return_value=({0: {"density": 3, "emergency_type": "none"}}, {})):
        with patch("gui.controlfun", return_value={"lane_no": 0, "signal": "Green"}):
            # 1. Vision with key present
            with patch("gui.get_detector_config", return_value={
                "detector": "vision",
                "provider": "groq",
                "active_model": "qwen/qwen3.8-27b",
                "has_api_key": True,
                "ambulance_model": "Model/best.pt"
            }):
                t = dash._boot_and_start_cycle()
                t.join(timeout=2)
                start_gui_fn = dash.after.call_args[0][1]
                start_gui_fn()
                dash._log.assert_any_call("Detector: GROQ (qwen/qwen3.8-27b)")

            # 2. Vision without key
            dash._log.reset_mock()
            dash.after.reset_mock()
            with patch("gui.get_detector_config", return_value={
                "detector": "vision",
                "provider": "gemini",
                "active_model": "gemini-3.5-flash-lite",
                "has_api_key": False,
                "ambulance_model": "Model/best.pt"
            }):
                t = dash._boot_and_start_cycle()
                t.join(timeout=2)
                start_gui_fn = dash.after.call_args[0][1]
                start_gui_fn()
                dash._log.assert_any_call("Detector: GEMINI (no key -> fallback Model/best.pt)")

            # 3. Local YOLO
            dash._log.reset_mock()
            dash.after.reset_mock()
            with patch("gui.get_detector_config", return_value={
                "detector": "yolo",
                "provider": "gemini",
                "active_model": "Model/best.pt",
                "has_api_key": False,
                "ambulance_model": "Model/best.pt"
            }):
                t = dash._boot_and_start_cycle()
                t.join(timeout=2)
                start_gui_fn = dash.after.call_args[0][1]
                start_gui_fn()
                dash._log.assert_any_call("Detector: LOCAL (Model/best.pt)")


@pytest.mark.unit
def test_pause_holds_timer_and_resume_decrements():
    """While paused, _tick_timer reschedules without decrementing time_left."""
    dash = object.__new__(gui.Dashboard)
    dash.running = True
    dash._stopped = False
    dash.paused = True
    dash.time_left = 10
    dash.after = MagicMock()
    dash.status_var = MagicMock()

    dash._tick_timer()

    assert dash.time_left == 10
    dash.after.assert_called_once_with(1000, dash._tick_timer)

    dash.paused = False
    dash.green_time = 30
    dash.yellow_time = 5
    dash.active_lane = 0
    dash.current_signal = "GREEN"
    dash.lane_data = {0: {"density": 3, "emergency_type": "none"}}
    dash.cards = {0: MagicMock()}
    dash.after.reset_mock()

    dash._tick_timer()

    assert dash.time_left == 9


@pytest.mark.unit
def test_toggle_pause_flips_state_and_status():
    """The space handler toggles paused and updates the status readout."""
    dash = object.__new__(gui.Dashboard)
    dash.running = True
    dash.paused = False
    dash.active_lane = 0
    dash.current_signal = "GREEN"
    dash.time_left = 12
    dash._manual_dialog = None
    dash.status_var = MagicMock()
    dash._log = MagicMock()
    dash.winfo_exists = MagicMock(return_value=True)
    dash.focus_get = MagicMock(return_value=None)

    dash._toggle_pause()
    assert dash.paused is True
    assert "PAUSED" in dash.status_var.set.call_args[0][0]

    dash._toggle_pause()
    assert dash.paused is False


@pytest.mark.unit
def test_escape_cancels_roi_edit_without_stopping():
    """Esc while editing cancels the ROI draft and never prompts or stops."""
    dash = object.__new__(gui.Dashboard)
    dash.running = True
    dash.winfo_exists = MagicMock(return_value=True)
    card = MagicMock()
    card.is_editing = True
    dash.cards = {0: card}
    dash._stop = MagicMock()

    with patch("gui.messagebox.askyesno") as ask:
        dash._on_escape()

    card.cancel_edit_roi.assert_called_once()
    dash._stop.assert_not_called()
    ask.assert_not_called()


@pytest.mark.unit
def test_escape_confirmation_controls_stop():
    """Esc stops only when the confirmation dialog returns True."""
    dash = object.__new__(gui.Dashboard)
    dash.running = True
    dash.winfo_exists = MagicMock(return_value=True)
    dash.cards = {}
    dash.on_stop = MagicMock()
    dash.status_var = MagicMock()
    dash.cameras = {}
    dash.btn_skip_roi = None
    dash._timer_job = None
    dash._video_job = None
    dash.winfo_toplevel = MagicMock(side_effect=RuntimeError)

    with patch("gui.messagebox.askyesno", return_value=False):
        dash._on_escape()
    assert dash.running is True
    dash.on_stop.assert_not_called()

    with patch("gui.messagebox.askyesno", return_value=True):
        dash._on_escape()
    assert dash.running is False
    dash.on_stop.assert_called_once()


@pytest.mark.unit
def test_manual_dialog_firetruck_sets_ambulance_and_emergency():
    """A firetruck submission sets both legacy emergency flags and its type."""
    dlg = object.__new__(gui.ManualDialog)
    dlg.lanes = 1
    entry = MagicMock()
    entry.get.return_value = "4"
    dlg.entries = {0: entry}
    var = MagicMock()
    var.get.return_value = "firetruck"
    dlg.emerg_vars = {0: var}
    dlg.on_submit = MagicMock()
    dlg.destroy = MagicMock()

    dlg._submit()

    dlg.on_submit.assert_called_once()
    assert dlg.on_submit.call_args[0][0] == {
        0: {"density": 4, "ambulance": True, "emergency": True,
            "emergency_type": "firetruck"},
    }


@pytest.mark.unit
def test_stop_before_boot_finishes_never_sets_running():
    """A stop that lands while the boot scan runs keeps running False."""
    dash = object.__new__(gui.Dashboard)
    dash.lanes = 1
    dash.cameras = {}
    dash.running = False
    dash._stopped = False
    dash._log = MagicMock()
    dash.after = MagicMock()
    dash.btn_skip_roi = MagicMock()

    def scan_during_stop(cameras, live=False):
        dash._stopped = True
        return {0: {"density": 1}}, {}

    with patch("gui.reset_control"):
        with patch("gui.scan_all_lanes", side_effect=scan_during_stop):
            with patch("gui.controlfun", return_value={"lane_no": 0}):
                thread = dash._boot_and_start_cycle()
                thread.join(timeout=2)

    assert dash.running is False
    dash.after.assert_not_called()


@pytest.mark.unit
def test_validate_timing_rejects_invalid_values():
    """Timing validation rejects bools, non-ints, bad yellow/green and thresholds."""
    assert gui.validate_timing("15", "30", "3", [15, 30, 40])[0] is None
    assert gui.validate_timing("5", "30", "3", [15, 30, 40]) == (
        {"yellow_time": 5, "default_green": 30, "starvation_threshold": 3}, None)
    assert gui.validate_timing(True, 30, 3, [15, 30])[0] is None
    assert gui.validate_timing("5", "99", "3", [15, 30])[0] is None
    assert gui.validate_timing("5", "30", "0", [15, 30])[0] is None


@pytest.mark.unit
def test_save_config_updates_preserves_roi_points(tmp_path, monkeypatch):
    """Atomic config saves merge updates without dropping roi_points."""
    cfg = tmp_path / "config.json"
    roi = {"cam0": [[1, 2], [3, 4], [5, 6], [7, 8]]}
    cfg.write_text(json.dumps({"roi_points": roi, "yellow_time": 5}),
                   encoding="utf-8")
    monkeypatch.setattr(gui, "CONFIG_PATH", cfg)

    gui.save_config_updates({"yellow_time": 4})

    saved = json.loads(cfg.read_text(encoding="utf-8"))
    assert saved["roi_points"] == roi
    assert saved["yellow_time"] == 4


@pytest.mark.unit
def test_session_key_is_memory_only_and_never_saved(tmp_path, monkeypatch):
    """Session keys go to os.environ only, never into config.json."""
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(gui, "CONFIG_PATH", cfg)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    assert gui.set_session_key("gemini", "secret-key-123") is True
    assert os.environ["GEMINI_API_KEY"] == "secret-key-123"

    gui.save_config_updates({"yellow_time": 4})
    assert "secret-key-123" not in cfg.read_text(encoding="utf-8")
    assert gui.set_session_key("yolo", "ignored") is False


@pytest.mark.unit
def test_pending_yellow_applies_on_next_cycle_only():
    """A settings yellow change waits for the cycle switch, keeping the scan trigger."""
    dash = object.__new__(gui.Dashboard)
    dash.running = True
    dash._stopped = False
    dash.paused = False
    dash.mode = 0
    dash.lanes = 2
    dash.green_time = 30
    dash.yellow_time = 5
    dash.time_left = 6
    dash.scanning = False
    dash.active_lane = 0
    dash.current_signal = "GREEN"
    dash.next_winner = 1
    dash.next_lane_data = {0: {"density": 1}, 1: {"density": 9}}
    dash.lane_data = {0: {"density": 1}, 1: {"density": 9}}
    dash.cards = {0: MagicMock(), 1: MagicMock()}
    dash.status_var = MagicMock()
    dash.after = MagicMock()
    dash._log = MagicMock()
    dash._pending_yellow_time = 4

    with patch.object(gui.threading, "Thread"):
        dash._tick_timer()
    assert dash.time_left == 5
    assert dash.yellow_time == 5

    dash.time_left = 0
    dash.scanning = False
    dash.next_winner = 1
    dash.next_lane_data = {0: {"density": 1}, 1: {"density": 9}}
    dash._tick_timer()
    assert dash.active_lane == 1
    assert dash.yellow_time == 4
    assert dash._pending_yellow_time is None


@pytest.mark.unit
def test_lanecard_canvas_dims_fallback_when_unrealized():
    """An unmapped LaneCard canvas falls back to the exact 320x200 headless size."""
    card = object.__new__(gui.LaneCard)
    card._canvas_dims = None
    assert card._get_canvas_dims() == (320, 200)


@pytest.mark.unit
def test_lanecard_letterbox_click_mapping_ignores_black_bars():
    """Clicks in letterbox bars are ignored; image clicks map to frame coordinates."""
    card = object.__new__(gui.LaneCard)
    card.show_feed = True
    card.lane_no = 0
    card.is_editing = True
    card.draft_points = []
    card.frozen_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    card._canvas_dims = (800, 600)
    card.canvas = MagicMock()
    card._redraw_edit_canvas = MagicMock()
    card._log = MagicMock()

    black_bar = MagicMock()
    black_bar.x, black_bar.y = 400, 10
    card._on_canvas_click(black_bar)
    assert card.draft_points == []

    inside = MagicMock()
    inside.x, inside.y = 400, 300
    card._on_canvas_click(inside)
    assert card.draft_points == [(400, 225)]
    assert gui.canvas_to_frame(400, 225, 800, 450, 1920, 1080) == (960, 540)


@pytest.mark.unit
def test_body_box_narrow_window_uses_full_width():
    """A narrow canvas uses full width and the larger of canvas/content height."""
    assert gui.body_box(800, 600, 500, 1100) == (0, 800, 600)


@pytest.mark.unit
def test_body_box_fullscreen_is_full_bleed():
    """A large canvas uses the full width and height with no floating island."""
    assert gui.body_box(2500, 1300, 500, 1100) == (0, 2500, 1300)


@pytest.mark.unit
def test_body_box_scrolls_when_content_is_taller():
    """Content taller than the canvas sets the window height to the content."""
    assert gui.body_box(1000, 400, 900, 1100) == (0, 1000, 900)


@pytest.mark.unit
def test_draw_preview_tile_skips_tiny_and_centers_text():
    """Tiles at or below 10px are skipped; realized tiles center one label."""
    screen = object.__new__(gui.SetupScreen)
    tile = MagicMock()
    screen._preview_canvases = [tile]
    screen.mode_var = MagicMock()
    screen.mode_var.get.return_value = 0
    screen._path_entries = []

    screen._draw_preview_tile(0, 5, 120)
    screen._draw_preview_tile(0, 8, 8)
    tile.create_text.assert_not_called()
    tile.delete.assert_not_called()

    screen._draw_preview_tile(0, 300, 120)
    tile.delete.assert_called_once_with("all")
    rect_args, rect_kwargs = tile.create_rectangle.call_args_list[0]
    assert rect_args == (47, 2, 253, 118)
    assert rect_kwargs["fill"] == gui.Theme.get("INPUT_BG")
    assert rect_kwargs["outline"] == gui.Theme.get("BORDER")
    assert rect_kwargs["width"] == 1
    badge = next(c for c in tile.create_text.call_args_list
                 if c.args == (150, 60))
    assert badge.kwargs["text"] == "L1  ● CAM 0"
    assert badge.kwargs["font"] == gui.FONT_MONO


@pytest.mark.unit
def test_draw_preview_tile_locks_16_9_in_tall_cell():
    """A tall cell gets a narrower centered 16:9 box, never a stretched tile."""
    screen = object.__new__(gui.SetupScreen)
    tile = MagicMock()
    screen._preview_canvases = [tile]
    screen.mode_var = MagicMock()
    screen.mode_var.get.return_value = 0
    screen._path_entries = []

    screen._draw_preview_tile(0, 200, 400)
    args, _ = tile.create_rectangle.call_args_list[0]
    assert args == (2, 145, 198, 255)


@pytest.mark.unit
def test_tile_row_h_is_width_driven_and_capped():
    """Row height follows holder width and the optional 16:9 cap."""
    assert gui.tile_row_h(10) is None
    assert gui.tile_row_h(700, 6, 480) == 202
    assert gui.tile_row_h(1000, 6, 480) == 282
    assert gui.tile_row_h(2000, 6, 480) == 282
    assert gui.tile_row_h(1000, 6) == 286


@pytest.mark.unit
def test_sb_needed_off_inside_margin():
    """A hidden scrollbar stays hidden while the overflow is within the margin."""
    assert gui.sb_needed(False, 510, 500) is False


@pytest.mark.unit
def test_sb_needed_off_past_margin():
    """A hidden scrollbar shows once the overflow passes the margin."""
    assert gui.sb_needed(False, 515, 500) is True


@pytest.mark.unit
def test_sb_needed_on_inside_margin():
    """A visible scrollbar stays visible while the overflow is within the margin."""
    assert gui.sb_needed(True, 490, 500) is True


@pytest.mark.unit
def test_sb_needed_on_past_margin():
    """A visible scrollbar hides once the content fits past the margin."""
    assert gui.sb_needed(True, 485, 500) is False


@pytest.mark.unit
def test_resize_tiles_does_not_mutate_canvas_geometry():
    """The grid sizes tiles; _resize_tiles stays a compatibility no-op."""
    class _FakeTile:
        def __init__(self):
            self.calls = []

        def configure(self, **kw):
            self.calls.append(kw)

    screen = object.__new__(gui.SetupScreen)
    screen.preview_holder = MagicMock()
    screen.preview_holder.winfo_width.return_value = 1000
    tiles = [_FakeTile(), _FakeTile()]
    screen._preview_canvases = tiles
    screen._tile_size = None

    screen._resize_tiles()
    screen._resize_tiles()
    for tile in tiles:
        assert tile.calls == []


@pytest.mark.unit
def test_green_duration_radio_updates_summary():
    """Clicking a GREEN DURATION pill refreshes the SUMMARY Green value."""
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is not available")
    root.withdraw()
    screen = None
    try:
        screen = gui.SetupScreen(root, on_start=lambda *a: None)

        def walk(widget):
            for child in widget.winfo_children():
                yield child
                yield from walk(child)

        radios = [w for w in walk(screen.col_left)
                  if isinstance(w, tk.Radiobutton) and w.cget("text") == "60s"]
        assert radios, "60s green duration radio not found"
        radios[0].invoke()
        assert screen.green_var.get() == 60
        assert screen._summary_vars["Green"][0].get() == "60s"
    finally:
        if screen is not None:
            screen.destroy()
        root.destroy()


@pytest.mark.unit
def test_setup_screen_initial_summary_and_attributes():
    """A fresh SetupScreen fills SUMMARY and exposes every required attribute."""
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display is not available")
    root.withdraw()
    screen = None
    try:
        screen = gui.SetupScreen(root, on_start=lambda *a: None)
        assert screen._summary_vars["Mode"][0].get() == "Live Camera"
        assert screen._summary_vars["Lanes"][0].get() == "2"
        assert screen._summary_vars["Green"][0].get() == f"{gui.DEFAULT_GREEN}s"
        assert screen._summary_vars["Status"][0].get() == "● ready"
        for name in ("engine_card", "path_card", "canvas", "body_frame",
                     "col_left", "col_right", "mode_var", "lane_var",
                     "green_var", "provider_var", "model_combo",
                     "btn_refresh_models", "start_btn"):
            assert hasattr(screen, name), name
    finally:
        if screen is not None:
            screen.destroy()
        root.destroy()

