"""
Reykjavik Job Tracker
---------------------
Desktop app (Tkinter) that aggregates retail / supermarket job offers in
Reykjavik and tracks which ones you applied to.

Setup:
    pip install requests beautifulsoup4
    (optional, for Bónus / Hagkaup / Samkaup / Domino's listings, which are built by JavaScript)
    pip install playwright && playwright install chromium (python -m playwright install chromium if the former does not work)
Run:
    python job_scrap.py

Data is stored locally in jobs.db next to this script.
"""

import datetime as dt
import os
import re
import sqlite3
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "jobs.db"

USER_AGENT = "Mozilla/5.0 (JobTrackerBot; personal use)"

# Keywords (English + Icelandic) used to keep only retail-type offers.
KEYWORDS = [
    "retail", "store", "shop", "cashier", "sales", "supermarket", "warehouse",
    "verslun", "afgreiðsla", "starfsmaður", "kassa", "sölu", "lager",
    "bónus", "krónan", "hagkaup", "nettó", "ikea", "elko", "byko", "costco",
]

# Source types:
#   "static" : entries always added to the list (general applications), no scraping.
#   "html"   : plain page fetched with requests (fast, no extra install).
#   "js"     : page built by JavaScript; needs Playwright (see header). Without it,
#              the app skips these sources and tells you, the static entries still work.
# "href_regex" keeps only links whose URL matches. "filter": True applies KEYWORDS
# to the link text (use it for generic job boards, not for single-company sites).
SOURCES = [
    # --- Generic job board -------------------------------------------------
    {"name": "Alfred.is (all employers)", "type": "html", "url": "https://alfred.is/storf",
     "href_regex": r"/starf/", "filter": True},

    # --- Supermarkets / retail ----------------------------------------------
    {"name": "Krónan", "type": "html", "url": "https://kronan.is/saekja-um-starf",
     "href_regex": r"jobs\.50skills\.com/kronan/\d+"},
    {"name": "Bónus", "type": "static",
     "title": "General application (33 stores)",
     "url": "https://ui-jobs.50skills.app/bonus.is/is"},
    {"name": "Bónus", "type": "js", "url": "https://ui-jobs.50skills.app/bonus.is/is",
     "href_regex": r"/bonus\.is/is/\d+"},
    {"name": "Hagkaup", "type": "static",
     "title": "General application (7 stores)",
     "url": "https://jobs.50skills.com/hagkaup/is"},
    {"name": "Hagkaup", "type": "js", "url": "https://jobs.50skills.com/hagkaup/is",
     "href_regex": r"/hagkaup/is/\d+"},
    {"name": "Samkaup (Nettó, Kjörbúðin, Krambúðin)", "type": "js",
     "url": "https://jobs.50skills.com/samkaup/is", "href_regex": r"/samkaup/is/\d+"},
    {"name": "BYKO", "type": "html", "url": "https://byko.is/um-byko/mannaudur/laus-storf",
     "href_regex": r"(umsokn|starf|job|50skills)"},
    {"name": "ELKO / Festi group", "type": "html", "url": "https://elko.is/um_elko/mannaudur",
     "href_regex": r"(50skills|laus-stor|umsokn)"},

    # --- Restaurants / fast food --------------------------------------------
    {"name": "Domino's Iceland", "type": "js", "url": "https://jobs.50skills.com/dominos/is",
     "href_regex": r"/dominos/is/\d+"},
]


# ----------------------------------------------------------------------------
# Storage (SQLite, local)
# ----------------------------------------------------------------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            title TEXT,
            url TEXT UNIQUE NOT NULL,
            applied_at TEXT,
            source TEXT
        )"""
    )
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    # Migration for databases created before the "source" column existed
    cols = [row[1] for row in conn.execute("PRAGMA table_info(jobs)")]
    if "source" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN source TEXT")
        for job_id, url in conn.execute("SELECT id, url FROM jobs").fetchall():
            conn.execute("UPDATE jobs SET source = ? WHERE id = ?", (urlparse(url).netloc, job_id))
        conn.commit()
    return conn


def add_job(company, title, url, source=""):
    with db() as conn:
        try:
            conn.execute(
                "INSERT INTO jobs (company, title, url, source) VALUES (?, ?, ?, ?)",
                (company, title, url, source),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def all_jobs():
    with db() as conn:
        return conn.execute(
            "SELECT id, company, title, url, applied_at, source FROM jobs ORDER BY id DESC"
        ).fetchall()


def get_meta(key):
    with db() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(key, value):
    with db() as conn:
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))


def set_applied(job_id, applied):
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M") if applied else None
    with db() as conn:
        conn.execute("UPDATE jobs SET applied_at = ? WHERE id = ?", (stamp, job_id))


# ----------------------------------------------------------------------------
# Scraping
# ----------------------------------------------------------------------------
def fetch_html(src):
    """Download a page. 'js' sources are rendered with Playwright (optional)."""
    if src["type"] == "js":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError(
                "needs Playwright: pip install playwright && playwright install chromium"
            )
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(src["url"], wait_until="networkidle", timeout=45000)
            html = page.content()
            browser.close()
        return html
    resp = requests.get(src["url"], headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    return resp.text


def scrape_source(src):
    """Return a list of (company, title, url, source) for one source."""
    if src["type"] == "static":
        return [(src["name"], src["title"], src["url"], urlparse(src["url"]).netloc)]

    soup = BeautifulSoup(fetch_html(src), "html.parser")
    pattern = re.compile(src["href_regex"])
    found, seen = [], set()
    for a in soup.find_all("a", href=True):
        url = urljoin(src["url"], a["href"])
        text = " ".join(a.get_text(" ", strip=True).split())
        if url in seen or not text or not pattern.search(url):
            continue
        if src.get("filter") and not any(k in text.lower() for k in KEYWORDS):
            continue
        seen.add(url)
        found.append((src["name"], text[:90], url, urlparse(src["url"]).netloc))
    return found


def scrape_all():
    """Returns (new_count, errors)."""
    new, errors = 0, []
    for src in SOURCES:
        try:
            for company, title, url, source in scrape_source(src):
                if add_job(company, title, url, source):
                    new += 1
        except Exception as exc:  # network error, site changed, Playwright missing...
            errors.append(f"{src['name']}: {exc}")
    return new, errors


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Reykjavik Job Tracker")
        self.geometry("1100x600")
        self._build_toolbar()
        self._build_table()
        self.refresh()

    # --- layout ---------------------------------------------------------
    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
        fetch_box = ttk.Frame(bar)
        fetch_box.pack(side="left")
        self.last_updated = tk.Label(fetch_box, font=("TkDefaultFont", 8, "italic"), fg="gray50")
        self.last_updated.pack(anchor="w")
        self._show_last_updated()
        self.fetch_btn = ttk.Button(fetch_box, text="Fetch new offers", command=self.fetch)
        self.fetch_btn.pack(anchor="w")
        ttk.Button(bar, text="Add offer manually", command=self.add_manual).pack(side="left", padx=6, anchor="s")
        self.status = ttk.Label(bar, text="")
        self.status.pack(side="left", padx=12, anchor="s")

    def _show_last_updated(self):
        stamp = get_meta("last_fetch")
        self.last_updated.config(text=f"Last updated: {stamp or 'never'}")

    def _build_table(self):
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(outer, highlightthickness=0)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.table = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.table, anchor="nw")
        self.table.bind(
            "<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

    def refresh(self):
        for w in self.table.winfo_children():
            w.destroy()
        headers = ["Company", "Source", "Offer", "Applied?", "Date applied"]
        for c, h in enumerate(headers):
            ttk.Label(self.table, text=h, font=("TkDefaultFont", 10, "bold")).grid(
                row=0, column=c, sticky="w", padx=8, pady=6
            )
        for r, (job_id, company, title, url, applied_at, source) in enumerate(all_jobs(), start=1):
            ttk.Label(self.table, text=company, wraplength=200).grid(row=r, column=0, sticky="w", padx=8, pady=3)

            ttk.Label(self.table, text=source or "-").grid(row=r, column=1, sticky="w", padx=8)

            link = tk.Label(self.table, text=title or url, fg="#1a5fb4", cursor="hand2", wraplength=380, justify="left")
            link.grid(row=r, column=2, sticky="w", padx=8)
            link.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))

            btns = ttk.Frame(self.table)
            btns.grid(row=r, column=3, padx=8)
            yes = ttk.Button(btns, text="Yes", width=5, command=lambda j=job_id: self.mark(j, True))
            no = ttk.Button(btns, text="No", width=5, command=lambda j=job_id: self.mark(j, False))
            yes.pack(side="left")
            no.pack(side="left", padx=2)
            if applied_at:
                yes.state(["disabled"])
            else:
                no.state(["disabled"])

            ttk.Label(self.table, text=applied_at or "").grid(row=r, column=4, padx=8)


    # --- actions --------------------------------------------------------
    def mark(self, job_id, applied):
        set_applied(job_id, applied)
        self.refresh()

    def fetch(self):
        self.fetch_btn.state(["disabled"])
        self.status.config(text="Fetching offers...")

        def work():
            new, errors = scrape_all()
            self.after(0, lambda: self._fetch_done(new, errors))

        threading.Thread(target=work, daemon=True).start()

    def _fetch_done(self, new, errors):
        set_meta("last_fetch", dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
        self._show_last_updated()
        self.fetch_btn.state(["!disabled"])
        self.status.config(text=f"{new} new offer(s) added.")
        self.refresh()
        if errors:
            messagebox.showwarning("Some sources failed", "\n".join(errors))

    def add_manual(self):
        win = tk.Toplevel(self)
        win.title("Add offer")
        entries = {}
        for i, label in enumerate(["Company", "Title", "URL"]):
            ttk.Label(win, text=label).grid(row=i, column=0, padx=8, pady=4, sticky="e")
            e = ttk.Entry(win, width=60)
            e.grid(row=i, column=1, padx=8, pady=4)
            entries[label] = e

        def save():
            company, title, url = (entries[k].get().strip() for k in ("Company", "Title", "URL"))
            if not company or not url:
                messagebox.showerror("Missing data", "Company and URL are required.", parent=win)
                return
            if not add_job(company, title, url, "Manual"):
                messagebox.showinfo("Duplicate", "This URL is already in the list.", parent=win)
            win.destroy()
            self.refresh()

        ttk.Button(win, text="Save", command=save).grid(row=3, column=1, sticky="e", padx=8, pady=8)


if __name__ == "__main__":
    App().mainloop()
