"""
Mouse and keyboard action helpers using pyautogui.
All actions add random jitter and configurable delays for reliability.

Coordinate space note
---------------------
mss captures at the monitor's PHYSICAL pixel resolution (e.g. 3840×2160).
pyautogui uses LOGICAL coordinates, which on a high-DPI display with Windows
scaling are smaller (e.g. 2560×1440 at 150% scaling).  _DPI_SCALE is computed
once at import time and applied to every coordinate before it reaches pyautogui
so that calibrated (physical) coordinates land exactly where expected.
"""

import random
import time

import mss
import pyautogui

from config import Config

# Move mouse to (0, 0) to abort — pyautogui FAILSAFE
pyautogui.FAILSAFE = True
# Disable pyautogui's built-in pause (we manage delays ourselves)
pyautogui.PAUSE = 0.0


def _compute_dpi_scale() -> tuple[float, float]:
    """Return (sx, sy) to convert physical mss coords → pyautogui logical coords."""
    try:
        pag_w, pag_h = pyautogui.size()
        with mss.mss() as sct:
            m = sct.monitors[1]          # primary monitor
            mss_w, mss_h = m["width"], m["height"]
        sx = pag_w / mss_w if mss_w else 1.0
        sy = pag_h / mss_h if mss_h else 1.0
        return sx, sy
    except Exception:
        return 1.0, 1.0


_DPI_SCALE_X, _DPI_SCALE_Y = _compute_dpi_scale()


def _to_pag(x: int, y: int) -> tuple[int, int]:
    """Convert calibration/mss coordinates to pyautogui coordinates."""
    return round(x * _DPI_SCALE_X), round(y * _DPI_SCALE_Y)


def _jitter(value: int, jitter: int) -> int:
    if jitter <= 0:
        return value
    return value + random.randint(-jitter, jitter)


def move_to(x: int, y: int, cfg: Config) -> None:
    """Move mouse to (x, y) with optional jitter."""
    px, py = _to_pag(x, y)
    tx = _jitter(px, cfg.click_jitter)
    ty = _jitter(py, cfg.click_jitter)
    pyautogui.moveTo(tx, ty, duration=0.05)


def left_click(x: int, y: int, cfg: Config) -> None:
    """Left-click at (x, y)."""
    move_to(x, y, cfg)
    pyautogui.click()
    time.sleep(cfg.action_delay)


def tab_click(x: int, y: int, cfg: Config) -> None:
    """Click a stash tab label — move, pause, hold 1 s, release, pause."""
    time.sleep(0.25)
    move_to(x, y, cfg)
    time.sleep(0.25)
    pyautogui.mouseDown()
    time.sleep(1.0)
    pyautogui.mouseUp()
    time.sleep(0.25)


def release_modifier_keys() -> None:
    """Force-release ctrl/shift/alt in case a previous action left them held."""
    for key in ("ctrl", "shift", "alt"):
        pyautogui.keyUp(key)


def focus_game_window(title: str = "Path of Exile") -> bool:
    """
    Bring the PoE window to the foreground so keyboard events land on it.
    Uses the ALT-key trick to work even when the calling process is in the
    background (Windows blocks SetForegroundWindow otherwise).
    Returns True if the window was found and focused.
    """
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            return False
        user32.keybd_event(0x12, 0, 0, 0)       # VK_MENU (Alt) down
        user32.SetForegroundWindow(hwnd)
        user32.keybd_event(0x12, 0, 0x0002, 0)  # VK_MENU (Alt) up
        time.sleep(0.3)
        return True
    except Exception:
        return False


_VK_CONTROL    = 0x11
_VK_SHIFT      = 0x10
_KEYEVENTF_UP  = 0x0002

def _key_down(vk: int) -> None:
    import ctypes
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)

def _key_up(vk: int) -> None:
    import ctypes
    ctypes.windll.user32.keybd_event(vk, 0, _KEYEVENTF_UP, 0)


def ctrl_click(x: int, y: int, cfg: Config) -> None:
    """Ctrl+Click — moves an item from the STASH into the player INVENTORY."""
    px, py = _to_pag(x, y)
    px = _jitter(px, cfg.click_jitter)
    py = _jitter(py, cfg.click_jitter)
    pyautogui.moveTo(px, py, duration=0.05)
    _key_down(_VK_CONTROL)
    time.sleep(0.05)
    pyautogui.click(px, py)
    time.sleep(0.05)
    _key_up(_VK_CONTROL)
    time.sleep(cfg.action_delay)


def ctrl_shift_click(x: int, y: int, cfg: Config) -> None:
    """Ctrl+Shift+Click — moves an item from the player INVENTORY into the STASH."""
    px, py = _to_pag(x, y)
    px = _jitter(px, cfg.click_jitter)
    py = _jitter(py, cfg.click_jitter)
    pyautogui.moveTo(px, py, duration=0.05)
    _key_down(_VK_CONTROL)
    _key_down(_VK_SHIFT)
    time.sleep(0.10)
    pyautogui.click(px, py)
    time.sleep(0.05)
    _key_up(_VK_SHIFT)
    _key_up(_VK_CONTROL)
    time.sleep(cfg.action_delay)


def scroll_at(x: int, y: int, clicks: int, cfg: Config) -> None:
    """
    Scroll the mouse wheel at (x, y).
    Positive clicks = scroll up/right, negative = scroll down/left.
    """
    move_to(x, y, cfg)
    pyautogui.scroll(clicks)
    time.sleep(cfg.action_delay)


def scroll_tabs_down(cfg: Config) -> None:
    """Scroll the vertical tab list down to reveal tabs lower in the list."""
    x = cfg.tab_strip.x + cfg.tab_strip.w // 2
    y = cfg.tab_strip.y + cfg.tab_strip.h // 2
    scroll_at(x, y, -cfg.tab_scroll_steps, cfg)


def scroll_tabs_up(cfg: Config) -> None:
    """Scroll the vertical tab list up (back to the top)."""
    x = cfg.tab_strip.x + cfg.tab_strip.w // 2
    y = cfg.tab_strip.y + cfg.tab_strip.h // 2
    scroll_at(x, y, cfg.tab_scroll_steps, cfg)


def reset_tab_list(cfg: Config) -> None:
    """Scroll the tab list all the way up with a single large scroll (fast)."""
    x = cfg.tab_strip.x + cfg.tab_strip.w // 2
    y = cfg.tab_strip.y + cfg.tab_strip.h // 2
    px, py = _to_pag(x, y)
    pyautogui.moveTo(px, py, duration=0.05)
    pyautogui.scroll(999)   # one big upward scroll — lands at the top regardless
    time.sleep(0.3)
