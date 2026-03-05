"""
Configuration management for PoE Stash Mover.
Loads/saves config.json with screen region definitions.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


@dataclass
class GridRegion:
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
    cols: int = 12
    rows: int = 12


@dataclass
class Config:
    # Stash grid region (12x12 cells)
    stash_grid: GridRegion = field(default_factory=lambda: GridRegion(cols=12, rows=12))
    # Player inventory region (12x5 cells)
    inventory_grid: GridRegion = field(default_factory=lambda: GridRegion(cols=12, rows=5))
    # Tab strip region (the row of clickable tab labels)
    tab_strip: GridRegion = field(default_factory=GridRegion)
    # Pixel coordinates of the scroll arrows on the tab strip
    tab_scroll_left: list = field(default_factory=lambda: [0, 0])
    tab_scroll_right: list = field(default_factory=lambda: [0, 0])
    # Delays and behaviour
    action_delay: float = 0.15      # seconds between actions
    click_jitter: int = 3           # random pixel offset for more natural clicks
    cell_sample_size: int = 8       # px square sampled from center of each cell for occupancy
    empty_value_threshold: int = 30 # (legacy, kept for compat)
    bright_pixel_threshold: int = 45  # HSV Value above this counts as a "bright" pixel
    bright_pixel_ratio: float = 0.05  # fraction of bright pixels needed to call a cell occupied
    tab_scroll_steps: int = 3       # scroll wheel ticks per tab-strip scroll
    max_tab_scrolls: int = 30       # max scroll attempts when looking for a tab
    inventory_dump_threshold: float = 0.90  # dump to dest when inventory is this % full
    calibrated: bool = False        # set True after successful calibration
    last_src_tab: str = ""          # last used source tab name
    last_dst_tab: str = ""          # last used destination tab name


def _grid_to_dict(g: GridRegion) -> dict:
    return {"x": g.x, "y": g.y, "w": g.w, "h": g.h, "cols": g.cols, "rows": g.rows}


def _dict_to_grid(d: dict, default_cols: int = 12, default_rows: int = 12) -> GridRegion:
    return GridRegion(
        x=d.get("x", 0),
        y=d.get("y", 0),
        w=d.get("w", 0),
        h=d.get("h", 0),
        cols=d.get("cols", default_cols),
        rows=d.get("rows", default_rows),
    )


def load_config() -> Config:
    if not CONFIG_PATH.exists():
        return Config()
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
        cfg = Config()   # start from dataclass defaults
        cfg.stash_grid = _dict_to_grid(data.get("stash_grid", {}), 12, 12)
        cfg.inventory_grid = _dict_to_grid(data.get("inventory_grid", {}), 12, 5)
        cfg.tab_strip = _dict_to_grid(data.get("tab_strip", {}))
        cfg.tab_scroll_left = data.get("tab_scroll_left", cfg.tab_scroll_left)
        cfg.tab_scroll_right = data.get("tab_scroll_right", cfg.tab_scroll_right)
        cfg.action_delay = data.get("action_delay", cfg.action_delay)
        cfg.click_jitter = data.get("click_jitter", cfg.click_jitter)
        cfg.cell_sample_size = data.get("cell_sample_size", cfg.cell_sample_size)
        cfg.empty_value_threshold = data.get("empty_value_threshold", cfg.empty_value_threshold)
        cfg.bright_pixel_threshold = data.get("bright_pixel_threshold", cfg.bright_pixel_threshold)
        cfg.bright_pixel_ratio = data.get("bright_pixel_ratio", cfg.bright_pixel_ratio)
        cfg.tab_scroll_steps = data.get("tab_scroll_steps", cfg.tab_scroll_steps)
        cfg.max_tab_scrolls = data.get("max_tab_scrolls", cfg.max_tab_scrolls)
        cfg.inventory_dump_threshold = data.get("inventory_dump_threshold", cfg.inventory_dump_threshold)
        cfg.calibrated = data.get("calibrated", cfg.calibrated)
        cfg.last_src_tab = data.get("last_src_tab", cfg.last_src_tab)
        cfg.last_dst_tab = data.get("last_dst_tab", cfg.last_dst_tab)
        return cfg
    except Exception as e:
        print(f"[config] Failed to load config.json: {e}. Using defaults.")
        return Config()


def save_config(cfg: Config) -> None:
    data = {
        "stash_grid": _grid_to_dict(cfg.stash_grid),
        "inventory_grid": _grid_to_dict(cfg.inventory_grid),
        "tab_strip": _grid_to_dict(cfg.tab_strip),
        "tab_scroll_left": cfg.tab_scroll_left,
        "tab_scroll_right": cfg.tab_scroll_right,
        "action_delay": cfg.action_delay,
        "click_jitter": cfg.click_jitter,
        "cell_sample_size": cfg.cell_sample_size,
        "empty_value_threshold": cfg.empty_value_threshold,
        "bright_pixel_threshold": cfg.bright_pixel_threshold,
        "bright_pixel_ratio": cfg.bright_pixel_ratio,
        "tab_scroll_steps": cfg.tab_scroll_steps,
        "max_tab_scrolls": cfg.max_tab_scrolls,
        "inventory_dump_threshold": cfg.inventory_dump_threshold,
        "calibrated": cfg.calibrated,
        "last_src_tab": cfg.last_src_tab,
        "last_dst_tab": cfg.last_dst_tab,
    }
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)
