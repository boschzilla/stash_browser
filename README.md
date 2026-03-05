# PoE Stash Browser

A lightweight desktop GUI for browsing and downloading Path of Exile 1 stash tab data.

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green)

> Not affiliated with or endorsed by Grinding Gear Games.

## Features

- **Browse all stash tabs** — fetches your full tab list with names, types, and item counts
- **Download selected or all tabs** — saves each tab's items as JSON to `stash_data/`
- **Items viewer** — browse all downloaded items across tabs with rarity colouring (Normal, Magic, Rare, Unique, Gem, Currency, Div Card)
- **Summary bar** — live counts by rarity at a glance
- **Rate limit handling** — automatic retry with countdown timer on GGG throttle responses
- **Credentials persistence** — league, account name, and POESESSID saved locally to `stash_browser_config.json`
- **Dark theme** — VS Code-inspired dark palette

## Requirements

- Python 3.10+
- `requests`

```
pip install requests
```

## Usage

```
python stash_browser.py
```

1. Enter your **League** (e.g. `Standard`, `Settlers`)
2. Enter your **Account Name** (visible on your pathofexile.com profile)
3. Enter your **POESESSID** cookie (see below)
4. Click **Refresh Tabs** to load your stash tab list
5. Click rows to select tabs, then **Retrieve Selected** — or **Retrieve All**
6. Switch to the **Items** tab to browse downloaded items

## Getting Your POESESSID

1. Log in to [pathofexile.com](https://www.pathofexile.com)
2. Open browser DevTools → Application → Cookies → `www.pathofexile.com`
3. Copy the value of the `POESESSID` cookie

> **Keep your POESESSID private** — it grants full access to your account session.

## Data Storage

Downloaded tab data is saved to `stash_data/` in the script directory:

```
stash_data/
  tabs.json        ← tab list metadata
  0.json           ← items from tab index 0
  1.json           ← items from tab index 1
  ...
```

Files are overwritten on each retrieval. Add `stash_data/` and `stash_browser_config.json` to `.gitignore` if you fork this repo.

## License

MIT
