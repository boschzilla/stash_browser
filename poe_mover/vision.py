"""
vision.py — Claude Vision API integration for PoE stash mover.

Responsibilities:
  - Capture the full 4K screen
  - Ask Claude to locate stash tab names and their click coordinates
  - Ask Claude to find all occupied item cells in the stash grid
  - Ask Claude to detect whether player inventory is full
"""

import anthropic
import base64
import io
import json
import re
import time
from PIL import ImageGrab, Image

MODEL  = "claude-opus-4-5"

def _client() -> anthropic.Anthropic:
    """Create a fresh client each call so it always picks up the current ANTHROPIC_API_KEY."""
    import os
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError(
            "ANTHROPIC_API_KEY is not set. Enter your key in the GUI and press Set."
        )
    return anthropic.Anthropic(api_key=key)

# ---------------------------------------------------------------------------
# Screen capture
# ---------------------------------------------------------------------------

def grab_screen() -> Image.Image:
    """Capture the full screen and return a PIL Image."""
    return ImageGrab.grab()


def pil_to_b64(img: Image.Image) -> str:
    """Encode PIL image as base64 PNG string."""
    # Downscale 4K → 1920×1080 to save tokens while keeping readability
    img = img.resize((1920, 1080), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def ask_claude(b64: str, prompt: str, max_tokens: int = 1024) -> str:
    msg = _client().messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64",
                                              "media_type": "image/png",
                                              "data": b64}},
                {"type": "text", "text": prompt},
            ]
        }]
    )
    return msg.content[0].text


# ---------------------------------------------------------------------------
# Tab list detection
# ---------------------------------------------------------------------------

TAB_LIST_PROMPT = """This is a Path of Exile screenshot at 1920x1080 (downscaled from 4K).
The stash tabs are listed vertically on the LEFT side of the stash panel.
There may be a scrollbar to reveal more tabs.

Task: Return a JSON array of every visible stash tab.
Each entry: {"name": "...", "x": <pixel x of centre of tab label>, "y": <pixel y of centre of tab label>}

Also return whether a scroll-down arrow/button is visible for the tab list:
{"tabs": [...], "can_scroll_down": true/false, "scroll_down_x": <x or null>, "scroll_down_y": <y or null>}

Respond with ONLY valid JSON, no markdown fences."""


def locate_tabs() -> dict:
    """
    Returns:
      {
        "tabs": [{"name": str, "x": int, "y": int}, ...],
        "can_scroll_down": bool,
        "scroll_down_x": int|None,
        "scroll_down_y": int|None
      }
    All coordinates are in DOWNSCALED (1920×1080) space.
    """
    img = grab_screen()
    b64 = pil_to_b64(img)
    raw = ask_claude(b64, TAB_LIST_PROMPT)
    return _parse_json(raw)


# ---------------------------------------------------------------------------
# Stash grid — occupied cell detection
# ---------------------------------------------------------------------------

STASH_ITEMS_PROMPT = """This is a Path of Exile screenshot at 1920×1080 (downscaled from 4K).
The stash grid is the large grid panel in the centre of the screen.

Task: Find every cell in the stash grid that contains an item (non-empty).
Return a JSON array of cell centres (in pixel coords at this resolution):
[{"x": <int>, "y": <int>}, ...]

Order: left-to-right, top-to-bottom.
If the stash appears empty return [].
Respond with ONLY valid JSON, no markdown fences."""


def locate_stash_items() -> list[dict]:
    """Return list of {x, y} pixel positions of occupied stash cells (1920×1080 space)."""
    img = grab_screen()
    b64 = pil_to_b64(img)
    raw = ask_claude(b64, STASH_ITEMS_PROMPT, max_tokens=2048)
    result = _parse_json(raw)
    if isinstance(result, list):
        return result
    return result.get("items", [])


# ---------------------------------------------------------------------------
# Inventory state detection
# ---------------------------------------------------------------------------

INVENTORY_PROMPT = """This is a Path of Exile screenshot at 1920×1080 (downscaled from 4K).
The player inventory is the grid in the BOTTOM-RIGHT corner of the screen.

Tasks:
1. Is the inventory completely full (no empty cells visible)?
2. List pixel centres of ALL occupied inventory cells.
3. List pixel centres of ALL empty inventory cells.

Return JSON:
{
  "is_full": <bool>,
  "occupied": [{"x": int, "y": int}, ...],
  "empty":    [{"x": int, "y": int}, ...]
}
Respond with ONLY valid JSON, no markdown fences."""


def get_inventory_state() -> dict:
    """
    Returns {is_full: bool, occupied: [{x,y}], empty: [{x,y}]}
    Coordinates in 1920×1080 space.
    """
    img = grab_screen()
    b64 = pil_to_b64(img)
    raw = ask_claude(b64, INVENTORY_PROMPT, max_tokens=2048)
    return _parse_json(raw)


# ---------------------------------------------------------------------------
# Coordinate scaling  (1920×1080 → actual 4K screen pixels)
# ---------------------------------------------------------------------------

def scale_to_screen(x: int, y: int, screen_w: int = 3840, screen_h: int = 2160) -> tuple[int, int]:
    """Convert downscaled 1920×1080 coordinates to actual screen coordinates."""
    sx = int(x * screen_w / 1920)
    sy = int(y * screen_h / 1080)
    return sx, sy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json(text: str):
    # Strip markdown fences if present
    text = re.sub(r"```[a-z]*\n?", "", text).strip().rstrip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"[\[{].*[\]}]", text, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise ValueError(f"Could not parse JSON from Claude response:\n{text}")
