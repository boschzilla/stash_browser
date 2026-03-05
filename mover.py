"""
Core stash mover logic.
Runs in a background thread; communicates progress via a log callback.

Transfer flow
-------------
1. Navigate to source tab.
2. If source is not a standard grid stash → stop (currency/special tabs unsupported).
3. If inventory is already ≥80% full → dump to destination first.
4. Loop:
     a. Scan source stash.  If empty → dump any remaining inventory → done.
     b. Ctrl+click items from source into inventory one by one.
     c. After every few clicks check inventory fill ratio.
        When ≥80% full → go to destination.
     d. At destination: verify it has enough free cells; if not → stop.
     e. Ctrl+Shift+click every inventory item into destination.
     f. Verify inventory is fully empty.  If not after 3 tries → stop.
     g. Navigate back to source and repeat.
"""

import threading
import time
from typing import Callable

from config import Config
import actions
import vision


LogFn = Callable[[str], None]

FILL_THRESHOLD = 0.80   # dump inventory to destination at this fill ratio


class StopRequested(Exception):
    pass


class TabNotFoundError(Exception):
    pass


class DestinationFullError(Exception):
    pass


class StashMover:
    def __init__(self, cfg: Config, src_tab: str, dst_tab: str, log: LogFn):
        self.cfg = cfg
        self.src_tab = src_tab
        self.dst_tab = dst_tab
        self.log = log
        self.stop_flag = threading.Event()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            self.log(f"Starting: '{self.src_tab}' -> '{self.dst_tab}'")

            # 1. Navigate to source tab.
            self._navigate_to_tab(self.src_tab)

            # 2. Verify source is a standard grid stash.
            if not vision.looks_like_grid_stash(self.cfg.stash_grid):
                self.log(
                    f"ERROR: '{self.src_tab}' does not look like a standard grid stash. "
                    "Currency, map, and other special tabs are not supported. Stopping."
                )
                return

            # Diagnostic: log grid geometry.
            s = self.cfg.stash_grid
            cell_w = s.w / s.cols
            cell_h = s.h / s.rows
            self.log(
                f"  Grid: {s.cols}x{s.rows} cells  "
                f"x={s.x} y={s.y} w={s.w} h={s.h}  "
                f"cell {cell_w:.1f}x{cell_h:.1f}px"
            )
            self.log(f"  DPI scale: {actions._DPI_SCALE_X:.3f}x{actions._DPI_SCALE_Y:.3f}")

            # 3. If inventory is already >=80% full, dump it before doing anything.
            inv_grid = vision.scan_grid_occupancy(self.cfg.inventory_grid, self.cfg)
            inv_fill = vision.inventory_fill_ratio(inv_grid)
            if inv_fill >= FILL_THRESHOLD:
                self.log(f"  Inventory already {inv_fill:.0%} full — dumping first...")
                self._dump_inventory_to_dest()
                self._navigate_to_tab(self.src_tab)

            # 4. Main transfer loop.
            pass_num = 0
            while not self.stop_flag.is_set():
                pass_num += 1

                # Scan source stash — one click per occupied CELL.
                # BFS connected-components would merge all adjacent items into
                # one center point (one click per pass = very slow on a full
                # quad stash).  Per-cell clicking is safe: the first click on
                # any cell of a multi-cell item moves the whole item; subsequent
                # clicks on its now-empty cells are no-ops in PoE.
                stash_grid = vision.scan_grid_occupancy(self.cfg.stash_grid, self.cfg)
                items = vision.nearest_neighbor_order([
                    vision.cell_center(self.cfg.stash_grid, col, row)
                    for col, row in vision.occupied_cells(stash_grid)
                ])

                if not items:
                    # Source is empty.  Dump anything left in inventory then finish.
                    inv_grid = vision.scan_grid_occupancy(self.cfg.inventory_grid, self.cfg)
                    if vision.count_occupied(inv_grid) > 0:
                        self.log("Source stash empty — dumping remaining inventory...")
                        self._dump_inventory_to_dest()
                    self.log("Done! All items transferred.")
                    return

                self.log(
                    f"[Pass {pass_num}] {len(items)} cell(s) found in source — "
                    "ctrl+clicking into inventory..."
                )

                # Ensure game window has keyboard focus before holding ctrl.
                actions.focus_game_window()
                actions.release_modifier_keys()  # clear any Alt held by focus trick

                # Pre-move to first item so the stash panel has focus before ctrl is held.
                actions.move_to(items[0][0], items[0][1], self.cfg)
                time.sleep(0.2)

                total_inv_cells = self.cfg.inventory_grid.cols * self.cfg.inventory_grid.rows
                # Check fill every N clicks (not after every single one).
                check_interval = max(3, total_inv_cells // 10)

                for i, (cx, cy) in enumerate(items):
                    self._check_stop()
                    self.log(f"    click ({cx}, {cy})")
                    actions.ctrl_click(cx, cy, self.cfg)

                    if (i + 1) % check_interval == 0 or i == len(items) - 1:
                        inv_grid = vision.scan_grid_occupancy(self.cfg.inventory_grid, self.cfg)
                        occupied = vision.count_occupied(inv_grid)
                        fill     = occupied / total_inv_cells if total_inv_cells else 0.0
                        self.log(f"  Inventory {fill:.0%} ({occupied}/{total_inv_cells} cells)")

                        if fill >= FILL_THRESHOLD:
                            self.log(f"  Inventory at {fill:.0%} — moving to destination...")
                            self._dump_inventory_to_dest()
                            self._navigate_to_tab(self.src_tab)
                            break   # re-scan source from top of loop

        except StopRequested:
            self.log("Stopped by user.")
        except DestinationFullError as e:
            self.log(f"STOPPED — destination full: {e}")
        except TabNotFoundError as e:
            self.log(f"ERROR: {e}")
        except Exception as e:
            self.log(f"UNEXPECTED ERROR: {e}")
            raise
        finally:
            # Always signal completion so the GUI poll loop can reset the UI.
            self.stop_flag.set()

    def stop(self) -> None:
        self.stop_flag.set()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_stop(self) -> None:
        if self.stop_flag.is_set():
            raise StopRequested()

    def _navigate_to_tab(self, tab_name: str) -> None:
        """Find and click the named stash tab."""
        actions.release_modifier_keys()
        self.log(f"  Navigating to '{tab_name}'...")

        # Fast path: already visible.
        tab_results = vision.read_tab_names(self.cfg.tab_strip)
        self.log(f"  OCR saw: {[t.text for t in tab_results]}")
        match = vision.find_tab(tab_name, tab_results)
        if match:
            self.log(f"  Found '{match.text}' (conf={match.confidence:.2f})")
            actions.tab_click(match.center_x, match.center_y, self.cfg)
            time.sleep(1.0)
            return

        # Reset to top then scan downward.
        self.log("  Tab not visible — resetting scroll to top...")
        actions.reset_tab_list(self.cfg)

        for attempt in range(self.cfg.max_tab_scrolls):
            self._check_stop()
            tab_results = vision.read_tab_names(self.cfg.tab_strip)
            self.log(f"  OCR saw: {[t.text for t in tab_results]}")
            match = vision.find_tab(tab_name, tab_results)
            if match:
                self.log(f"  Found '{match.text}' (conf={match.confidence:.2f})")
                actions.tab_click(match.center_x, match.center_y, self.cfg)
                time.sleep(1.0)
                return
            self.log(f"  Scrolling down (attempt {attempt + 1})...")
            actions.scroll_tabs_down(self.cfg)
            time.sleep(0.2)

        raise TabNotFoundError(
            f"Could not find tab '{tab_name}' after reset + {self.cfg.max_tab_scrolls} scrolls. "
            "Check the tab name and that the tab strip region is calibrated."
        )

    def _dump_inventory_to_dest(self) -> None:
        """
        Navigate to destination, verify it has enough free cells, then
        ctrl+shift+click every inventory item in.  Finally verify inventory
        is completely empty.

        Raises DestinationFullError if destination does not have enough room.
        Raises StopRequested if inventory is not empty after 3 attempts.
        """
        self._navigate_to_tab(self.dst_tab)

        # Check destination free space vs inventory occupied cells.
        dst_grid     = vision.scan_grid_occupancy(self.cfg.stash_grid, self.cfg)
        total_dst    = self.cfg.stash_grid.cols * self.cfg.stash_grid.rows
        free_in_dst  = total_dst - vision.count_occupied(dst_grid)

        inv_grid     = vision.scan_grid_occupancy(self.cfg.inventory_grid, self.cfg)
        occupied_inv = vision.count_occupied(inv_grid)

        self.log(
            f"  Destination: {free_in_dst}/{total_dst} cells free.  "
            f"Inventory: {occupied_inv} cells occupied."
        )

        if free_in_dst < occupied_inv:
            raise DestinationFullError(
                f"'{self.dst_tab}' has {free_in_dst} free cells but inventory "
                f"occupies {occupied_inv} cells — not enough room."
            )

        actions.focus_game_window()
        actions.release_modifier_keys()

        # --- Phase 1: Ctrl+Click every occupied inventory cell ----------------
        inv_grid = vision.scan_grid_occupancy(self.cfg.inventory_grid, self.cfg)
        cells_p1 = vision.nearest_neighbor_order([
            vision.cell_center(self.cfg.inventory_grid, col, row)
            for col, row in vision.occupied_cells(inv_grid)
        ])

        if not cells_p1:
            self.log("  Inventory empty — dump complete.")
            return

        self.log(f"  Ctrl+clicking {len(cells_p1)} cell(s) into '{self.dst_tab}'...")
        actions.move_to(cells_p1[0][0], cells_p1[0][1], self.cfg)
        time.sleep(0.2)

        for cx, cy in cells_p1:
            self._check_stop()
            actions.ctrl_click(cx, cy, self.cfg)

        # --- Phase 2: Ctrl+Shift+Click any stragglers -------------------------
        inv_grid2 = vision.scan_grid_occupancy(self.cfg.inventory_grid, self.cfg)
        cells_p2  = vision.nearest_neighbor_order([
            vision.cell_center(self.cfg.inventory_grid, col, row)
            for col, row in vision.occupied_cells(inv_grid2)
        ])

        if cells_p2:
            self.log(f"  {len(cells_p2)} straggler(s) — Ctrl+Shift+clicking...")
            for cx, cy in cells_p2:
                self._check_stop()
                actions.ctrl_shift_click(cx, cy, self.cfg)

        remaining = vision.count_occupied(
            vision.scan_grid_occupancy(self.cfg.inventory_grid, self.cfg)
        )
        if remaining:
            self.log(f"  WARNING: {remaining} cell(s) still in inventory — continuing anyway.")
        else:
            self.log("  Inventory confirmed empty — dump complete.")


def start_mover(cfg: Config, src_tab: str, dst_tab: str, log: LogFn) -> StashMover:
    """Create a StashMover and start it in a daemon thread.  Returns the mover."""
    mover  = StashMover(cfg, src_tab, dst_tab, log)
    thread = threading.Thread(target=mover.run, daemon=True)
    thread.start()
    return mover
