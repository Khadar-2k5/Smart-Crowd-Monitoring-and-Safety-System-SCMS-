"""Live accumulated movement heatmap generation."""

from __future__ import annotations

import cv2
import numpy as np


class Heatmap:
    def __init__(self) -> None:
        self.accumulator = None

    def reset(self) -> None:
        self.accumulator = None

    def update(self, frame, detections) -> None:
        height, width = frame.shape[:2]
        if self.accumulator is None or self.accumulator.shape != (height, width):
            self.accumulator = np.zeros((height, width), dtype=np.float32)
        for detection in detections:
            x, y = detection["center"]
            cv2.circle(self.accumulator, (int(x), int(y)), max(20, min(width, height) // 18), 1.0, -1)
        cv2.GaussianBlur(self.accumulator, (0, 0), 18, dst=self.accumulator)

    def render(self, frame, opacity: float = 0.45):
        if self.accumulator is None or self.accumulator.max() <= 0:
            return frame.copy()
        normalized = cv2.normalize(self.accumulator, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        colors = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
        return cv2.addWeighted(frame, 1 - opacity, colors, opacity, 0)
