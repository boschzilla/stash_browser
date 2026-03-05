"""
PoE Stash Item Mover — Main GUI
Run: python main.py
"""

__version__ = "1.1.0"

import os
import sys
import queue
import time
import tkinter as tk
from tkinter import ttk, messagebox

import keyboard

from config import load_config, save_config
import mover as mover_module
import calibrate
import tab_picker
import vision


# ---------------------------------------------------------------------------
# Main Application Window
# ---------------------------------------------------------------------------

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"PoE Stash Mover v{__version__}")
        self.root.configure(bg="#1a1a1a")
        self.root.resizable(False, False)

        self.cfg = load_config()
        self.active_mover = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self._space_hotkey = None

        self._build_ui()
        self._poll_log()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Warn if not yet calibrated
        if not self.cfg.calibrated:
            self._append_log(
                "Not calibrated. Click 'Calibrate' with your stash open in PoE before starting."
            )

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        # Title
        tk.Label(
            self.root,
            text="Path of Exile — Stash Mover",
            font=("Consolas", 14, "bold"),
            bg="#1a1a1a",
            fg="#c8a840",
        ).grid(row=0, column=0, columnspan=3, **pad)

        # Source tab
        tk.Label(self.root, text="Source Tab:", bg="#1a1a1a", fg="#cccccc",
                 font=("Consolas", 11)).grid(row=1, column=0, sticky="e", padx=(10, 4), pady=4)
        self.src_var = tk.StringVar(value=self.cfg.last_src_tab)
        tk.Entry(self.root, textvariable=self.src_var, font=("Consolas", 11),
                 bg="#2a2a2a", fg="white", insertbackground="white", width=22,
                 relief="flat").grid(row=1, column=1, sticky="w", pady=4)

        # Destination tab
        tk.Label(self.root, text="Destination Tab:", bg="#1a1a1a", fg="#cccccc",
                 font=("Consolas", 11)).grid(row=2, column=0, sticky="e", padx=(10, 4), pady=4)
        self.dst_var = tk.StringVar(value=self.cfg.last_dst_tab)
        tk.Entry(self.root, textvariable=self.dst_var, font=("Consolas", 11),
                 bg="#2a2a2a", fg="white", insertbackground="white", width=22,
                 relief="flat").grid(row=2, column=1, sticky="w", pady=4)

        # Inter-click delay slider
        tk.Label(self.root, text="Click Delay (s):", bg="#1a1a1a", fg="#cccccc",
                 font=("Consolas", 10)).grid(row=3, column=0, sticky="e", padx=(10, 4), pady=2)
        self.delay_var = tk.DoubleVar(value=self.cfg.action_delay)
        delay_scale = tk.Scale(
            self.root, variable=self.delay_var, from_=0.0, to=2.0, resolution=0.05,
            orient="horizontal", length=200, bg="#2a2a2a", fg="white",
            troughcolor="#444", highlightthickness=0,
            command=self._on_delay_change,
        )
        delay_scale.grid(row=3, column=1, sticky="w", pady=2)

        # Buttons row
        btn_frame = tk.Frame(self.root, bg="#1a1a1a")
        btn_frame.grid(row=4, column=0, columnspan=3, pady=8)

        self.start_btn = tk.Button(
            btn_frame, text="Start", command=self._on_start,
            bg="#2a6a2a", fg="white", font=("Consolas", 11, "bold"),
            width=10, relief="flat",
        )
        self.start_btn.pack(side="left", padx=5)

        self.stop_btn = tk.Button(
            btn_frame, text="Stop", command=self._on_stop, state="disabled",
            bg="#6a2a2a", fg="white", font=("Consolas", 11, "bold"),
            width=10, relief="flat",
        )
        self.stop_btn.pack(side="left", padx=5)

        self.pick_btn = tk.Button(
            btn_frame, text="Pick Tabs", command=self._on_pick_tabs,
            bg="#4a2a6a", fg="white", font=("Consolas", 11),
            width=10, relief="flat",
        )
        self.pick_btn.pack(side="left", padx=5)

        self.calib_btn = tk.Button(
            btn_frame, text="Calibrate", command=self._on_calibrate,
            bg="#2a4a6a", fg="white", font=("Consolas", 11),
            width=10, relief="flat",
        )
        self.calib_btn.pack(side="left", padx=5)

        self.dump_btn = tk.Button(
            btn_frame, text="Dump Inv", command=self._on_dump_inventory,
            bg="#6a3a1a", fg="white", font=("Consolas", 11),
            width=10, relief="flat",
        )
        self.dump_btn.pack(side="left", padx=5)

        self.debug_btn = tk.Button(
            btn_frame, text="Debug View", command=self._on_debug,
            bg="#4a4a1a", fg="white", font=("Consolas", 11),
            width=10, relief="flat",
        )
        self.debug_btn.pack(side="left", padx=5)

        self.reload_btn = tk.Button(
            btn_frame, text="Reload", command=self._on_reload,
            bg="#3a3a3a", fg="white", font=("Consolas", 11),
            width=8, relief="flat",
        )
        self.reload_btn.pack(side="left", padx=5)

        # Status label
        self.status_var = tk.StringVar(value="Idle")
        tk.Label(
            self.root, textvariable=self.status_var,
            font=("Consolas", 10, "italic"), bg="#1a1a1a", fg="#aaaaaa",
        ).grid(row=5, column=0, columnspan=3)

        # Log area
        log_frame = tk.Frame(self.root, bg="#1a1a1a")
        log_frame.grid(row=6, column=0, columnspan=3, padx=10, pady=(4, 10))

        self.log_text = tk.Text(
            log_frame, width=60, height=16,
            font=("Consolas", 9), bg="#0d0d0d", fg="#aaffaa",
            state="disabled", relief="flat", wrap="word",
        )
        scrollbar = tk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both")
        scrollbar.pack(side="right", fill="y")

        # Keyboard shortcut: Escape = stop
        self.root.bind("<Escape>", lambda _: self._on_stop())

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_start(self):
        src = self.src_var.get().strip()
        dst = self.dst_var.get().strip()
        if not src or not dst:
            messagebox.showwarning("Input required", "Please enter both source and destination tab names.")
            return
        if src == dst:
            messagebox.showwarning("Same tab", "Source and destination tabs are the same.")
            return
        if not self.cfg.calibrated:
            if not messagebox.askyesno(
                "Not calibrated",
                "The tool has not been calibrated yet.\n"
                "Screen regions may be wrong.\n\n"
                "Continue anyway?",
            ):
                return

        # Persist tab names so they're restored on next launch.
        self.cfg.last_src_tab = src
        self.cfg.last_dst_tab = dst
        save_config(self.cfg)

        self._append_log("-" * 50)
        self.cfg.action_delay = self.delay_var.get()
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_var.set("Running...")

        def log_fn(msg: str):
            self.log_queue.put(msg)

        self.active_mover = mover_module.start_mover(self.cfg, src, dst, log_fn)

        # Global spacebar hotkey — fires even when PoE has focus
        try:
            self._space_hotkey = keyboard.add_hotkey("space", self._on_stop)
        except Exception:
            pass

        # Poll until done
        self._poll_mover()

    def _on_stop(self):
        if self.active_mover:
            self.active_mover.stop()
        self._set_idle()

    def _on_dump_inventory(self):
        """Ctrl+Shift+click every inventory item into whichever stash tab is currently open."""
        if not self.cfg.calibrated:
            if not messagebox.askyesno(
                "Not calibrated",
                "The tool has not been calibrated yet.\nContinue anyway?",
            ):
                return

        self._append_log("-" * 50)
        self._append_log("Dumping inventory into current stash tab...")
        self.cfg.action_delay = self.delay_var.get()
        self.start_btn.config(state="disabled")
        self.dump_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_var.set("Dumping inventory...")

        def log_fn(msg: str):
            self.log_queue.put(msg)

        import threading
        import actions
        import vision

        # Use a minimal stand-in so _poll_mover can detect completion
        class _FakeMover:
            def __init__(self):
                self.stop_flag = threading.Event()
            def stop(self):
                self.stop_flag.set()

        self.active_mover = _FakeMover()
        stop_flag = self.active_mover.stop_flag

        def _run_wrapped():
            try:
                # Give the user time to click back into the game window.
                for secs in (3, 2, 1):
                    if stop_flag.is_set():
                        log_fn("Stopped.")
                        return
                    log_fn(f"  Click into PoE now... starting in {secs}s")
                    time.sleep(1.0)

                # Focus PoE so ctrl/shift key events land on the game window.
                focused = actions.focus_game_window()
                actions.release_modifier_keys()
                log_fn(f"  Game window {'focused' if focused else 'not found — make sure PoE is open'}.")

                # --- Phase 1: ctrl_click each occupied inventory cell ----------
                inv_grid = vision.scan_grid_occupancy(self.cfg.inventory_grid, self.cfg)
                cells_p1 = vision.nearest_neighbor_order([
                    vision.cell_center(self.cfg.inventory_grid, col, row)
                    for col, row in vision.occupied_cells(inv_grid)
                ])

                if not cells_p1:
                    log_fn("Inventory empty — nothing to dump.")
                    return

                log_fn(f"  {len(cells_p1)} cell(s) found — Ctrl+clicking into stash...")
                actions.move_to(cells_p1[0][0], cells_p1[0][1], self.cfg)
                time.sleep(0.2)

                for cx, cy in cells_p1:
                    if stop_flag.is_set():
                        log_fn("Stopped.")
                        return
                    log_fn(f"    click ({cx}, {cy})")
                    actions.ctrl_click(cx, cy, self.cfg)

                # --- Phase 2: ctrl_shift_click any stragglers -----------------
                inv_grid2 = vision.scan_grid_occupancy(self.cfg.inventory_grid, self.cfg)
                cells_p2 = vision.nearest_neighbor_order([
                    vision.cell_center(self.cfg.inventory_grid, col, row)
                    for col, row in vision.occupied_cells(inv_grid2)
                ])

                if cells_p2:
                    log_fn(f"  {len(cells_p2)} straggler(s) — Ctrl+Shift+clicking...")
                    for cx, cy in cells_p2:
                        if stop_flag.is_set():
                            log_fn("Stopped.")
                            return
                        log_fn(f"    click ({cx}, {cy})")
                        actions.ctrl_shift_click(cx, cy, self.cfg)

                remaining = vision.count_occupied(
                    vision.scan_grid_occupancy(self.cfg.inventory_grid, self.cfg)
                )
                if remaining:
                    log_fn(f"WARNING: {remaining} cell(s) still in inventory — continuing anyway.")
                else:
                    log_fn("Inventory confirmed empty — done.")
            except Exception as e:
                log_fn(f"ERROR: {e}")
            finally:
                stop_flag.set()   # triggers _poll_mover to reset UI

        threading.Thread(target=_run_wrapped, daemon=True).start()
        self._poll_mover()

    def _on_close(self):
        if self.active_mover:
            self.active_mover.stop()
        self.cfg.action_delay = self.delay_var.get()
        save_config(self.cfg)
        self.root.destroy()

    def _on_pick_tabs(self):
        tab_picker.run_tab_picker(self.cfg, self._on_tabs_picked)

    def _on_tabs_picked(self, src_name: str, dst_name: str):
        self.src_var.set(src_name)
        self.dst_var.set(dst_name)
        self._append_log(f"Tabs selected — Source: '{src_name}', Destination: '{dst_name}'")

    def _on_reload(self):
        """Save config and restart the process to pick up code changes."""
        self.cfg.action_delay = self.delay_var.get()
        save_config(self.cfg)
        if self.active_mover:
            self.active_mover.stop()
        self.root.destroy()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def _on_debug(self):
        if not self.cfg.calibrated:
            messagebox.showwarning("Not calibrated", "Calibrate first so grid regions are defined.")
            return
        try:
            stash_path = vision.save_debug_overlay(
                self.cfg.stash_grid, self.cfg, "debug_stash.png"
            )
            inv_path = vision.save_debug_overlay(
                self.cfg.inventory_grid, self.cfg, "debug_inventory.png"
            )
            self._append_log(f"Debug images saved:")
            self._append_log(f"  {stash_path}")
            self._append_log(f"  {inv_path}")
            os.startfile(stash_path)
            os.startfile(inv_path)
        except Exception as e:
            self._append_log(f"Debug error: {e}")

    def _on_calibrate(self):
        calibrate.run_calibration(self.cfg, self._on_calibration_done)

    def _on_calibration_done(self, updated_cfg):
        self.cfg = updated_cfg
        self._append_log("Calibration saved.")
        self.status_var.set("Idle — calibrated")

    def _on_delay_change(self, _value):
        self.cfg.action_delay = self.delay_var.get()

    # ------------------------------------------------------------------
    # Polling helpers
    # ------------------------------------------------------------------

    def _poll_log(self):
        """Drain the log queue and append to the text widget."""
        while not self.log_queue.empty():
            try:
                msg = self.log_queue.get_nowait()
                self._append_log(msg)
            except queue.Empty:
                break
        self.root.after(100, self._poll_log)

    def _poll_mover(self):
        """Check if the mover thread is still alive; reset UI when done."""
        if self.active_mover and self.active_mover.stop_flag.is_set():
            self._set_idle()
            return
        # Check if the mover's thread finished by trying to detect inactivity via queue
        # We use a simple approach: schedule ourselves and check
        self.root.after(500, self._poll_mover)

    def _set_idle(self):
        if self._space_hotkey is not None:
            try:
                keyboard.remove_hotkey(self._space_hotkey)
            except Exception:
                pass
            self._space_hotkey = None
        self.start_btn.config(state="normal")
        self.dump_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.status_var.set("Idle")
        self.active_mover = None

    # ------------------------------------------------------------------
    # Log display
    # ------------------------------------------------------------------

    def _append_log(self, msg: str):
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _move_to_monitor2(root: tk.Tk) -> None:
    """Move the window to monitor 2 if it exists, otherwise leave it on monitor 1."""
    try:
        import mss
        with mss.mss() as sct:
            monitors = sct.monitors  # index 0 = combined, 1 = primary, 2+ = individual
            if len(monitors) >= 3:  # at least 2 real monitors
                m2 = monitors[2]
                root.update_idletasks()
                # Centre the window on monitor 2
                win_w = root.winfo_width()
                win_h = root.winfo_height()
                x = m2["left"] + (m2["width"] - win_w) // 2
                y = m2["top"] + (m2["height"] - win_h) // 2
                root.geometry(f"+{x}+{y}")
    except Exception:
        pass  # silently fall back to default position


def main():
    root = tk.Tk()
    app = App(root)
    root.update_idletasks()   # let tkinter compute window size first
    _move_to_monitor2(root)
    root.mainloop()


if __name__ == "__main__":
    main()
