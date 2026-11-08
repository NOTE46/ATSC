from unittest.mock import MagicMock, patch
import numpy as np
import pytest
import cvfile


@pytest.mark.unit
def test_cameraf_init_has_lock_and_last_frame():
    """Cameraf initializes with _lock, last_frame=None, and opens video source."""
    with patch("cv2.VideoCapture") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap_cls.return_value = mock_cap

        cam = cvfile.Cameraf(0, 0)
        assert hasattr(cam, "_lock")
        assert cam.last_frame is None
        assert cam.lane_no == 0


@pytest.mark.unit
def test_cameraf_init_raises_runtime_error_if_not_opened():
    """If video capture fails to open, raise RuntimeError."""
    with patch("cv2.VideoCapture") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_cap_cls.return_value = mock_cap

        with pytest.raises(RuntimeError):
            cvfile.Cameraf(1, "invalid_video.mp4")


@pytest.mark.unit
def test_cameraf_read_frame_success(fake_frame):
    """read_frame returns frame and stores it in self.last_frame."""
    with patch("cv2.VideoCapture") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, fake_frame)
        mock_cap_cls.return_value = mock_cap

        cam = cvfile.Cameraf(0, 0)
        frame = cam.read_frame()

        assert frame is not None
        assert cam.last_frame is not None
        assert np.array_equal(frame, fake_frame)


@pytest.mark.unit
def test_cameraf_read_frame_loops_at_eof(fake_frame):
    """When vid.read() reaches EOF (ret=False), rewind to frame 0 and re-read."""
    with patch("cv2.VideoCapture") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        # First call False (EOF), second call True (rewound)
        mock_cap.read.side_effect = [(False, None), (True, fake_frame)]
        mock_cap_cls.return_value = mock_cap

        cam = cvfile.Cameraf(0, 0)
        frame = cam.read_frame()

        assert mock_cap.set.called
        assert frame is not None
        assert np.array_equal(frame, fake_frame)


@pytest.mark.unit
def test_cameraf_cvfun_fallback(fake_frame):
    """cvfun grabs FRAME_S frames, calls retrieve and uamodel."""
    with patch("cv2.VideoCapture") as mock_cap_cls:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.retrieve.return_value = (True, fake_frame)
        mock_cap_cls.return_value = mock_cap

        with patch("cvfile.uamodel", return_value={"density": 4, "ambulance": False, "emergency": False, "emergency_type": "none"}):
            with patch("cvfile.ambulance_detect", return_value=False):
                cam = cvfile.Cameraf(0, 0)
                data = cam.cvfun()

    assert data["density"] == 4
    assert data["ambulance"] is False


@pytest.mark.unit
def test_scan_all_lanes_live_mode_uses_cached_frame(fake_frame):
    """live=True uses cam.last_frame.copy() instead of calling read_frame()."""
    cam0 = MagicMock()
    cam0.last_frame = fake_frame.copy()
    cam0.read_frame.return_value = None

    cameras = {0: cam0}
    with patch("cvfile.uamodel", return_value={"density": 3, "ambulance": False, "emergency": False, "emergency_type": "none"}):
        with patch("cvfile.detect_emergencies_batch", return_value={0: {"ambulance": False, "emergency": False, "emergency_type": "none"}}):
            lane_data, frames = cvfile.scan_all_lanes(cameras, live=True)

    assert not cam0.read_frame.called
    assert 0 in frames
    assert lane_data[0]["density"] == 3


@pytest.mark.unit
def test_scan_all_lanes_cli_mode_always_reads_fresh_frame(fake_frame):
    """live=False always calls read_frame() so CLI mode grabs fresh frame."""
    cam0 = MagicMock()
    cam0.last_frame = fake_frame.copy()
    cam0.read_frame.return_value = fake_frame.copy()

    cameras = {0: cam0}
    with patch("cvfile.uamodel", return_value={"density": 2, "ambulance": False, "emergency": False, "emergency_type": "none"}):
        with patch("cvfile.detect_emergencies_batch", return_value={0: {"ambulance": False, "emergency": False, "emergency_type": "none"}}):
            lane_data, frames = cvfile.scan_all_lanes(cameras, live=False)

    assert cam0.read_frame.called
    assert lane_data[0]["density"] == 2


@pytest.mark.unit
def test_scan_all_lanes_null_frame_guard(fake_frame):
    """A lane with a None frame defaults to zero traffic and is excluded from detect_emergencies_batch."""
    cam0 = MagicMock()
    cam0.last_frame = None
    cam0.read_frame.return_value = None

    cam1 = MagicMock()
    cam1.last_frame = fake_frame.copy()
    cam1.read_frame.return_value = fake_frame.copy()

    cameras = {0: cam0, 1: cam1}
    with patch("cvfile.uamodel", return_value={"density": 5, "ambulance": False, "emergency": False, "emergency_type": "none"}):
        with patch("cvfile.detect_emergencies_batch") as mock_batch:
            mock_batch.return_value = {1: {"ambulance": False, "emergency": False, "emergency_type": "none"}}
            lane_data, frames = cvfile.scan_all_lanes(cameras, live=False)

    # Lane 0 should NOT be passed into batch stitcher; only Lane 1 is passed
    assert 0 not in mock_batch.call_args[0][0]
    assert 1 in mock_batch.call_args[0][0]
    assert lane_data[0] == {
        "density": 0,
        "ambulance": False,
        "emergency": False,
        "emergency_type": "none",
    }
    assert lane_data[1]["density"] == 5
    assert frames[0] is None
    assert frames[1] is not None
