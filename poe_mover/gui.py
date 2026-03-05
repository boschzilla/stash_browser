"""
gui.py — Path of Exile Stash Mover GUI
"""

import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading
import time
import os

import engine as eng

# ── Palette ──────────────────────────────────────────────────────────────────
BG          = "#0e0c0a"
PANEL       = "#171310"
CARD        = "#1f1b17"
GOLD        = "#c8a052"
GOLD_DIM    = "#7a6030"
RED         = "#7a1f1f"
RED_BRIGHT  = "#c04040"
GREEN       = "#3a7a4a"
GREEN_LIT   = "#50c870"
TEXT        = "#ddd0bb"
TEXT_DIM    = "#706050"
BORDER      = "#2e2820"
AMBER       = "#e8a020"


class StashMoverApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PoE Stash Mover")
        self.root.configure(bg=BG)
        self.root.geometry("680x620")
        self.root.resizable(False, False)

        self._engine: eng.TransferEngine | None = None
        self._thread: threading.Thread | None   = None
        self._running = False
        self._paused  = False

        self._build()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build(self):
        # ── Title bar ──
        bar = tk.Frame(self.root, bg=RED, height=52)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="⚗  POE STASH MOVER",
                 bg=RED, fg=GOLD,
                 font=("Georgia", 16, "bold"), padx=18).pack(side="left", pady=10)
        tk.Label(bar, text="Standard Mode  ·  4K  ·  Claude Vision",
                 bg=RED, fg=GOLD_DIM, font=("Georgia", 9)).pack(side="right", padx=18)

        # ── Config panel ──
        cfg = tk.Frame(self.root, bg=PANEL, bd=0)
        cfg.pack(fill="x", padx=18, pady=(16, 0))

        # API key row
        self._row(cfg, "Anthropic API Key",
                  self._mk_entry(cfg, show="•", var_name="_key_var",
                                 default=os.environ.get("ANTHROPIC_API_KEY", "")))

        sep = tk.Frame(cfg, bg=BORDER, height=1)
        sep.pack(fill="x", pady=10)

        # Source / destination rows
        self._row(cfg, "Source Tab Name",
                  self._mk_entry(cfg, var_name="_src_var", placeholder="e.g.  Dump"))
        self._row(cfg, "Destination Tab Name",
                  self._mk_entry(cfg, var_name="_dst_var", placeholder="e.g.  Currency"))

        sep2 = tk.Frame(cfg, bg=BORDER, height=1)
        sep2.pack(fill="x", pady=10)

        # Countdown delay
        delay_row = tk.Frame(cfg, bg=PANEL)
        delay_row.pack(fill="x", pady=2)
        tk.Label(delay_row, text="Start Delay (seconds)",
                 bg=PANEL, fg=TEXT_DIM, font=("Consolas", 10), width=24, anchor="w"
                 ).pack(side="left")
        self._delay_var = tk.IntVar(value=5)
        delay_spin = tk.Spinbox(delay_row, from_=3, to=30, textvariable=self._delay_var,
                                width=5, bg=CARD, fg=TEXT, insertbackground=GOLD,
                                font=("Consolas", 11), relief="flat", bd=4,
                                buttonbackground=CARD)
        delay_spin.pack(side="left", padx=(8, 0))
        tk.Label(delay_row, text="(switch to PoE during countdown)",
                 bg=PANEL, fg=TEXT_DIM, font=("Consolas", 8)).pack(side="left", padx=8)

        # ── Button row ──
        btns = tk.Frame(self.root, bg=BG)
        btns.pack(fill="x", padx=18, pady=14)

        btn_cfg = dict(font=("Georgia", 11, "bold"), relief="flat",
                       cursor="hand2", pady=10, bd=0)

        self._btn_start = tk.Button(
            btns, text="▶  START", bg=GREEN, fg="#ffffff",
            activebackground=GREEN_LIT, activeforeground=BG,
            command=self._start, **btn_cfg)
        self._btn_start.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self._btn_pause = tk.Button(
            btns, text="⏸  PAUSE", bg=CARD, fg=GOLD,
            activebackground=GOLD, activeforeground=BG,
            command=self._toggle_pause, state="disabled", **btn_cfg)
        self._btn_pause.pack(side="left", fill="x", expand=True, padx=5)

        self._btn_stop = tk.Button(
            btns, text="■  STOP", bg=RED, fg="#ffffff",
            activebackground=RED_BRIGHT, activeforeground=BG,
            command=self._stop, state="disabled", **btn_cfg)
        self._btn_stop.pack(side="left", fill="x", expand=True, padx=(5, 0))

        # ── Status badge ──
        status_outer = tk.Frame(self.root, bg=CARD, bd=0)
        status_outer.pack(fill="x", padx=18, pady=(0, 6))
        status_inner = tk.Frame(status_outer, bg=CARD, padx=12, pady=6)
        status_inner.pack(fill="x")

        self._status_dot = tk.Label(status_inner, text="●", bg=CARD, fg=TEXT_DIM,
                                    font=("Consolas", 12))
        self._status_dot.pack(side="left")
        self._status_lbl = tk.Label(status_inner, text="Idle — configure tabs above and press START",
                                    bg=CARD, fg=TEXT_DIM, font=("Consolas", 9), anchor="w")
        self._status_lbl.pack(side="left", padx=(6, 0))

        # ── Log ──
        log_hdr = tk.Frame(self.root, bg=BG)
        log_hdr.pack(fill="x", padx=18, pady=(4, 0))
        tk.Label(log_hdr, text="ACTIVITY LOG", bg=BG, fg=GOLD_DIM,
                 font=("Georgia", 9, "bold")).pack(side="left")
        tk.Button(log_hdr, text="Clear", bg=BG, fg=TEXT_DIM,
                  font=("Consolas", 8), relief="flat", cursor="hand2",
                  command=self._clear_log).pack(side="right")

        self._log_box = scrolledtext.ScrolledText(
            self.root, bg=PANEL, fg=TEXT_DIM,
            font=("Consolas", 8), relief="flat",
            wrap="word", padx=10, pady=8, state="disabled",
            height=14
        )
        self._log_box.pack(fill="both", expand=True, padx=18, pady=(4, 14))

        # ── Failsafe reminder ──
        tk.Label(self.root,
                 text="⚠  Move mouse to TOP-LEFT corner at any time to emergency-abort",
                 bg=BG, fg=TEXT_DIM, font=("Consolas", 8)).pack(pady=(0, 8))

    # ── Widget helpers ────────────────────────────────────────────────────

    def _mk_entry(self, parent, var_name: str, show: str = "",
                  default: str = "", placeholder: str = "") -> tk.Entry:
        var = tk.StringVar(value=default or placeholder)
        setattr(self, var_name, var)
        e = tk.Entry(parent, textvariable=var, show=show,
                     bg=CARD, fg=TEXT if default else TEXT_DIM,
                     insertbackground=GOLD,
                     font=("Consolas", 10), relief="flat", bd=6, width=34)
        # Placeholder behaviour
        if placeholder and not default:
            def on_focus_in(ev, v=var, p=placeholder, widget=e):
                if v.get() == p:
                    v.set("")
                    widget.config(fg=TEXT)
            def on_focus_out(ev, v=var, p=placeholder, widget=e):
                if not v.get().strip():
                    v.set(p)
                    widget.config(fg=TEXT_DIM)
            e.bind("<FocusIn>",  on_focus_in)
            e.bind("<FocusOut>", on_focus_out)
        return e

    def _row(self, parent, label: str, widget: tk.Widget):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, bg=PANEL, fg=TEXT_DIM,
                 font=("Consolas", 10), width=24, anchor="w").pack(side="left")
        widget.pack(side="left", fill="x", expand=True)

    # ── Control logic ─────────────────────────────────────────────────────

    def _start(self):
        key = self._key_var.get().strip()
        src = self._src_var.get().strip()
        dst = self._dst_var.get().strip()
        delay = self._delay_var.get()

        # Basic validation
        placeholder_src = "e.g.  Dump"
        placeholder_dst = "e.g.  Currency"
        if not key or key.startswith("sk-ant") is False and len(key) < 10:
            messagebox.showerror("Missing API Key", "Please enter your Anthropic API key.")
            return
        if not src or src == placeholder_src:
            messagebox.showerror("Missing Source", "Please enter the source tab name.")
            return
        if not dst or dst == placeholder_dst:
            messagebox.showerror("Missing Destination", "Please enter the destination tab name.")
            return
        if src.lower() == dst.lower():
            messagebox.showerror("Same Tab", "Source and destination tabs must be different.")
            return

        # Set API key env var
        os.environ["ANTHROPIC_API_KEY"] = key

        self._btn_start.config(state="disabled")
        self._btn_pause.config(state="normal")
        self._btn_stop.config(state="normal")
        self._running = True
        self._paused  = False

        def run():
            # Countdown
            for i in range(delay, 0, -1):
                if self._engine and self._engine.is_stopped():
                    return
                self._set_status(f"Starting in {i}s — switch to Path of Exile now…", AMBER)
                time.sleep(1)

            self._set_status(f"Running: '{src}' → '{dst}'", GREEN_LIT)
            self._log(f"Transfer started: '{src}' → '{dst}'")

            e = eng.TransferEngine(log_fn=self._log)
            self._engine = e
            e.run(src, dst)

            self._running = False
            self.root.after(0, self._on_finished)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def _toggle_pause(self):
        if not self._engine:
            return
        if self._paused:
            self._engine.resume()
            self._paused = False
            self._btn_pause.config(text="⏸  PAUSE")
            self._set_status("Resumed.", GREEN_LIT)
            self._log("Resumed by user.")
        else:
            self._engine.pause()
            self._paused = True
            self._btn_pause.config(text="▶  RESUME")
            self._set_status("Paused — click RESUME to continue.", AMBER)
            self._log("Paused by user.")

    def _stop(self):
        if self._engine:
            self._engine.stop()
            self._log("Stop requested by user.")
        self._set_status("Stopping…", RED_BRIGHT)

    def _on_finished(self):
        self._btn_start.config(state="normal")
        self._btn_pause.config(state="disabled", text="⏸  PAUSE")
        self._btn_stop.config(state="disabled")
        self._running = False
        self._set_status("Finished.", GOLD)

    # ── Status / log helpers ──────────────────────────────────────────────

    def _set_status(self, msg: str, colour: str = TEXT_DIM):
        def _do():
            self._status_dot.config(fg=colour)
            self._status_lbl.config(text=msg, fg=colour)
        self.root.after(0, _do)

    def _log(self, msg: str):
        def _do():
            import datetime
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            self._log_box.config(state="normal")
            self._log_box.insert("end", f"[{ts}] {msg}\n")
            self._log_box.see("end")
            self._log_box.config(state="disabled")
        self.root.after(0, _do)

    def _clear_log(self):
        self._log_box.config(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.config(state="disabled")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    app = StashMoverApp(root)
    root.mainloop()
