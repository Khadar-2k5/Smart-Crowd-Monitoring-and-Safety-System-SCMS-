"""Frame-to-MJPEG encoder."""

from __future__ import annotations

import cv2


class FrameEncoder:
    @staticmethod
    def encode(frame) -> bytes | None:
        success, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return encoded.tobytes() if success else None

    @staticmethod
    def mjpeg(frame_bytes: bytes) -> bytes:
        return b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
