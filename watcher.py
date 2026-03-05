"""
watcher.py - Live OpenCV viewer for the Path of Exile window.
Captures the PoE window and displays it with FPS overlay and monster detection.

Controls:
  ESC / Q  - quit
  S        - save a screenshot to watcher_screenshot.png
  D        - toggle monster detection overlay
"""

import sys
import time
import ctypes
import ctypes.wintypes
import numpy as np
import cv2
import mss
from detector import MonsterDetector, draw_detections

user32 = ctypes.windll.user32

POE_TITLES = ["Path of Exile"]
DISPLAY_SCALE = 0.35  # shrink 4K to fit a normal monitor


def find_poe_window():
    """Return (hwnd, title, (x, y, w, h)) for the first visible PoE window, or None."""
    found = []

    def _cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        title = buf.value
        for t in POE_TITLES:
            if t.lower() in title.lower():
                found.append((hwnd, title))
        return True

    ProcType = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    user32.EnumWindows(ProcType(_cb), 0)

    if not found:
        return None, None, None

    hwnd, title = found[0]
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    x, y = rect.left, rect.top
    w, h = rect.right - rect.left, rect.bottom - rect.top
    return hwnd, title, (x, y, w, h)


def main():
    print("Searching for Path of Exile window...")
    hwnd, title, rect = find_poe_window()

    if rect is None:
        print("ERROR: Path of Exile window not found. Start the game first.")
        input("Press Enter to exit.")
        sys.exit(1)

    x, y, w, h = rect
    print(f"Found: '{title}'  pos=({x},{y})  size={w}x{h}")
    print("ESC/Q to quit  |  S to screenshot")

    disp_w = max(1, int(w * DISPLAY_SCALE))
    disp_h = max(1, int(h * DISPLAY_SCALE))

    win_name = "PoE Watcher"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_name, disp_w, disp_h)

    monitor = {"top": y, "left": x, "width": w, "height": h}
    fps_samples = []
    screenshot_count = 0
    detector = MonsterDetector()
    detection_on = True
    print("D to toggle detection  |  S to screenshot  |  ESC/Q to quit")

    with mss.mss() as sct:
        while True:
            t0 = time.perf_counter()

            raw = sct.grab(monitor)
            frame = np.array(raw)[:, :, :3]  # BGRA → BGR

            elapsed = time.perf_counter() - t0
            fps_samples.append(1.0 / max(elapsed, 1e-9))
            if len(fps_samples) > 60:
                fps_samples.pop(0)
            fps = sum(fps_samples) / len(fps_samples)

            display = cv2.resize(frame, (disp_w, disp_h))

            # Monster detection
            if detection_on:
                boxes = detector.detect(display)
                draw_detections(display, boxes)

            # HUD
            mode_label = "DET:ON" if detection_on else "DET:OFF"
            cv2.putText(display, f"FPS: {fps:.1f}  [{mode_label}]", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2, cv2.LINE_AA)
            cv2.putText(display, f"{w}x{h} -> {disp_w}x{disp_h}", (10, 58),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1, cv2.LINE_AA)

            cv2.imshow(win_name, display)
            key = cv2.waitKey(1) & 0xFF

            if key in (27, ord('q')):   # ESC or Q
                break
            elif key == ord('d'):
                detection_on = not detection_on
                if not detection_on:
                    detector.reset()
                print(f"Detection {'ON' if detection_on else 'OFF'}")
            elif key == ord('s'):
                fname = f"watcher_screenshot_{screenshot_count}.png"
                cv2.imwrite(fname, frame)
                screenshot_count += 1
                print(f"Saved {fname} ({w}x{h})")

    cv2.destroyAllWindows()
    print("Watcher stopped.")


if __name__ == "__main__":
    main()
