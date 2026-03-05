# PoE Stash Mover

Moves every item from one stash tab into another, automatically, using Claude Vision to navigate the stash tab list and locate items.

**Resolution:** 3840×2160 (4K)  
**Tab layout:** Vertical list on the left side of the stash panel  

---

## Setup

```bash
pip install -r requirements.txt
```

Set your API key (or enter it in the GUI):
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Run

```bash
python gui.py
```

---

## How it works

1. You enter **Source Tab** name and **Destination Tab** name, then press **START**
2. A countdown gives you time to switch to Path of Exile with your stash open
3. The engine loops:
   - Scrolls the left tab list until it finds the source tab → clicks it
   - Asks Claude Vision which stash cells are occupied
   - Ctrl-clicks items one by one into your inventory
   - Every 8 clicks, re-checks whether inventory is full
   - When inventory is full (or stash batch done) → navigates to destination tab
   - Ctrl-clicks all inventory items into destination stash
   - Navigates back to source and repeats
4. Stops automatically when the source stash tab is empty

---

## Controls

| Button | Action |
|--------|--------|
| **START** | Begin transfer (after countdown) |
| **PAUSE / RESUME** | Suspend between batches |
| **STOP** | Abort immediately |
| Move mouse to **top-left corner** | Emergency abort (PyAutoGUI failsafe) |

---

## Files

| File | Purpose |
|------|---------|
| `gui.py` | Tkinter GUI — entry point |
| `engine.py` | Transfer loop logic |
| `vision.py` | All Claude Vision API calls |
| `actions.py` | All mouse/keyboard operations |

---

## Notes

- Tab name matching is **case-insensitive and partial** — "curr" will match "Currency"
- The program scales all coordinates from 1920×1080 (Claude sees a downscaled image) back to 3840×2160 automatically
- Claude Vision is called: once per tab scan, once per stash scan, every 8 clicks for inventory checks, and once per inventory dump
- API costs are roughly ~$0.01–0.03 per full batch depending on stash size
