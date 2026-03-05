import os
POESESSID    = os.environ.get("POESESSID", "")
ACCOUNT_NAME = os.environ.get("POE_ACCOUNT", "boschmorden#1614")
"""
Path of Exile 1 - Stash Tab Downloader
=======================================
Downloads all stash tabs and their items for a given league,
then saves the data as JSON files.

NOTE: This product isn't affiliated with or endorsed by Grinding Gear Games in any way.

Usage:
    pip install requests
    python poe_stash_downloader.py

Requirements:
    - Your POESESSID cookie (find it in your browser after logging into pathofexile.com)
    - Your account name (visible on your profile page)
    - The league name you want to download (e.g. "Standard", "Hardcore", "Settlers")
"""

import requests
import json
import time
import os
from datetime import datetime

# â”€â”€â”€ CONFIGURATION â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

LEAGUE       = "Standard"             # League to download (e.g. "Standard", "Hardcore")
OUTPUT_DIR   = "poe_stash_data"       # Folder where data will be saved

# Delay between requests to respect GGG's rate limits (seconds)
REQUEST_DELAY = 1.5

# Set to True to print request URLs and headers for every API call
DEBUG = False

# â”€â”€â”€ CONSTANTS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

BASE_URL   = "https://www.pathofexile.com"
USER_AGENT = "poe-stash-downloader/1.0 (contact: your@email.com)"

# â”€â”€â”€ SETUP â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

session = requests.Session()
session.cookies.set("POESESSID", POESESSID, domain="www.pathofexile.com")
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
})


def rate_limit_wait(response: requests.Response) -> None:
    """Parse rate limit headers and sleep if necessary."""
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        wait = int(retry_after) + 1
        print(f"  âš   Rate limited. Waiting {wait}s...")
        time.sleep(wait)
    else:
        time.sleep(REQUEST_DELAY)


def get(url: str, params: dict = None) -> dict | None:
    """Make a GET request with error handling and rate limit respect."""
    try:
        req = requests.Request("GET", url, params=params, headers=session.headers,
                               cookies=session.cookies)
        prepared = session.prepare_request(req)

        if DEBUG:
            print(f"\n  â”€â”€ REQUEST â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€")
            print(f"  URL     : {prepared.url}")
            print(f"  Headers :")
            for k, v in prepared.headers.items():
                # Mask the session cookie value for safety
                if k.lower() == "cookie":
                    masked = "; ".join(
                        f"{p.split('=')[0]}=***" if p.strip().startswith("POESESSID") else p
                        for p in v.split(";")
                    )
                    print(f"    {k}: {masked}")
                else:
                    print(f"    {k}: {v}")
            print(f"  â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€")

        resp = session.get(url, params=params, timeout=30)
        rate_limit_wait(resp)

        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 429:
            print(f"  âš   Rate limited on {url}. Retrying after delay...")
            time.sleep(60)
            return get(url, params)  # retry once
        elif resp.status_code == 401:
            print("  âœ—  Unauthorized â€” check your POESESSID.")
            return None
        elif resp.status_code == 403:
            print("  âœ—  Forbidden â€” your session may have expired.")
            return None
        else:
            print(f"  âœ—  HTTP {resp.status_code} on {url}")
            try:
                print(f"     {resp.json()}")
            except Exception:
                pass
            return None

    except requests.RequestException as e:
        print(f"  âœ—  Request error: {e}")
        return None


def save_json(data: dict, filename: str) -> None:
    """Save data to a JSON file in OUTPUT_DIR."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  âœ”  Saved â†’ {path}")


def fetch_stash_list() -> list[dict]:
    """Fetch the list of all stash tabs (without items)."""
    print(f"\nðŸ“¦ Fetching stash tab list for league '{LEAGUE}'...")
    url = f"{BASE_URL}/character-window/get-stash-items"
    params = {
        "accountName": ACCOUNT_NAME,
        "league": LEAGUE,
        "tabs": 1,
        "tabIndex": 0,
    }
    data = get(url, params)
    if data is None:
        return []
    tabs = data.get("tabs", [])
    print(f"  Found {len(tabs)} stash tab(s).")
    return tabs


def fetch_tab_items(tab_index: int, tab_name: str) -> dict | None:
    """Fetch all items from a specific stash tab by index."""
    url = f"{BASE_URL}/character-window/get-stash-items"
    params = {
        "accountName": ACCOUNT_NAME,
        "league": LEAGUE,
        "tabs": 0,
        "tabIndex": tab_index,
    }
    data = get(url, params)
    if data is None:
        print(f"  âœ—  Failed to fetch tab '{tab_name}' (index {tab_index})")
        return None
    items = data.get("items", [])
    print(f"  âœ”  Tab [{tab_index}] '{tab_name}': {len(items)} item(s)")
    return data


def summarise_items(all_tabs_data: list[dict]) -> dict:
    """
    Build a simple summary:
      - total item count
      - counts by item type (typeLine)
      - list of unique items
    """
    total = 0
    type_counts: dict[str, int] = {}
    uniques: list[dict] = []

    for tab in all_tabs_data:
        for item in tab.get("items", []):
            total += 1
            type_line = item.get("typeLine", "Unknown")
            type_counts[type_line] = type_counts.get(type_line, 0) + 1

            # frameType 3 = unique
            if item.get("frameType") == 3:
                uniques.append({
                    "name": item.get("name", ""),
                    "typeLine": type_line,
                    "ilvl": item.get("ilvl"),
                    "identified": item.get("identified"),
                    "tab": tab.get("tab_name", "?"),
                })

    return {
        "total_items": total,
        "unique_items_count": len(uniques),
        "unique_items": uniques,
        "type_counts": dict(sorted(type_counts.items(), key=lambda x: -x[1])[:50]),
    }


def main():
    print("=" * 55)
    print("  Path of Exile 1 â€” Stash Tab Downloader")
    print("=" * 55)

    # Validate config
    if not POESESSID:
        print("\n✗  POESESSID environment variable not set.")
        print("   set POESESSID=<value>  (Windows cmd)")
        print("   export POESESSID=<value>  (bash/PowerShell)\n")
        return

    if ACCOUNT_NAME == "YOUR_ACCOUNT_NAME":
        print("\nâœ—  Please set your ACCOUNT_NAME in the script.\n")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Step 1: Get tab list
    tabs = fetch_stash_list()
    if not tabs:
        print("\nâœ—  Could not retrieve stash tabs. Check your credentials.")
        return

    # Save tab list overview
    save_json({"league": LEAGUE, "account": ACCOUNT_NAME, "tabs": tabs},
              f"tab_list_{LEAGUE}_{timestamp}.json")

    # Step 2: Download items from each tab
    all_tabs_data = []
    print(f"\nðŸ“¥ Downloading items from {len(tabs)} tab(s)...\n")

    for tab in tabs:
        tab_index = tab.get("i", 0)
        tab_name  = tab.get("n", f"Tab_{tab_index}")
        tab_type  = tab.get("type", "NormalStash")

        print(f"  â†’ [{tab_index}] '{tab_name}' ({tab_type})")

        # Skip quad/map/special tabs that may need different handling
        data = fetch_tab_items(tab_index, tab_name)

        if data:
            data["tab_name"] = tab_name
            data["tab_index"] = tab_index
            data["tab_type"] = tab_type
            all_tabs_data.append(data)

            # Save each tab individually
            safe_name = "".join(c if c.isalnum() or c in "_ -" else "_" for c in tab_name)
            save_json(data, f"tab_{tab_index:03d}_{safe_name}_{timestamp}.json")

    # Step 3: Save combined file
    combined = {
        "meta": {
            "account": ACCOUNT_NAME,
            "league": LEAGUE,
            "downloaded_at": timestamp,
            "tab_count": len(all_tabs_data),
        },
        "tabs": all_tabs_data,
    }
    save_json(combined, f"all_stashes_{LEAGUE}_{timestamp}.json")

    # Step 4: Summary
    print("\nðŸ“Š Generating summary...")
    summary = summarise_items(all_tabs_data)
    summary["meta"] = combined["meta"]
    save_json(summary, f"summary_{LEAGUE}_{timestamp}.json")

    print("\n" + "=" * 55)
    print(f"  âœ… Done!")
    print(f"  Total items downloaded : {summary['total_items']}")
    print(f"  Unique items found     : {summary['unique_items_count']}")
    print(f"  Files saved to         : ./{OUTPUT_DIR}/")
    print("=" * 55)

    # Print top 10 most common item types
    if summary["type_counts"]:
        print("\n  Top item types:")
        for i, (itype, count) in enumerate(list(summary["type_counts"].items())[:10], 1):
            print(f"    {i:>2}. {itype} Ã—{count}")
    print()


if __name__ == "__main__":
    main()