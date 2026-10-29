from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    frames: int
    fps: float

    def to_dict(self) -> dict[str, int | float]:
        return {
            "width": self.width,
            "height": self.height,
            "frames": self.frames,
            "fps": self.fps,
        }


def probe_video(path: Path) -> VideoInfo:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"Could not open input video: {path}")
    try:
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 24.0)
    finally:
        capture.release()
    if width <= 0 or height <= 0:
        raise ValueError(f"Could not determine dimensions for: {path}")
    if frames <= 0:
        # Some containers do not expose a frame count. Decode once to obtain
        # a reliable limit before the job is accepted.
        capture = cv2.VideoCapture(str(path))
        try:
            frames = 0
            while capture.grab():
                frames += 1
        finally:
            capture.release()
    if frames <= 0:
        raise ValueError(f"Input contains no frames: {path}")
    return VideoInfo(width, height, frames, fps)


def aligned(value: int) -> int:
    return max(128, ((int(value) + 127) // 128) * 128)


def even(value: int) -> int:
    return max(2, ((int(value) + 1) // 2) * 2)


def model_dimensions(width: int, height: int) -> tuple[int, int]:
    return aligned(width), aligned(height)


def target_dimensions(info: VideoInfo, scale: float, width: int | None, height: int | None) -> tuple[int, int]:
    if width is not None or height is not None:
        if width is None or height is None:
            raise ValueError("width and height must be supplied together")
        return even(width), even(height)
    if scale < 1.0 or scale > 4.0:
        raise ValueError("scale must be between 1 and 4")
    return even(round(info.width * scale)), even(round(info.height * scale))
