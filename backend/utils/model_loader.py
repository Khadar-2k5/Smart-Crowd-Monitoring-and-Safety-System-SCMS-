"""Thread-safe, lazy YOLO model loading."""

from __future__ import annotations

import threading

from backend.config import Config
from backend.utils.logger import logger

_model = None
_model_lock = threading.Lock()
_inference_lock = threading.RLock()


def get_yolo_model():
    global _model
    with _model_lock:
        if _model is not None:
            return _model
        if not Config.MODEL_PATH.exists():
            raise RuntimeError(f"YOLO model not found at '{Config.MODEL_PATH}'. Put yolov8n.pt in models/.")
        try:
            from ultralytics import YOLO
        except ImportError as error:
            raise RuntimeError("Ultralytics is not installed. Run: pip install -r requirements.txt") from error
        logger.info("Loading YOLO model from %s", Config.MODEL_PATH)
        _model = YOLO(str(Config.MODEL_PATH))
        return _model


def run_inference(frame, confidence: float):
    """Run one shared YOLO inference safely across independently tracked cameras."""
    model = get_yolo_model()
    # Ultralytics predictor state is mutable. Serialising inference keeps one
    # model memory footprint while every camera retains its own ByteTrack state.
    with _inference_lock:
        return model.predict(
            frame,
            classes=[0],
            conf=confidence,
            verbose=False,
        )

