import json
import threading
from pathlib import Path
import cv2 as cv
from uafile import uamodel
from ambdet import ambulance_detect, detect_emergencies_batch


def _load_frame_skip():
    """Load frame_skip from config.json, defaulting to 5."""
    config_path = Path("config.json")
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return cfg.get("frame_skip", 5)
        except Exception:
            pass
    return 5


FRAME_S = _load_frame_skip()


class Cameraf:
    def __init__(self, lane_no, source):
        self.lane_no = lane_no
        self.source = source
        self.last_frame = None
        self._lock = threading.Lock()
        self.frame_skip = _load_frame_skip()
        self.vid = cv.VideoCapture(source)

        if not self.vid.isOpened():
            raise RuntimeError(f"Camera failed on {lane_no}")

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
            return frame

    def cvfun(self):
        """
        Grab FRAME_S frames, retrieve (or loop to 0), update self.last_frame,
        run uamodel(frame), and check ambulance_detect(frame) for single-lane fallback.
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

        data = uamodel(frame)
        if ambulance_detect(frame):
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
            valid_frames[lane_id] = frame
            lane_data[lane_id] = uamodel(frame)

    if valid_frames:
        emerg_results = detect_emergencies_batch(valid_frames)
        for lane_id, emerg_info in emerg_results.items():
            if lane_id in lane_data:
                lane_data[lane_id]["ambulance"] = emerg_info.get("ambulance", False)
                lane_data[lane_id]["emergency"] = emerg_info.get("emergency", False)
                lane_data[lane_id]["emergency_type"] = emerg_info.get("emergency_type", "none")

    return lane_data, frames


        
    


