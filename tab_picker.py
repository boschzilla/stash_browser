"""
Tab picker window.
Shows a screenshot of the current screen and lets the user click on
two stash tabs to set the source and destination tab names.
OCRs a region around each click to extract the tab label text.
"""

import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import numpy as np
import cv2

from config import Config
from capture import capture_full_screen
import vision


# How large a region (px at native resolution) to OCR around the click point
_OCR_HALF_W = 250
_OCR_HALF_H = 35


class TabPickerWindow:
    STEPS = ["SOURCE", "DESTINATION"]

    def __init__(self, cfg: Config, on_done):
        """
        cfg     : current Config (used for tab_strip region if calibrated).
        on_done : callback(src_name: str, dst_name: str)
        """
        self.cfg = cfg
        self.on_done = on_done
        self.step = 0          # 0 = picking source, 1 = picking destination
        self.results: list[str] = []  # [src_name, dst_name]

        self.screen_bgr = capture_full_screen()
        self.screen_h, self.screen_w = self.screen_bgr.shape[:2]
        self._build_window()

    # ------------------------------------------------------------------
    # Window setup
    # ------------------------------------------------------------------

    def _build_window(self):
        self.win = tk.Toplevel()
        self.win.title("Pick Stash Tabs")
        self.win.configure(bg="#1a1a1a")

        disp_w = self.win.winfo_screenwidth() - 40
        disp_h = self.win.winfo_screenheight() - 140
        scale_w = disp_w / self.screen_w
        scale_h = disp_h / self.screen_h
        self.scale = min(scale_w, scale_h, 1.0)
        self.disp_w = int(self.screen_w * self.scale)
        self.disp_h = int(self.screen_h * self.scale)

        self.instr_var = tk.StringVar()
        tk.Label(
            self.win, textvariable=self.instr_var,
            font=("Consolas", 12, "bold"), bg="#1a1a1a", fg="#e0c060",
        ).pack(padx=10, pady=6)

        self.detected_var = tk.StringVar(value="")
        tk.Label(
            self.win, textvariable=self.detected_var,
            font=("Consolas", 10), bg="#1a1a1a", fg="#88ff88",
        ).pack()

        btn_frame = tk.Frame(self.win, bg="#1a1a1a")
        btn_frame.pack(pady=6)
        tk.Button(btn_frame, text="Cancel", command=self.win.destroy,
                  bg="#6a2a2a", fg="white", padx=8).pack(side="left", padx=4)

        self.canvas = tk.Canvas(
            self.win, width=self.disp_w, height=self.disp_h,
            bg="black", cursor="crosshair",
        )
        self.canvas.pack(padx=10, pady=4)
        self.canvas.bind("<Button-1>", self._on_click)

        self._render_screenshot()
        self._update_instructions()

    def _render_screenshot(self):
        rgb = cv2.cvtColor(self.screen_bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb).resize((self.disp_w, self.disp_h), Image.LANCZOS)
        self._tk_img = ImageTk.PhotoImage(img)
        self.canvas.create_image(0, 0, anchor="nw", image=self._tk_img)

    def _update_instructions(self):
        label = self.STEPS[self.step]
        self.instr_var.set(
            f"Click on the {label} stash tab in the screenshot  "
            f"({self.step + 1} of {len(self.STEPS)})"
        )
        self.detected_var.set("")

    # ------------------------------------------------------------------
    # Click handling
    # ------------------------------------------------------------------

    def _on_click(self, event):
        # Map display coords → native screen coords
        screen_x = int(event.x / self.scale)
        screen_y = int(event.y / self.scale)

        tab_name = self._ocr_at(screen_x, screen_y)

        if not tab_name:
            self.detected_var.set("Could not read tab name — try clicking closer to the tab label.")
            return

        self.detected_var.set(f"Detected: \"{tab_name}\"  (click again to re-pick, or proceed)")

        # Draw marker
        self.canvas.create_oval(
            event.x - 6, event.y - 6, event.x + 6, event.y + 6,
            fill="#00ff88" if self.step == 0 else "#ff8800", outline="white", width=2,
        )
        self.canvas.create_text(
            event.x + 10, event.y,
            text=f"{self.STEPS[self.step]}: {tab_name}",
            fill="#ffffff", font=("Consolas", 9), anchor="w",
        )

        self.results.append(tab_name)
        self.step += 1

        if self.step >= len(self.STEPS):
            self.win.after(400, self._finish)
        else:
            self._update_instructions()

    def _finish(self):
        src, dst = self.results[0], self.results[1]
        self.win.destroy()
        self.on_done(src, dst)

    # ------------------------------------------------------------------
    # OCR
    # ------------------------------------------------------------------

    def _ocr_at(self, screen_x: int, screen_y: int) -> str:
        """
        OCR a region around the click point.
        If calibrated, read only the single row the user clicked on by cropping
        a narrow strip at that y-position spanning the full tab list width.
        """
        if self.cfg.calibrated and self.cfg.tab_strip.w > 0:
            return self._ocr_row_at(screen_x, screen_y)
        return self._ocr_patch(screen_x, screen_y)

    def _ocr_row_at(self, screen_x: int, screen_y: int) -> str:
        """
        OCR only the row the user clicked.
        Uses the full tab list width so long names like 'Heist (Remove-only)'
        are captured, but keeps the height tight (±20 px) so adjacent rows
        are excluded.
        """
        ts = self.cfg.tab_strip
        row_half_h = 20   # pixels at native resolution — one row is ~25–30 px
        x1 = ts.x
        x2 = ts.x + ts.w
        y1 = max(0, screen_y - row_half_h)
        y2 = min(self.screen_h, screen_y + row_half_h)
        patch = self.screen_bgr[y1:y2, x1:x2]

        if patch.size == 0:
            return ""

        reader = vision._get_ocr_reader()
        scale = 2
        scaled = cv2.resize(patch, (patch.shape[1] * scale, patch.shape[0] * scale),
                            interpolation=cv2.INTER_CUBIC)
        results = reader.readtext(scaled)

        if not results:
            return ""

        # Sort fragments left-to-right and join into the full tab name
        frags = sorted(
            [(np.array(bbox, dtype=float)[:, 0].min(), text.strip())
             for bbox, text, _conf in results if text.strip()],
            key=lambda f: f[0],
        )
        return " ".join(text for _, text in frags)

    def _ocr_patch(self, screen_x: int, screen_y: int) -> str:
        """OCR a small rectangle around the click point in the captured screenshot."""
        x1 = max(0, screen_x - _OCR_HALF_W)
        x2 = min(self.screen_w, screen_x + _OCR_HALF_W)
        y1 = max(0, screen_y - _OCR_HALF_H)
        y2 = min(self.screen_h, screen_y + _OCR_HALF_H)
        patch = self.screen_bgr[y1:y2, x1:x2]

        reader = vision._get_ocr_reader()
        scaled = cv2.resize(patch, (patch.shape[1] * 2, patch.shape[0] * 2), interpolation=cv2.INTER_CUBIC)
        results = reader.readtext(scaled)

        if not results:
            return ""
        # Return the highest-confidence result
        best = max(results, key=lambda r: r[2])
        return best[1].strip()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_tab_picker(cfg: Config, on_done) -> None:
    """Launch the tab picker window (call from main tkinter thread)."""
    TabPickerWindow(cfg, on_done)
