import json
import math
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

import cvfile
import gui


# ---------------------------------------------------------------------------
# 1. roi_key tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_roi_key_integer():
    assert cvfile.roi_key(0) == "cam0"
    assert cvfile.roi_key(1) == "cam1"
    assert cvfile.roi_key(42) == "cam42"


@pytest.mark.unit
def test_roi_key_digit_string():
    assert cvfile.roi_key("0") == "cam0"
    assert cvfile.roi_key("  2  ") == "cam2"
    assert cvfile.roi_key('"3"') == "cam3"


@pytest.mark.unit
def test_roi_key_filepath():
    assert cvfile.roi_key("video.mp4") == "video.mp4"
    assert cvfile.roi_key(r"C:\videos\lane1.mp4") == "lane1.mp4"
    assert cvfile.roi_key(r'"C:\videos\lane1.mp4"') == "lane1.mp4"
    assert cvfile.roi_key("'lane2.avi'") == "lane2.avi"
    assert cvfile.roi_key("/var/traffic/cam_north.mov") == "cam_north.mov"


# ---------------------------------------------------------------------------
# 2. validate_roi tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_validate_roi_invalid_counts_and_dimensions():
    assert cvfile.validate_roi(None, 640, 480) is None
    assert cvfile.validate_roi([], 640, 480) is None
    assert cvfile.validate_roi([[10, 10], [20, 20]], 640, 480) is None
    assert cvfile.validate_roi([[0, 0], [10, 0], [10, 10], [0, 10], [5, 5]], 640, 480) is None
    assert cvfile.validate_roi([[0, 0], [10, 0], [10, 10], [0, 10]], 0, 480) is None
    assert cvfile.validate_roi([[0, 0], [10, 0], [10, 10], [0, 10]], 640, -10) is None
    assert cvfile.validate_roi("not a list", 640, 480) is None
    assert cvfile.validate_roi([[0, "a"], [10, 0], [10, 10], [0, 10]], 640, 480) is None


@pytest.mark.unit
def test_validate_roi_clamping_and_types():
    raw = [[-20, -10], [700, -5], [800, 600], [-10, 500]]
    valid = cvfile.validate_roi(raw, 640, 480)
    assert valid is not None
    assert len(valid) == 4
    for pt in valid:
        assert isinstance(pt[0], int)
        assert isinstance(pt[1], int)
        assert 0 <= pt[0] <= 639
        assert 0 <= pt[1] <= 479


@pytest.mark.unit
def test_validate_roi_clockwise_ordering_for_bowtie():
    # Given bow-tie order (self-intersecting clicks)
    raw = [[100, 100], [300, 300], [300, 100], [100, 300]]
    ordered = cvfile.validate_roi(raw, 640, 480)
    assert ordered is not None
    # Calculate angles from centroid to verify strictly sorted
    cx = sum(p[0] for p in ordered) / 4.0
    cy = sum(p[1] for p in ordered) / 4.0
    angles = [math.atan2(p[1] - cy, p[0] - cx) for p in ordered]
    assert angles == sorted(angles)


@pytest.mark.unit
def test_validate_roi_area_threshold():
    # Frame area: 100 x 100 = 10,000. 1% threshold is 100.
    tiny = [[10, 10], [12, 10], [12, 12], [10, 12]]  # Area = 4
    assert cvfile.validate_roi(tiny, 100, 100) is None

    valid_box = [[10, 10], [50, 10], [50, 50], [10, 50]]  # Area = 1600 (16%)
    res = cvfile.validate_roi(valid_box, 100, 100)
    assert res is not None
    assert len(res) == 4


# ---------------------------------------------------------------------------
# 3. crop_roi tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_crop_roi_null_and_invalid():
    assert cvfile.crop_roi(None, [[0, 0], [10, 0], [10, 10], [0, 10]]) is None

    frame = np.ones((100, 100, 3), dtype=np.uint8) * 128
    res = cvfile.crop_roi(frame, None)
    assert np.array_equal(res, frame)

    res_inv = cvfile.crop_roi(frame, [[0, 0]])
    assert np.array_equal(res_inv, frame)


@pytest.mark.unit
def test_crop_roi_masks_outside_and_preserves_input():
    # 200 x 200 white frame
    frame = np.ones((200, 200, 3), dtype=np.uint8) * 255
    frame_copy = frame.copy()

    # Centered rectangular ROI: x in [50, 150], y in [50, 150]
    pts = [[50, 50], [150, 50], [150, 150], [50, 150]]
    cropped = cvfile.crop_roi(frame, pts)

    # Input frame must NOT be mutated
    assert np.array_equal(frame, frame_copy)

    # Cropped shape must equal bounding box (101 x 101, 3)
    assert cropped.shape == (101, 101, 3)
    # Center pixel inside polygon should remain white
    assert np.all(cropped[50, 50] == 255)


@pytest.mark.unit
def test_crop_roi_triangular_mask_zeros_outside_contour():
    # Trapezoid / triangle inside 100x100 frame
    frame = np.ones((100, 100, 3), dtype=np.uint8) * 255
    pts = [[10, 10], [90, 10], [60, 90], [40, 90]]
    cropped = cvfile.crop_roi(frame, pts)
    # Inside polygon should be white (255)
    assert np.all(cropped[10, 40] == 255)
    # Bottom-left corner of bounding rect (outside contour) should be masked to 0
    assert np.all(cropped[-1, 0] == 0)


# ---------------------------------------------------------------------------
# 4. canvas_to_frame and frame_to_canvas tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_coordinate_conversion_roundtrip():
    canvas_w, canvas_h = 320, 200
    frame_w, frame_h = 1920, 1080

    for cx, cy in [(0, 0), (160, 100), (319, 199)]:
        fx, fy = cvfile.canvas_to_frame(cx, cy, canvas_w, canvas_h, frame_w, frame_h)
        back_cx, back_cy = cvfile.frame_to_canvas(fx, fy, canvas_w, canvas_h, frame_w, frame_h)
        assert abs(back_cx - cx) <= 1
        assert abs(back_cy - cy) <= 1


@pytest.mark.unit
def test_coordinate_conversion_clamping_and_invalid():
    assert cvfile.canvas_to_frame(-10, -20, 320, 200, 640, 480) == (0, 0)
    assert cvfile.canvas_to_frame(500, 500, 320, 200, 640, 480) == (639, 479)
    assert cvfile.canvas_to_frame(10, 10, 0, 200, 640, 480) == (0, 0)
    assert cvfile.frame_to_canvas(10, 10, 320, 200, 0, 480) == (0, 0)


# ---------------------------------------------------------------------------
# 5. save_roi and load_roi tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_save_and_load_roi_preserves_config(tmp_path, monkeypatch):
    test_cfg_path = tmp_path / "config.json"
    initial_data = {
        "yellow_time": 5,
        "default_green": 30,
        "roi_points": {"cam1": [[1, 1], [2, 1], [2, 2], [1, 2]]}
    }
    with open(test_cfg_path, "w", encoding="utf-8") as f:
        json.dump(initial_data, f)

    monkeypatch.setattr(cvfile, "CONFIG_PATH", test_cfg_path)

    # Load existing cam1
    pts1 = cvfile.load_roi("cam1")
    assert pts1 == [[1, 1], [2, 1], [2, 2], [1, 2]]

    # Save new cam0
    new_pts = [[10, 10], [50, 10], [50, 50], [10, 50]]
    cvfile.save_roi(0, new_pts)

    # Verify cam0 loaded
    assert cvfile.load_roi(0) == new_pts

    # Verify other keys preserved
    with open(test_cfg_path, "r", encoding="utf-8") as f:
        saved_cfg = json.load(f)
    assert saved_cfg["yellow_time"] == 5
    assert saved_cfg["roi_points"]["cam1"] == [[1, 1], [2, 1], [2, 2], [1, 2]]
    assert saved_cfg["roi_points"]["cam0"] == new_pts

    # Clear cam0 with None
    cvfile.save_roi(0, None)
    assert cvfile.load_roi(0) is None
    with open(test_cfg_path, "r", encoding="utf-8") as f:
        saved_cfg2 = json.load(f)
    assert "cam0" not in saved_cfg2["roi_points"]
    assert "cam1" in saved_cfg2["roi_points"]


@pytest.mark.unit
def test_load_roi_handles_corrupt_or_missing_config(tmp_path, monkeypatch):
    missing_path = tmp_path / "non_existent.json"
    monkeypatch.setattr(cvfile, "CONFIG_PATH", missing_path)
    assert cvfile.load_roi("cam0") is None

    corrupt_path = tmp_path / "corrupt.json"
    with open(corrupt_path, "w", encoding="utf-8") as f:
        f.write("{invalid json")
    monkeypatch.setattr(cvfile, "CONFIG_PATH", corrupt_path)
    assert cvfile.load_roi("cam0") is None


# ---------------------------------------------------------------------------
# 6. Cameraf lazy ROI validation and setters
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_cameraf_lazy_roi_validation(fake_frame, tmp_path, monkeypatch):
    test_cfg_path = tmp_path / "config.json"
    raw_box = [[10, 10], [100, 10], [100, 100], [10, 100]]
    with open(test_cfg_path, "w", encoding="utf-8") as f:
        json.dump({"roi_points": {"cam0": raw_box}}, f)

    monkeypatch.setattr(cvfile, "CONFIG_PATH", test_cfg_path)

    with patch("cv2.VideoCapture") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, fake_frame)
        mock_cap_cls.return_value = mock_cap

        cam = cvfile.Cameraf(0, 0)
        # Before read_frame: lazy validation has not occurred
        assert cam.get_roi() is None

        # After read_frame: validated
        cam.read_frame()
        assert cam.get_roi() is not None
        assert len(cam.get_roi()) == 4


@pytest.mark.unit
def test_cameraf_set_roi_and_clear(fake_frame, tmp_path, monkeypatch):
    test_cfg_path = tmp_path / "config.json"
    with open(test_cfg_path, "w", encoding="utf-8") as f:
        json.dump({"roi_points": {}}, f)
    monkeypatch.setattr(cvfile, "CONFIG_PATH", test_cfg_path)

    with patch("cv2.VideoCapture") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, fake_frame)
        mock_cap_cls.return_value = mock_cap

        cam = cvfile.Cameraf(0, 0)
        cam.read_frame()

        valid_box = [[20, 20], [120, 20], [120, 120], [20, 120]]
        assert cam.set_roi(valid_box) is True
        assert cam.get_roi() is not None

        # Invalid box (area too small) fails and does not change ROI
        tiny_box = [[20, 20], [21, 20], [21, 21], [20, 21]]
        assert cam.set_roi(tiny_box) is False
        assert cam.get_roi() is not None

        # None clears ROI
        assert cam.set_roi(None) is True
        assert cam.get_roi() is None


# ---------------------------------------------------------------------------
# 7. scan_all_lanes with ROI
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_scan_all_lanes_crops_before_detection(fake_frame):
    cam = MagicMock()
    cam.last_frame = fake_frame.copy()
    cam.get_roi.return_value = [[50, 50], [150, 50], [150, 150], [50, 150]]

    captured_crop = {}

    def mock_uamodel(frame):
        captured_crop["shape"] = frame.shape
        return {"density": 2, "ambulance": False, "emergency": False, "emergency_type": "none"}

    with patch("cvfile.uamodel", side_effect=mock_uamodel):
        with patch("cvfile.detect_emergencies_batch", return_value={0: {"ambulance": False, "emergency": False, "emergency_type": "none"}}):
            lane_data, frames = cvfile.scan_all_lanes({0: cam}, live=True)

    # uamodel must have received cropped shape (bounding box ~101x101)
    assert captured_crop["shape"][0] < fake_frame.shape[0]
    assert captured_crop["shape"][1] < fake_frame.shape[1]

    # Returned frames dict must preserve FULL uncropped frame
    assert frames[0].shape == fake_frame.shape


# ---------------------------------------------------------------------------
# 8. Headless LaneCard and Dashboard ROI logic
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_lanecard_roi_edit_flow(fake_frame):
    card = object.__new__(gui.LaneCard)
    card.lane_no = 0
    card.show_feed = True
    card.is_editing = False
    card.draft_points = []
    card.frozen_frame = None
    card._log = MagicMock()
    card.update_frame = MagicMock()
    card._redraw_edit_canvas = MagicMock()
    card.btn_edit_roi = MagicMock()
    card._get_dashboard = MagicMock(return_value=None)

    cam = MagicMock()
    cam.last_frame = fake_frame.copy()
    cam.set_roi.return_value = True
    card.set_camera(cam)

    # 1. Start editing
    card.start_edit_roi()
    assert card.is_editing is True
    assert card.frozen_frame is not None
    assert card.draft_points == []

    # 2. Add 3 clicks
    event = MagicMock()
    for pt in [(10, 10), (100, 10), (100, 100)]:
        event.x, event.y = pt
        card._on_canvas_click(event)
    assert len(card.draft_points) == 3
    assert card.is_editing is True

    # 3. 4th click completes valid ROI
    event.x, event.y = (10, 100)
    card._on_canvas_click(event)
    assert card.is_editing is False
    assert card.draft_points == []
    assert cam.set_roi.called


@pytest.mark.unit
def test_lanecard_roi_invalid_4th_click_resets_points(fake_frame):
    card = object.__new__(gui.LaneCard)
    card.lane_no = 0
    card.show_feed = True
    card.is_editing = True
    card.draft_points = [(10, 10), (11, 10), (11, 11)]
    card.frozen_frame = fake_frame.copy()
    card._log = MagicMock()
    card._redraw_edit_canvas = MagicMock()
    card.btn_edit_roi = MagicMock()
    card._get_dashboard = MagicMock(return_value=None)

    cam = MagicMock()
    card.set_camera(cam)

    # 4th click makes tiny area (<1%)
    event = MagicMock()
    event.x, event.y = (10, 11)
    card._on_canvas_click(event)

    # Must stay in edit mode but clear draft points
    assert card.is_editing is True
    assert card.draft_points == []
    assert not cam.set_roi.called
    assert card._log.called


@pytest.mark.unit
def test_lanecard_cancel_and_clear_roi(fake_frame):
    card = object.__new__(gui.LaneCard)
    card.lane_no = 1
    card.show_feed = True
    card.is_editing = True
    card.draft_points = [(10, 10)]
    card.frozen_frame = fake_frame.copy()
    card._log = MagicMock()
    card.update_frame = MagicMock()
    card.btn_edit_roi = MagicMock()

    cam = MagicMock()
    cam.last_frame = fake_frame.copy()
    card.set_camera(cam)

    card.cancel_edit_roi()
    assert card.is_editing is False
    assert card.draft_points == []

    card.clear_roi()
    cam.set_roi.assert_called_with(None)


@pytest.mark.unit
def test_dashboard_skip_roi():
    dash = object.__new__(gui.Dashboard)
    dash.running = False
    dash.btn_skip_roi = MagicMock()
    dash._log = MagicMock()
    dash._boot_and_start_cycle = MagicMock()

    mock_card = MagicMock()
    mock_card.is_editing = True
    dash.cards = {0: mock_card}

    dash._on_skip_roi()

    mock_card.cancel_edit_roi.assert_called_once()
    dash.btn_skip_roi.pack_forget.assert_called_once()
    dash._boot_and_start_cycle.assert_called_once()


@pytest.mark.unit
def test_dashboard_lane_roi_configured_sequence():
    dash = object.__new__(gui.Dashboard)
    dash.running = False
    dash.btn_skip_roi = MagicMock()
    dash._log = MagicMock()
    dash._boot_and_start_cycle = MagicMock()

    cam0 = MagicMock()
    cam0.get_roi.return_value = [[0, 0], [1, 0], [1, 1], [0, 1]]
    cam1 = MagicMock()
    cam1.get_roi.return_value = None  # Lane 1 still unconfigured

    card0 = MagicMock()
    card1 = MagicMock()

    dash.cameras = {0: cam0, 1: cam1}
    dash.cards = {0: card0, 1: card1}

    # Lane 0 was configured; should advance to Lane 1
    dash._on_lane_roi_configured(0)
    card1.start_edit_roi.assert_called_once()
    assert not dash._boot_and_start_cycle.called

    # Now Lane 1 also configured
    cam1.get_roi.return_value = [[0, 0], [1, 0], [1, 1], [0, 1]]
    dash._on_lane_roi_configured(1)
    dash._boot_and_start_cycle.assert_called_once()


@pytest.mark.unit
def test_dashboard_lane_roi_configured_while_running_does_not_reboot():
    dash = object.__new__(gui.Dashboard)
    dash.running = True
    dash._log = MagicMock()
    dash._boot_and_start_cycle = MagicMock()

    dash._on_lane_roi_configured(0)
    assert not dash._boot_and_start_cycle.called
    assert dash._log.called


@pytest.mark.unit
def test_lanecard_toggle_edit_roi(fake_frame):
    card = object.__new__(gui.LaneCard)
    card.lane_no = 0
    card.show_feed = True
    card.is_editing = False
    card.draft_points = []
    card.frozen_frame = None
    card._log = MagicMock()
    card.update_frame = MagicMock()
    card._redraw_edit_canvas = MagicMock()
    card.btn_edit_roi = MagicMock()
    card._get_dashboard = MagicMock(return_value=None)

    cam = MagicMock()
    cam.last_frame = fake_frame.copy()
    card.set_camera(cam)

    # First toggle starts edit
    card.toggle_edit_roi()
    assert card.is_editing is True

    # Second toggle cancels edit
    card.toggle_edit_roi()
    assert card.is_editing is False


@pytest.mark.unit
def test_lanecard_start_edit_roi_guards():
    card = object.__new__(gui.LaneCard)
    card.lane_no = 0
    card.show_feed = False
    card.is_editing = False
    card.start_edit_roi()
    assert card.is_editing is False

    card.show_feed = True
    card._get_cam = MagicMock(return_value=None)
    card._log = MagicMock()
    card.start_edit_roi()
    assert card.is_editing is False
    assert card._log.called


@pytest.mark.unit
def test_cameraf_set_roi_when_last_frame_is_none():
    with patch("cv2.VideoCapture") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap_cls.return_value = mock_cap

        cam = cvfile.Cameraf(0, 0)
        assert cam.last_frame is None
        # set_roi with points should return False if no last_frame
        assert cam.set_roi([[10, 10], [50, 10], [50, 50], [10, 50]]) is False


@pytest.mark.unit
def test_cameraf_releasevid():
    with patch("cv2.VideoCapture") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap_cls.return_value = mock_cap

        cam = cvfile.Cameraf(0, 0)
        cam.releasevid()
        mock_cap.release.assert_called_once()


@pytest.mark.unit
def test_scan_all_lanes_with_list_input(fake_frame):
    cam = MagicMock()
    cam.read_frame.return_value = fake_frame.copy()
    cam.get_roi.return_value = None

    with patch("cvfile.uamodel", return_value={"density": 1, "ambulance": False, "emergency": False, "emergency_type": "none"}):
        with patch("cvfile.detect_emergencies_batch", return_value={0: {"ambulance": False, "emergency": False, "emergency_type": "none"}}):
            lane_data, frames = cvfile.scan_all_lanes([cam], live=False)

    assert 0 in lane_data
    assert 0 in frames


@pytest.mark.unit
def test_dashboard_init_cameras_triggers_roi_setup_when_unconfigured(fake_frame):
    dash = object.__new__(gui.Dashboard)
    dash.lanes = 1
    dash.mode = 0
    dash.paths = []
    dash.running = False
    dash.cameras = {}
    dash.btn_skip_roi = MagicMock()
    dash.status_var = MagicMock()
    dash._log = MagicMock()
    dash.after = MagicMock()

    mock_card = MagicMock()
    mock_card.is_editing = False
    dash.cards = {0: mock_card}

    with patch("gui.Cameraf") as mock_cam_cls:
        mock_cam = MagicMock()
        mock_cam.get_roi.return_value = None  # Not configured
        mock_cam.last_frame = fake_frame.copy()
        mock_cam_cls.return_value = mock_cam

        dash._init_cameras()

    # dash.after should be called with 0 and a callback
    assert dash.after.called
    callback = dash.after.call_args[0][1]
    # Execute callback on GUI
    callback()
    dash.btn_skip_roi.pack.assert_called_once()
    mock_card.start_edit_roi.assert_called_once()


@pytest.mark.unit
def test_dashboard_init_cameras_direct_boot_when_already_configured(fake_frame):
    dash = object.__new__(gui.Dashboard)
    dash.lanes = 1
    dash.mode = 0
    dash.paths = []
    dash.running = False
    dash.cameras = {}
    dash.after = MagicMock()
    dash._boot_and_start_cycle = MagicMock()

    mock_card = MagicMock()
    dash.cards = {0: mock_card}

    with patch("gui.Cameraf") as mock_cam_cls:
        mock_cam = MagicMock()
        mock_cam.get_roi.return_value = [[10, 10], [50, 10], [50, 50], [10, 50]]
        mock_cam.last_frame = fake_frame.copy()
        mock_cam_cls.return_value = mock_cam

        dash._init_cameras()

    # dash.after should be called with self._boot_and_start_cycle
    assert dash.after.called
    assert dash.after.call_args[0][1] == dash._boot_and_start_cycle

