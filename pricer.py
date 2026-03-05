"""
PoE Item Pricer — standalone clipboard watcher.

Usage:
    python pricer.py [--league LeagueName]

Defaults to Standard if no league is given.

Press Ctrl+C on any item in-game; the window updates automatically.

Pricing sources:
  - Rares:    poeprices.ai API (best-guess) + local mod-tier scoring fallback
  - Uniques:  poe.ninja price data (fetched at startup, cached 1 hour)
  - Currency / Divination Cards: poe.ninja
  - Gems:     poe.ninja (level 20 base price)
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from item_parser import ParsedItem, is_poe_item, parse_item
from mod_tiers import score_mods, suggest_price, TIER_POINTS

# ── Constants ────────────────────────────────────────────────────────────────

CACHE_DIR = Path(r"C:\poe")
NINJA_CACHE_MAX_AGE_SECONDS = 3600  # 1 hour

# poe.ninja categories to fetch
_NINJA_ITEM_TYPES = [
    "UniqueWeapon", "UniqueArmour", "UniqueAccessory",
    "UniqueFlask", "UniqueJewel", "UniqueMap",
    "SkillGem", "DivinationCard",
]
_NINJA_CURRENCY_TYPES = ["Currency", "Fragment"]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Tier display: label → (color, bar)
TIER_STYLE: dict[str, tuple[str, str]] = {
    "T1": ("#FFD700", "████"),   # gold
    "T2": ("#90EE90", "███ "),   # green
    "T3": ("#87CEEB", "██  "),   # blue
    "T4": ("#A8A8A8", "█   "),   # gray
    "T5": ("#606060", "▒   "),   # dark gray
    "T6": ("#404040", "▒   "),
    "—":  ("#505050", "    "),   # unrecognised
}

RARITY_COLOR = {
    "Normal":          "#C8C8C8",
    "Magic":           "#8888FF",
    "Rare":            "#FFFF77",
    "Unique":          "#AF6025",
    "Currency":        "#AA9E82",
    "Gem":             "#1BA29B",
    "Divination Card": "#CCCCCC",
}


# ── poe.ninja cache ──────────────────────────────────────────────────────────

class NinjaCache:
    """
    Fetches and caches poe.ninja price data for a league.

    Lookup methods return chaos value (float) or None.
    Also exposes divine_chaos so callers can show div equivalents.
    """

    def __init__(self, league: str) -> None:
        self.league = league
        self._lock = threading.Lock()
        self._data: dict[str, list[dict]] = {}   # category → list of entries
        self._fetched_at: Optional[datetime] = None
        self._cache_file = CACHE_DIR / f"pricer_cache_{league}.json"
        self.divine_chaos: float = 200.0          # updated after fetch
        self.status: str = "not loaded"

    # ── public ──────────────────────────────────────────────────────────

    def load_or_fetch_async(self, on_done: callable) -> None:
        """Non-blocking: load from disk cache or fetch from network."""
        t = threading.Thread(target=self._load_or_fetch, args=(on_done,), daemon=True)
        t.start()

    def fetch_async(self, on_done: callable) -> None:
        """Force a fresh fetch from network."""
        t = threading.Thread(target=self._fetch_all, args=(on_done,), daemon=True)
        t.start()

    def lookup_unique(self, name: str, links: int = 0) -> Optional[dict]:
        """
        Return the best matching ninja entry for a unique item.
        Tries to match links if available; falls back to unlinked.
        Returns dict with chaosValue, divineValue, count, or None.
        """
        with self._lock:
            for cat in _NINJA_ITEM_TYPES:
                entries = self._data.get(cat, [])
                for entry in entries:
                    if entry.get("name", "").lower() == name.lower():
                        entry_links = entry.get("links") or 0
                        if links >= 5 and entry_links == links:
                            return entry
                        if (links < 5 or entry_links == 0) and not entry_links:
                            return entry
            # Second pass: any match on name, no links filter
            for cat in _NINJA_ITEM_TYPES:
                for entry in self._data.get(cat, []):
                    if entry.get("name", "").lower() == name.lower():
                        return entry
        return None

    def lookup_currency(self, name: str) -> Optional[float]:
        """Return chaos value for a currency/fragment/divination card."""
        with self._lock:
            for cat in _NINJA_CURRENCY_TYPES:
                for entry in self._data.get(cat, []):
                    if entry.get("name", "").lower() == name.lower():
                        return entry.get("chaosValue")
            for entry in self._data.get("DivinationCard", []):
                if entry.get("name", "").lower() == name.lower():
                    return entry.get("chaosValue")
        return None

    def lookup_gem(self, name: str, level: int = 20) -> Optional[dict]:
        """Return ninja entry for a skill gem at the given level."""
        with self._lock:
            best = None
            for entry in self._data.get("SkillGem", []):
                if entry.get("name", "").lower() != name.lower():
                    continue
                if entry.get("gemLevel") == level:
                    if best is None or (entry.get("gemQuality") or 0) > (best.get("gemQuality") or 0):
                        best = entry
            return best

    # ── internal ────────────────────────────────────────────────────────

    def _load_or_fetch(self, on_done: callable) -> None:
        """Try loading from disk cache; fetch if stale or missing."""
        if self._cache_file.exists():
            try:
                with open(self._cache_file, encoding="utf-8") as f:
                    payload = json.load(f)
                fetched_at = datetime.fromisoformat(payload.get("fetchedAt", ""))
                age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
                if age < NINJA_CACHE_MAX_AGE_SECONDS:
                    with self._lock:
                        self._data = payload.get("data", {})
                        self._fetched_at = fetched_at
                    self._update_divine_price()
                    age_min = int(age // 60)
                    self.status = f"loaded from cache ({age_min}min old)"
                    on_done()
                    return
            except Exception:
                pass  # fall through to fetch

        self._fetch_all(on_done)

    def _fetch_all(self, on_done: callable) -> None:
        self.status = "fetching…"
        on_done()  # update UI to show "fetching"

        combined: dict[str, list] = {}

        try:
            for cat in _NINJA_ITEM_TYPES:
                url = (
                    f"https://poe.ninja/api/data/itemoverview"
                    f"?league={urllib.request.quote(self.league)}&type={cat}"
                )
                try:
                    data = self._fetch_url(url)
                    combined[cat] = data.get("lines", [])
                    time.sleep(0.3)
                except Exception:
                    combined[cat] = []

            for cat in _NINJA_CURRENCY_TYPES:
                url = (
                    f"https://poe.ninja/api/data/currencyoverview"
                    f"?league={urllib.request.quote(self.league)}&type={cat}"
                )
                try:
                    data = self._fetch_url(url)
                    # Normalise currency entries to match item format
                    entries = []
                    for e in data.get("lines", []):
                        entries.append({
                            "name": e.get("currencyTypeName", ""),
                            "chaosValue": e.get("chaosEquivalent", 0.0),
                        })
                    combined[cat] = entries
                    time.sleep(0.3)
                except Exception:
                    combined[cat] = []

            now = datetime.now(timezone.utc)
            with self._lock:
                self._data = combined
                self._fetched_at = now
            self._update_divine_price()

            # Persist to disk
            payload = {
                "fetchedAt": now.isoformat(),
                "league": self.league,
                "data": combined,
            }
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)

            self.status = "prices loaded"

        except Exception as exc:
            self.status = f"fetch error: {exc}"

        on_done()

    @staticmethod
    def _fetch_url(url: str) -> dict:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())

    def _update_divine_price(self) -> None:
        for entry in self._data.get("Currency", []):
            if entry.get("name", "").lower() == "divine orb":
                self.divine_chaos = entry.get("chaosValue", 200.0)
                break


# ── poeprices.ai query ────────────────────────────────────────────────────────

def query_poeprices(item_text: str, league: str) -> Optional[dict]:
    """
    Query poeprices.ai for a price estimate.
    Returns dict with keys: min, max, currency, confidence_rating or None on failure.
    API: GET https://www.poeprices.info/api?l={league}&i={base64(item_text)}
    """
    try:
        encoded = base64.b64encode(item_text.encode("utf-8")).decode("ascii")
        league_enc = urllib.request.quote(league)
        url = f"https://www.poeprices.info/api?l={league_enc}&i={encoded}"
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        # Expected response: {"min": 5, "max": 10, "currency": "chaos", "confidence_rating": "high", ...}
        if "error" in data and data["error"] != 0:
            return None
        return data
    except Exception:
        return None


# ── GUI ───────────────────────────────────────────────────────────────────────

BG = "#1e1e1e"
BG2 = "#2a2a2a"
FG = "#d4d4d4"
FG_DIM = "#707070"
FONT_MONO = ("Consolas", 10)
FONT_MONO_BOLD = ("Consolas", 10, "bold")
FONT_HEADER = ("Consolas", 11, "bold")


class PricerApp:
    def __init__(self, root: tk.Tk, league: str) -> None:
        self.root = root
        self.league = league
        self.ninja = NinjaCache(league)

        self._last_clipboard: str = ""
        self._current_item: Optional[ParsedItem] = None
        self._poeprices_result: Optional[dict] = None
        self._poeprices_thread: Optional[threading.Thread] = None

        self._build_ui()
        self._start_clipboard_poll()

        # Kick off price data load
        self.ninja.load_or_fetch_async(self._on_prices_updated)

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = self.root
        root.title("PoE Item Pricer")
        root.configure(bg=BG)
        root.resizable(False, False)
        root.attributes("-topmost", True)

        # ── Title bar ────────────────────────────────────────────────────
        hdr = tk.Frame(root, bg="#111111", pady=4)
        hdr.pack(fill="x")
        tk.Label(
            hdr, text=f"PoE Pricer  •  {self.league}",
            bg="#111111", fg="#d4d4d4", font=FONT_HEADER,
        ).pack(side="left", padx=8)
        tk.Button(
            hdr, text="↺ Refresh prices",
            bg="#333333", fg=FG, font=FONT_MONO,
            relief="flat", cursor="hand2",
            command=self._refresh_prices,
        ).pack(side="right", padx=8)

        # ── Status bar ───────────────────────────────────────────────────
        status_frame = tk.Frame(root, bg=BG2, pady=3)
        status_frame.pack(fill="x")
        self._status_var = tk.StringVar(value="● Watching clipboard…")
        self._price_status_var = tk.StringVar(value="prices: loading…")
        tk.Label(
            status_frame, textvariable=self._status_var,
            bg=BG2, fg="#88cc88", font=FONT_MONO, anchor="w",
        ).pack(side="left", padx=8)
        tk.Label(
            status_frame, textvariable=self._price_status_var,
            bg=BG2, fg=FG_DIM, font=FONT_MONO, anchor="e",
        ).pack(side="right", padx=8)

        # ── Item display (scrollable Text widget) ────────────────────────
        frame = tk.Frame(root, bg=BG)
        frame.pack(fill="both", expand=True, padx=6, pady=6)

        self._text = tk.Text(
            frame, width=55, height=28,
            bg=BG, fg=FG,
            font=FONT_MONO,
            relief="flat",
            cursor="arrow",
            state="disabled",
            wrap="word",
            padx=6, pady=4,
        )
        self._text.pack(side="left", fill="both", expand=True)

        sb = tk.Scrollbar(frame, command=self._text.yview, bg=BG2, troughcolor=BG)
        sb.pack(side="right", fill="y")
        self._text.configure(yscrollcommand=sb.set)

        # Configure text tags
        self._text.tag_configure("rarity_rare",   foreground="#FFFF77", font=FONT_MONO_BOLD)
        self._text.tag_configure("rarity_unique",  foreground="#AF6025", font=FONT_MONO_BOLD)
        self._text.tag_configure("rarity_magic",   foreground="#8888FF", font=FONT_MONO_BOLD)
        self._text.tag_configure("rarity_currency",foreground="#AA9E82", font=FONT_MONO_BOLD)
        self._text.tag_configure("rarity_gem",     foreground="#1BA29B", font=FONT_MONO_BOLD)
        self._text.tag_configure("rarity_div",     foreground="#FFFFFF", font=FONT_MONO_BOLD)
        self._text.tag_configure("rarity_normal",  foreground="#C8C8C8", font=FONT_MONO_BOLD)

        for tier, (color, _) in TIER_STYLE.items():
            self._text.tag_configure(f"tier_{tier}", foreground=color)

        self._text.tag_configure("section",  foreground="#888888")
        self._text.tag_configure("price",    foreground="#FFD700", font=FONT_MONO_BOLD)
        self._text.tag_configure("dim",      foreground=FG_DIM)
        self._text.tag_configure("implicit", foreground="#aaaaff")
        self._text.tag_configure("info",     foreground="#88aacc")
        self._text.tag_configure("warn",     foreground="#cc8844")

        self._show_waiting()

    # ── Clipboard polling ────────────────────────────────────────────────

    def _start_clipboard_poll(self) -> None:
        self.root.after(500, self._poll_clipboard)

    def _poll_clipboard(self) -> None:
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            text = ""

        if text != self._last_clipboard:
            self._last_clipboard = text
            if is_poe_item(text):
                item = parse_item(text)
                if item:
                    self._current_item = item
                    self._poeprices_result = None
                    self._display_item(item)
                    self._start_poeprices_query(item)

        self.root.after(500, self._poll_clipboard)

    # ── poeprices.ai async query ─────────────────────────────────────────

    def _start_poeprices_query(self, item: ParsedItem) -> None:
        if item.rarity != "Rare" or not item.identified:
            return
        self._status_var.set("● querying poeprices.ai…")

        def _run() -> None:
            result = query_poeprices(item.raw, self.league)
            # Make sure the item hasn't changed while we were fetching
            if self._current_item is item:
                self._poeprices_result = result
                self.root.after(0, lambda: self._update_poeprices_section(item, result))

        t = threading.Thread(target=_run, daemon=True)
        t.start()

    def _update_poeprices_section(self, item: ParsedItem, result: Optional[dict]) -> None:
        if self._current_item is not item:
            return
        self._status_var.set("● Watching clipboard…")
        self._display_item(item)  # redraw with poeprices data

    # ── Display ──────────────────────────────────────────────────────────

    def _tw(self, text: str, tag: str = "") -> None:
        """Append text to the display widget."""
        self._text.configure(state="normal")
        if tag:
            self._text.insert("end", text, tag)
        else:
            self._text.insert("end", text)
        self._text.configure(state="disabled")

    def _clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")

    def _sep(self) -> None:
        self._tw("─" * 52 + "\n", "section")

    def _show_waiting(self) -> None:
        self._clear()
        self._tw("\n  Waiting for item…\n\n", "dim")
        self._tw("  Ctrl+C on any item in PoE to price it.\n", "dim")

    def _display_item(self, item: ParsedItem) -> None:
        self._clear()

        rarity_tag = {
            "Rare":           "rarity_rare",
            "Unique":         "rarity_unique",
            "Magic":          "rarity_magic",
            "Currency":       "rarity_currency",
            "Gem":            "rarity_gem",
            "Divination Card":"rarity_div",
        }.get(item.rarity, "rarity_normal")

        # ── Header ───────────────────────────────────────────────────────
        self._sep()

        rarity_icon = {
            "Rare": "◆", "Unique": "★", "Magic": "◇",
            "Currency": "¤", "Gem": "◉", "Divination Card": "☸",
        }.get(item.rarity, "•")

        flags = []
        if item.corrupted:
            flags.append("Corrupted")
        if item.mirrored:
            flags.append("Mirrored")
        if not item.identified:
            flags.append("Unidentified")
        flag_str = "  " + " | ".join(flags) if flags else ""

        ilvl_str = f"  iLvl {item.item_level}" if item.item_level else ""
        self._tw(f"  {rarity_icon} {item.rarity}{ilvl_str}{flag_str}\n", rarity_tag)
        self._tw(f"  {item.name}\n", rarity_tag)
        if item.base and item.base != item.name:
            self._tw(f"  {item.base}\n", "dim")
        if item.quality:
            self._tw(f"  Quality: +{item.quality}%\n", "dim")
        if item.sockets:
            self._tw(f"  Sockets: {item.sockets}\n", "dim")
        self._sep()

        # ── Route by rarity ──────────────────────────────────────────────
        if item.rarity == "Rare" and item.identified:
            self._display_rare(item)
        elif item.rarity == "Unique":
            self._display_unique(item)
        elif item.rarity in ("Currency", "Fragment"):
            self._display_currency(item)
        elif item.rarity == "Divination Card":
            self._display_divcard(item)
        elif item.rarity == "Gem":
            self._display_gem(item)
        elif not item.identified:
            self._tw("  (Unidentified — cannot price)\n", "warn")
        else:
            self._tw(f"  No pricing data for {item.rarity} items.\n", "dim")

    def _display_rare(self, item: ParsedItem) -> None:
        # Implicits
        if item.implicits:
            self._tw("  IMPLICIT\n", "section")
            for mod in item.implicits:
                self._tw(f"    {mod}\n", "implicit")
            self._sep()

        # Score the explicit mods
        score, scored_mods = score_mods(item.explicits)

        # Explicit mods with tier labels
        self._tw("  EXPLICIT MODS\n", "section")
        for sm in scored_mods:
            tier = sm.tier
            color_tag = f"tier_{tier}"
            bar = TIER_STYLE.get(tier, ("", "    "))[1]
            label = f"[{tier}]" if tier != "—" else " [?]"
            # Truncate mod line to fit
            mod_short = sm.raw_line[:34].ljust(34)
            self._tw(f"    {mod_short} ", "")
            self._tw(f"{label} {bar}\n", color_tag)

        self._sep()

        # Local heuristic price
        local_price = suggest_price(score)
        self._tw(f"  Local score: {score} pts\n", "info")
        self._tw(f"  Heuristic:   {local_price}\n", "info")

        # poeprices.ai result (if available)
        pp = self._poeprices_result
        if pp is not None:
            self._sep()
            self._tw("  poeprices.ai\n", "section")
            p_min = pp.get("min", 0)
            p_max = pp.get("max", 0)
            currency = pp.get("currency", "chaos")
            conf = pp.get("confidence_rating", "?")
            conf_color = "price" if conf == "high" else ("info" if conf == "medium" else "warn")
            if p_min == p_max:
                price_str = f"{p_min} {currency}"
            else:
                price_str = f"{p_min}–{p_max} {currency}"
            self._tw(f"  Estimate:    {price_str}\n", "price")
            self._tw(f"  Confidence:  {conf}\n", conf_color)
            # Show div equivalent if price > 50c
            chaos_mid = (p_min + p_max) / 2 if currency == "chaos" else 0
            if chaos_mid > 50 and self.ninja.divine_chaos > 0:
                div_val = chaos_mid / self.ninja.divine_chaos
                self._tw(f"               (~{div_val:.1f} div)\n", "dim")
        else:
            self._sep()
            self._tw("  poeprices.ai: querying…\n", "dim")

    def _display_unique(self, item: ParsedItem) -> None:
        entry = self.ninja.lookup_unique(item.name, item.link_count)
        if entry is None:
            self._tw("  Not found on poe.ninja.\n", "warn")
            self._tw("  (May be a new league unique or low-confidence item)\n", "dim")
            return

        chaos = entry.get("chaosValue", 0)
        count = entry.get("count") or 0
        div_val = chaos / self.ninja.divine_chaos if self.ninja.divine_chaos > 0 else 0

        self._tw("  poe.ninja\n", "section")
        self._tw(f"  Price:  {chaos:.0f}c", "price")
        if div_val >= 0.1:
            self._tw(f"  (~{div_val:.1f} div)", "dim")
        self._tw("\n")

        if count:
            self._tw(f"  Listed: {count} items\n", "dim")

        variant = entry.get("variant")
        if variant:
            self._tw(f"  Variant: {variant}\n", "dim")

        links = entry.get("links") or 0
        if links:
            self._tw(f"  Links: {links}L\n", "dim")

        if item.link_count >= 5 and (entry.get("links") or 0) != item.link_count:
            self._sep()
            self._tw(f"  Note: your item has {item.link_count}L — check trade\n", "warn")
            self._tw(f"  site for exact linked price.\n", "warn")

    def _display_currency(self, item: ParsedItem) -> None:
        chaos = self.ninja.lookup_currency(item.name)
        self._tw("  poe.ninja\n", "section")
        if chaos is None:
            self._tw("  Not found in price data.\n", "warn")
            return
        self._tw(f"  Value:  {chaos:.2f}c\n", "price")
        if chaos > 50 and self.ninja.divine_chaos > 0:
            self._tw(f"          (~{chaos / self.ninja.divine_chaos:.2f} div)\n", "dim")

    def _display_divcard(self, item: ParsedItem) -> None:
        chaos = self.ninja.lookup_currency(item.name)
        self._tw("  poe.ninja\n", "section")
        if chaos is None:
            self._tw("  Not found in price data.\n", "warn")
            return
        self._tw(f"  Card value: {chaos:.1f}c\n", "price")
        if chaos > 50 and self.ninja.divine_chaos > 0:
            self._tw(f"              (~{chaos / self.ninja.divine_chaos:.2f} div)\n", "dim")

    def _display_gem(self, item: ParsedItem) -> None:
        # Try to read level from properties
        level = 20
        for line in (item.explicits + item.implicits):
            m = re.search(r"Level:\s*(\d+)", item.raw)
            if m:
                level = int(m.group(1))
                break

        entry = self.ninja.lookup_gem(item.name, level)
        self._tw("  poe.ninja\n", "section")
        if entry is None:
            entry = self.ninja.lookup_gem(item.name, 20)
        if entry is None:
            self._tw("  Not found in price data.\n", "warn")
            return
        chaos = entry.get("chaosValue", 0)
        gem_lv = entry.get("gemLevel", "?")
        gem_q = entry.get("gemQuality", 0)
        corrupted = entry.get("corrupted", False)
        self._tw(f"  Level {gem_lv} / {gem_q}% quality", "dim")
        if corrupted:
            self._tw(" [Corrupted]", "warn")
        self._tw("\n")
        self._tw(f"  Price:  {chaos:.0f}c\n", "price")

    # ── Callbacks ────────────────────────────────────────────────────────

    def _refresh_prices(self) -> None:
        self._price_status_var.set("prices: fetching…")
        self.ninja.fetch_async(self._on_prices_updated)

    def _on_prices_updated(self) -> None:
        """Called from background thread — schedule UI update on main thread."""
        self.root.after(0, self._update_price_status)

    def _update_price_status(self) -> None:
        self._price_status_var.set(f"prices: {self.ninja.status}")
        # Redraw current item with updated ninja data
        if self._current_item and self._current_item.rarity in ("Unique", "Currency", "Gem", "Divination Card"):
            self._display_item(self._current_item)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="PoE Item Pricer")
    parser.add_argument(
        "--league", "-l",
        default="Standard",
        help="League name (default: Standard)",
    )
    args = parser.parse_args()

    root = tk.Tk()
    app = PricerApp(root, args.league)
    root.mainloop()


if __name__ == "__main__":
    main()
