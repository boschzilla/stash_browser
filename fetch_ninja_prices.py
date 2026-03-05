"""
Fetches current prices from poe.ninja for Standard league and saves to poe_ninja_prices.json.
"""
import json
import time
import urllib.request
import urllib.error
from datetime import datetime

BASE_CURRENCY_URL = "https://poe.ninja/api/data/currencyoverview?league=Standard&type={}"
BASE_ITEM_URL = "https://poe.ninja/api/data/itemoverview?league=Standard&type={}"

CATEGORIES = [
    ("Currency",          BASE_CURRENCY_URL, "currency"),
    ("Fragment",          BASE_CURRENCY_URL, "currency"),
    ("UniqueWeapon",      BASE_ITEM_URL,     "item"),
    ("UniqueArmour",      BASE_ITEM_URL,     "item"),
    ("UniqueAccessory",   BASE_ITEM_URL,     "item"),
    ("UniqueFlask",       BASE_ITEM_URL,     "item"),
    ("UniqueJewel",       BASE_ITEM_URL,     "item"),
    ("SkillGem",          BASE_ITEM_URL,     "item"),
    ("DivinationCard",    BASE_ITEM_URL,     "item"),
    ("Fossil",            BASE_ITEM_URL,     "item"),
    ("Resonator",         BASE_ITEM_URL,     "item"),
    ("Essence",           BASE_ITEM_URL,     "item"),
    ("Scarab",            BASE_ITEM_URL,     "item"),
    ("Oil",               BASE_ITEM_URL,     "item"),
    ("Tattoo",            BASE_ITEM_URL,     "item"),
    ("Omen",              BASE_ITEM_URL,     "item"),
    ("UniqueMap",         BASE_ITEM_URL,     "item"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def fetch_url(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return json.loads(raw)


def parse_currency(data: dict, category_key: str) -> list:
    """Parse currencyoverview response."""
    lines = data.get("lines", [])
    result = []
    for entry in lines:
        name = entry.get("currencyTypeName", "")
        chaos_value = entry.get("chaosEquivalent", 0.0)
        pay = entry.get("pay", {}) or {}
        receive = entry.get("receive", {}) or {}
        result.append({
            "name": name,
            "chaosValue": chaos_value,
            "payRatio": pay.get("value"),
            "receiveRatio": receive.get("value"),
        })
    return result


def parse_items(data: dict, category_key: str) -> list:
    """Parse itemoverview response."""
    lines = data.get("lines", [])
    result = []
    for entry in lines:
        name = entry.get("name", "")
        chaos_value = entry.get("chaosValue", 0.0)
        item_entry = {
            "name": name,
            "chaosValue": chaos_value,
            "exaltedValue": entry.get("exaltedValue"),
            "divineValue": entry.get("divineValue"),
            "count": entry.get("count"),
            "itemClass": entry.get("itemClass"),
            "links": entry.get("links"),
            "variant": entry.get("variant"),
        }
        # Gems: include level and quality in key fields
        if category_key == "SkillGem":
            item_entry["gemLevel"] = entry.get("gemLevel")
            item_entry["gemQuality"] = entry.get("gemQuality")
            item_entry["corrupted"] = entry.get("corrupted")
        result.append(item_entry)
    return result


def main():
    combined = {}
    summary = {}
    errors = []

    print(f"Starting poe.ninja price fetch at {datetime.now().isoformat()}\n")

    for (cat_type, url_template, kind) in CATEGORIES:
        url = url_template.format(cat_type)
        print(f"Fetching {cat_type} ... ", end="", flush=True)
        try:
            data = fetch_url(url)
            if kind == "currency":
                items = parse_currency(data, cat_type)
            else:
                items = parse_items(data, cat_type)
            combined[cat_type] = items
            summary[cat_type] = len(items)
            print(f"{len(items)} items")
        except urllib.error.HTTPError as e:
            msg = f"HTTP {e.code} for {cat_type}"
            print(f"ERROR: {msg}")
            errors.append(msg)
            combined[cat_type] = []
            summary[cat_type] = 0
        except Exception as e:
            msg = f"{type(e).__name__}: {e} for {cat_type}"
            print(f"ERROR: {msg}")
            errors.append(msg)
            combined[cat_type] = []
            summary[cat_type] = 0

        # Be polite to the API
        time.sleep(0.5)

    output = {
        "fetchedAt": datetime.utcnow().isoformat() + "Z",
        "league": "Standard",
        "summary": summary,
        "errors": errors,
        "data": combined,
    }

    out_path = r"C:\poe\poe_ninja_prices.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to {out_path}")
    print("\n=== Summary ===")
    total = 0
    for cat, count in summary.items():
        print(f"  {cat:<22} {count:>5} items")
        total += count
    print(f"  {'TOTAL':<22} {total:>5} items")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")

    return output


if __name__ == "__main__":
    main()
