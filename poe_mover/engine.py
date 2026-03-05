"""
engine.py — Core stash-transfer loop.

Loop per batch:
  1. Navigate to source tab  (scroll left tab list → click)
  2. Scan stash → ctrl-click items into inventory (stop when full or stash empty)
  3. Navigate to destination tab
  4. Ctrl-click all inventory items into destination stash
  5. Repeat until source stash is empty
"""

import threading
import time
from typing import Callable

import vision
import actions

RECHECK_EVERY       = 8   # re-check inventory after this many clicks
MAX_SCROLL_ATTEMPTS = 20  # give up finding a tab after this many scroll steps


class TransferEngine:
    def __init__(self, log_fn: Callable[[str], None]):
        self._log   = log_fn
        self._stop  = threading.Event()
        self._pause = threading.Event()
        self._pause.set()   # not paused initially

    # ── Public control API ───────────────────────────────────────────────

    def stop(self):       self._stop.set()
    def pause(self):      self._pause.clear()
    def resume(self):     self._pause.set()
    def is_stopped(self): return self._stop.is_set()

    # ── Main entry point ─────────────────────────────────────────────────

    def run(self, source_tab: str, dest_tab: str):
        self._log(f"=== Transfer start: '{source_tab}' → '{dest_tab}' ===")
        batch = 0

        while not self._stop.is_set():
            batch += 1
            self._log(f"── Batch {batch} ─────────────────────────────")

            # PHASE 1 — go to source
            self._log(f"Navigating to source: {source_tab}")
            if not self._navigate_to_tab(source_tab):
                self._log(f"ERROR: Cannot find '{source_tab}'. Stopping.")
                break
            if self._stop.is_set(): break

            # PHASE 2 — scan stash
            self._log("Scanning source stash…")
            stash_cells = vision.locate_stash_items()
            if not stash_cells:
                self._log("Source stash is empty — done!")
                break
            self._log(f"Found {len(stash_cells)} item(s) in source stash.")

            # PHASE 2b — pick up items
            inv_full, clicked = self._fill_inventory(stash_cells)
            if clicked == 0:
                self._log("Zero items moved — possible detection issue. Stopping.")
                break
            if self._stop.is_set(): break

            # PHASE 3 — go to destination
            self._log(f"Moving to destination: {dest_tab}")
            if not self._navigate_to_tab(dest_tab):
                self._log(f"ERROR: Cannot find '{dest_tab}'. Stopping.")
                break
            if self._stop.is_set(): break

            # PHASE 3b — dump inventory
            dumped = self._dump_inventory()
            self._log(f"Dumped {dumped} item(s) into '{dest_tab}'.")

            time.sleep(0.4)   # brief pause between batches

        self._log("=== Transfer engine finished. ===")

    # ── Tab navigation ────────────────────────────────────────────────────

    def _navigate_to_tab(self, tab_name: str) -> bool:
        needle = tab_name.strip().lower()

        for attempt in range(MAX_SCROLL_ATTEMPTS):
            self._wait_or_stop()
            if self._stop.is_set():
                return False

            self._log(f"  Tab scan attempt {attempt + 1}/{MAX_SCROLL_ATTEMPTS}…")
            try:
                result = vision.locate_tabs()
            except Exception as e:
                self._log(f"  Vision error: {e}")
                time.sleep(1.5)
                continue

            tabs     = result.get("tabs", [])
            scroll_x = result.get("scroll_down_x")
            scroll_y = result.get("scroll_down_y")

            names = [t["name"] for t in tabs]
            self._log(f"  Visible: {names}")

            for tab in tabs:
                if needle in tab["name"].strip().lower():
                    sx, sy = vision.scale_to_screen(tab["x"], tab["y"])
                    self._log(f"  ✓ '{tab['name']}' → screen ({sx}, {sy})")
                    actions.click_tab(sx, sy)
                    return True

            # Not found — scroll the tab list down
            if tabs:
                fx, fy = vision.scale_to_screen(tabs[0]["x"], tabs[0]["y"])
                self._log("  Scrolling tab list down…")
                if scroll_x and scroll_y:
                    sx2, sy2 = vision.scale_to_screen(scroll_x, scroll_y)
                    actions.scroll_tab_list_down(sx2, sy2)
                else:
                    actions.scroll_tab_list_at(fx, fy)
            else:
                self._log("  No tabs visible — is the stash open?")
                time.sleep(2.0)

        self._log(f"  ✗ Tab '{tab_name}' not found after {MAX_SCROLL_ATTEMPTS} attempts.")
        return False

    # ── Fill inventory from stash ─────────────────────────────────────────

    def _fill_inventory(self, stash_cells: list[dict]) -> tuple[bool, int]:
        total = 0
        for i, cell in enumerate(stash_cells):
            self._wait_or_stop()
            if self._stop.is_set():
                return False, total

            sx, sy = vision.scale_to_screen(cell["x"], cell["y"])
            actions.ctrl_click(sx, sy)
            total += 1
            self._log(f"  [src→inv] {total}/{len(stash_cells)}  ({sx},{sy})")

            if total % RECHECK_EVERY == 0:
                self._log("  Re-checking inventory…")
                try:
                    inv = vision.get_inventory_state()
                    if inv.get("is_full"):
                        self._log("  Inventory FULL — stopping pick-up.")
                        return True, total
                    free = len(inv.get("empty", []))
                    self._log(f"  {free} slot(s) still free.")
                except Exception as e:
                    self._log(f"  Inv check error (continuing): {e}")

        try:
            inv = vision.get_inventory_state()
            return inv.get("is_full", False), total
        except Exception:
            return False, total

    # ── Dump inventory to destination stash ──────────────────────────────

    def _dump_inventory(self) -> int:
        try:
            inv = vision.get_inventory_state()
        except Exception as e:
            self._log(f"  Cannot read inventory: {e}")
            return 0

        occupied = inv.get("occupied", [])
        if not occupied:
            self._log("  Inventory already empty.")
            return 0

        self._log(f"  Dumping {len(occupied)} item(s)…")
        for i, cell in enumerate(occupied):
            self._wait_or_stop()
            if self._stop.is_set():
                return i
            sx, sy = vision.scale_to_screen(cell["x"], cell["y"])
            actions.ctrl_click(sx, sy)
            self._log(f"  [inv→dst] {i+1}/{len(occupied)}  ({sx},{sy})")

        return len(occupied)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _wait_or_stop(self):
        self._pause.wait()
