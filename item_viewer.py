"""
PoE Item Viewer — search your stash and display items as styled in-game tooltips.

Usage:
    python item_viewer.py
"""

import json
import tkinter as tk
from tkinter import font as tkfont
from pathlib import Path

STASH_DIR = Path(r"C:\Users\jbharvey\Documents\poestash\poe_stash_data")
STASH_FILE = next(STASH_DIR.glob("all_stashes_*.json"), None)

CARD_W = 440   # item card pixel width
PAD    = 16    # horizontal text padding inside card
BAR_H  = 5     # nameplate bar height
SEP_H  = 8     # total height of a section separator

# ── Colour scheme ─────────────────────────────────────────────────────────────

APP_BG      = "#111111"
ENTRY_BG    = "#1E1E1E"
ENTRY_FG    = "#D4D4D4"
LIST_BG     = "#161616"
LIST_FG     = "#C8C8C8"
LIST_SEL_BG = "#2A2000"
LIST_SEL_FG = "#FFFF77"
PANEL_BG    = "#0A0A0A"

ITEM_BG     = "#0D0D0D"
SEP_LINE    = "#3A2A1A"
SEP_DIAMOND = "#604830"

# Text colours
C_TEXT      = "#C8C8C8"
C_AUG       = "#8888FF"   # augmented property value
C_IMPLICIT  = "#7F7FFF"   # implicit mods
C_CRAFTED   = "#B4B4FF"   # master-crafted mods
C_FLAVOR    = "#AF6025"   # flavour text
C_CORRUPT   = "#FF0000"
C_MIRRORED  = "#8888FF"
C_DIM       = "#666666"   # labels like "Requirements:"
C_INFLUENCE = "#C8A870"

# Per-rarity: name text colour, nameplate bar colour, border colour
RARITY = {
    "Normal":          dict(name="#C8C8C8", bar="#AAAAAA", border="#888888"),
    "Magic":           dict(name="#8888FF", bar="#6666CC", border="#6666CC"),
    "Rare":            dict(name="#FFFF77", bar="#C8AA6E", border="#A07820"),
    "Unique":          dict(name="#AF6025", bar="#AF6025", border="#AF6025"),
    "Gem":             dict(name="#1BA29B", bar="#1BA29B", border="#1BA29B"),
    "Currency":        dict(name="#AA9E82", bar="#AA9E82", border="#7A6A3A"),
    "Divination Card": dict(name="#FFFFFF", bar="#AAAAAA", border="#808080"),
}
_DEFAULT_RC = dict(name="#C8C8C8", bar="#AAAAAA", border="#888888")


# ── Font helpers ──────────────────────────────────────────────────────────────

_font_cache: dict = {}

def _font(size: int, bold: bool = False) -> tkfont.Font:
    key = (size, bold)
    if key not in _font_cache:
        weight = "bold" if bold else "normal"
        for family in ("Palatino Linotype", "Palatino", "Georgia", "Times New Roman"):
            f = tkfont.Font(family=family, size=size, weight=weight)
            actual = f.actual().get("family", "").lower()
            if "courier" not in actual and "fixed" not in actual:
                _font_cache[key] = f
                break
        else:
            _font_cache[key] = tkfont.Font(size=size, weight=weight)
    return _font_cache[key]


# ── Stash loading + search ────────────────────────────────────────────────────

_stash_items: list[tuple[str, dict]] = []   # (tab_name, item)


def load_stash():
    global _stash_items
    if not STASH_FILE:
        return
    with open(STASH_FILE, encoding="utf-8") as f:
        data = json.load(f)
    seen = set()
    items = []
    for tab in data.get("tabs", []):
        tab_name = tab.get("tab_name") or "(unnamed)"
        for item in tab.get("items", []):
            iid = item.get("id", "")
            if iid in seen:
                continue
            seen.add(iid)
            items.append((tab_name, item))
    _stash_items = items


def search_items(query: str) -> list[tuple[str, dict]]:
    q = query.strip().lower()
    if not q:
        return []
    results = []
    for tab_name, item in _stash_items:
        name = item.get("name", "").lower()
        base = item.get("typeLine", "").lower()
        if q in name or q in base:
            results.append((tab_name, item))
    return results


# ── Item renderer ─────────────────────────────────────────────────────────────

class ItemRenderer:
    """Draws a PoE-style item tooltip onto a tk.Canvas."""

    def __init__(self, canvas: tk.Canvas):
        self.c = canvas

    def render(self, item: dict, tab_name: str = ""):
        c = self.c
        c.delete("all")

        rarity = item.get("rarity", "Normal")
        rc = RARITY.get(rarity, _DEFAULT_RC)

        y = self._nameplate(item, rc)
        sections = self._build_sections(item, tab_name)

        for section_lines in sections:
            y = self._separator(y)
            y = self._section(section_lines, y)

        y += 8  # bottom padding before border

        # Border drawn last so it's on top
        self._border(y, rc)

        c.configure(scrollregion=(0, 0, CARD_W, y), height=y)

    # ── private drawing helpers ───────────────────────────────────────────

    def _text(self, x, y, text, color, fnt, anchor="nw", wrap=True) -> int:
        """Draw text, return bottom y of the rendered bbox."""
        kw = dict(text=text, fill=color, font=fnt, anchor=anchor)
        if wrap:
            kw["width"] = CARD_W - 2 * PAD
        tid = self.c.create_text(x, y, **kw)
        bb = self.c.bbox(tid)
        return bb[3] if bb else y + fnt.metrics("linespace")

    def _nameplate(self, item: dict, rc: dict) -> int:
        c = self.c
        y = 0

        # Top bar
        c.create_rectangle(0, y, CARD_W, y + BAR_H, fill=rc["bar"], outline="")
        y += BAR_H + 10

        # Item name (large, bold, rarity-coloured, centred)
        name = item.get("name", "")
        y = self._text(CARD_W // 2, y, name, rc["name"], _font(14, bold=True),
                       anchor="n", wrap=False)
        y += 3

        # Base type (if different from name)
        base = item.get("typeLine", "")
        if base and base != name:
            y = self._text(CARD_W // 2, y, base, rc["name"], _font(12),
                           anchor="n", wrap=False)
            y += 2

        # Influence labels (Shaper Item, Elder Item, etc.)
        influences = [k.title() for k, v in item.get("influences", {}).items() if v]
        if influences:
            inf_text = "   ".join(f"{i} Item" for i in influences)
            y = self._text(CARD_W // 2, y + 2, inf_text, C_INFLUENCE,
                           _font(10), anchor="n", wrap=False)
            y += 2

        y += 8
        # Bottom bar
        c.create_rectangle(0, y, CARD_W, y + BAR_H, fill=rc["bar"], outline="")
        y += BAR_H
        return y

    def _separator(self, y: int) -> int:
        y += 3
        self.c.create_line(PAD, y, CARD_W - PAD, y, fill=SEP_LINE, width=1)
        # Small diamond ornament at centre
        cx = CARD_W // 2
        self.c.create_polygon(cx, y - 4, cx + 4, y, cx, y + 4, cx - 4, y,
                               fill=SEP_DIAMOND, outline="")
        y += 4
        return y

    def _section(self, lines: list[tuple[str, str, object]], y: int) -> int:
        y += 4
        for text, color, fnt in lines:
            if text == "":
                y += 3
                continue
            y = self._text(PAD, y, text, color, fnt) + 2
        return y

    def _border(self, total_h: int, rc: dict):
        c = self.c
        bc = rc["border"]
        S = 8  # corner ornament size

        # Main outline
        c.create_rectangle(1, 1, CARD_W - 1, total_h - 1, outline=bc, width=1)

        # Corner ornaments — small filled squares
        for cx, cy in [(0, 0), (CARD_W - S, 0),
                       (0, total_h - S), (CARD_W - S, total_h - S)]:
            c.create_rectangle(cx, cy, cx + S, cy + S, fill=bc, outline="")

    # ── section builder ───────────────────────────────────────────────────

    def _build_sections(self, item: dict, tab_name: str) -> list:
        """Return a list of sections; each section is [(text, colour, font), ...]."""
        ft  = _font(11)
        fts = _font(10)
        sections: list[list] = []

        # Properties (armour, es, damage, quality, etc.)
        props = item.get("properties", [])
        if props:
            lines = []
            for prop in props:
                pname = prop["name"]
                vals  = prop.get("values", [])
                if not vals:
                    lines.append((pname, C_DIM, fts))
                    continue
                augmented = any(v[1] != 0 for v in vals)
                val_str   = ", ".join(v[0] for v in vals)
                color     = C_AUG if augmented else C_TEXT
                # "{0}" placeholder e.g. "Weapon Range: {0} metres"
                if "{0}" in pname:
                    lines.append((pname.replace("{0}", val_str), color, ft))
                else:
                    lines.append((f"{pname}: {val_str}", color, ft))
            if lines:
                sections.append(lines)

        # Requirements
        reqs = item.get("requirements", [])
        if reqs:
            parts = "   ".join(
                f"{r['name']}: {r['values'][0][0]}" for r in reqs
            )
            sections.append([
                ("Requirements:", C_DIM, fts),
                (f"  {parts}", C_TEXT, ft),
            ])

        # Sockets
        sockets = item.get("sockets", [])
        if sockets:
            groups: dict[int, list[str]] = {}
            for s in sockets:
                groups.setdefault(s.get("group", 0), []).append(s.get("sColour", "?"))
            socket_str = " ".join("-".join(g) for g in groups.values())
            sections.append([(f"Sockets: {socket_str}", C_TEXT, ft)])

        # Item Level
        sections.append([(f"Item Level: {item.get('ilvl', 0)}", C_TEXT, ft)])

        # Enchant mods
        enchants = item.get("enchantMods", [])
        if enchants:
            sections.append([(m, C_IMPLICIT, ft) for m in enchants])

        # Implicit mods
        implicits = item.get("implicitMods", [])
        if implicits:
            sections.append([(m, C_IMPLICIT, ft) for m in implicits])

        # Explicit mods (with crafted-mod detection)
        explicits = item.get("explicitMods", [])
        crafted   = set(item.get("craftedMods", []))
        if explicits:
            lines = []
            for m in explicits:
                color = C_CRAFTED if m in crafted else C_TEXT
                lines.append((m, color, ft))
            sections.append(lines)

        # Fractured mods (separate from explicits when present)
        fractured = item.get("fracturedMods", [])
        if fractured:
            sections.append([(m, "#A0A0FF", ft) for m in fractured])

        # Flavour text
        flavour = item.get("flavourText", [])
        if flavour:
            text = " ".join(flavour).replace("\r", "").strip()
            sections.append([(text, C_FLAVOR, fts)])

        # Note (~price tag set by the player)
        note = item.get("note", "")
        if note:
            sections.append([(f"Note: {note}", C_DIM, fts)])

        # Corruption / mirror
        flags = []
        if item.get("corrupted"):
            flags.append(("Corrupted", C_CORRUPT, ft))
        if item.get("mirrored"):
            flags.append(("Mirrored", C_MIRRORED, ft))
        if flags:
            sections.append(flags)

        # Tab location (appended at bottom)
        if tab_name:
            sections.append([(f"Tab: {tab_name}", C_DIM, fts)])

        return sections


# ── Main application ──────────────────────────────────────────────────────────

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("PoE Item Viewer")
        root.configure(bg=APP_BG)
        root.geometry("900x680")

        self._results: list[tuple[str, dict]] = []
        self._build_ui()

        root.after(100, self._load_stash_async)

    def _build_ui(self):
        root = self.root

        # ── Top search bar ────────────────────────────────────────────────
        top = tk.Frame(root, bg=APP_BG, pady=8)
        top.pack(fill="x", padx=10)

        tk.Label(top, text="Search:", bg=APP_BG, fg=ENTRY_FG,
                 font=_font(11)).pack(side="left")

        self._entry = tk.Entry(top, bg=ENTRY_BG, fg=ENTRY_FG, insertbackground=ENTRY_FG,
                               font=_font(12), relief="flat", width=35)
        self._entry.pack(side="left", padx=(6, 4))
        self._entry.bind("<Return>", lambda _: self._do_search())
        self._entry.focus_set()

        tk.Button(top, text="Search", bg="#2A2A2A", fg=ENTRY_FG,
                  font=_font(11), relief="flat", cursor="hand2",
                  command=self._do_search).pack(side="left", padx=4)

        self._status = tk.StringVar(value="Loading stash…")
        tk.Label(top, textvariable=self._status, bg=APP_BG, fg="#666666",
                 font=_font(10)).pack(side="right")

        # ── Main paned area ───────────────────────────────────────────────
        pane = tk.PanedWindow(root, orient="horizontal", bg=APP_BG,
                              sashwidth=4, sashrelief="flat")
        pane.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Left panel: results list
        left = tk.Frame(pane, bg=APP_BG)
        pane.add(left, minsize=220)

        self._result_count = tk.StringVar(value="")
        tk.Label(left, textvariable=self._result_count, bg=APP_BG, fg="#666666",
                 font=_font(10), anchor="w").pack(fill="x", padx=4)

        list_frame = tk.Frame(left, bg=APP_BG)
        list_frame.pack(fill="both", expand=True)

        sb = tk.Scrollbar(list_frame, bg=APP_BG, troughcolor="#222222")
        sb.pack(side="right", fill="y")

        self._listbox = tk.Listbox(
            list_frame,
            bg=LIST_BG, fg=LIST_FG,
            selectbackground=LIST_SEL_BG, selectforeground=LIST_SEL_FG,
            font=_font(11), relief="flat",
            activestyle="none",
            yscrollcommand=sb.set,
        )
        self._listbox.pack(fill="both", expand=True)
        sb.config(command=self._listbox.yview)
        self._listbox.bind("<<ListboxSelect>>", self._on_select)

        # Right panel: item display
        right = tk.Frame(pane, bg=PANEL_BG)
        pane.add(right, minsize=460)

        right_canvas = tk.Canvas(right, bg=PANEL_BG, highlightthickness=0)
        right_scroll = tk.Scrollbar(right, command=right_canvas.yview,
                                    bg=APP_BG, troughcolor="#222222")
        right_canvas.configure(yscrollcommand=right_scroll.set)

        right_scroll.pack(side="right", fill="y")
        right_canvas.pack(fill="both", expand=True)

        # Inner frame to hold the item canvas
        self._inner = tk.Frame(right_canvas, bg=PANEL_BG)
        self._inner_id = right_canvas.create_window(20, 20, anchor="nw",
                                                     window=self._inner)
        right_canvas.bind("<Configure>", lambda e: right_canvas.configure(
            scrollregion=right_canvas.bbox("all")))
        # Mouse wheel scrolling
        right_canvas.bind("<MouseWheel>", lambda e: right_canvas.yview_scroll(
            -1 * (e.delta // 120), "units"))

        self._right_canvas = right_canvas

        # The actual item-drawing canvas lives inside _inner
        self._item_canvas = tk.Canvas(self._inner, bg=ITEM_BG,
                                      width=CARD_W, highlightthickness=0)
        self._item_canvas.pack(padx=0, pady=0)
        self._renderer = ItemRenderer(self._item_canvas)

        # Placeholder text
        self._item_canvas.create_text(
            CARD_W // 2, 60,
            text="Search for an item above\nthen click a result",
            fill="#444444", font=_font(12), justify="center",
        )

    # ── Actions ───────────────────────────────────────────────────────────

    def _load_stash_async(self):
        try:
            load_stash()
            count = len(_stash_items)
            self._status.set(f"{count:,} items loaded")
        except Exception as exc:
            self._status.set(f"Error: {exc}")

    def _do_search(self):
        query = self._entry.get().strip()
        if not query:
            return

        results = search_items(query)
        self._results = results

        self._listbox.delete(0, "end")
        if not results:
            self._result_count.set("No results")
            return

        self._result_count.set(f"{len(results)} result{'s' if len(results) != 1 else ''}")
        for tab_name, item in results:
            name = item.get("name") or item.get("typeLine", "?")
            rarity = item.get("rarity", "")
            suffix = " ✦" if item.get("corrupted") else ""
            self._listbox.insert("end", f"{name}{suffix}")

        # Colour each listbox entry by rarity
        rarity_list_colors = {
            "Rare":           "#FFFF77",
            "Unique":         "#AF6025",
            "Magic":          "#8888FF",
            "Gem":            "#1BA29B",
            "Currency":       "#AA9E82",
            "Divination Card":"#CCCCCC",
        }
        for i, (_, item) in enumerate(results):
            r = item.get("rarity", "Normal")
            color = rarity_list_colors.get(r, LIST_FG)
            self._listbox.itemconfig(i, fg=color)

        # Auto-select first result
        if results:
            self._listbox.selection_set(0)
            self._show_item(0)

    def _on_select(self, _event):
        sel = self._listbox.curselection()
        if sel:
            self._show_item(sel[0])

    def _show_item(self, index: int):
        if index >= len(self._results):
            return
        tab_name, item = self._results[index]
        self._renderer.render(item, tab_name)
        # Update scroll region of outer canvas
        self._inner.update_idletasks()
        self._right_canvas.configure(
            scrollregion=self._right_canvas.bbox("all")
        )


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
