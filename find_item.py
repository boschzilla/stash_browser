"""
Search PoE stash data for an item by name and display it in PoE clipboard format.

Usage:
    python find_item.py <item name>
    python find_item.py honour branch
    python find_item.py "chimeric horn"
"""

import json
import sys
from pathlib import Path

STASH_DIR = Path(r"C:\Users\jbharvey\Documents\poestash\poe_stash_data")
STASH_FILE = next(STASH_DIR.glob("all_stashes_*.json"), None)


def build_poe_text(item: dict) -> str:
    lines = []

    rarity = item.get("rarity", "Normal")
    name = item.get("name", "")
    base = item.get("typeLine", "")

    lines.append(f"Rarity: {rarity}")
    lines.append(name)
    if base and base != name:
        lines.append(base)
    lines.append("--------")

    # Influences
    influences = [k.title() for k, v in item.get("influences", {}).items() if v]
    if influences:
        for inf in influences:
            lines.append(f"{inf} Item")

    # Properties (damage, armour, es, etc.)
    props = item.get("properties", [])
    prop_lines = []
    for prop in props:
        pname = prop["name"]
        vals = prop.get("values", [])
        if not vals:
            prop_lines.append(pname)
        else:
            val_str = ", ".join(v[0] for v in vals)
            augmented = any(v[1] != 0 for v in vals)
            suffix = " (augmented)" if augmented else ""
            prop_lines.append(f"{pname}: {val_str}{suffix}")
    if prop_lines:
        lines.extend(prop_lines)
        lines.append("--------")

    # Requirements
    reqs = item.get("requirements", [])
    if reqs:
        lines.append("Requirements:")
        for req in reqs:
            val = req["values"][0][0]
            lines.append(f"{req['name']}: {val}")
        lines.append("--------")

    # Sockets
    sockets = item.get("sockets", [])
    if sockets:
        groups: dict[int, list[str]] = {}
        for s in sockets:
            groups.setdefault(s.get("group", 0), []).append(s.get("sColour", "?"))
        socket_str = " ".join("-".join(g) for g in groups.values())
        lines.append(f"Sockets: {socket_str}")
        lines.append("--------")

    lines.append(f"Item Level: {item.get('ilvl', 0)}")

    # Implicits
    implicits = item.get("implicitMods", [])
    if implicits:
        lines.append("--------")
        lines.extend(implicits)

    # Explicits
    explicits = item.get("explicitMods", [])
    if explicits:
        lines.append("--------")
        lines.extend(explicits)

    # Flavour text
    flavour = item.get("flavourText", [])
    if flavour:
        lines.append("--------")
        lines.append(" ".join(flavour).replace("\r", "").strip())

    if item.get("corrupted"):
        lines.append("--------")
        lines.append("Corrupted")

    if item.get("mirrored"):
        lines.append("--------")
        lines.append("Mirrored")

    return "\n".join(lines)


def search(query: str) -> list[tuple[str, dict]]:
    """Return list of (tab_name, item) matching the query (case-insensitive substring)."""
    if not STASH_FILE:
        print(f"ERROR: No all_stashes_*.json found in {STASH_DIR}", file=sys.stderr)
        sys.exit(1)

    with open(STASH_FILE, encoding="utf-8") as f:
        data = json.load(f)

    q = query.lower()
    results = []
    seen_ids = set()

    for tab in data["tabs"]:
        tab_name = tab.get("tab_name") or "(unnamed)"
        for item in tab.get("items", []):
            item_id = item.get("id", "")
            if item_id in seen_ids:
                continue

            name = item.get("name", "").lower()
            base = item.get("typeLine", "").lower()

            if q in name or q in base:
                seen_ids.add(item_id)
                results.append((tab_name, item))

    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: python find_item.py <item name>")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    results = search(query)

    if not results:
        print(f'No items found matching "{query}"')
        sys.exit(0)

    SEP = "--------"
    DIVIDER = "=" * 60

    for i, (tab_name, item) in enumerate(results):
        if i > 0:
            print(f"\n{DIVIDER}\n")
        text = build_poe_text(item)
        print(text)
        print(f"{SEP}")
        print(f"Tab: {tab_name}")

    if len(results) > 1:
        print(f"\n({len(results)} items found)")


if __name__ == "__main__":
    main()
