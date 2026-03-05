"""
Mod tier thresholds and scoring for PoE 1 rare items.

Each entry in MOD_TIERS is a dict:
  name:        display name
  pattern:     regex to match the mod line
  value_group: which capture group holds the value (default 1)
               use "high" to take group(2) for "Adds X to Y" patterns
  tiers:       [(min_value, label), ...] sorted highest-to-lowest
               first matching tier wins

Tier point values used for scoring:
  T1 = 4,  T2 = 3,  T3 = 2,  T4 = 1,  T5 = 0

Price suggestion brackets based on total score:
  0–2  → 1c or vendor
  3–4  → 2–5c
  5–7  → 5–15c
  8–10 → 15–50c
  11–13→ 50–150c
  14+  → 150c+  (likely worth checking trade)
"""

from __future__ import annotations
import re
from typing import NamedTuple


# ── Tier data ────────────────────────────────────────────────────────────────

# Each entry: (name, regex, tiers, value_group)
# value_group is "high" for Adds X to Y mods, else an int (default 1)
MOD_TIERS: list[dict] = [

    # ── Defences ──────────────────────────────────────────────────────────
    {
        # T1=100-109, T2=90-99, T3=80-89, T4=70-79, T5=60-69 (ilvl 86+ rolls)
        "name": "Maximum Life",
        "pattern": r"\+(\d+) to maximum Life",
        "tiers": [(100, "T1"), (90, "T2"), (80, "T3"), (70, "T4"), (60, "T5"), (0, "T6")],
    },
    {
        "name": "Maximum Energy Shield",
        "pattern": r"\+(\d+) to maximum Energy Shield",
        "tiers": [(76, "T1"), (60, "T2"), (45, "T3"), (30, "T4"), (0, "T5")],
    },
    {
        # Body armour T1=140-159%, helmets/gloves/boots top out much lower (~60-80%)
        # Using moderate thresholds that work across slots
        "name": "Energy Shield %",
        "pattern": r"(\d+)% increased Energy Shield$",
        "tiers": [(120, "T1"), (90, "T2"), (60, "T3"), (30, "T4"), (0, "T5")],
    },
    {
        "name": "Evasion Rating %",
        "pattern": r"(\d+)% increased Evasion Rating$",
        "tiers": [(120, "T1"), (90, "T2"), (60, "T3"), (30, "T4"), (0, "T5")],
    },
    {
        "name": "Maximum Mana",
        "pattern": r"\+(\d+) to maximum Mana",
        "tiers": [(100, "T1"), (80, "T2"), (60, "T3"), (40, "T4"), (0, "T5")],
    },

    # ── Resistances ───────────────────────────────────────────────────────
    # PoE 1 single-element resist tiers at ilvl 86+:
    #   T1=46-48%, T2=42-45%, T3=37-41%, T4=32-36%, T5=27-31%
    {
        "name": "Fire Resistance",
        "pattern": r"\+(\d+)% to Fire Resistance",
        "tiers": [(46, "T1"), (42, "T2"), (37, "T3"), (32, "T4"), (27, "T5"), (0, "T6")],
    },
    {
        "name": "Cold Resistance",
        "pattern": r"\+(\d+)% to Cold Resistance",
        "tiers": [(46, "T1"), (42, "T2"), (37, "T3"), (32, "T4"), (27, "T5"), (0, "T6")],
    },
    {
        "name": "Lightning Resistance",
        "pattern": r"\+(\d+)% to Lightning Resistance",
        "tiers": [(46, "T1"), (42, "T2"), (37, "T3"), (32, "T4"), (27, "T5"), (0, "T6")],
    },
    {
        "name": "Chaos Resistance",
        "pattern": r"\+(\d+)% to Chaos Resistance",
        "tiers": [(25, "T1"), (17, "T2"), (9, "T3"), (0, "T4")],
    },
    {
        "name": "All Elemental Resistances",
        "pattern": r"\+(\d+)% to all Elemental Resistances",
        "tiers": [(16, "T1"), (13, "T2"), (10, "T3"), (7, "T4"), (4, "T5"), (0, "T6")],
    },
    {
        "name": "Fire + Cold Resistances",
        "pattern": r"\+(\d+)% to Fire and Cold Resistances",
        "tiers": [(22, "T1"), (17, "T2"), (12, "T3"), (0, "T4")],
    },
    {
        "name": "Fire + Lightning Resistances",
        "pattern": r"\+(\d+)% to Fire and Lightning Resistances",
        "tiers": [(22, "T1"), (17, "T2"), (12, "T3"), (0, "T4")],
    },
    {
        "name": "Cold + Lightning Resistances",
        "pattern": r"\+(\d+)% to Cold and Lightning Resistances",
        "tiers": [(22, "T1"), (17, "T2"), (12, "T3"), (0, "T4")],
    },

    # ── Movement ──────────────────────────────────────────────────────────
    # PoE 1 boots MS tiers: T1=35%, T2=30%, T3=25%, T4=20% (fixed roll values)
    {
        "name": "Movement Speed",
        "pattern": r"(\d+)% increased Movement Speed",
        "tiers": [(35, "T1"), (30, "T2"), (25, "T3"), (20, "T4"), (0, "T5")],
    },

    # ── Attributes ────────────────────────────────────────────────────────
    {
        "name": "All Attributes",
        "pattern": r"\+(\d+) to all Attributes",
        "tiers": [(30, "T1"), (25, "T2"), (20, "T3"), (15, "T4"), (0, "T5")],
    },
    {
        "name": "Strength",
        "pattern": r"\+(\d+) to Strength$",
        "tiers": [(55, "T1"), (46, "T2"), (38, "T3"), (30, "T4"), (0, "T5")],
    },
    {
        "name": "Dexterity",
        "pattern": r"\+(\d+) to Dexterity$",
        "tiers": [(55, "T1"), (46, "T2"), (38, "T3"), (30, "T4"), (0, "T5")],
    },
    {
        "name": "Intelligence",
        "pattern": r"\+(\d+) to Intelligence$",
        "tiers": [(55, "T1"), (46, "T2"), (38, "T3"), (30, "T4"), (0, "T5")],
    },

    # ── Attack modifiers ──────────────────────────────────────────────────
    {
        "name": "Attack Speed",
        "pattern": r"(\d+)% increased Attack Speed",
        "tiers": [(25, "T1"), (20, "T2"), (15, "T3"), (10, "T4"), (0, "T5")],
    },
    {
        "name": "Physical Damage %",
        "pattern": r"(\d+)% increased Physical Damage",
        "tiers": [(170, "T1"), (150, "T2"), (130, "T3"), (100, "T4"), (0, "T5")],
    },
    {
        "name": "Added Phys Damage (Attacks)",
        "pattern": r"Adds (\d+) to (\d+) Physical Damage to Attacks",
        "value_group": "high",
        "tiers": [(28, "T1"), (22, "T2"), (16, "T3"), (10, "T4"), (0, "T5")],
    },
    {
        "name": "Added Fire Damage (Attacks)",
        "pattern": r"Adds (\d+) to (\d+) Fire Damage to Attacks",
        "value_group": "high",
        "tiers": [(48, "T1"), (38, "T2"), (28, "T3"), (18, "T4"), (0, "T5")],
    },
    {
        "name": "Added Cold Damage (Attacks)",
        "pattern": r"Adds (\d+) to (\d+) Cold Damage to Attacks",
        "value_group": "high",
        "tiers": [(42, "T1"), (33, "T2"), (25, "T3"), (16, "T4"), (0, "T5")],
    },
    {
        "name": "Added Lightning Damage (Attacks)",
        "pattern": r"Adds (\d+) to (\d+) Lightning Damage to Attacks",
        "value_group": "high",
        "tiers": [(60, "T1"), (48, "T2"), (36, "T3"), (24, "T4"), (0, "T5")],
    },

    # ── Crit ──────────────────────────────────────────────────────────────
    {
        "name": "Critical Strike Chance",
        "pattern": r"(\d+)% increased Critical Strike Chance",
        "tiers": [(40, "T1"), (35, "T2"), (30, "T3"), (25, "T4"), (0, "T5")],
    },
    {
        "name": "Critical Strike Multiplier",
        "pattern": r"\+(\d+)% to Critical Strike Multiplier",
        "tiers": [(40, "T1"), (33, "T2"), (27, "T3"), (20, "T4"), (0, "T5")],
    },
    {
        "name": "Global Crit Chance",
        "pattern": r"(\d+)% increased Global Critical Strike Chance",
        "tiers": [(40, "T1"), (35, "T2"), (30, "T3"), (25, "T4"), (0, "T5")],
    },
    {
        "name": "Global Crit Multiplier",
        "pattern": r"\+(\d+)% to Global Critical Strike Multiplier",
        "tiers": [(40, "T1"), (33, "T2"), (27, "T3"), (20, "T4"), (0, "T5")],
    },

    # ── Spell modifiers ───────────────────────────────────────────────────
    {
        "name": "Spell Damage",
        "pattern": r"(\d+)% increased Spell Damage",
        "tiers": [(43, "T1"), (37, "T2"), (30, "T3"), (22, "T4"), (0, "T5")],
    },
    {
        "name": "Cast Speed",
        "pattern": r"(\d+)% increased Cast Speed",
        "tiers": [(16, "T1"), (13, "T2"), (10, "T3"), (7, "T4"), (0, "T5")],
    },
    {
        "name": "Added Fire Damage (Spells)",
        "pattern": r"Adds (\d+) to (\d+) Fire Damage to Spells",
        "value_group": "high",
        "tiers": [(40, "T1"), (32, "T2"), (24, "T3"), (16, "T4"), (0, "T5")],
    },
    {
        "name": "Added Cold Damage (Spells)",
        "pattern": r"Adds (\d+) to (\d+) Cold Damage to Spells",
        "value_group": "high",
        "tiers": [(35, "T1"), (28, "T2"), (21, "T3"), (14, "T4"), (0, "T5")],
    },
    {
        "name": "Added Lightning Damage (Spells)",
        "pattern": r"Adds (\d+) to (\d+) Lightning Damage to Spells",
        "value_group": "high",
        "tiers": [(50, "T1"), (40, "T2"), (30, "T3"), (20, "T4"), (0, "T5")],
    },

    # ── Recovery ──────────────────────────────────────────────────────────
    {
        "name": "Life Regeneration",
        "pattern": r"Regenerate ([\d.]+) Life per second",
        "tiers": [(10, "T1"), (7, "T2"), (5, "T3"), (3, "T4"), (0, "T5")],
    },
    {
        "name": "Life Regen %",
        "pattern": r"([\d.]+)% of Life Regenerated per second",
        "tiers": [(2.0, "T1"), (1.5, "T2"), (1.0, "T3"), (0.5, "T4"), (0, "T5")],
    },
    {
        "name": "Life on Hit",
        "pattern": r"\+(\d+) Life gained on Hit",
        "tiers": [(8, "T1"), (6, "T2"), (4, "T3"), (2, "T4"), (0, "T5")],
    },
    {
        "name": "Mana Regeneration",
        "pattern": r"(\d+)% increased Mana Regeneration Rate",
        "tiers": [(40, "T1"), (30, "T2"), (20, "T3"), (10, "T4"), (0, "T5")],
    },

    # ── Armour-specific ───────────────────────────────────────────────────
    {
        "name": "Armour %",
        "pattern": r"(\d+)% increased Armour$",
        "tiers": [(40, "T1"), (30, "T2"), (20, "T3"), (10, "T4"), (0, "T5")],
    },
    {
        "name": "Armour + ES %",
        "pattern": r"(\d+)% increased Armour and Energy Shield",
        "tiers": [(35, "T1"), (27, "T2"), (19, "T3"), (11, "T4"), (0, "T5")],
    },
    {
        "name": "Armour + Evasion %",
        "pattern": r"(\d+)% increased Armour and Evasion",
        "tiers": [(35, "T1"), (27, "T2"), (19, "T3"), (11, "T4"), (0, "T5")],
    },
    {
        "name": "Evasion + ES %",
        "pattern": r"(\d+)% increased Evasion and Energy Shield",
        "tiers": [(35, "T1"), (27, "T2"), (19, "T3"), (11, "T4"), (0, "T5")],
    },
]


# ── Scoring ──────────────────────────────────────────────────────────────────

TIER_POINTS: dict[str, int] = {"T1": 4, "T2": 3, "T3": 2, "T4": 1, "T5": 0}

# (min_score, max_score_inclusive_or_None, display)
# Based on community rule of thumb: need 3+ T2 mods to be worth listing;
# 2+ T1 mods = worth listing regardless; shifts with league economy.
PRICE_BRACKETS = [
    (12, None, "50c+  (check trade site)"),
    (9,  11,   "20–50c"),
    (6,  8,    "5–20c"),
    (4,  5,    "1–5c"),
    (0,  3,    "vendor / not worth listing"),
]


class ScoredMod(NamedTuple):
    raw_line: str       # original mod text
    mod_name: str       # human-readable mod name, "" if unrecognised
    tier: str           # T1/T2/.../T5 or "—" if unrecognised
    points: int         # TIER_POINTS value


def _get_tier(value: float, tiers: list[tuple]) -> str:
    for min_val, label in tiers:
        if value >= min_val:
            return label
    return "T5"


def score_mods(mods: list[str]) -> tuple[int, list[ScoredMod]]:
    """
    Score a list of explicit (or implicit) mod strings.

    Returns:
        total_score: sum of tier points
        scored:      list of ScoredMod for each mod line
    """
    results: list[ScoredMod] = []
    total = 0

    for mod_line in mods:
        matched = False
        for entry in MOD_TIERS:
            pattern = entry["pattern"]
            tiers = entry["tiers"]
            vg = entry.get("value_group", 1)

            m = re.search(pattern, mod_line, re.IGNORECASE)
            if not m:
                continue

            if vg == "high":
                value = float(m.group(2))
            else:
                value = float(m.group(vg))

            tier = _get_tier(value, tiers)
            pts = TIER_POINTS.get(tier, 0)
            total += pts
            results.append(ScoredMod(mod_line, entry["name"], tier, pts))
            matched = True
            break

        if not matched:
            results.append(ScoredMod(mod_line, "", "—", 0))

    return total, results


def suggest_price(score: int) -> str:
    """Return a price suggestion string for the given total score."""
    for min_s, max_s, label in PRICE_BRACKETS:
        if max_s is None and score >= min_s:
            return label
        if max_s is not None and min_s <= score <= max_s:
            return label
    return "1c or vendor"
