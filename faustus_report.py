import json, os, glob, re
from collections import defaultdict

STASH_DIR = r"C:\Users\jbharvey\Documents\poestash\poe_stash_data"
PRICES_FILE = r"C:\poe\poe_ninja_prices.json"

# Load prices
with open(PRICES_FILE, "r", encoding="utf-8") as f:
    ninja = json.load(f)

# Build flat price lookup: name (lowercase) -> chaosValue
price_lookup = {}
for category, items in ninja["data"].items():
    for item in items:
        name = item.get("name", "").strip().lower()
        val = item.get("chaosValue", 0) or 0
        # Keep highest value if name appears multiple times (e.g. gem variants)
        if name not in price_lookup or val > price_lookup[name]:
            price_lookup[name] = val

# Divine orb chaos value
divine_chaos = price_lookup.get("divine orb", 1)
print(f"1 Divine Orb = {divine_chaos:.1f} chaos (Standard)\n")

# Faustus accepts stackable items — skip magic/rare/normal gear and gems
STACKABLE_FRAME_TYPES = {5, 6}  # currency=5, div card=6
# Also include: fossils, essences, oils, scarabs, tattoos, omens, resonators
# These show up as frameType=5 in the API typically

# Aggregate quantities across all tabs
stash_items = defaultdict(int)  # name -> total stack

tab_files = sorted(glob.glob(os.path.join(STASH_DIR, "tab_*.json")))
print(f"Reading {len(tab_files)} tab files...")

for path in tab_files:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("items", [])
        for item in items:
            ft = item.get("frameType", -1)
            # Only stackable: currency (5) and div cards (6)
            if ft not in STACKABLE_FRAME_TYPES:
                continue
            name = (item.get("typeLine") or item.get("name") or "").strip()
            if not name:
                continue
            stack = item.get("stackSize", 1) or 1
            stash_items[name] += stack
    except Exception:
        pass

print(f"Found {len(stash_items)} distinct stackable item types\n")

# Cross-reference with poe.ninja
results = []
not_found = []

for name, qty in stash_items.items():
    key = name.lower()
    price = price_lookup.get(key)
    if price is None:
        not_found.append((name, qty))
        continue
    total_c = price * qty
    total_div = total_c / divine_chaos
    results.append((name, qty, price, total_c, total_div))

# Sort by total chaos value desc
results.sort(key=lambda x: x[3], reverse=True)

print("=" * 80)
print("TOP ITEMS TO SELL AT FAUSTUS (by total stack value)")
print("=" * 80)
print(f"{'Item':<45} {'Qty':>7} {'Each (c)':>9} {'Total (c)':>10} {'Total (div)':>11}")
print("-" * 80)

grand_total_c = 0
for name, qty, price, total_c, total_div in results:
    grand_total_c += total_c
    if total_c >= 10 or price >= 1:  # only show items worth at least 10c total or 1c each
        marker = " **" if price >= 50 else (" *" if price >= 10 else "")
        print(f"{name:<45} {qty:>7,} {price:>9.1f} {total_c:>10,.0f} {total_div:>11.1f}{marker}")

print("-" * 80)
grand_div = grand_total_c / divine_chaos
print(f"{'GRAND TOTAL (all stackables)':<45} {'':>7} {'':>9} {grand_total_c:>10,.0f} {grand_div:>11.1f}")

print(f"\n** = 50+ chaos each   * = 10+ chaos each")

# Items not on poe.ninja
if not_found:
    print(f"\nItems NOT found on poe.ninja ({len(not_found)} types):")
    for name, qty in sorted(not_found, key=lambda x: x[1], reverse=True)[:20]:
        print(f"  {name} x{qty:,}")
