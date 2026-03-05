"""
Screen capture utilities using mss.
Returns numpy uint8 BGR arrays compatible with OpenCV.

Note: mss uses thread-local Win32 device context handles on Windows, so a
cached global instance cannot be shared across threads.  We use a new context
manager per call instead — the overhead is negligible for our capture rate.
"""

import numpy as np
import mss
from config import GridRegion


def capture_region(x: int, y: int, w: int, h: int) -> np.ndarray:
    """Capture a screen region and return as BGR numpy array."""
    with mss.mss() as sct:
        monitor = {"top": y, "left": x, "width": w, "height": h}
        img = sct.grab(monitor)
        # mss returns BGRA; drop alpha and keep BGR
        return np.array(img)[:, :, :3]


def capture_grid(region: GridRegion) -> np.ndarray:
    """Capture the full grid region."""
    return capture_region(region.x, region.y, region.w, region.h)


def capture_full_screen() -> np.ndarray:
    """Capture the entire primary monitor."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # index 1 = primary monitor
        img = sct.grab(monitor)
        return np.array(img)[:, :, :3]
