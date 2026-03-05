"""
Computer vision utilities for PoE stash automation.

Occupancy detection uses three HSV signals combined:
  - Value mean       : brightness (most items are brighter than empty cells)
  - Saturation mean  : colourfulness (currency art, gem icons, etc.)
  - Value std-dev    : texture variation (even dark items have non-uniform pixels)

OCR preprocessing uses CLAHE + adaptive threshold instead of global Otsu so
that the tab strip text stays readable regardless of background colour.
"""

import difflib
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from config import Config, GridRegion
from capture import capture_grid, capture_region

# EasyOCR reader is expensive to initialise; load once lazily.
_ocr_reader = None


def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        _ocr_reader = easyocr.Reader(["en"], verbose=False)
    return _ocr_reader


# ---------------------------------------------------------------------------
# Cell occupancy — multi-signal detection
# ---------------------------------------------------------------------------

def cell_center(region: GridRegion, col: int, row: int) -> tuple[int, int]:
    """Return the screen (x, y) pixel centre of a grid cell (0-indexed)."""
    cell_w = region.w / region.cols
    cell_h = region.h / region.rows
    cx = round(region.x + (col + 0.5) * cell_w)
    cy = round(region.y + (row + 0.5) * cell_h)
    return cx, cy


def _cell_patch(hsv: np.ndarray, col: int, row: int,
                cell_w: float, cell_h: float) -> np.ndarray:
    """
    Return the HSV patch for the inner 70% of a grid cell.
    A 15% margin on each side avoids border/divider pixels while
    capturing more of the item art for better dark-item detection.
    """
    margin_x = cell_w * 0.15
    margin_y = cell_h * 0.15
    x1 = max(0, int(col * cell_w + margin_x))
    y1 = max(0, int(row * cell_h + margin_y))
    x2 = min(hsv.shape[1], int((col + 1) * cell_w - margin_x))
    y2 = min(hsv.shape[0], int((row + 1) * cell_h - margin_y))
    return hsv[y1:y2, x1:x2]


def _is_occupied(patch: np.ndarray, cfg: Config) -> bool:
    """
    Decide whether a cell patch contains an item.  Three independent rules;
    any one firing means the cell is occupied.

    A. Bright-pixel rule: ≥3% of pixels have Value > 45.
       Fires on items with any highlights.

    B. Colour-AND-brightness rule: mean Saturation > 20 AND mean Value > 22.
       Fires on colourful items that are meaningfully brighter than background.

    C. Strong texture-variation rule: std-dev of Value > 12.
       Complex item artwork always has variation; empty cells are ~3-8.

    D. Weak combined rule: mean Value > 20 AND std-dev > 7.
       Catches very dark items whose mean brightness and variation are only
       slightly above the near-black background (mean ~12-18, std ~3-6).
       Requiring BOTH conditions avoids triggering on the background alone.

    Empty cells: mean V ≈ 12-18, std V ≈ 3-6  → all rules fail.
    Dark item:   mean V ≈ 20-40, std V ≈ 7-20  → Rule D (and usually C) fires.
    """
    if patch.size == 0:
        return False
    v = patch[:, :, 2].astype(np.float32)  # HSV Value
    s = patch[:, :, 1].astype(np.float32)  # HSV Saturation
    mean_v     = float(v.mean())
    std_v      = float(v.std())
    mean_s     = float(s.mean())
    bright_ratio = float((v > cfg.bright_pixel_threshold).sum()) / v.size
    # A: any bright pixels
    if bright_ratio > 0.03:
        return True
    # B: colorful and bright
    if mean_s > 20 and mean_v > 22:
        return True
    # C: strong variation
    if std_v > 12:
        return True
    # D: modest variation + slightly above background
    if mean_v > 20 and std_v > 7:
        return True
    # E: catch-all for very dark items — any cell that is noticeably above
    #    near-black background AND has ANY variation at all is likely occupied.
    #    Background is mean_v ~12-18, std_v ~3-5.
    if mean_v > 18 and std_v > 5:
        return True
    return False


def looks_like_grid_stash(region: GridRegion) -> bool:
    """
    Return True if the stash region looks like a standard operable grid tab.

    Standard grid stash tabs (normal, quad) have a uniformly near-black
    background — empty cells are V < 50 in HSV, covering the vast majority
    of the area.

    Special tabs (currency, map, fragment, unique, etc.) have bright text
    labels, coloured artwork, or atlas imagery that make the region
    significantly brighter overall.

    A dark-pixel ratio above 0.60 (60 % of the area) indicates a standard
    grid tab.  Adjust the threshold down if heavily-filled stashes trigger
    false negatives.
    """
    img = capture_grid(region)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    v   = hsv[:, :, 2].astype(np.float32)
    dark_ratio = float((v < 50).sum()) / v.size
    return dark_ratio > 0.60


def scan_grid_occupancy(region: GridRegion, cfg: Config) -> list[list[bool]]:
    """
    Return a 2-D list [row][col] of booleans: True = cell occupied.
    Uses multi-signal HSV analysis on the inner 50% of each cell.
    """
    img = capture_grid(region)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    cell_w = region.w / region.cols
    cell_h = region.h / region.rows

    return [
        [_is_occupied(_cell_patch(hsv, col, row, cell_w, cell_h), cfg)
         for col in range(region.cols)]
        for row in range(region.rows)
    ]


def count_occupied(grid: list[list[bool]]) -> int:
    return sum(cell for row in grid for cell in row)


def inventory_fill_ratio(grid: list[list[bool]]) -> float:
    """Return the fraction of inventory cells that appear occupied (0.0–1.0)."""
    total = sum(len(row) for row in grid)
    return count_occupied(grid) / total if total else 0.0


def has_inventory_space(grid: list[list[bool]]) -> bool:
    """Return True if any inventory cell is empty."""
    return any(not cell for row in grid for cell in row)


def occupied_cells(grid: list[list[bool]]) -> list[tuple[int, int]]:
    """Return list of (col, row) for all occupied cells, row-major order."""
    return [
        (col, row)
        for row, row_data in enumerate(grid)
        for col, occ in enumerate(row_data)
        if occ
    ]


def find_items_with_cells(
    grid: list[list[bool]], region: GridRegion
) -> list[tuple[tuple[int, int], list[tuple[int, int]]]]:
    """
    BFS connected-component scan.  Returns one entry per item:
        ((click_x, click_y), [(col, row), ...])
    The click point is the screen-pixel centre of the component bounding box.
    The cell list is every (col, row) that belongs to the component so the
    caller can mark those cells as cleared in its own local state without
    needing to rescan the screen.
    """
    num_rows = len(grid)
    num_cols = len(grid[0]) if num_rows > 0 else 0
    visited = [[False] * num_cols for _ in range(num_rows)]
    cell_w = region.w / region.cols
    cell_h = region.h / region.rows
    result: list[tuple[tuple[int, int], list[tuple[int, int]]]] = []

    for r in range(num_rows):
        for c in range(num_cols):
            if not grid[r][c] or visited[r][c]:
                continue
            cells: list[tuple[int, int]] = []
            min_c = max_c = c
            min_r = max_r = r
            queue = [(r, c)]
            visited[r][c] = True
            while queue:
                cr, cc = queue.pop(0)
                cells.append((cc, cr))          # (col, row)
                if cc < min_c: min_c = cc
                if cc > max_c: max_c = cc
                if cr < min_r: min_r = cr
                if cr > max_r: max_r = cr
                for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    nr, nc = cr + dr, cc + dc
                    if (0 <= nr < num_rows and 0 <= nc < num_cols
                            and grid[nr][nc] and not visited[nr][nc]):
                        visited[nr][nc] = True
                        queue.append((nr, nc))
            cx = round(region.x + ((min_c + max_c) / 2.0 + 0.5) * cell_w)
            cy = round(region.y + ((min_r + max_r) / 2.0 + 0.5) * cell_h)
            result.append(((cx, cy), cells))

    return result


def find_items(grid: list[list[bool]], region: GridRegion) -> list[tuple[int, int]]:
    """
    Identify distinct items using 4-connected component analysis and return
    one screen (x, y) click point per item, at the geometric centre of each
    item's bounding box.

    In PoE a single ctrl+click on ANY cell of a multi-cell item transfers the
    whole item, so one click per connected component is sufficient — no need
    to click every cell the item occupies.
    """
    num_rows = len(grid)
    num_cols = len(grid[0]) if num_rows > 0 else 0
    visited = [[False] * num_cols for _ in range(num_rows)]
    cell_w = region.w / region.cols
    cell_h = region.h / region.rows
    click_points: list[tuple[int, int]] = []

    for r in range(num_rows):
        for c in range(num_cols):
            if not grid[r][c] or visited[r][c]:
                continue
            # BFS — track bounding box of this connected component.
            min_c = max_c = c
            min_r = max_r = r
            queue = [(r, c)]
            visited[r][c] = True
            while queue:
                cr, cc = queue.pop(0)
                if cc < min_c: min_c = cc
                if cc > max_c: max_c = cc
                if cr < min_r: min_r = cr
                if cr > max_r: max_r = cr
                for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    nr, nc = cr + dr, cc + dc
                    if (0 <= nr < num_rows and 0 <= nc < num_cols
                            and grid[nr][nc] and not visited[nr][nc]):
                        visited[nr][nc] = True
                        queue.append((nr, nc))
            # Geometric centre of bounding box → screen coordinates.
            cx = round(region.x + ((min_c + max_c) / 2.0 + 0.5) * cell_w)
            cy = round(region.y + ((min_r + max_r) / 2.0 + 0.5) * cell_h)
            click_points.append((cx, cy))

    return click_points


def nearest_neighbor_order(
    cells: list[tuple[int, int]],
    start: tuple[int, int] = (0, 0),
) -> list[tuple[int, int]]:
    """
    Reorder *cells* using a greedy nearest-neighbor traversal so the mouse
    jumps directly between items rather than sweeping row by row.

    Uses squared cell-coordinate distance (no sqrt needed for comparison).
    """
    if not cells:
        return []
    remaining = list(cells)
    ordered: list[tuple[int, int]] = []
    cx, cy = start
    while remaining:
        closest = min(remaining, key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)
        ordered.append(closest)
        remaining.remove(closest)
        cx, cy = closest
    return ordered


# ---------------------------------------------------------------------------
# Debug visualisation
# ---------------------------------------------------------------------------

def save_debug_overlay(region: GridRegion, cfg: Config,
                       filename: str = "debug_grid.png") -> str:
    """
    Capture the grid region, draw coloured cell outlines (green = occupied,
    red = empty), print mean_v in each cell, and save to *filename*.
    Also writes a CSV of per-cell pixel stats alongside the image so
    thresholds can be tuned from real data.
    Returns the absolute path written.
    """
    import csv

    img = capture_grid(region)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    cell_w = region.w / region.cols
    cell_h = region.h / region.rows
    overlay = img.copy()

    csv_path = str(Path(filename).with_suffix(".csv").resolve())
    rows_out = []

    for row in range(region.rows):
        for col in range(region.cols):
            patch = _cell_patch(hsv, col, row, cell_w, cell_h)
            occ = _is_occupied(patch, cfg)

            x1 = int(col * cell_w)
            y1 = int(row * cell_h)
            x2 = int((col + 1) * cell_w)
            y2 = int((row + 1) * cell_h)

            colour = (0, 200, 0) if occ else (0, 0, 200)
            cv2.rectangle(overlay, (x1, y1), (x2, y2), colour, 2)

            # Draw mean_v value so we can see what signals missed cells have.
            if patch.size > 0:
                v   = patch[:, :, 2].astype(np.float32)
                s   = patch[:, :, 1].astype(np.float32)
                mv  = float(v.mean())
                sv  = float(v.std())
                ms  = float(s.mean())
                br  = float((v > cfg.bright_pixel_threshold).sum()) / v.size
                rows_out.append([col, row, int(occ), f"{mv:.0f}", f"{sv:.0f}",
                                 f"{ms:.0f}", f"{br:.3f}"])
                font_scale = max(0.25, cell_w / 150)
                cv2.putText(overlay, f"{mv:.0f}", (x1 + 2, y1 + int(cell_h * 0.45)),
                            cv2.FONT_HERSHEY_SIMPLEX, font_scale, colour, 1,
                            cv2.LINE_AA)
            else:
                rows_out.append([col, row, int(occ), "N/A", "N/A", "N/A", "N/A"])

    out_path = str(Path(filename).resolve())
    cv2.imwrite(out_path, overlay)

    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["col", "row", "occupied", "mean_v", "std_v", "mean_s", "bright_ratio"])
        w.writerows(rows_out)

    return out_path


# ---------------------------------------------------------------------------
# Tab name OCR
# ---------------------------------------------------------------------------

def _preprocess_for_ocr(img: np.ndarray) -> np.ndarray:
    """
    Prepare a tab strip image for EasyOCR.

    EasyOCR is trained on natural (colour) images — binarising the input
    degrades accuracy significantly.  Instead we:
      1. Upscale 2× so small PoE tab text is large enough to read reliably.
      2. Apply unsharp masking to sharpen text edges without destroying colour.

    The result is a colour BGR image passed directly to EasyOCR.
    """
    scaled = cv2.resize(img, (img.shape[1] * 2, img.shape[0] * 2),
                        interpolation=cv2.INTER_CUBIC)

    # Unsharp mask: sharpen = original + weight * (original - blurred)
    blurred = cv2.GaussianBlur(scaled, (0, 0), sigmaX=2)
    sharpened = cv2.addWeighted(scaled, 1.5, blurred, -0.5, 0)
    return sharpened


class TabResult:
    """OCR result for a single detected tab."""
    def __init__(self, text: str, center_x: int, center_y: int, confidence: float):
        self.text = text
        self.center_x = center_x
        self.center_y = center_y
        self.confidence = confidence


def read_tab_names(tab_strip: GridRegion) -> list[TabResult]:
    """
    OCR the vertical tab list and return one TabResult per visible tab row.

    The vertical tab list has one tab per horizontal row. Strategy:
      1. Sort all OCR fragments by vertical position (top → bottom).
      2. Cluster fragments into rows: a new row starts when the y-gap
         from the current row's centre exceeds the row's text height.
      3. Within each row, sort fragments left-to-right and join their
         text — this reconstructs "Heist (Remove-only)" from split pieces.
    """
    img = capture_region(tab_strip.x, tab_strip.y, tab_strip.w, tab_strip.h)
    processed = _preprocess_for_ocr(img)

    reader = _get_ocr_reader()
    raw = reader.readtext(processed)

    scale = 2  # upscaled by 2 in _preprocess_for_ocr

    # Parse OCR hits
    items = []
    for bbox, text, conf in raw:
        if not text.strip():
            continue
        pts = np.array(bbox, dtype=float)
        x1, x2 = pts[:, 0].min(), pts[:, 0].max()
        y1, y2 = pts[:, 1].min(), pts[:, 1].max()
        items.append({
            "x1": x1, "x2": x2,
            "cy": (y1 + y2) / 2,
            "h":  y2 - y1,
            "text": text.strip(),
            "conf": conf,
        })

    if not items:
        return []

    # Sort top-to-bottom
    items.sort(key=lambda i: i["cy"])

    # Cluster into rows: fragments whose centres are within one text-height
    # of the current row's running centre belong to the same row.
    rows: list[list[dict]] = []
    for item in items:
        if not rows:
            rows.append([item])
            continue
        last_row = rows[-1]
        row_cy = sum(f["cy"] for f in last_row) / len(last_row)
        row_h  = max(f["h"] for f in last_row)
        if abs(item["cy"] - row_cy) < row_h * 0.7:
            last_row.append(item)
        else:
            rows.append([item])

    # Build one TabResult per row
    tabs: list[TabResult] = []
    for row in rows:
        row.sort(key=lambda f: f["x1"])           # left-to-right within row
        combined_text = " ".join(f["text"] for f in row)
        avg_conf      = sum(f["conf"]  for f in row) / len(row)
        cy_avg    = sum(f["cy"] for f in row) / len(row)
        # Use horizontal centre of the tab strip panel — clicking anywhere in the
        # row selects the tab, so this is more reliable than the OCR bbox centre.
        screen_cx = tab_strip.x + tab_strip.w // 2
        screen_cy = tab_strip.y + int(cy_avg / scale)
        tabs.append(TabResult(combined_text, screen_cx, screen_cy, avg_conf))

    return tabs


def find_tab(tab_name: str, tab_results: list[TabResult],
             threshold: float = 0.5) -> Optional[TabResult]:
    """
    Find the best-matching tab from OCR results using several strategies:
      1. Full fuzzy match against the whole OCR string.
      2. Substring containment (handles icon-prefixed rows like "> $" → "$").
      3. Fuzzy match against the right-hand portion of the OCR string
         (skips leading icon fragments that OCR'd as short tokens).
    Returns None if no match reaches *threshold*.
    """
    target = tab_name.lower().strip()
    best: Optional[TabResult] = None
    best_score = 0.0

    for tab in tab_results:
        text = tab.text.lower().strip()

        # Strategy 1: direct fuzzy match
        score = difflib.SequenceMatcher(None, target, text).ratio()

        # Strategy 2: target contained verbatim in OCR text
        if target in text:
            score = max(score, 0.95)

        # Strategy 3: fuzzy match against each right-aligned sub-phrase
        # (drop leading tokens one at a time to skip icon noise like ">" or ">")
        words = text.split()
        for start in range(1, len(words)):
            partial = " ".join(words[start:])
            partial_score = difflib.SequenceMatcher(None, target, partial).ratio()
            score = max(score, partial_score * 0.95)

        if score > best_score:
            best_score = score
            best = tab

    return best if best_score >= threshold else None
