"""
Path of Exile 1 - Stash Item Search
=====================================
Searches all downloaded stash JSON files using key=value queries.
Supports dotted notation for nested fields and list scanning.

NOTE: This product isn't affiliated with or endorsed by Grinding Gear Games in any way.

Usage:
    python poe_stash_search.py <key> <value> [options]

Examples:
    # Find all unique items (frameType 3 = unique)
    python poe_stash_search.py frameType 3

    # Find items by name
    python poe_stash_search.py name "Shavronne's Wrappings"

    # Find items of a specific base type
    python poe_stash_search.py typeLine "Occultist's Vestment"

    # Nested: find items with a specific property name (scans list entries)
    python poe_stash_search.py properties.name "Quality"

    # Find by item level
    python poe_stash_search.py ilvl 100

    # Find corrupted items
    python poe_stash_search.py corrupted true

    # Search only specific files
    python poe_stash_search.py frameType 3 --dir ./poe_stash_data

    # Output results as JSON
    python poe_stash_search.py typeLine "Jade Flask" --json

    # Case-insensitive partial match
    python poe_stash_search.py name "shav" --contains --ignore-case
"""

import json
import os
import sys
import argparse
import glob
from typing import Any


# ─── CONFIGURATION ────────────────────────────────────────────────────────────

DEFAULT_DATA_DIR = "poe_stash_data"


# ─── DOTTED KEY RESOLVER ──────────────────────────────────────────────────────

def resolve_key(obj: Any, dotted_key: str) -> list[Any]:
    """
    Resolve a dotted key path against a JSON object.
    Returns a flat list of all matching values found.

    Handles:
      - Simple keys:       "ilvl"             → obj["ilvl"]
      - Nested dicts:      "league"           → obj["league"]
      - Dotted nested:     "properties.name"  → obj["properties"][*]["name"]
      - List scanning:     if a node is a list, recurse into each element

    Examples on a PoE item:
      resolve_key(item, "ilvl")              → [86]
      resolve_key(item, "properties.name")   → ["Quality", "Lasts X Seconds", ...]
      resolve_key(item, "sockets.attr")      → ["S", "D", "I", ...]
    """
    parts = dotted_key.split(".", 1)
    head = parts[0]
    tail = parts[1] if len(parts) > 1 else None

    if isinstance(obj, list):
        # Fan out across list elements
        results = []
        for element in obj:
            results.extend(resolve_key(element, dotted_key))
        return results

    if isinstance(obj, dict):
        if head not in obj:
            return []
        value = obj[head]
        if tail is None:
            # Reached the end of the path
            if isinstance(value, list):
                return value  # return all list elements as candidates
            return [value]
        else:
            return resolve_key(value, tail)

    return []


def coerce_value(raw: str) -> Any:
    """Try to coerce a string CLI value to int, float, or bool."""
    low = raw.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw  # keep as string


def matches(resolved_values: list[Any], target: Any,
            contains: bool, ignore_case: bool) -> bool:
    """Check whether any resolved value satisfies the match condition."""
    for val in resolved_values:
        if contains:
            # Partial string match
            v_str = str(val).lower() if ignore_case else str(val)
            t_str = str(target).lower() if ignore_case else str(target)
            if t_str in v_str:
                return True
        else:
            if ignore_case and isinstance(val, str) and isinstance(target, str):
                if val.lower() == target.lower():
                    return True
            else:
                if val == target:
                    return True
    return False


# ─── FILE LOADING ─────────────────────────────────────────────────────────────

def load_items_from_file(filepath: str) -> list[dict]:
    """
    Load a stash JSON file and extract all item objects.
    Handles both per-tab files (have "items" key) and
    combined files (have "tabs" → each with "items").
    Attaches source file and tab name to each item for context.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ⚠  Skipping {filepath}: {e}", file=sys.stderr)
        return []

    items = []
    filename = os.path.basename(filepath)

    # Combined file: { "tabs": [ { "tab_name": ..., "items": [...] } ] }
    if "tabs" in data and isinstance(data["tabs"], list):
        for tab in data["tabs"]:
            tab_name = tab.get("tab_name", tab.get("n", "unknown"))
            for item in tab.get("items", []):
                item["_source_file"] = filename
                item["_tab_name"]    = tab_name
                items.append(item)

    # Per-tab file: { "items": [...], "tab_name": ... }
    elif "items" in data and isinstance(data["items"], list):
        tab_name = data.get("tab_name", "unknown")
        for item in data["items"]:
            item["_source_file"] = filename
            item["_tab_name"]    = tab_name
            items.append(item)

    return items


def collect_all_items(data_dir: str) -> list[dict]:
    """Load items from all JSON files in the data directory."""
    pattern = os.path.join(data_dir, "*.json")
    files = sorted(glob.glob(pattern))

    if not files:
        print(f"✗  No JSON files found in '{data_dir}'", file=sys.stderr)
        sys.exit(1)

    # Prefer the combined file to avoid duplicates; fall back to individual tabs
    combined = [f for f in files if os.path.basename(f).startswith("all_stashes_")]
    if combined:
        target_files = combined  # single combined file is enough
    else:
        # Exclude summary files (no raw items), use per-tab files
        target_files = [f for f in files
                        if not os.path.basename(f).startswith("summary_")
                        and not os.path.basename(f).startswith("tab_list_")]

    all_items = []
    seen_ids: set[str] = set()

    for filepath in target_files:
        for item in load_items_from_file(filepath):
            item_id = item.get("id")
            if item_id:
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
            all_items.append(item)

    return all_items


# ─── DISPLAY ──────────────────────────────────────────────────────────────────

FRAME_TYPES = {
    0: "Normal", 1: "Magic", 2: "Rare", 3: "Unique",
    4: "Gem", 5: "Currency", 6: "Divination Card",
    7: "Quest", 8: "Prophecy", 9: "Foil Unique",
}


def get_item_quantity(item: dict) -> int:
    """
    Return the true quantity of an item using the correct attribute:

    - stackSize  : currency, essences, fragments, div cards (e.g. Chaos Orb x143)
    - 1          : all other items (gear, flasks, maps) are single items
    """
    stack_size = item.get("stackSize")
    if stack_size is not None:
        return int(stack_size)
    return 1


def format_item(item: dict, index: int) -> str:
    """Pretty-print a single item result."""
    name       = item.get("name", "")
    type_line  = item.get("typeLine", "Unknown")
    ilvl       = item.get("ilvl", "?")
    frame      = FRAME_TYPES.get(item.get("frameType", 0), "Unknown")
    tab        = item.get("_tab_name", "?")
    source     = item.get("_source_file", "?")
    corrupted  = " [CORRUPTED]" if item.get("corrupted") else ""
    identified = "" if item.get("identified", True) else " [UNIDENTIFIED]"
    qty        = get_item_quantity(item)
    qty_str    = f" x{qty}" if qty > 1 else ""

    display_name = f"{name} {type_line}".strip() if name else type_line

    lines = [
        f"  [{index}] {display_name}{qty_str}{corrupted}{identified}",
        f"       Type : {frame}  |  iLvl : {ilvl}  |  Tab : {tab}",
    ]

    # Explicit mods
    mods = item.get("explicitMods", [])
    if mods:
        lines.append(f"       Mods : {' / '.join(mods[:3])}" +
                     (" ..." if len(mods) > 3 else ""))

    lines.append(f"       File : {source}")
    return "\n".join(lines)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Search PoE stash JSON files by key=value (supports dotted notation).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("key",   help="Field to search, e.g. 'frameType' or 'properties.name'")
    parser.add_argument("value", help="Value to match, e.g. '3' or 'Quality'")
    parser.add_argument("--dir", default=DEFAULT_DATA_DIR,
                        help=f"Directory containing stash JSON files (default: {DEFAULT_DATA_DIR})")
    parser.add_argument("--contains",    action="store_true",
                        help="Partial string match instead of exact match")
    parser.add_argument("--ignore-case", action="store_true",
                        help="Case-insensitive matching")
    parser.add_argument("--json",        action="store_true",
                        help="Output results as a JSON array")
    parser.add_argument("--limit",       type=int, default=0,
                        help="Max results to show (0 = unlimited)")

    args = parser.parse_args()

    target_value = coerce_value(args.value)

    print(f"\n🔍 Searching '{args.dir}' for  {args.key} = {repr(target_value)}")
    if args.contains:
        print("   Mode: partial match")
    if args.ignore_case:
        print("   Mode: case-insensitive")
    print()

    all_items = collect_all_items(args.dir)
    print(f"   Loaded {len(all_items)} items from files.\n")

    results = []
    for item in all_items:
        resolved = resolve_key(item, args.key)
        if resolved and matches(resolved, target_value, args.contains, args.ignore_case):
            results.append(item)

    if not results:
        print("  No items matched.")
        return

    total_quantity = sum(get_item_quantity(item) for item in results)
    stack_note = " (quantity-aware)" if total_quantity != len(results) else ""
    print(f"  ✔  {len(results)} stack(s) found  |  Total quantity: {total_quantity}{stack_note}\n")

    display_results = results if args.limit == 0 else results[:args.limit]

    if args.json:
        # Strip internal metadata keys before outputting
        clean = [{k: v for k, v in item.items()
                  if not k.startswith("_")} for item in display_results]
        print(json.dumps(clean, indent=2, ensure_ascii=False))
    else:
        for i, item in enumerate(display_results, 1):
            print(format_item(item, i))
            print()
        if args.limit and len(results) > args.limit:
            print(f"  ... and {len(results) - args.limit} more (use --limit 0 to show all)")

    print(f"{'─' * 50}")
    print(f"  Stacks matched : {len(results)}")
    print(f"  Total quantity : {total_quantity}\n")


if __name__ == "__main__":
    main()
