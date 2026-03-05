"""
Parse Path of Exile 1 item text from clipboard (Ctrl+C on an item in-game).

The clipboard format is sections separated by '--------', e.g.:
  Item Class: Helmets
  Rarity: Rare
  Gale Coronet
  Scholar's Cap
  --------
  Quality: +17% (augmented)
  Energy Shield: 144 (augmented)
  --------
  Requirements:
  Level: 67
  Int: 116
  --------
  Sockets: B-B B-B
  --------
  Item Level: 82
  --------
  +25 to Intelligence        <- implicit
  --------
  +82 to maximum Life        <- explicits start
  +38% to Cold Resistance
  ...
  --------
  Corrupted                  <- optional flags
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional


# Marker suffixes that appear on augmented/crafted/enchanted mod lines.
_ANNOTATION_RE = re.compile(
    r"\s*\((augmented|crafted|enchanted|fractured|scourged)\)\s*$",
    re.IGNORECASE,
)


def strip_annotation(line: str) -> str:
    """Remove '(augmented)' etc. from a mod line."""
    return _ANNOTATION_RE.sub("", line).strip()


@dataclass
class ParsedItem:
    rarity: str = ""       # Normal / Magic / Rare / Unique / Currency / Gem / Divination Card / ...
    name: str = ""         # Unique/Rare generated name (or item name for currency/gem)
    base: str = ""         # Base type (same as name for currency/gem)
    item_class: str = ""   # From "Item Class:" line
    item_level: int = 0
    quality: int = 0
    sockets: str = ""      # e.g. "R-G-B B-B B"
    socket_count: int = 0
    link_count: int = 0    # Largest link group
    implicits: list[str] = field(default_factory=list)   # raw lines
    explicits: list[str] = field(default_factory=list)   # raw lines
    corrupted: bool = False
    mirrored: bool = False
    identified: bool = True
    note: str = ""         # ~price note if present
    raw: str = ""


def _parse_sockets(socket_str: str) -> tuple[int, int]:
    """Return (total_socket_count, largest_link_group)."""
    socket_str = socket_str.strip()
    # Socket groups are separated by spaces, links within a group by '-'
    groups = socket_str.split()
    total = 0
    max_link = 0
    for group in groups:
        sockets_in_group = group.split("-")
        total += len(sockets_in_group)
        max_link = max(max_link, len(sockets_in_group))
    return total, max_link


def is_poe_item(text: str) -> bool:
    """Quick check: does this clipboard text look like a PoE item?"""
    return bool(text) and "Rarity:" in text and "--------" in text


def parse_item(text: str) -> Optional[ParsedItem]:
    """Parse a PoE 1 clipboard item text. Returns None if not a recognisable item."""
    if not is_poe_item(text):
        return None

    item = ParsedItem(raw=text)

    # Split on the separator, strip whitespace, drop empty sections
    sections = [s.strip() for s in text.split("--------")]
    sections = [s for s in sections if s]

    if not sections:
        return None

    # ── Header section ──────────────────────────────────────────────────────
    header_lines = [l.strip() for l in sections[0].splitlines() if l.strip()]

    for line in header_lines:
        if line.startswith("Item Class:"):
            item.item_class = line[len("Item Class:"):].strip()
        elif line.startswith("Rarity:"):
            item.rarity = line[len("Rarity:"):].strip()

    name_lines = [
        l for l in header_lines
        if not l.startswith("Item Class:") and not l.startswith("Rarity:")
    ]

    if item.rarity in ("Rare", "Unique"):
        item.name = name_lines[0] if name_lines else ""
        item.base = name_lines[1] if len(name_lines) >= 2 else item.name
    else:
        item.name = name_lines[0] if name_lines else ""
        item.base = item.name

    # ── Scan all sections for properties / flags ────────────────────────────
    item_level_idx: Optional[int] = None

    for i, section in enumerate(sections):
        lines = [l.strip() for l in section.splitlines() if l.strip()]

        # Item Level
        if item_level_idx is None:
            for line in lines:
                m = re.match(r"Item Level:\s*(\d+)", line)
                if m:
                    item.item_level = int(m.group(1))
                    item_level_idx = i
                    break

        # Quality
        if item.quality == 0:
            for line in lines:
                m = re.match(r"Quality:\s*\+?(\d+)%", line)
                if m:
                    item.quality = int(m.group(1))
                    break

        # Sockets
        if not item.sockets:
            for line in lines:
                m = re.match(r"Sockets:\s*(.+)", line)
                if m:
                    item.sockets = m.group(1).strip()
                    item.socket_count, item.link_count = _parse_sockets(item.sockets)
                    break

        # Flags
        if section.strip() == "Corrupted":
            item.corrupted = True
        if section.strip() == "Mirrored":
            item.mirrored = True
        if section.strip() == "Unidentified":
            item.identified = False

        # ~price note
        if section.startswith("Note:"):
            item.note = section[len("Note:"):].strip()

    # ── Extract mod sections (everything after Item Level) ──────────────────
    if item_level_idx is not None:
        after = sections[item_level_idx + 1:]

        # Filter out noise-only sections (flags, notes, flavour text markers)
        _noise = {"corrupted", "mirrored", "unidentified"}

        def is_mod_line(line: str) -> bool:
            low = line.lower()
            if low in _noise:
                return False
            if low.startswith("note:"):
                return False
            # Flavour text block marker
            if low == "right click to remove from the socket." :
                return False
            return True

        mod_sections: list[list[str]] = []
        for section in after:
            lines = [l.strip() for l in section.splitlines() if l.strip()]
            lines = [l for l in lines if is_mod_line(l)]
            if lines:
                mod_sections.append(lines)

        if len(mod_sections) == 1:
            # No implicits, or item has only one mod section
            item.explicits = [strip_annotation(l) for l in mod_sections[0]]
        elif len(mod_sections) >= 2:
            # First section = implicits, remainder = explicits
            item.implicits = [strip_annotation(l) for l in mod_sections[0]]
            explicits: list[str] = []
            for s in mod_sections[1:]:
                explicits.extend(strip_annotation(l) for l in s)
            item.explicits = explicits

    return item
