"""
Calibration overlay window.
Captures the current screen, shows it scaled to fit the display,
and lets the user click to define the stash grid, inventory, and tab list regions.
"""

import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import numpy as np
import cv2

from config import Config, GridRegion, save_config
from capture import capture_full_screen


# ---------------------------------------------------------------------------
# Calibration steps definition
# ---------------------------------------------------------------------------
STEPS = [
    {
        "name": "Stash Grid",
        "instructions": (
            "STASH GRID\n\n"
            "Set Grid cols × rows above FIRST (Normal = 12×12, Quad = 24×24).\n\n"
            "Click the CENTER of the TOP-LEFT cell (row 1, col 1).\n"
            "Then click the CENTER of the BOTTOM-RIGHT cell.\n\n"
            "Cyan dots will appear — verify each dot is centred in a stash cell.\n"
            "If misaligned, click Retry Step and try again."
        ),
        "clicks": 2,
        "target": "stash_grid",
        "mode": "cell_centers",
    },
    {
        "name": "Player Inventory",
        "instructions": (
            "PLAYER INVENTORY\n\n"
            "Inventory is always 12×5 — set Grid to 12×5 above if changed.\n\n"
            "Click the CENTER of the TOP-LEFT inventory cell.\n"
            "Then click the CENTER of the BOTTOM-RIGHT inventory cell.\n\n"
            "Cyan dots will appear — verify alignment, then Retry if needed."
        ),
        "clicks": 2,
        "target": "inventory_grid",
        "mode": "cell_centers",
    },
    {
        "name": "Tab List",
        "instructions": (
            "TAB LIST (vertical panel)\n\n"
            "Click the TOP-LEFT corner of the vertical tab list\n"
            "(the panel on the RIGHT side of the screen that lists all\n"
            "stash tabs top-to-bottom — NOT the horizontal strip).\n"
            "Then click the BOTTOM-RIGHT corner."
        ),
        "clicks": 2,
        "target": "tab_strip",
        "mode": "corners",
    },
]


class CalibrationWindow:
    def __init__(self, parent_cfg: Config, on_done):
        """
        parent_cfg: the Config object to update.
        on_done: callback(cfg) called when calibration is saved.
        """
        self.cfg = parent_cfg
        self.on_done = on_done

        # Capture screen before opening the window
        self.screen_bgr = capture_full_screen()
        self.screen_h, self.screen_w = self.screen_bgr.shape[:2]

        self.step_index = 0
        self.click_points: list[tuple[int, int]] = []  # raw screen coords
        self.pending_region_clicks: list[tuple[int, int]] = []  # for current step

        self._build_window()

    def _build_window(self):
        self.win = tk.Toplevel()
        self.win.title("Calibration")
        self.win.configure(bg="#1a1a1a")
        self.win.resizable(True, True)

        # Determine display scale so the screenshot fits on screen
        screen_display_w = self.win.winfo_screenwidth()
        screen_display_h = self.win.winfo_screenheight()
        scale_w = (screen_display_w - 40) / self.screen_w
        scale_h = (screen_display_h - 140) / self.screen_h
        self.scale = min(scale_w, scale_h, 1.0)  # never upscale

        self.disp_w = int(self.screen_w * self.scale)
        self.disp_h = int(self.screen_h * self.scale)

        # Instruction label
        self.label_var = tk.StringVar()
        lbl = tk.Label(
            self.win,
            textvariable=self.label_var,
            font=("Consolas", 11),
            bg="#1a1a1a",
            fg="#e0c060",
            justify="left",
            wraplength=self.disp_w,
        )
        lbl.pack(padx=10, pady=8, anchor="w")

        # Buttons above the screenshot so they're always visible
        btn_frame = tk.Frame(self.win, bg="#1a1a1a")
        btn_frame.pack(pady=6)
        tk.Button(btn_frame, text="Retry Step", command=self._retry_step,
                  bg="#444", fg="white", padx=8).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Skip Step", command=self._skip_step,
                  bg="#555", fg="white", padx=8).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Save & Close", command=self._save,
                  bg="#2a6a2a", fg="white", padx=8).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Cancel", command=self.win.destroy,
                  bg="#6a2a2a", fg="white", padx=8).pack(side="left", padx=4)

        # Cols × Rows spinboxes — visible for grid steps, let user correct the count
        tk.Label(btn_frame, text="  Grid:", bg="#1a1a1a", fg="#aaa",
                 font=("Consolas", 10)).pack(side="left", padx=(12, 2))
        self.cols_var = tk.IntVar(value=self.cfg.stash_grid.cols)
        tk.Spinbox(btn_frame, textvariable=self.cols_var, from_=1, to=48, width=4,
                   bg="#2a2a2a", fg="white", buttonbackground="#444",
                   font=("Consolas", 10)).pack(side="left")
        tk.Label(btn_frame, text="×", bg="#1a1a1a", fg="#aaa",
                 font=("Consolas", 10)).pack(side="left", padx=2)
        self.rows_var = tk.IntVar(value=self.cfg.stash_grid.rows)
        tk.Spinbox(btn_frame, textvariable=self.rows_var, from_=1, to=48, width=4,
                   bg="#2a2a2a", fg="white", buttonbackground="#444",
                   font=("Consolas", 10)).pack(side="left")

        # Canvas for the screenshot
        self.canvas = tk.Canvas(
            self.win,
            width=self.disp_w,
            height=self.disp_h,
            bg="black",
            cursor="crosshair",
        )
        self.canvas.pack(padx=10, pady=4)
        self.canvas.bind("<Button-1>", self._on_click)

        self._render_screenshot()
        self._update_instructions()

    def _render_screenshot(self):
        """Draw the captured screenshot onto the canvas."""
        rgb = cv2.cvtColor(self.screen_bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb).resize((self.disp_w, self.disp_h), Image.LANCZOS)
        self._tk_img = ImageTk.PhotoImage(img)
        self.canvas.create_image(0, 0, anchor="nw", image=self._tk_img)

    def _update_instructions(self):
        if self.step_index >= len(STEPS):
            self.label_var.set("All regions defined. Click 'Save & Close'.")
            return
        step = STEPS[self.step_index]
        clicks_remaining = step["clicks"] - len(self.pending_region_clicks)
        extra = f"\n\n({clicks_remaining} click(s) remaining for this step)"
        self.label_var.set(step["instructions"] + extra)

        # Sync spinboxes to the current step's grid dimensions
        target = step.get("target", "")
        if target == "stash_grid":
            self.cols_var.set(self.cfg.stash_grid.cols)
            self.rows_var.set(self.cfg.stash_grid.rows)
        elif target == "inventory_grid":
            self.cols_var.set(self.cfg.inventory_grid.cols)
            self.rows_var.set(self.cfg.inventory_grid.rows)

    def _on_click(self, event):
        if self.step_index >= len(STEPS):
            return

        step = STEPS[self.step_index]
        # Convert display coords back to screen coords
        screen_x = int(event.x / self.scale)
        screen_y = int(event.y / self.scale)

        self.pending_region_clicks.append((screen_x, screen_y))

        # Draw a small marker on the canvas
        cx, cy = event.x, event.y
        color = "#00ff88" if len(self.pending_region_clicks) == 1 else "#ff4444"
        self.canvas.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill=color, outline="white")

        if len(self.pending_region_clicks) >= step["clicks"]:
            self._commit_step()

    def _commit_step(self):
        step = STEPS[self.step_index]
        pts = self.pending_region_clicks
        cx1, cy1 = pts[0]
        cx2, cy2 = pts[1]
        target = step["target"]

        if step.get("mode") == "cell_centers":
            # User clicked the centre of the top-left cell and the centre of
            # the bottom-right cell.  Derive the full grid region from those
            # two centre points so every subsequent cell_center() call lands
            # exactly where the user aimed.
            # Use the spinbox values so Normal (12×12) and Quad (24×24) both work.
            cols = max(1, self.cols_var.get())
            rows = max(1, self.rows_var.get())
            # Also persist the (possibly updated) cols/rows back into cfg
            if target == "stash_grid":
                self.cfg.stash_grid.cols = cols
                self.cfg.stash_grid.rows = rows
            else:
                self.cfg.inventory_grid.cols = cols
                self.cfg.inventory_grid.rows = rows
            # Distance between the two clicked centres spans (cols-1) cell widths.
            cell_w = abs(cx2 - cx1) / max(cols - 1, 1)
            cell_h = abs(cy2 - cy1) / max(rows - 1, 1)
            x = round(min(cx1, cx2) - cell_w / 2)
            y = round(min(cy1, cy2) - cell_h / 2)
            w = round(cols * cell_w)
            h = round(rows * cell_h)
        else:
            # tab_strip: user clicked outer corners, use as-is.
            x, y = min(cx1, cx2), min(cy1, cy2)
            w, h = abs(cx2 - cx1), abs(cy2 - cy1)

        if target == "stash_grid":
            self.cfg.stash_grid.x = x
            self.cfg.stash_grid.y = y
            self.cfg.stash_grid.w = w
            self.cfg.stash_grid.h = h
        elif target == "inventory_grid":
            self.cfg.inventory_grid.x = x
            self.cfg.inventory_grid.y = y
            self.cfg.inventory_grid.w = w
            self.cfg.inventory_grid.h = h
        elif target == "tab_strip":
            self.cfg.tab_strip.x = x
            self.cfg.tab_strip.y = y
            self.cfg.tab_strip.w = w
            self.cfg.tab_strip.h = h

        # Draw a rectangle overlay on canvas for visual confirmation
        sx1 = int(pts[0][0] * self.scale)
        sy1 = int(pts[0][1] * self.scale)
        sx2 = int(pts[1][0] * self.scale)
        sy2 = int(pts[1][1] * self.scale)
        self.canvas.create_rectangle(sx1, sy1, sx2, sy2, outline="#00ff88", width=2)

        # For cell_centers mode: draw a cyan dot at every computed cell centre
        # so the user can verify the grid aligns with the actual PoE cells.
        if step.get("mode") == "cell_centers":
            if target == "stash_grid":
                cols, rows = self.cfg.stash_grid.cols, self.cfg.stash_grid.rows
            else:
                cols, rows = self.cfg.inventory_grid.cols, self.cfg.inventory_grid.rows
            cw = w / cols
            ch = h / rows
            for row in range(rows):
                for col in range(cols):
                    dot_x = (x + (col + 0.5) * cw) * self.scale
                    dot_y = (y + (row + 0.5) * ch) * self.scale
                    r = 3
                    self.canvas.create_oval(
                        dot_x - r, dot_y - r, dot_x + r, dot_y + r,
                        fill="cyan", outline="",
                    )

        self.pending_region_clicks = []
        self.step_index += 1
        self._update_instructions()

    def _retry_step(self):
        """Clear pending clicks for the current step so the user can try again."""
        self.pending_region_clicks = []
        self._render_screenshot()   # redraw clean screenshot (removes dots/markers)
        self._update_instructions()

    def _skip_step(self):
        self.pending_region_clicks = []
        self.step_index += 1
        self._update_instructions()

    def _save(self):
        self.cfg.calibrated = True
        save_config(self.cfg)
        self.win.destroy()
        self.on_done(self.cfg)


def run_calibration(cfg: Config, on_done) -> None:
    """Launch calibration window (must be called from the main tkinter thread)."""
    CalibrationWindow(cfg, on_done)
