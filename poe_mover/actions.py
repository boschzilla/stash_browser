"""
actions.py — All mouse / keyboard operations for the stash mover.

Every public function operates in ACTUAL screen pixel space (3840×2160).
The caller (engine.py) is responsible for scaling coordinates from vision space.

PyAutoGUI failsafe is always ON — move mouse to top-left corner to abort.
"""

import time
import pyautogui

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.05   # minimal inter-call pause; we add explicit sleeps below

# How long to wait after clicking a stash tab before assuming it has loaded
TAB_LOAD_WAIT   = 0.6   # seconds
# Delay between ctrl-clicks to avoid PoE missing them
CLICK_INTERVAL  = 0.12  # seconds
# How far to scroll the tab list per scroll action (pixels)
SCROLL_AMOUNT   = 3     # notches


def move_to(x: int, y: int, duration: float = 0.12) -> None:
    pyautogui.moveTo(x, y, duration=duration)


def click(x: int, y: int, duration: float = 0.12) -> None:
    pyautogui.moveTo(x, y, duration=duration)
    pyautogui.click()
    time.sleep(0.08)


def ctrl_click(x: int, y: int) -> None:
    """Ctrl+click an item (moves it to/from inventory in PoE)."""
    pyautogui.moveTo(x, y, duration=0.10)
    pyautogui.keyDown("ctrl")
    time.sleep(0.04)
    pyautogui.click()
    time.sleep(0.04)
    pyautogui.keyUp("ctrl")
    time.sleep(CLICK_INTERVAL)


def click_tab(x: int, y: int) -> None:
    """Click a stash tab and wait for it to load."""
    click(x, y)
    time.sleep(TAB_LOAD_WAIT)


def scroll_tab_list_down(scroll_btn_x: int, scroll_btn_y: int) -> None:
    """
    Scroll the vertical stash tab list down.
    Two strategies: click the scroll-down arrow, or scroll wheel over the tab area.
    We try scroll wheel first (more reliable), then click the arrow.
    """
    pyautogui.moveTo(scroll_btn_x, scroll_btn_y, duration=0.15)
    pyautogui.scroll(-SCROLL_AMOUNT)
    time.sleep(0.35)


def scroll_tab_list_at(tab_list_x: int, tab_list_y: int) -> None:
    """Scroll wheel down over the tab list area."""
    pyautogui.moveTo(tab_list_x, tab_list_y, duration=0.15)
    pyautogui.scroll(-SCROLL_AMOUNT)
    time.sleep(0.35)


def ctrl_click_all(positions: list[tuple[int, int]], log_fn=None) -> int:
    """
    Ctrl-click a list of (x, y) positions.
    Returns the number of clicks performed.
    Stops early if caller's stop_flag is set (checked via stop_fn).
    """
    count = 0
    for x, y in positions:
        ctrl_click(x, y)
        count += 1
        if log_fn:
            log_fn(f"  ctrl-clicked ({x}, {y})  [{count}/{len(positions)}]")
    return count
