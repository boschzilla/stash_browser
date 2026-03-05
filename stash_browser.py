"""
PoE Stash Browser
- Credentials persist via stash_browser_config.json
- Select stash tabs to retrieve individually or all at once
- Downloads saved to stash_data/{index}.json (overwrites)
- Items tab shows all downloaded items with summary
"""

import json
import os
import sys
import subprocess
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox
import requests


MAX_RETRIES   = 5
BASE_URL      = "https://www.pathofexile.com"
USER_AGENT    = "poe-stash-browser/1.0"
SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE   = os.path.join(SCRIPT_DIR, "stash_browser_config.json")
DATA_DIR      = os.path.join(SCRIPT_DIR, "stash_data")
REQUEST_DELAY = 1.5

# Dark palette
BG       = "#1e1e1e"
BG2      = "#2d2d2d"
BG3      = "#3a3a3a"
FG       = "#d4d4d4"
FG_DIM   = "#888888"
ACCENT   = "#4ec9b0"
SEL_BG   = "#264f78"
ENTRY_BG = "#3c3c3c"
BORDER   = "#555555"
GREEN    = "#6db36d"
RED      = "#f44747"
ORANGE   = "#ce9178"
BLUE     = "#9cdcfe"
YELLOW   = "#dcdcaa"

FRAME_TYPE = {
    0: "Normal", 1: "Magic", 2: "Rare", 3: "Unique",
    4: "Gem", 5: "Currency", 6: "Div Card", 7: "Quest",
    8: "Prophecy", 9: "Foil",
}
RARITY_COLORS = {
    "Normal": FG, "Magic": BLUE, "Rare": YELLOW, "Unique": ORANGE,
    "Gem": GREEN, "Currency": FG, "Div Card": FG_DIM,
    "Quest": GREEN, "Prophecy": FG, "Foil": ORANGE,
}


# ── Persistence ──────────────────────────────────────────────────────────────

def load_config() -> dict:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(data: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


class RateLimitedError(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limited — retry after {retry_after}s")


# ── API ───────────────────────────────────────────────────────────────────────

def _make_session(poesessid: str) -> requests.Session:
    s = requests.Session()
    s.cookies.set("POESESSID", poesessid, domain="www.pathofexile.com")
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return s


def fetch_stash_tabs(poesessid: str, account: str, league: str) -> list[dict]:
    s    = _make_session(poesessid)
    url  = f"{BASE_URL}/character-window/get-stash-items"
    resp = s.get(url, params={"accountName": account, "league": league,
                               "tabs": 1, "tabIndex": 0}, timeout=30)
    if resp.status_code == 401: raise PermissionError("Unauthorized — check your POESESSID.")
    if resp.status_code == 403: raise PermissionError("Forbidden — session may have expired.")
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 60))
        raise RateLimitedError(retry_after)
    if resp.status_code != 200: raise RuntimeError(f"HTTP {resp.status_code}")
    return resp.json().get("tabs", [])


def fetch_tab_items(poesessid: str, account: str, league: str, tab_index: int) -> dict:
    s    = _make_session(poesessid)
    url  = f"{BASE_URL}/character-window/get-stash-items"
    resp = s.get(url, params={"accountName": account, "league": league,
                               "tabs": 0, "tabIndex": tab_index}, timeout=30)
    if resp.status_code == 401: raise PermissionError("Unauthorized — check your POESESSID.")
    if resp.status_code == 403: raise PermissionError("Forbidden — session may have expired.")
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 60))
        raise RateLimitedError(retry_after)
    if resp.status_code != 200: raise RuntimeError(f"HTTP {resp.status_code}")
    return resp.json()


# ── App ───────────────────────────────────────────────────────────────────────

class StashBrowserApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PoE Stash Browser")
        self.configure(bg=BG)
        self.resizable(True, True)

        self._tabs_meta: list[dict] = []   # raw tab list from API
        self._selected:  set[int]   = set()  # selected tab indices
        self._downloading = False
        self._refreshing  = False
        self._cancel_requested = False
        self._countdown_event: threading.Event | None = None

        self._apply_theme()
        self._build_ui()
        self._load_fields()
        self.after(30_000, self._tick_ages)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_theme(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".",
            background=BG, foreground=FG, fieldbackground=ENTRY_BG,
            bordercolor=BORDER, troughcolor=BG2,
            selectbackground=SEL_BG, selectforeground=FG)
        style.configure("TLabelframe",   background=BG,  bordercolor=BORDER)
        style.configure("TLabelframe.Label", background=BG, foreground=ACCENT)
        style.configure("TLabel",        background=BG,  foreground=FG)
        style.configure("TEntry",        fieldbackground=ENTRY_BG, foreground=FG, insertcolor=FG)
        style.configure("TButton",       background=BG3, foreground=FG,
                        bordercolor=BORDER, focuscolor=BG3, relief="flat", padding=4)
        style.map("TButton",
            background=[("active", BG2), ("disabled", BG2)],
            foreground=[("disabled", FG_DIM)])
        style.configure("TNotebook",     background=BG,  bordercolor=BORDER, tabmargins=0)
        style.configure("TNotebook.Tab", background=BG2, foreground=FG_DIM,
                        padding=[10, 4], bordercolor=BORDER)
        style.map("TNotebook.Tab",
            background=[("selected", BG3)],
            foreground=[("selected", FG)])
        style.configure("TScrollbar",    background=BG3, troughcolor=BG2,
                        bordercolor=BG, arrowcolor=FG)
        style.configure("Treeview",      background=BG2, foreground=FG,
                        fieldbackground=BG2, rowheight=22,
                        bordercolor=BORDER)
        style.configure("Treeview.Heading", background=BG3, foreground=ACCENT,
                        relief="flat", bordercolor=BORDER)
        style.map("Treeview",
            background=[("selected", SEL_BG)],
            foreground=[("selected", FG)])
        style.map("Treeview.Heading",
            background=[("active", BG2)])

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # Credentials bar
        self._build_creds(self)

        # Notebook
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        stash_frame = ttk.Frame(self.notebook)
        items_frame = ttk.Frame(self.notebook)
        self.notebook.add(stash_frame, text="  Stash Tabs  ")
        self.notebook.add(items_frame, text="  Items  ")

        stash_frame.columnconfigure(0, weight=1)
        stash_frame.rowconfigure(1, weight=1)
        items_frame.columnconfigure(0, weight=1)
        items_frame.rowconfigure(0, weight=1)

        self._build_stash_tab(stash_frame)
        self._build_items_tab(items_frame)

    def _build_creds(self, parent):
        f = ttk.LabelFrame(parent, text="Credentials")
        f.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        f.columnconfigure(1, weight=1)
        pad = {"padx": 8, "pady": 3}

        ttk.Label(f, text="League:").grid(row=0, column=0, sticky="e", **pad)
        self.var_league = tk.StringVar(value="Standard")
        ttk.Entry(f, textvariable=self.var_league, width=22).grid(row=0, column=1, sticky="w", **pad)

        ttk.Label(f, text="Account:").grid(row=1, column=0, sticky="e", **pad)
        self.var_account = tk.StringVar()
        ttk.Entry(f, textvariable=self.var_account, width=28).grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(f, text="POESESSID:").grid(row=2, column=0, sticky="e", **pad)
        self.var_sessid = tk.StringVar()
        ttk.Entry(f, textvariable=self.var_sessid, width=48, show="*").grid(row=2, column=1, sticky="w", **pad)

        btn_row = tk.Frame(f, bg=BG)
        btn_row.grid(row=3, column=0, columnspan=2, pady=(4, 6))
        ttk.Button(btn_row, text="Refresh Tabs",   command=self._on_refresh).pack(side="left", padx=6)
        ttk.Button(btn_row, text="Reload Script",  command=self._on_reload).pack(side="left", padx=6)

        self.var_status = tk.StringVar(value="Enter credentials and click Refresh Tabs.")
        tk.Label(f, textvariable=self.var_status, bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 9)).grid(row=4, column=0, columnspan=2, pady=(0, 4))

    def _build_stash_tab(self, parent):
        # Button row
        btn_row = tk.Frame(parent, bg=BG)
        btn_row.grid(row=0, column=0, sticky="w", padx=6, pady=6)

        self.btn_retrieve_sel = ttk.Button(btn_row, text="Retrieve Selected",
                                           command=self._on_retrieve_selected, state="disabled")
        self.btn_retrieve_sel.pack(side="left", padx=4)

        self.btn_retrieve_all = ttk.Button(btn_row, text="Retrieve All",
                                           command=self._on_retrieve_all, state="disabled")
        self.btn_retrieve_all.pack(side="left", padx=4)

        self.btn_cancel = ttk.Button(btn_row, text="Cancel",
                                     command=self._on_cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=4)

        sel_lbl = tk.Label(btn_row, text="(click row to toggle selection)",
                           bg=BG, fg=FG_DIM, font=("Segoe UI", 9))
        sel_lbl.pack(side="left", padx=10)

        # Throttle countdown bar
        self._throttle_frame = tk.Frame(parent, bg=BG)
        self._throttle_frame.grid(row=0, column=0, sticky="e", padx=8, pady=6)
        self._throttle_label = tk.Label(self._throttle_frame, text="", bg=BG,
                                        fg=FG_DIM, font=("Segoe UI", 9), width=14)
        self._throttle_label.pack(side="left", padx=(0, 4))
        self._throttle_var = tk.DoubleVar(value=0)
        self._throttle_bar = ttk.Progressbar(self._throttle_frame, variable=self._throttle_var,
                                             maximum=100, length=140, mode="determinate")
        self._throttle_bar.pack(side="left")
        self._throttle_frame.grid_remove()  # hidden until downloading

        # Treeview
        tv_frame = tk.Frame(parent, bg=BG)
        tv_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        tv_frame.columnconfigure(0, weight=1)
        tv_frame.rowconfigure(0, weight=1)

        cols = ("idx", "name", "type", "items", "updated", "age", "status")
        self.tab_tree = ttk.Treeview(tv_frame, columns=cols, show="headings",
                                     height=22, selectmode="none")
        self.tab_tree.heading("idx",     text="Index")
        self.tab_tree.heading("name",    text="Name")
        self.tab_tree.heading("type",    text="Type")
        self.tab_tree.heading("items",   text="Items")
        self.tab_tree.heading("updated", text="Last Updated")
        self.tab_tree.heading("age",     text="Age")
        self.tab_tree.heading("status",  text="Status")

        self.tab_tree.column("idx",     width=60,  anchor="center", stretch=False)
        self.tab_tree.column("name",    width=210, anchor="w")
        self.tab_tree.column("type",    width=120, anchor="w")
        self.tab_tree.column("items",   width=55,  anchor="center", stretch=False)
        self.tab_tree.column("updated", width=130, anchor="center", stretch=False)
        self.tab_tree.column("age",     width=90,  anchor="center", stretch=False)
        self.tab_tree.column("status",  width=70,  anchor="center", stretch=False)

        sb = ttk.Scrollbar(tv_frame, orient="vertical", command=self.tab_tree.yview)
        self.tab_tree.configure(yscrollcommand=sb.set)

        self.tab_tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        self.tab_tree.tag_configure("selected",    background="#1e3a52", foreground=FG)
        self.tab_tree.tag_configure("downloading", foreground=YELLOW)
        self.tab_tree.tag_configure("done",        foreground=GREEN)
        self.tab_tree.tag_configure("error",       foreground=RED)

        self.tab_tree.bind("<ButtonRelease-1>", self._on_tab_tree_click)

    def _build_items_tab(self, parent):
        # Treeview
        tv_frame = tk.Frame(parent, bg=BG)
        tv_frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        tv_frame.columnconfigure(0, weight=1)
        tv_frame.rowconfigure(0, weight=1)

        cols = ("tab", "item", "rarity", "ilvl", "stack")
        self.item_tree = ttk.Treeview(tv_frame, columns=cols, show="headings",
                                      height=26, selectmode="browse")
        self.item_tree.heading("tab",    text="Tab")
        self.item_tree.heading("item",   text="Item")
        self.item_tree.heading("rarity", text="Rarity")
        self.item_tree.heading("ilvl",   text="iLvl")
        self.item_tree.heading("stack",  text="Stack")

        self.item_tree.column("tab",    width=140, anchor="w")
        self.item_tree.column("item",   width=300, anchor="w")
        self.item_tree.column("rarity", width=90,  anchor="center", stretch=False)
        self.item_tree.column("ilvl",   width=50,  anchor="center", stretch=False)
        self.item_tree.column("stack",  width=60,  anchor="center", stretch=False)

        isb = ttk.Scrollbar(tv_frame, orient="vertical", command=self.item_tree.yview)
        self.item_tree.configure(yscrollcommand=isb.set)
        self.item_tree.grid(row=0, column=0, sticky="nsew")
        isb.grid(row=0, column=1, sticky="ns")

        # Tag colors per rarity
        for rarity, color in RARITY_COLORS.items():
            self.item_tree.tag_configure(rarity, foreground=color)

        # Summary bar
        summary_frame = tk.Frame(parent, bg=BG2, pady=6)
        summary_frame.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 6))

        self._summary_vars: dict[str, tk.StringVar] = {}
        labels = ["Total", "Normal", "Magic", "Rare", "Unique",
                  "Gem", "Currency", "Div Card"]
        for i, lbl in enumerate(labels):
            var = tk.StringVar(value=f"{lbl}: —")
            self._summary_vars[lbl] = var
            color = RARITY_COLORS.get(lbl, FG)
            tk.Label(summary_frame, textvariable=var, bg=BG2, fg=color,
                     font=("Consolas", 10), padx=10).pack(side="left")

    # ── Credentials persistence ───────────────────────────────────────────────

    def _load_fields(self):
        cfg = load_config()
        if "league"  in cfg: self.var_league.set(cfg["league"])
        if "account" in cfg: self.var_account.set(cfg["account"])
        if "sessid"  in cfg: self.var_sessid.set(cfg["sessid"])
        if "geometry" in cfg:
            try:
                self.geometry(cfg["geometry"])
            except Exception:
                pass
        self._restore_tab_cache(cfg)

    def _restore_tab_cache(self, cfg: dict):
        """Populate the tab tree from the cached tabs.json without hitting the API."""
        tabs_path = os.path.join(DATA_DIR, "tabs.json")
        if not os.path.exists(tabs_path):
            return
        try:
            with open(tabs_path, "r", encoding="utf-8") as f:
                tabs = json.load(f)
        except Exception:
            return
        if not tabs:
            return

        # Populate tree (clears _selected)
        self._populate_tab_tree(tabs, write_cache=False)

        # Restore previously selected indices
        saved_selected: list[int] = cfg.get("selected", [])
        for idx in saved_selected:
            iid = str(idx)
            if not self.tab_tree.exists(iid):
                continue
            self._selected.add(idx)
            vals = list(self.tab_tree.item(iid, "values"))
            vals[1] = vals[1].replace("☐", "☑")
            tags = list(self.tab_tree.item(iid, "tags"))
            if "selected" not in tags:
                tags.append("selected")
            self.tab_tree.item(iid, values=vals, tags=tags)

        self._set_status(f"{len(tabs)} tab(s) loaded from cache.")

    def _save_fields(self):
        save_config({
            "league":   self.var_league.get().strip(),
            "account":  self.var_account.get().strip(),
            "sessid":   self.var_sessid.get().strip(),
            "geometry": self.geometry(),
            "selected": sorted(self._selected),
        })

    def _on_close(self):
        self._save_fields()
        self.destroy()

    def _on_reload(self):
        self._save_fields()
        self.destroy()
        subprocess.Popen([sys.executable, os.path.abspath(__file__)])

    # ── Refresh tab list ──────────────────────────────────────────────────────

    REFRESH_RETRIES  = 10   # retry up to 10 times (~10 min total)
    REFRESH_INTERVAL = 60   # seconds between retries

    def _on_refresh(self):
        if self._refreshing or self._downloading:
            return
        league  = self.var_league.get().strip()
        account = self.var_account.get().strip()
        sessid  = self.var_sessid.get().strip()
        if not league or not account or not sessid:
            messagebox.showwarning("Missing Input", "Please fill in all fields.")
            return
        self._save_fields()
        self._refreshing = True
        self._cancel_requested = False
        self._set_retrieve_buttons("disabled")
        self.btn_cancel.config(state="disabled")
        self._set_status("Fetching tab list...")

        def worker():
            for attempt in range(1, self.REFRESH_RETRIES + 2):
                if self._cancel_requested:
                    self.after(0, self._on_refresh_cancelled)
                    return
                try:
                    tabs = fetch_stash_tabs(sessid, account, league)
                    self.after(0, self._on_refresh_done)
                    self.after(0, lambda t=tabs: self._populate_tab_tree(t))
                    return
                except PermissionError as e:
                    # Auth errors won't fix themselves — fail immediately
                    msg = (f"{e}\n\n"
                           "Make sure your POESESSID is current — log out and back in "
                           "to pathofexile.com to get a fresh one.")
                    self.after(0, self._on_refresh_done)
                    self.after(0, lambda m=msg: self._refresh_error("Auth Error", m))
                    return
                except Exception as e:
                    if attempt > self.REFRESH_RETRIES:
                        msg = f"{type(e).__name__}: {e}"
                        self.after(0, self._on_refresh_done)
                        self.after(0, lambda m=msg: self._refresh_error("Refresh Failed", m))
                        return
                    # Use server-supplied wait time if available, else fixed interval
                    wait   = e.retry_after if isinstance(e, RateLimitedError) else self.REFRESH_INTERVAL
                    prefix = f"Retry {attempt}/{self.REFRESH_RETRIES}"
                    self.after(0, lambda p=prefix, err=e:
                               self._set_status(f"{p} — {type(err).__name__}: {err}"))
                    self.after(0, lambda: self.btn_cancel.config(state="normal"))
                    self.after(0, self._throttle_frame.grid)
                    evt = threading.Event()
                    self._countdown_event = evt
                    self.after(0, lambda e2=evt, w=wait, p=prefix:
                               self._countdown_tick(w, w, e2, p))
                    evt.wait()
                    self.after(0, self._throttle_frame.grid_remove)
                    self.after(0, lambda: self.btn_cancel.config(state="disabled"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_refresh_done(self):
        self._refreshing = False
        self._cancel_requested = False
        self._countdown_event = None
        self._throttle_frame.grid_remove()
        self.btn_cancel.config(state="disabled")

    def _on_refresh_cancelled(self):
        self._refreshing = False
        self._cancel_requested = False
        self._countdown_event = None
        self._throttle_frame.grid_remove()
        self.btn_cancel.config(state="disabled")
        self._set_retrieve_buttons("normal" if self._tabs_meta else "disabled")
        self._set_status("Refresh cancelled.")

    def _refresh_error(self, title: str, msg: str):
        self._set_retrieve_buttons("normal" if self._tabs_meta else "disabled")
        self._set_status(f"Error — {msg.splitlines()[0]}")
        messagebox.showerror(title, msg)

    def _populate_tab_tree(self, tabs: list[dict], write_cache: bool = True):
        self._tabs_meta = tabs
        self._selected.clear()

        # Persist tab metadata for items loading
        if write_cache:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(os.path.join(DATA_DIR, "tabs.json"), "w", encoding="utf-8") as f:
                json.dump(tabs, f, indent=2)

        for row in self.tab_tree.get_children():
            self.tab_tree.delete(row)

        for tab in tabs:
            idx      = tab.get("i", "?")
            name     = tab.get("n", f"Tab {idx}")
            tab_type = tab.get("type", "NormalStash")
            cached   = os.path.exists(os.path.join(DATA_DIR, f"{idx}.json"))
            mtime    = self._tab_mtime(idx)
            self.tab_tree.insert("", "end", iid=str(idx),
                                 values=(f"[{idx}]", f"☐  {name}", tab_type,
                                         self._tab_item_count(idx),
                                         mtime, self._tab_age(idx),
                                         "✓" if cached else ""),
                                 tags=("done" if cached else "",))

        self._set_status(f"{len(tabs)} tab(s) found.")
        self._set_retrieve_buttons("normal")

    # ── Tab tree selection ────────────────────────────────────────────────────

    def _on_tab_tree_click(self, event):
        if self._downloading:
            return
        iid = self.tab_tree.identify_row(event.y)
        if not iid:
            return
        idx = int(iid)
        vals = list(self.tab_tree.item(iid, "values"))
        name_raw = vals[1]  # e.g. "☐  TabName" or "☑  TabName"

        if idx in self._selected:
            self._selected.discard(idx)
            vals[1] = name_raw.replace("☑", "☐")
            current_tags = list(self.tab_tree.item(iid, "tags"))
            current_tags = [t for t in current_tags if t != "selected"]
            self.tab_tree.item(iid, values=vals, tags=current_tags)
        else:
            self._selected.add(idx)
            vals[1] = name_raw.replace("☐", "☑")
            current_tags = list(self.tab_tree.item(iid, "tags"))
            if "selected" not in current_tags:
                current_tags.append("selected")
            self.tab_tree.item(iid, values=vals, tags=current_tags)

    # ── Retrieve ──────────────────────────────────────────────────────────────

    def _on_cancel(self):
        self._cancel_requested = True
        self.btn_cancel.config(state="disabled")
        if self._refreshing:
            self._set_status("Cancelling refresh...")
        else:
            self._set_status("Cancelling after current tab completes...")
        if self._countdown_event:
            self._countdown_event.set()  # unblock worker immediately

    def _on_retrieve_selected(self):
        if not self._selected:
            messagebox.showinfo("Nothing Selected", "Click rows to select tabs first.")
            return
        self._start_download(sorted(self._selected))

    def _on_retrieve_all(self):
        indices = [t.get("i", 0) for t in self._tabs_meta]
        self._start_download(indices)

    def _start_download(self, indices: list[int]):
        league  = self.var_league.get().strip()
        account = self.var_account.get().strip()
        sessid  = self.var_sessid.get().strip()
        if not sessid or not account or not league:
            messagebox.showwarning("Missing Input", "Please fill in credentials.")
            return

        self._downloading = True
        self._cancel_requested = False
        self._set_retrieve_buttons("disabled")
        self.btn_cancel.config(state="normal")
        self._throttle_frame.grid()
        self._throttle_var.set(0)
        self._throttle_label.config(text="")
        self._set_status(f"Downloading {len(indices)} tab(s)...")

        def worker():
            os.makedirs(DATA_DIR, exist_ok=True)
            errors = 0
            completed = 0
            total = len(indices)
            for idx in indices:
                if self._cancel_requested:
                    self.after(0, lambda: self._set_status(
                        f"Cancelled — {completed}/{len(indices)} tab(s) downloaded."))
                    break
                self.after(0, lambda i=idx: self._set_tab_dl_status(i, "downloading"))
                self.after(0, lambda c=completed, t=total:
                           self._set_status(f"Downloading… {c}/{t} done"))
                success = False
                for attempt in range(1, MAX_RETRIES + 1):
                    if self._cancel_requested:
                        break
                    try:
                        data = fetch_tab_items(sessid, account, league, idx)
                        path = os.path.join(DATA_DIR, f"{idx}.json")
                        with open(path, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=2)
                        self.after(0, lambda i=idx: self._set_tab_dl_status(i, "done"))
                        completed += 1
                        success = True
                        break
                    except RateLimitedError as e:
                        if attempt == MAX_RETRIES:
                            errors += 1
                            self.after(0, lambda i=idx: self._set_tab_dl_status(i, "error"))
                            self.after(0, lambda a=attempt: self._set_status(
                                f"Gave up after {a} attempt(s) — still rate limited."))
                            break
                        prefix = f"Throttled  •  attempt {attempt}/{MAX_RETRIES}"
                        wait   = e.retry_after
                        self.after(0, lambda p=prefix: self._set_status(p))
                        evt = threading.Event()
                        self._countdown_event = evt
                        self.after(0, lambda e2=evt, w=wait, p=prefix:
                                   self._countdown_tick(w, w, e2, p))
                        evt.wait()
                    except Exception:
                        errors += 1
                        self.after(0, lambda i=idx: self._set_tab_dl_status(i, "error"))
                        break

                # Normal inter-tab rate-limit delay
                if success and not self._cancel_requested:
                    evt = threading.Event()
                    self._countdown_event = evt
                    self.after(0, lambda e=evt: self._countdown_tick(
                        REQUEST_DELAY, REQUEST_DELAY, e, "Throttling"))
                    evt.wait()

            if not self._cancel_requested:
                self.after(0, lambda: self._on_download_complete(len(indices), errors))
            else:
                self.after(0, self._on_download_cancelled)

        threading.Thread(target=worker, daemon=True).start()

    def _set_tab_dl_status(self, idx: int, state: str):
        iid = str(idx)
        if not self.tab_tree.exists(iid):
            return
        symbol = {"downloading": "→", "done": "✓", "error": "✗"}.get(state, "")
        vals = list(self.tab_tree.item(iid, "values"))
        if state == "done":
            vals[3] = self._tab_item_count(idx)
            vals[4] = self._tab_mtime(idx)
            vals[5] = self._tab_age(idx)
        vals[6] = symbol
        # Preserve selection tag, replace status tag
        tags = [t for t in self.tab_tree.item(iid, "tags")
                if t not in ("downloading", "done", "error")]
        tags.append(state)
        self.tab_tree.item(iid, values=vals, tags=tags)
        self.tab_tree.see(iid)

    def _on_download_cancelled(self):
        self._downloading = False
        self._cancel_requested = False
        self._countdown_event = None
        self._throttle_frame.grid_remove()
        self.btn_cancel.config(state="disabled")
        self._set_retrieve_buttons("normal")

    def _on_download_complete(self, total: int, errors: int):
        self._downloading = False
        self._cancel_requested = False
        self._countdown_event = None
        self._throttle_frame.grid_remove()
        self.btn_cancel.config(state="disabled")
        self._set_retrieve_buttons("normal")
        msg = f"Done — {total - errors}/{total} tab(s) downloaded."
        if errors:
            msg += f" {errors} error(s)."
        self._set_status(msg)
        self._load_items()
        self.notebook.select(1)  # switch to Items tab

    # ── Items tab ─────────────────────────────────────────────────────────────

    def _load_items(self):
        # Load tab name map
        tabs_path = os.path.join(DATA_DIR, "tabs.json")
        tab_names: dict[int, str] = {}
        if os.path.exists(tabs_path):
            try:
                tabs_list = json.loads(open(tabs_path, encoding="utf-8").read())
                tab_names = {t.get("i", 0): t.get("n", "?") for t in tabs_list}
            except Exception:
                pass

        # Clear existing
        for row in self.item_tree.get_children():
            self.item_tree.delete(row)

        counters: dict[str, int] = {k: 0 for k in
            ["Total", "Normal", "Magic", "Rare", "Unique", "Gem", "Currency", "Div Card"]}

        if not os.path.isdir(DATA_DIR):
            return

        # Iterate downloaded JSON files in index order
        files = sorted(
            [f for f in os.listdir(DATA_DIR) if f.endswith(".json") and f != "tabs.json"],
            key=lambda f: int(f[:-5]) if f[:-5].isdigit() else 9999
        )

        for fname in files:
            idx = int(fname[:-5]) if fname[:-5].isdigit() else -1
            tab_name = tab_names.get(idx, f"Tab {idx}")
            try:
                data = json.loads(open(os.path.join(DATA_DIR, fname), encoding="utf-8").read())
            except Exception:
                continue

            for item in data.get("items", []):
                frame  = item.get("frameType", 0)
                rarity = FRAME_TYPE.get(frame, "Normal")
                name   = item.get("name", "").strip()
                type_  = item.get("typeLine", "").strip()
                display = f"{name} {type_}".strip() if name else type_
                ilvl   = item.get("ilvl", "")
                stack  = item.get("stackSize", "")

                self.item_tree.insert("", "end",
                                      values=(tab_name, display, rarity,
                                              ilvl or "", stack or ""),
                                      tags=(rarity,))

                counters["Total"] += 1
                if rarity in counters:
                    counters[rarity] += 1

        for lbl, var in self._summary_vars.items():
            var.set(f"{lbl}: {counters.get(lbl, '—')}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _countdown_tick(self, remaining: float, total: float,
                        event: threading.Event, prefix: str = "Throttling"):
        if event.is_set():
            self._throttle_var.set(0)
            self._throttle_label.config(text="")
            return
        if remaining <= 0:
            self._throttle_var.set(0)
            self._throttle_label.config(text="")
            event.set()
            return
        pct = (remaining / total) * 100
        self._throttle_var.set(pct)
        self._throttle_label.config(text=f"{prefix}  {remaining:.1f}s")
        self.after(100, lambda: self._countdown_tick(
            round(remaining - 0.1, 1), total, event, prefix))

    def _tab_item_count(self, idx: int) -> str:
        path = os.path.join(DATA_DIR, f"{idx}.json")
        if not os.path.exists(path):
            return ""
        try:
            data = json.loads(open(path, encoding="utf-8").read())
            return str(len(data.get("items", [])))
        except Exception:
            return "?"

    def _tab_mtime(self, idx: int) -> str:
        path = os.path.join(DATA_DIR, f"{idx}.json")
        if not os.path.exists(path):
            return ""
        return datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")

    def _tab_age(self, idx: int) -> str:
        path = os.path.join(DATA_DIR, f"{idx}.json")
        if not os.path.exists(path):
            return ""
        secs = int(time.time() - os.path.getmtime(path))
        if secs < 60:       return f"{secs}s ago"
        if secs < 3600:     return f"{secs // 60}m ago"
        if secs < 86400:    return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"

    def _tick_ages(self):
        """Refresh the Age column every 30 seconds."""
        for iid in self.tab_tree.get_children():
            try:
                idx  = int(iid)
                vals = list(self.tab_tree.item(iid, "values"))
                if vals[4]:  # has a Last Updated value
                    vals[5] = self._tab_age(idx)
                    self.tab_tree.item(iid, values=vals)
            except (ValueError, IndexError):
                pass
        self.after(30_000, self._tick_ages)

    def _set_status(self, msg: str, error: bool = False):
        self.var_status.set(msg)

    def _set_retrieve_buttons(self, state: str):
        self.btn_retrieve_sel.config(state=state)
        self.btn_retrieve_all.config(state=state)
        if state == "normal":
            self.btn_cancel.config(state="disabled")


if __name__ == "__main__":
    app = StashBrowserApp()
    app.mainloop()
