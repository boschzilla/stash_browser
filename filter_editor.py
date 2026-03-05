#!/usr/bin/env python3
"""PoE Item Filter Editor — Visual color configuration tool for Path of Exile loot filters."""

import tkinter as tk
from tkinter import ttk, colorchooser, messagebox
from tkinter.filedialog import asksaveasfilename
import os
from dataclasses import dataclass, field
from typing import List

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POE_FILTER_DIR = os.path.join(
    os.environ.get("USERPROFILE", os.path.expanduser("~")),
    "OneDrive", "Documents", "My Games", "Path of Exile",
)

SAMPLE_ITEMS: dict[str, list[str]] = {
    "Currency":             ["Chaos Orb", "Divine Orb", "Exalted Orb", "Mirror of Kalandra"],
    "Divination Cards":     ["The Doctor", "The Fool", "A Mother's Parting Gift"],
    "Skill Gems":           ["Fireball", "Flicker Strike", "Raise Zombie"],
    "Quest Items":          ["Maligaro's Spike", "Malachai's Heart"],
    "Maps":                 ["Strand Map", "Cemetery Map", "Crimson Township"],
    "Jewels":               ["Viridian Jewel", "Cobalt Jewel", "Timeless Jewel"],
    "Flasks":               ["Divine Life Flask", "Quicksilver Flask of Adrenaline"],
    "Unique Items":         ["Headhunter", "Kaom's Heart", "Shavronne's Wrappings"],
    "Rare Items":           ["Viper Strike", "Soul Tether", "Havoc Loop", "Dusk Shroud"],
    "Magic Items":          ["Blazing Sword of Flames", "Coral Ring of Resistance"],
    "Normal Items":         ["Iron Sword", "Leather Belt", "Linen Robe"],
    "Hide Everything Else": ["Rusted Sword", "Twig Spirit Shield"],
}

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class FilterRule:
    name: str
    show: bool = True           # True = Show block, False = Hide block
    enabled: bool = True        # include this block in output
    conditions: dict = field(default_factory=dict)
    text_color: list = field(default_factory=lambda: [200, 200, 200, 255])
    bg_color: list = field(default_factory=lambda: [0, 0, 0, 240])
    border_color: list = field(default_factory=lambda: [200, 200, 200, 255])
    font_size: int = 32
    comment: str = ""


def _make_default_rules() -> List[FilterRule]:
    return [
        FilterRule("Currency",
            conditions={"Class": '"Currency"'},
            text_color=[170, 158, 130, 255], bg_color=[0, 0, 0, 240],
            border_color=[170, 158, 130, 255], font_size=40,
            comment="Currency items"),
        FilterRule("Divination Cards",
            conditions={"Class": '"Divination Cards"'},
            text_color=[14, 186, 255, 255], bg_color=[0, 0, 0, 240],
            border_color=[14, 186, 255, 255], font_size=38,
            comment="Divination cards"),
        FilterRule("Skill Gems",
            conditions={"Class": '"Gems"'},
            text_color=[26, 162, 155, 255], bg_color=[0, 0, 0, 240],
            border_color=[26, 162, 155, 255], font_size=34,
            comment="Skill and support gems"),
        FilterRule("Quest Items",
            conditions={"Class": '"Quest Items"'},
            text_color=[74, 230, 58, 255], bg_color=[0, 0, 0, 240],
            border_color=[74, 230, 58, 255], font_size=36,
            comment="Quest items"),
        FilterRule("Maps",
            conditions={"Class": '"Maps"'},
            text_color=[255, 255, 255, 255], bg_color=[50, 0, 0, 240],
            border_color=[255, 50, 50, 255], font_size=36,
            comment="Maps"),
        FilterRule("Jewels",
            conditions={"Class": '"Jewels"'},
            text_color=[255, 255, 119, 255], bg_color=[0, 0, 0, 240],
            border_color=[200, 200, 50, 255], font_size=34,
            comment="Jewels"),
        FilterRule("Flasks",
            conditions={"Class": '"Flasks"'},
            text_color=[200, 200, 200, 255], bg_color=[0, 0, 0, 200],
            border_color=[150, 150, 150, 255], font_size=30,
            comment="All flask types"),
        FilterRule("Unique Items",
            conditions={"Rarity": "= Unique"},
            text_color=[175, 96, 37, 255], bg_color=[0, 0, 0, 240],
            border_color=[175, 96, 37, 255], font_size=40,
            comment="Unique rarity"),
        FilterRule("Rare Items",
            conditions={"Rarity": "= Rare"},
            text_color=[255, 255, 119, 255], bg_color=[0, 0, 0, 240],
            border_color=[255, 255, 119, 255], font_size=36,
            comment="Rare rarity"),
        FilterRule("Magic Items",
            conditions={"Rarity": "= Magic"},
            text_color=[136, 136, 255, 255], bg_color=[0, 0, 0, 200],
            border_color=[136, 136, 255, 255], font_size=30,
            comment="Magic rarity"),
        FilterRule("Normal Items",
            conditions={"Rarity": "= Normal"},
            text_color=[200, 200, 200, 255], bg_color=[0, 0, 0, 180],
            border_color=[100, 100, 100, 255], font_size=26,
            comment="Normal rarity"),
        FilterRule("Hide Everything Else",
            show=False, conditions={},
            text_color=[100, 100, 100, 150], bg_color=[0, 0, 0, 100],
            border_color=[50, 50, 50, 100], font_size=20,
            comment="Default catch-all — hide remaining items"),
    ]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rgba_to_hex(rgba) -> str:
    return f"#{rgba[0]:02x}{rgba[1]:02x}{rgba[2]:02x}"

def hex_to_rgba(h: str, alpha: int = 255) -> list:
    h = h.lstrip("#")
    return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha]

def luminance(rgba) -> float:
    return 0.299 * rgba[0] + 0.587 * rgba[1] + 0.114 * rgba[2]

def generate_filter(rules: List[FilterRule], filter_name: str) -> str:
    lines = [
        f"# {filter_name}",
        "# Generated by PoE Filter Editor (c:\\poe\\filter_editor.py)",
        "",
    ]
    for rule in rules:
        if not rule.enabled:
            continue
        if rule.comment:
            lines.append(f"# {rule.comment}")
        lines.append("Show" if rule.show else "Hide")
        for key, val in rule.conditions.items():
            lines.append(f"    {key} {val}")
        if rule.show:
            r, g, b, a = rule.text_color
            lines.append(f"    SetTextColor {r} {g} {b} {a}")
            r, g, b, a = rule.bg_color
            lines.append(f"    SetBackgroundColor {r} {g} {b} {a}")
            r, g, b, a = rule.border_color
            lines.append(f"    SetBorderColor {r} {g} {b} {a}")
            lines.append(f"    SetFontSize {rule.font_size}")
        lines.append("")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

class ColorSwatch(tk.Label):
    """Clickable colored rectangle that opens a color picker."""

    def __init__(self, parent, rgba: list, title: str, on_change, **kw):
        super().__init__(parent, width=3, relief="solid", bd=1,
                         cursor="hand2", font=("Arial", 7), **kw)
        self._rgba = list(rgba)
        self._title = title
        self._on_change = on_change
        self._render()
        self.bind("<Button-1>", self._pick)

    def _render(self):
        hex_c = rgba_to_hex(self._rgba)
        fg = "#000000" if luminance(self._rgba) > 128 else "#ffffff"
        self.config(bg=hex_c, fg=fg, text="  ")

    def set_rgba(self, rgba: list):
        self._rgba = list(rgba)
        self._render()

    def get_rgba(self) -> list:
        return list(self._rgba)

    def _pick(self, _=None):
        # Defer so the label click doesn't interfere with the dialog
        self.after(10, self._open_dialog)

    def _open_dialog(self):
        result = colorchooser.askcolor(rgba_to_hex(self._rgba), title=f"Color: {self._title}")
        if result and result[1]:
            new = hex_to_rgba(result[1], self._rgba[3])
            self.set_rgba(new)
            self._on_change(list(new))


class RuleRow(tk.Frame):
    """One horizontal row representing a single filter rule."""

    SHOW_STYLE = dict(text="Show", bg="#1e3a1e", fg="#88ff88")
    HIDE_STYLE = dict(text="Hide", bg="#3a1e1e", fg="#ff8888")

    def __init__(self, parent, rule: FilterRule, on_change, **kw):
        super().__init__(parent, bd=1, relief="ridge", **kw)
        self.rule = rule
        self.on_change = on_change
        self._build()

    def _build(self):
        lbl = dict(font=("Arial", 7), bg=self["bg"], fg="#aaaaaa")

        # Enabled checkbox
        self._enabled_var = tk.BooleanVar(value=self.rule.enabled)
        tk.Checkbutton(self, variable=self._enabled_var,
                       command=self._on_enabled,
                       bg=self["bg"], activebackground=self["bg"],
                       selectcolor="#333333").pack(side="left")

        # Show / Hide toggle button
        self._show_btn = tk.Button(self, width=4, relief="flat",
                                   font=("Arial", 8, "bold"),
                                   command=self._toggle_show)
        self._show_btn.pack(side="left", padx=2, pady=2)
        self._update_show_btn()

        # Rule name
        tk.Label(self, text=self.rule.name, width=17, anchor="w",
                 font=("Arial", 9, "bold"),
                 bg=self["bg"], fg="#dddddd").pack(side="left", padx=(4, 8))

        # Color swatches: T / B / ◻
        tk.Label(self, text="T", **lbl).pack(side="left")
        self._text_sw = ColorSwatch(self, self.rule.text_color,
                                    f"{self.rule.name} — Text", self._set_text)
        self._text_sw.pack(side="left", padx=(0, 4))

        tk.Label(self, text="B", **lbl).pack(side="left")
        self._bg_sw = ColorSwatch(self, self.rule.bg_color,
                                  f"{self.rule.name} — Background", self._set_bg)
        self._bg_sw.pack(side="left", padx=(0, 4))

        tk.Label(self, text="◻", **lbl).pack(side="left")
        self._border_sw = ColorSwatch(self, self.rule.border_color,
                                      f"{self.rule.name} — Border", self._set_border)
        self._border_sw.pack(side="left", padx=(0, 6))

        # Font size spinbox
        tk.Label(self, text="Sz", **lbl).pack(side="left")
        self._size_var = tk.IntVar(value=self.rule.font_size)
        sb = tk.Spinbox(self, from_=14, to=45, width=3,
                        textvariable=self._size_var,
                        command=self._set_size,
                        font=("Arial", 8),
                        bg="#2a2a2a", fg="white",
                        buttonbackground="#3a3a3a",
                        relief="flat", bd=1)
        sb.pack(side="left", padx=(0, 4))
        sb.bind("<Return>", lambda _: self._set_size())
        sb.bind("<FocusOut>", lambda _: self._set_size())

    def _update_show_btn(self):
        style = self.SHOW_STYLE if self.rule.show else self.HIDE_STYLE
        self._show_btn.config(**style)

    def _toggle_show(self):
        self.rule.show = not self.rule.show
        self._update_show_btn()
        self.on_change()

    def _on_enabled(self):
        self.rule.enabled = self._enabled_var.get()
        self.on_change()

    def _set_text(self, rgba):
        self.rule.text_color = rgba
        self.on_change()

    def _set_bg(self, rgba):
        self.rule.bg_color = rgba
        self.on_change()

    def _set_border(self, rgba):
        self.rule.border_color = rgba
        self.on_change()

    def _set_size(self):
        try:
            self.rule.font_size = int(self._size_var.get())
            self.on_change()
        except (ValueError, tk.TclError):
            pass


class PreviewCanvas(tk.Canvas):
    """Renders fake PoE-style item name labels for each rule."""

    BG = "#111111"
    PAD_X = 12
    PAD_Y = 8
    ITEM_H = 30
    ITEM_W = 300
    GROUP_GAP = 6

    def __init__(self, parent, **kw):
        super().__init__(parent, bg=self.BG, highlightthickness=0, **kw)

    def render(self, rules: List[FilterRule]):
        self.delete("all")
        y = self.PAD_Y

        for rule in rules:
            if not rule.enabled:
                continue
            samples = SAMPLE_ITEMS.get(rule.name, [rule.name])
            for item_name in samples[:3]:
                self._draw_item(item_name, rule, y)
                y += self.ITEM_H + 3
            y += self.GROUP_GAP

        self.config(scrollregion=(0, 0,
                                  self.ITEM_W + self.PAD_X * 2,
                                  y + self.PAD_Y))

    def _draw_item(self, name: str, rule: FilterRule, y: int):
        x = self.PAD_X
        w = self.ITEM_W
        h = self.ITEM_H

        if rule.show:
            bg_hex     = rgba_to_hex(rule.bg_color)
            border_hex = rgba_to_hex(rule.border_color)
            text_hex   = rgba_to_hex(rule.text_color)
            font_size  = max(8, rule.font_size // 2)
            label      = f"  {name}"
        else:
            bg_hex     = "#151515"
            border_hex = "#2a2a2a"
            text_hex   = "#3a3a3a"
            font_size  = 9
            label      = f"  {name}  [hidden]"

        self.create_rectangle(x, y, x + w, y + h,
                              fill=bg_hex, outline=border_hex, width=2)
        self.create_text(x + 8, y + h // 2,
                         text=label, anchor="w",
                         fill=text_hex,
                         font=("Arial", font_size, "bold"))

# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class FilterEditorApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("PoE Item Filter Editor")
        self.geometry("980x660")
        self.minsize(700, 480)
        self.configure(bg="#1a1a1a")
        self.rules = _make_default_rules()
        self._build_ui()
        self._refresh_preview()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self._build_topbar()
        self._build_main_area()

    def _build_topbar(self):
        bar = tk.Frame(self, bg="#222222", pady=7, padx=10)
        bar.pack(side="top", fill="x")

        tk.Label(bar, text="PoE Item Filter Editor",
                 bg="#222222", fg="#cccccc",
                 font=("Arial", 11, "bold")).pack(side="left", padx=(0, 20))

        tk.Label(bar, text="Filter name:", bg="#222222", fg="#aaaaaa",
                 font=("Arial", 10)).pack(side="left")
        self._name_var = tk.StringVar(value="MyFilter")
        tk.Entry(bar, textvariable=self._name_var, width=18,
                 font=("Arial", 10), bg="#333333", fg="white",
                 insertbackground="white", relief="flat").pack(side="left", padx=(4, 16))

        tk.Button(bar, text="Reset to Defaults", command=self._reset_defaults,
                  bg="#3a3a3a", fg="#cccccc", font=("Arial", 9),
                  relief="flat", padx=8).pack(side="left", padx=4)

        tk.Button(bar, text="Export As...", command=self._export_as,
                  bg="#2a3a5a", fg="white", font=("Arial", 10),
                  relief="flat", padx=10).pack(side="right", padx=4)
        tk.Button(bar, text="▶  Save to PoE Dir", command=self._save_to_poe,
                  bg="#1a5a1a", fg="white", font=("Arial", 10, "bold"),
                  relief="flat", padx=12).pack(side="right", padx=6)

    def _build_main_area(self):
        pane = tk.PanedWindow(self, orient="horizontal",
                              bg="#1a1a1a", sashwidth=5, sashrelief="flat")
        pane.pack(fill="both", expand=True, padx=6, pady=6)

        # ── Left: scrollable rules list ─────────────────────────────────────
        left = tk.Frame(pane, bg="#1a1a1a")
        pane.add(left, width=610)

        tk.Label(left,
                 text="RULES — ✓=enabled  Show/Hide  T=text  B=background  ◻=border  Sz=font size",
                 bg="#1a1a1a", fg="#666666", font=("Arial", 8)).pack(anchor="w", padx=4, pady=(0, 2))

        outer = tk.Frame(left, bg="#1a1a1a")
        outer.pack(fill="both", expand=True)

        self._list_canvas = tk.Canvas(outer, bg="#1a1a1a", highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=self._list_canvas.yview)
        self._list_canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._list_canvas.pack(side="left", fill="both", expand=True)

        self._rules_frame = tk.Frame(self._list_canvas, bg="#1a1a1a")
        self._win_id = self._list_canvas.create_window(
            (0, 0), window=self._rules_frame, anchor="nw")

        self._rules_frame.bind("<Configure>", lambda _:
            self._list_canvas.configure(
                scrollregion=self._list_canvas.bbox("all")))
        self._list_canvas.bind("<Configure>", lambda e:
            self._list_canvas.itemconfig(self._win_id, width=e.width))
        self._list_canvas.bind("<MouseWheel>", lambda e:
            self._list_canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        self._populate_rule_rows()

        # ── Right: preview ──────────────────────────────────────────────────
        right = tk.Frame(pane, bg="#1a1a1a")
        pane.add(right, width=330)

        tk.Label(right, text="PREVIEW",
                 bg="#1a1a1a", fg="#666666", font=("Arial", 8)).pack(anchor="w", padx=4, pady=(0, 2))

        prev_outer = tk.Frame(right, bg="#111111")
        prev_outer.pack(fill="both", expand=True)

        self._preview = PreviewCanvas(prev_outer)
        psb = ttk.Scrollbar(prev_outer, orient="vertical", command=self._preview.yview)
        self._preview.configure(yscrollcommand=psb.set)
        psb.pack(side="right", fill="y")
        self._preview.pack(side="left", fill="both", expand=True)
        self._preview.bind("<MouseWheel>", lambda e:
            self._preview.yview_scroll(-1 * (e.delta // 120), "units"))

    def _populate_rule_rows(self):
        for w in self._rules_frame.winfo_children():
            w.destroy()
        for rule in self.rules:
            row = RuleRow(self._rules_frame, rule,
                          on_change=self._refresh_preview,
                          bg="#242424")
            row.pack(fill="x", pady=2, padx=2)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _refresh_preview(self):
        self._preview.render(self.rules)

    def _reset_defaults(self):
        if messagebox.askyesno("Reset", "Reset all rules to default colors?"):
            self.rules = _make_default_rules()
            self._populate_rule_rows()
            self._refresh_preview()

    def _generate_text(self) -> str:
        name = self._name_var.get().strip() or "MyFilter"
        return generate_filter(self.rules, name)

    def _save_to_poe(self):
        name = self._name_var.get().strip() or "MyFilter"
        if not name.lower().endswith(".filter"):
            name += ".filter"

        os.makedirs(POE_FILTER_DIR, exist_ok=True)
        path = os.path.join(POE_FILTER_DIR, name)

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._generate_text())
            messagebox.showinfo("Saved", f"Filter saved to:\n{path}\n\nReload it in-game with Ctrl+F5.")
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to save:\n{exc}")

    def _export_as(self):
        name = self._name_var.get().strip() or "MyFilter"
        if not name.lower().endswith(".filter"):
            name += ".filter"

        initial_dir = POE_FILTER_DIR if os.path.isdir(POE_FILTER_DIR) else os.path.expanduser("~")
        path = asksaveasfilename(
            defaultextension=".filter",
            filetypes=[("PoE Filter", "*.filter"), ("Text file", "*.txt"), ("All files", "*.*")],
            initialfile=name,
            initialdir=initial_dir,
            title="Export filter as...",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._generate_text())
            messagebox.showinfo("Exported", f"Filter exported to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to export:\n{exc}")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = FilterEditorApp()
    app.mainloop()
