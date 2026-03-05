"""
PoE Build Optimizer — paste a PoB export code, ask a question, get AI recommendations.
"""
import base64
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk
import zlib
import xml.etree.ElementTree as ET

try:
    import anthropic
except ImportError:
    anthropic = None

# ── Constants ────────────────────────────────────────────────────────────────
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "build_optimizer_config.json")
MODEL = "claude-sonnet-4-6"

BG       = "#1a1a1a"
BG2      = "#252525"
FG       = "#c8c8c8"
GOLD     = "#c8a840"
RED      = "#ff6060"
FONT     = ("Consolas", 10)
FONT_LG  = ("Consolas", 14, "bold")
FONT_SM  = ("Consolas", 9)

SYSTEM_PROMPT = (
    "You are an expert Path of Exile 1 build analyst with deep knowledge of all "
    "skills, passive nodes, gear, keystones, ascendancies, and league mechanics. "
    "When given a build summary and a question, provide specific, actionable "
    "recommendations. Reference concrete item bases, passive notables, and gem "
    "setups by name. Be direct and prioritize the highest-impact changes first."
)

STATS_OF_INTEREST = [
    "Life", "LifeUnreserved", "EnergyShield", "TotalDPS", "WithPoisonDPS",
    "LifeRegen", "LifeLeech", "ManaUnreserved", "ManaRegen",
    "CritChance", "CritMultiplier", "Accuracy", "Speed",
    "CastSpeed", "AttackSpeed",
    "Armour", "Evasion", "Ward", "BlockChance",
    "FireResist", "ColdResist", "LightningResist", "ChaosResist",
    "FireResistOverCap", "ColdResistOverCap", "LightningResistOverCap",
]


# ── PoB Decoding & Parsing ────────────────────────────────────────────────────

def decode_pob(code: str) -> str:
    """Decode a PoB export code (base64 + zlib) to XML string."""
    code = code.strip().replace("\n", "").replace("\r", "").replace(" ", "")
    # PoB uses URL-safe base64 variants
    code = code.replace("-", "+").replace("_", "/")
    # Pad to multiple of 4
    padding = (4 - len(code) % 4) % 4
    code += "=" * padding
    data = base64.b64decode(code)
    return zlib.decompress(data).decode("utf-8")


def _fmt_stat(value: str) -> str:
    """Format a stat value: round floats, add commas for large integers."""
    try:
        f = float(value)
        if f == int(f):
            return f"{int(f):,}"
        return f"{f:.1f}"
    except ValueError:
        return value


def parse_build(xml_str: str) -> dict:
    """Extract a compact build summary dict from PoB XML."""
    root = ET.fromstring(xml_str)

    # ── Character info ────────────────────────────────────────────────────────
    build_el = root.find("Build")
    char_class    = build_el.get("className", "Unknown")
    ascendancy    = build_el.get("ascendClassName", "")
    level         = build_el.get("level", "?")
    main_group    = build_el.get("mainSocketGroup", "1")
    try:
        main_group_idx = int(main_group) - 1  # 0-based
    except ValueError:
        main_group_idx = 0

    # ── Stats ─────────────────────────────────────────────────────────────────
    stats = {}
    for ps in build_el.findall("PlayerStat"):
        name = ps.get("stat", "")
        val  = ps.get("value", "")
        if name in STATS_OF_INTEREST:
            stats[name] = _fmt_stat(val)

    # ── Main skill ────────────────────────────────────────────────────────────
    skills_el = root.find("Skills")
    main_gems = []
    if skills_el is not None:
        skill_list = skills_el.findall("Skill")
        if 0 <= main_group_idx < len(skill_list):
            skill = skill_list[main_group_idx]
        elif skill_list:
            # Fall back to the first enabled skill with gems
            skill = next(
                (s for s in skill_list if s.get("enabled", "true") == "true" and s.findall("Gem")),
                skill_list[0],
            )
        else:
            skill = None
        if skill is not None:
            for gem in skill.findall("Gem"):
                if gem.get("enabled", "true") == "true":
                    main_gems.append(gem.get("nameSpec", ""))

    # ── Items ─────────────────────────────────────────────────────────────────
    items_el = root.find("Items")
    items_by_slot: dict[str, str] = {}
    if items_el is not None:
        # Build id → name map (first non-empty line of item text block)
        id_to_name: dict[str, str] = {}
        for item in items_el.findall("Item"):
            item_id  = item.get("id", "")
            raw_text = (item.text or "").strip()
            lines    = [l.strip() for l in raw_text.splitlines() if l.strip()]
            # Skip "Rarity: X" line, take next meaningful line as name
            name = ""
            for line in lines:
                if line.lower().startswith("rarity:"):
                    continue
                name = line
                break
            id_to_name[item_id] = name or "Unknown"

        # Active ItemSet
        active_set_id = items_el.get("activeItemSet", "1")
        item_set = None
        for s in items_el.findall("ItemSet"):
            if s.get("id") == active_set_id:
                item_set = s
                break
        if item_set is None and items_el.findall("ItemSet"):
            item_set = items_el.findall("ItemSet")[0]

        if item_set is not None:
            for slot in item_set.findall("Slot"):
                slot_name = slot.get("name", "")
                item_id   = slot.get("itemId", "0")
                if item_id != "0" and item_id in id_to_name:
                    items_by_slot[slot_name] = id_to_name[item_id]

    # ── Passive node count ────────────────────────────────────────────────────
    node_count = 0
    tree_el = root.find("Tree")
    if tree_el is not None:
        spec_el = tree_el.find("Spec")
        if spec_el is not None:
            nodes_el = spec_el.find("nodes")
            if nodes_el is not None and nodes_el.text:
                node_count = len([n for n in nodes_el.text.split(",") if n.strip()])

    return {
        "class":      char_class,
        "ascendancy": ascendancy,
        "level":      level,
        "main_gems":  main_gems,
        "stats":      stats,
        "items":      items_by_slot,
        "node_count": node_count,
    }


def build_prompt(summary: dict, question: str) -> str:
    lines = ["## Build Summary"]
    cls_str = summary["class"]
    if summary["ascendancy"] and summary["ascendancy"] != "None":
        cls_str += f" / {summary['ascendancy']}"
    lines.append(f"**Class:** {cls_str} (Level {summary['level']})")

    if summary["main_gems"]:
        lines.append(f"**Main Skill:** {', '.join(summary['main_gems'])}")

    s = summary["stats"]
    stat_lines = []
    if "LifeUnreserved" in s:
        stat_lines.append(f"Life: {s['LifeUnreserved']} unreserved")
    elif "Life" in s:
        stat_lines.append(f"Life: {s['Life']}")
    if "EnergyShield" in s and s["EnergyShield"] != "0":
        stat_lines.append(f"ES: {s['EnergyShield']}")
    for dps_key in ("TotalDPS", "WithPoisonDPS"):
        if dps_key in s:
            stat_lines.append(f"DPS ({dps_key}): {s[dps_key]}")
            break
    for key in ("CritChance", "CritMultiplier"):
        if key in s:
            stat_lines.append(f"{key}: {s[key]}")
    for res in ("FireResist", "ColdResist", "LightningResist", "ChaosResist"):
        if res in s:
            stat_lines.append(f"{res}: {s[res]}%")
    for key in ("Armour", "Evasion", "Ward", "BlockChance"):
        if key in s and s[key] != "0":
            stat_lines.append(f"{key}: {s[key]}")
    for key in ("CastSpeed", "AttackSpeed", "Speed"):
        if key in s:
            stat_lines.append(f"{key}: {s[key]}")
            break
    if stat_lines:
        lines.append("**Key Stats:**")
        for sl in stat_lines:
            lines.append(f"- {sl}")

    if summary["items"]:
        lines.append("**Items:**")
        for slot, name in summary["items"].items():
            lines.append(f"- {slot}: {name}")

    if summary["node_count"]:
        lines.append(f"**Passive nodes allocated:** {summary['node_count']}")

    lines.append("")
    lines.append("## Question")
    lines.append(question.strip() or "Analyze this build and suggest the highest-impact improvements.")

    return "\n".join(lines)


# ── Config persistence ────────────────────────────────────────────────────────

def load_opt_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_opt_config(data: dict) -> None:
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


# ── Tkinter App ───────────────────────────────────────────────────────────────

class BuildOptimizerApp:
    def __init__(self, root: tk.Tk):
        self.root   = root
        self.queue  = queue.Queue()
        self._analyzing = False
        self._cfg   = load_opt_config()

        root.title("PoE Build Optimizer")
        root.configure(bg=BG)
        root.resizable(True, True)
        root.minsize(700, 700)

        self._build_ui()
        self._load_saved_state()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = self.root
        pad = {"padx": 10, "pady": 4}

        # Title
        tk.Label(root, text="PoE Build Optimizer", font=FONT_LG,
                 bg=BG, fg=GOLD).pack(**pad, anchor="w")

        ttk.Separator(root, orient="horizontal").pack(fill="x", padx=10, pady=2)

        # API Key
        key_frame = tk.Frame(root, bg=BG)
        key_frame.pack(fill="x", **pad)
        tk.Label(key_frame, text="Anthropic API Key:", font=FONT, bg=BG, fg=FG,
                 width=20, anchor="w").pack(side="left")
        self.key_var = tk.StringVar()
        self.key_entry = tk.Entry(key_frame, textvariable=self.key_var, show="*",
                                  font=FONT, bg=BG2, fg=FG,
                                  insertbackground=FG, relief="flat", bd=4)
        self.key_entry.pack(side="left", fill="x", expand=True)
        tk.Label(key_frame, text="(or set ANTHROPIC_API_KEY env var)",
                 font=FONT_SM, bg=BG, fg="#888").pack(side="left", padx=6)

        # PoB Code
        pob_header = tk.Frame(root, bg=BG)
        pob_header.pack(fill="x", **pad)
        tk.Label(pob_header, text="PoB Export Code:", font=FONT, bg=BG, fg=FG,
                 anchor="w").pack(side="left")
        tk.Button(pob_header, text="Paste", font=FONT_SM, bg=BG2, fg=GOLD,
                  relief="flat", bd=0, cursor="hand2",
                  command=self._paste_pob).pack(side="right", padx=2)
        tk.Button(pob_header, text="Clear", font=FONT_SM, bg=BG2, fg=FG,
                  relief="flat", bd=0, cursor="hand2",
                  command=lambda: self.pob_text.delete("1.0", "end")).pack(side="right", padx=2)

        pob_frame = tk.Frame(root, bg=BG2, bd=2, relief="flat")
        pob_frame.pack(fill="x", padx=10, pady=2)
        self.pob_text = tk.Text(pob_frame, height=5, font=FONT_SM,
                                bg=BG2, fg=FG, insertbackground=FG,
                                relief="flat", wrap="char", bd=4)
        pob_sb = tk.Scrollbar(pob_frame, orient="vertical", command=self.pob_text.yview)
        self.pob_text.configure(yscrollcommand=pob_sb.set)
        pob_sb.pack(side="right", fill="y")
        self.pob_text.pack(fill="x")

        # Question
        q_frame = tk.Frame(root, bg=BG)
        q_frame.pack(fill="x", **pad)
        tk.Label(q_frame, text="Your Question:", font=FONT, bg=BG, fg=FG,
                 width=20, anchor="w").pack(side="left")
        self.q_var = tk.StringVar()
        tk.Entry(q_frame, textvariable=self.q_var, font=FONT,
                 bg=BG2, fg=FG, insertbackground=FG, relief="flat", bd=4).pack(
            side="left", fill="x", expand=True)

        # Analyze button
        btn_frame = tk.Frame(root, bg=BG)
        btn_frame.pack(pady=8)
        self.analyze_btn = tk.Button(btn_frame, text="  Analyze Build  ",
                                     font=("Consolas", 11, "bold"),
                                     bg=GOLD, fg="#1a1a1a", relief="flat", bd=0,
                                     cursor="hand2", command=self._on_analyze)
        self.analyze_btn.pack()

        ttk.Separator(root, orient="horizontal").pack(fill="x", padx=10, pady=4)

        # Response area
        tk.Label(root, text="Analysis:", font=FONT, bg=BG, fg=FG,
                 anchor="w").pack(padx=10, anchor="w")
        resp_frame = tk.Frame(root, bg=BG2)
        resp_frame.pack(fill="both", expand=True, padx=10, pady=(2, 4))
        self.resp_text = scrolledtext.ScrolledText(
            resp_frame, font=FONT, bg=BG2, fg=FG,
            insertbackground=FG, relief="flat", wrap="word", bd=4,
            state="disabled"
        )
        self.resp_text.pack(fill="both", expand=True)

        # Status bar
        self.status_var = tk.StringVar(value="Ready — paste a PoB code and ask a question.")
        tk.Label(root, textvariable=self.status_var, font=FONT_SM,
                 bg="#111", fg="#888", anchor="w").pack(fill="x", padx=10, pady=(0, 4))

        root.bind("<Return>", lambda _: self._on_analyze())
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── State helpers ─────────────────────────────────────────────────────────

    def _load_saved_state(self):
        # API key: env var takes priority, then saved config
        env_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if env_key:
            self.key_var.set(env_key)
        elif self._cfg.get("api_key"):
            self.key_var.set(self._cfg["api_key"])

    def _on_close(self):
        # Save API key only if user typed it (not from env)
        if not os.environ.get("ANTHROPIC_API_KEY"):
            self._cfg["api_key"] = self.key_var.get().strip()
            save_opt_config(self._cfg)
        self.root.destroy()

    def _paste_pob(self):
        try:
            text = self.root.clipboard_get()
            self.pob_text.delete("1.0", "end")
            self.pob_text.insert("1.0", text.strip())
        except tk.TclError:
            self._set_status("Clipboard is empty.", error=True)

    def _set_status(self, msg: str, error: bool = False):
        self.status_var.set(msg)
        self.root.nametowidget(".").update_idletasks()

    def _set_response(self, text: str):
        self.resp_text.configure(state="normal")
        self.resp_text.delete("1.0", "end")
        self.resp_text.insert("1.0", text)
        self.resp_text.configure(state="disabled")

    def _append_response(self, chunk: str):
        self.resp_text.configure(state="normal")
        self.resp_text.insert("end", chunk)
        self.resp_text.see("end")
        self.resp_text.configure(state="disabled")

    # ── Analysis ──────────────────────────────────────────────────────────────

    def _on_analyze(self):
        if self._analyzing:
            return

        api_key = self.key_var.get().strip()
        if not api_key:
            self._set_status("Enter your Anthropic API key first.", error=True)
            return

        if anthropic is None:
            self._set_status("anthropic package not installed — run: pip install anthropic", error=True)
            return

        pob_code = self.pob_text.get("1.0", "end").strip()
        if not pob_code:
            self._set_status("Paste a PoB export code first.", error=True)
            return

        question = self.q_var.get().strip() or "Analyze this build and suggest the highest-impact improvements."

        # Decode + parse
        try:
            xml_str = decode_pob(pob_code)
        except Exception as e:
            self._set_status(f"Invalid PoB code: {e}", error=True)
            return
        try:
            summary = parse_build(xml_str)
        except Exception as e:
            self._set_status(f"Failed to parse build XML: {e}", error=True)
            return

        prompt = build_prompt(summary, question)

        # Clear response and kick off thread
        self._set_response("")
        self._analyzing = True
        self.analyze_btn.configure(state="disabled", text="  Analyzing…  ")
        self._set_status(
            f"Analyzing {summary['class']} / {summary['ascendancy']} lv{summary['level']}…"
        )

        threading.Thread(
            target=self._call_claude,
            args=(api_key, prompt),
            daemon=True,
        ).start()
        self._poll_response()

    def _call_claude(self, api_key: str, prompt: str):
        try:
            client = anthropic.Anthropic(api_key=api_key)
            with client.messages.stream(
                model=MODEL,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for chunk in stream.text_stream:
                    self.queue.put(("chunk", chunk))
            self.queue.put(("done", None))
        except Exception as e:
            self.queue.put(("error", str(e)))

    def _poll_response(self):
        try:
            while True:
                kind, data = self.queue.get_nowait()
                if kind == "chunk":
                    self._append_response(data)
                elif kind == "done":
                    self._analyzing = False
                    self.analyze_btn.configure(state="normal", text="  Analyze Build  ")
                    self._set_status("Done.")
                    return
                elif kind == "error":
                    self._analyzing = False
                    self.analyze_btn.configure(state="normal", text="  Analyze Build  ")
                    self._set_response(f"[API Error]\n{data}")
                    self._set_status(f"Error: {data}", error=True)
                    return
        except queue.Empty:
            pass
        if self._analyzing:
            self.root.after(50, self._poll_response)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    BuildOptimizerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
