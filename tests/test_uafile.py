from unittest.mock import MagicMock, patch
import pytest
import uafile


def _create_mock_box(cls_id):
    box = MagicMock()
    box.cls = cls_id
    return box


@pytest.mark.unit
def test_uamodel_counts_target_classes_only(fake_frame):
    """uamodel must count 'car', 'motorcycle', 'truck', 'bus' and ignore other labels."""
    mock_res = MagicMock()
    mock_res.names = {
        0: "person",
        1: "car",
        2: "motorcycle",
        3: "bus",
        4: "truck",
        5: "traffic light",
        6: "dog",
    }
    # 2 cars, 1 bus, 1 truck, 1 person, 1 dog -> density should be 4
    mock_res.boxes = [
        _create_mock_box(1),
        _create_mock_box(1),
        _create_mock_box(3),
        _create_mock_box(4),
        _create_mock_box(0),
        _create_mock_box(6),
    ]

    mock_model = MagicMock()
    mock_model.return_value = [mock_res]

    with patch.object(uafile, "_get_vehicle_model", return_value=mock_model):
        res = uafile.uamodel(fake_frame)

    assert res["density"] == 4
    assert res["ambulance"] is False
    assert res["emergency"] is False
    assert res["emergency_type"] == "none"


@pytest.mark.unit
def test_uamodel_handles_none_frame():
    """If frame is None, return zero density dict without running inference."""
    res = uafile.uamodel(None)
    assert res == {
        "density": 0,
        "ambulance": False,
        "emergency": False,
        "emergency_type": "none",
    }


@pytest.mark.unit
def test_uamodel_empty_boxes(fake_frame):
    """If no bounding boxes detected, density is 0."""
    mock_res = MagicMock()
    mock_res.boxes = []
    mock_res.names = {0: "car"}

    mock_model = MagicMock()
    mock_model.return_value = [mock_res]

    with patch.object(uafile, "_get_vehicle_model", return_value=mock_model):
        res = uafile.uamodel(fake_frame)

    assert res["density"] == 0


@pytest.mark.unit
def test_uamodel_never_calls_ambulance_detect(fake_frame):
    """uamodel must not import or call ambulance_detect (decoupled)."""
    assert not hasattr(uafile, "ambulance_detect")


@pytest.mark.unit
def test_vehicle_model_default_path():
    """Verify default fallback vehicle model path is Model/yolo26n.pt."""
    with patch.object(uafile, "_vehicle_model", None), \
         patch.object(uafile, "model", None), \
         patch("uafile.Path.exists", return_value=False), \
         patch("uafile.YOLO") as mock_yolo:
        uafile._get_vehicle_model()
        mock_yolo.assert_called_once_with("Model/yolo26n.pt")
