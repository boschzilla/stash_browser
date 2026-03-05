# fetch_ninja_prices.py

Fetches current item prices from [poe.ninja](https://poe.ninja) and saves them to a single JSON file. Defaults to the **Standard** league; any league can be specified via a command-line switch.

## Requirements

No third-party packages — uses only the Python standard library (`urllib`, `json`).

## Usage

```
python fetch_ninja_prices.py                        # fetch Standard league (default)
python fetch_ninja_prices.py --league Settlers      # fetch a specific league
python fetch_ninja_prices.py --list-leagues         # print available leagues and exit
```

| Switch | Description |
|---|---|
| `--league NAME` | League to fetch prices for (default: `Standard`) |
| `--list-leagues` | Print available leagues from the GGG API and exit |

Output is written to `C:\poe\poe_ninja_prices.json`.

## What It Fetches

| Category | API Type |
|---|---|
| Currency | currencyoverview |
| Fragment | currencyoverview |
| UniqueWeapon | itemoverview |
| UniqueArmour | itemoverview |
| UniqueAccessory | itemoverview |
| UniqueFlask | itemoverview |
| UniqueJewel | itemoverview |
| SkillGem | itemoverview |
| DivinationCard | itemoverview |
| Fossil | itemoverview |
| Resonator | itemoverview |
| Essence | itemoverview |
| Scarab | itemoverview |
| Oil | itemoverview |
| Tattoo | itemoverview |
| Omen | itemoverview |
| UniqueMap | itemoverview |

Requests are spaced 0.5 s apart to be polite to the poe.ninja API.

## Output Format

```json
{
  "fetchedAt": "2025-03-05T12:00:00Z",
  "league": "Standard",
  "summary": {
    "Currency": 42,
    "DivinationCard": 310,
    ...
  },
  "errors": [],
  "data": {
    "Currency": [
      {
        "name": "Divine Orb",
        "chaosValue": 180.0,
        "payRatio": 0.0055,
        "receiveRatio": 180.5
      },
      ...
    ],
    "UniqueWeapon": [
      {
        "name": "Headhunter",
        "chaosValue": 45000.0,
        "exaltedValue": 250.0,
        "divineValue": 250.0,
        "count": 12,
        "itemClass": "Belt",
        "links": null,
        "variant": null
      },
      ...
    ],
    "SkillGem": [
      {
        "name": "Empower Support",
        "chaosValue": 800.0,
        "gemLevel": 4,
        "gemQuality": 20,
        "corrupted": false,
        ...
      },
      ...
    ]
  }
}
```

### Field notes

- **Currency / Fragment** entries include `payRatio` and `receiveRatio` (the exchange ratios from the poe.ninja trade data).
- **SkillGem** entries include `gemLevel`, `gemQuality`, and `corrupted`.
- All items include `chaosValue`. Items also carry `divineValue` and `exaltedValue` where poe.ninja provides them.
- `errors` lists any categories that failed to fetch; their `data` entry will be an empty array.

