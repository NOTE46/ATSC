import json
import math
import os
from pathlib import Path
import tempfile
import threading
import cv2 as cv
import numpy as np
from uafile import uamodel
from ambdet import ambulance_detect, detect_emergencies_batch

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
_roi_config_lock = threading.Lock()


def _load_frame_skip():
    """Load frame_skip from config.json, defaulting to 5."""
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return cfg.get("frame_skip", 5)
    except Exception:
        pass
    return 5


FRAME_S = _load_frame_skip()


def roi_key(source) -> str:
    if isinstance(source, int):
        return f"cam{source}"
    s = str(source).strip().strip('"').strip("'")
    if s.isdigit():
        return f"cam{s}"
    return Path(s.replace("\\", "/")).name


def validate_roi(points, frame_w, frame_h):
    """
    Validate and normalize 4 ROI points in original frame pixel coordinates.
    - Exactly 4 points
    - Clamped to [0, frame_w - 1] and [0, frame_h - 1]
    - Ordered clockwise around their centroid via math.atan2
    - Contour area >= 1% of frame area (0.01 * frame_w * frame_h)
    Returns list of 4 [int(x), int(y)] pairs, or None if invalid.
    """
    if not points or len(points) != 4 or frame_w <= 0 or frame_h <= 0:
        return None

    clamped = []
    for pt in points:
        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
            return None
        try:
            x = max(0, min(frame_w - 1, int(round(pt[0]))))
            y = max(0, min(frame_h - 1, int(round(pt[1]))))
            clamped.append((x, y))
        except (ValueError, TypeError):
            return None

    cx = sum(p[0] for p in clamped) / 4.0
    cy = sum(p[1] for p in clamped) / 4.0

    # Sort clockwise in image space (y goes down): atan2(y - cy, x - cx)
    ordered = sorted(clamped, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
    pts_arr = np.array(ordered, dtype=np.int32)
    area = cv.contourArea(pts_arr)
    if area < 0.01 * frame_w * frame_h:
        return None

    return [[int(p[0]), int(p[1])] for p in ordered]


def crop_roi(frame, points):
    """
    Mask and crop frame to polygon ROI bounding box.
    If frame is None or points is None/invalid, returns frame unchanged.
    Never mutates input frame.
    """
    if frame is None or points is None:
        return frame
    fh, fw = frame.shape[:2]
    valid_pts = validate_roi(points, fw, fh)
    if valid_pts is None:
        return frame

    pts = np.array(valid_pts, dtype=np.int32)
    mask = np.zeros((fh, fw), dtype=np.uint8)
    cv.fillPoly(mask, [pts], 255)
    masked = cv.bitwise_and(frame, frame, mask=mask)
    x, y, w, h = cv.boundingRect(pts)
    if w <= 0 or h <= 0:
        return frame
    return masked[y:y + h, x:x + w]


def canvas_to_frame(x, y, canvas_w, canvas_h, frame_w, frame_h):
    """Convert canvas coordinates to original frame pixel coordinates."""
    if canvas_w <= 0 or canvas_h <= 0 or frame_w <= 0 or frame_h <= 0:
        return (0, 0)
    fx = int(round(x * frame_w / canvas_w))
    fy = int(round(y * frame_h / canvas_h))
    fx = max(0, min(frame_w - 1, fx))
    fy = max(0, min(frame_h - 1, fy))
    return (fx, fy)


def frame_to_canvas(x, y, canvas_w, canvas_h, frame_w, frame_h):
    """Convert original frame pixel coordinates to canvas coordinates."""
    if canvas_w <= 0 or canvas_h <= 0 or frame_w <= 0 or frame_h <= 0:
        return (0, 0)
    cx = int(round(x * canvas_w / frame_w))
    cy = int(round(y * canvas_h / frame_h))
    cx = max(0, min(canvas_w - 1, cx))
    cy = max(0, min(canvas_h - 1, cy))
    return (cx, cy)


def load_roi(source):
    """Load saved ROI points for source from config.json without crashing."""
    try:
        p = Path(CONFIG_PATH)
        if not p.is_file():
            return None
        with open(p, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            return None
        rois = cfg.get("roi_points", {})
        if not isinstance(rois, dict):
            return None
        key = roi_key(source)
        pts = rois.get(key)
        if isinstance(pts, list) and len(pts) == 4:
            return pts
        return None
    except Exception:
        return None


def save_roi(source, points):
    """Update roi_points in config.json atomically under thread lock."""
    with _roi_config_lock:
        p = Path(CONFIG_PATH)
        cfg = {}
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {}
        if not isinstance(cfg, dict):
            cfg = {}
        if "roi_points" not in cfg or not isinstance(cfg["roi_points"], dict):
            cfg["roi_points"] = {}

        key = roi_key(source)
        if points is None:
            cfg["roi_points"].pop(key, None)
        else:
            cfg["roi_points"][key] = points

        parent_dir = p.parent
        parent_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_file = tempfile.mkstemp(dir=parent_dir, prefix="config_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            os.replace(tmp_file, p)
        except Exception:
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except OSError:
                    pass
            raise


class Cameraf:
    def __init__(self, lane_no, source):
        self.lane_no = lane_no
        self.source = source
        self.last_frame = None
        self._lock = threading.Lock()
        self.frame_skip = _load_frame_skip()
        self.vid = cv.VideoCapture(source)

        self._raw_roi = load_roi(source)
        self.roi_points = None
        self._roi_validated = False

        if not self.vid.isOpened():
            raise RuntimeError(f"Camera failed on {lane_no}")

    def _check_lazy_roi(self, frame):
        """Validate raw ROI on first frame read."""
        if not self._roi_validated and frame is not None:
            fh, fw = frame.shape[:2]
            self.roi_points = validate_roi(self._raw_roi, fw, fh) if self._raw_roi is not None else None
            self._roi_validated = True

    def get_roi(self):
        """Return validated ROI points if validated, else None."""
        return self.roi_points if self._roi_validated else None

    def set_roi(self, points):
        """
        Set or clear ROI points.
        If points is None, clears ROI and saves.
        Otherwise validates against last_frame dimensions and saves.
        Returns True on success, False if validation fails or no frame available.
        """
        if points is None:
            self._raw_roi = None
            self.roi_points = None
            self._roi_validated = True
            save_roi(self.source, None)
            return True

        if self.last_frame is not None:
            fh, fw = self.last_frame.shape[:2]
            valid_pts = validate_roi(points, fw, fh)
            if valid_pts is None:
                return False
            self.roi_points = valid_pts
            self._raw_roi = valid_pts
            self._roi_validated = True
            save_roi(self.source, self.roi_points)
            return True
        return False

    def read_frame(self):
        """Read a single frame with thread safety and auto-loop to frame 0 on EOF."""
        with self._lock:
            ret, frame = self.vid.read()
            if not ret or frame is None:
                self.vid.set(cv.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.vid.read()
                if not ret or frame is None:
                    return None
            self.last_frame = frame
            self._check_lazy_roi(frame)
            return frame

    def cvfun(self):
        """
        Grab FRAME_S frames, retrieve (or loop to 0), update self.last_frame,
        run uamodel(frame) on cropped ROI, and check ambulance_detect(frame).
        """
        frame = None
        with self._lock:
            for _ in range(self.frame_skip):
                self.vid.grab()
            ret, frame = self.vid.retrieve()
            if not ret or frame is None:
                self.vid.set(cv.CAP_PROP_POS_FRAMES, 0)
                for _ in range(self.frame_skip):
                    self.vid.grab()
                ret, frame = self.vid.retrieve()
                if not ret or frame is None:
                    ret, frame = self.vid.read()
                    if not ret or frame is None:
                        print(f"Video capture failed on lane {self.lane_no}")
                        return {
                            "density": 0,
                            "ambulance": False,
                            "emergency": False,
                            "emergency_type": "none"
                        }
            self.last_frame = frame
            self._check_lazy_roi(frame)

        roi = self.get_roi()
        processed_frame = crop_roi(frame, roi) if roi is not None else frame
        data = uamodel(processed_frame)
        if ambulance_detect(processed_frame):
            data["ambulance"] = True
            data["emergency"] = True
            data["emergency_type"] = "ambulance"
        return data

    def releasevid(self):
        with self._lock:
            if self.vid is not None and self.vid.isOpened():
                self.vid.release()


def scan_all_lanes(cameras, live=False):
    """
    Scan all camera lanes, collect frames, count vehicles, and perform batch emergency detection.
    Frames are cropped to ROI before detection; returned frames hold full uncropped images.
    Returns (lane_data, frames) according to the ATSC contract.
    """
    lane_data = {}
    frames = {}
    valid_frames = {}

    if isinstance(cameras, dict):
        cam_items = list(cameras.items())
    elif isinstance(cameras, (list, tuple)):
        cam_items = list(enumerate(cameras))
    else:
        cam_items = []

    for lane_id, cam in cam_items:
        frame = None
        if live:
            if getattr(cam, "last_frame", None) is not None:
                frame = cam.last_frame.copy()
            elif hasattr(cam, "read_frame"):
                frame = cam.read_frame()
        else:
            if hasattr(cam, "read_frame"):
                frame = cam.read_frame()

        frames[lane_id] = frame

        if frame is None:
            # Null-Frame Guard: Default zero-density schema and exclude from vision stitcher
            lane_data[lane_id] = {
                "density": 0,
                "ambulance": False,
                "emergency": False,
                "emergency_type": "none"
            }
        else:
            roi = cam.get_roi() if hasattr(cam, "get_roi") else None
            processed_frame = crop_roi(frame, roi) if roi is not None else frame
            valid_frames[lane_id] = processed_frame
            lane_data[lane_id] = uamodel(processed_frame)

    if valid_frames:
        emerg_results = detect_emergencies_batch(valid_frames)
        for lane_id, emerg_info in emerg_results.items():
            if lane_id in lane_data:
                lane_data[lane_id]["ambulance"] = emerg_info.get("ambulance", False)
                lane_data[lane_id]["emergency"] = emerg_info.get("emergency", False)
                lane_data[lane_id]["emergency_type"] = emerg_info.get("emergency_type", "none")

    return lane_data, frames
