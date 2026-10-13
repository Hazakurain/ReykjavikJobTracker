# Reykjavik Job Tracker

A small desktop app (Python + Tkinter) that gathers retail, supermarket and restaurant job offers in Reykjavik, Iceland, into one table, and lets you track which ones you have applied to.

It is meant for **personal use**: you click "Fetch new offers", the app collects links from several Icelandic employers' career pages, and you keep track of your applications locally on your own computer.

## What the app does

| Column | Meaning |
|---|---|
| **Company** | The employer (e.g. Krónan, Bónus, Hagkaup, Domino's Iceland...) |
| **Source** | The website the offer was found on (e.g. `kronan.is`, `alfred.is`, `jobs.50skills.com`, or `Manual`) |
| **Offer** | Clickable link to the offer, opens in your web browser |
| **Applied?** | `Yes` / `No` buttons. Clicking `Yes` records the date and time |
| **Date applied** | Filled in automatically when you click `Yes` |

Buttons in the top bar:

- **Fetch new offers**: visits every source listed in the script and adds the offers it has not seen before. A small italic "Last updated" line above the button shows the date and time of the last fetch (it is remembered between launches).
- **Add offer manually**: lets you type in a company, a title and a link yourself (useful for offers found elsewhere).

Everything is stored locally in a file called `jobs.db`. Nothing is sent anywhere.

---

## Requirements

- **Python 3.9 or newer** (check with `python --version`).
- An internet connection when you click "Fetch new offers".
- **Linux only**: Tkinter is sometimes packaged separately. If you get `No module named tkinter`, install it with `sudo apt install python3-tk` (Debian/Ubuntu). On Windows and macOS it comes with the official Python installer.

---

## Installation: everything that gets installed, and why

The app uses two kinds of things: **built-in Python modules** (nothing to install) and **third-party packages** (installed with `pip`). Here is the complete list, with the reason for each one.

### 1. Required packages (always install these)

```bash
pip install requests beautifulsoup4
```

| Package | What it is | Why the app needs it |
|---|---|---|
| **`requests`** | A library to download web pages over HTTP. | The app has to download the career pages of Krónan, Alfred.is, BYKO, etc. to read the offers they list. Python can do this without it, but `requests` is much simpler and more reliable (timeouts, redirects, error messages). |
| **`beautifulsoup4`** (imported as `bs4`) | A library to read HTML. | A downloaded web page is a big block of HTML text. `beautifulsoup4` lets the app find every link (`<a href="...">`) on the page and read its text, so it can pick out the job offers. |

### 2. Optional package (install only if you want the JavaScript-based sites)

```bash
pip install playwright
playwright install chromium
```

| Package | What it is | Why the app needs it |
|---|---|---|
| **`playwright`** | A library that controls a real (invisible) web browser from Python. | Some sites (Bónus, Hagkaup, Samkaup, Domino's Iceland) publish their jobs on the **50skills** platform. Those pages arrive almost empty and the job list is built afterwards by JavaScript running in the browser. `requests` only downloads the empty shell, so it would see **zero offers**. Playwright opens the page in a real browser, waits until the list is displayed, then hands the finished HTML to the app. |
| **Chromium** (installed by the command `playwright install chromium`) | The open-source web browser that Playwright drives. | Playwright is only the remote control; it needs an actual browser to control. This second command downloads a private copy of Chromium (roughly 150 MB or more) that is used **only by Playwright** and does not touch your normal browser. It runs "headless", meaning without a visible window. |

**If you skip Playwright:** the app still works. Sources that need it are skipped, and the app shows a message saying so. The "general application" lines for Bónus and Hagkaup are still added to the table, because they are built into the script, and sources that do not need JavaScript (Krónan, and Alfred.is, BYKO, ELKO if they work as plain pages) keep working.

### 3. Built-in modules (nothing to install)

These ship with Python. They are listed so you know exactly what the code uses.

| Module | Used for |
|---|---|
| `tkinter` | The desktop window, the table and the buttons. |
| `sqlite3` | The local database file `jobs.db` (see below). |
| `threading` | Runs "Fetch new offers" in the background so the window does not freeze while pages download. |
| `webbrowser` | Opens an offer link in your default browser when you click it. |
| `datetime` | Records the date and time when you mark an offer as applied. |
| `re` | Regular expressions, used to keep only the links that look like job offers. |
| `urllib.parse` | Builds full web addresses from relative ones and extracts the site name for the Source column. |
| `pathlib`, `os` | Locating `jobs.db` next to the script. |

### Recommended: use a virtual environment

A virtual environment keeps these packages separate from the rest of your computer, so you can delete them cleanly later.

```bash
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install requests beautifulsoup4
# optional:
pip install playwright
playwright install chromium
```

---

## Running the app

From the folder containing the script:

```bash
python job_scrap.py
```

A window opens with the table. On first launch the table is empty: click **Fetch new offers**.

---

## Where the data is stored

The app creates a file `jobs.db` in the same folder as the script. It is a **SQLite** database: a real SQL database, but contained in a single file, with no server to install or run.

- Data persists between launches.
- To back it up, copy the file. To start from scratch, delete it (it will be recreated empty).
- If you move the script, move `jobs.db` with it, otherwise the app starts with an empty database.
- You can open it with a free tool such as [DB Browser for SQLite](https://sqlitebrowser.org/) to view, edit or export it to CSV.

The main table is called `jobs` with the columns `id`, `company`, `title`, `url` (unique, so the same offer is never added twice), `applied_at`, and `source`. A second tiny table, `meta`, stores the date and time of the last fetch for the "Last updated" label.

If you already have a `jobs.db` from an earlier version without the `source` column, it is upgraded automatically at startup.

---

## Sources currently configured

| Source | Method | Notes |
|---|---|---|
| Alfred.is | plain HTML | Iceland's largest job board. Filtered with retail keywords. Not verified: see Troubleshooting. |
| Krónan | plain HTML | Career page lists real offers. |
| Bónus | built-in entry + Playwright | General application is always added. Individual offers need Playwright. |
| Hagkaup | built-in entry + Playwright | Same as Bónus. |
| Samkaup (Nettó, Kjörbúðin, Krambúðin) | Playwright | |
| Domino's Iceland | Playwright | The Icelandic franchise, not another country's. |
| BYKO | plain HTML | Not verified: see Troubleshooting. |
| ELKO / Festi group | plain HTML | Not verified: see Troubleshooting. |

### Adding your own source

Each source is a small dictionary in the `SOURCES` list near the top of `reykjavik_job_tracker.py`:

```python
{"name": "Krónan", "type": "html", "url": "https://kronan.is/saekja-um-starf",
 "href_regex": r"jobs\.50skills\.com/kronan/\d+"},
```

| Field | Meaning |
|---|---|
| `name` | Shown in the **Company** column. |
| `type` | `"html"` (plain download), `"js"` (rendered with Playwright), or `"static"` (a fixed entry, nothing is downloaded; needs a `title` field). |
| `url` | The page that lists the offers. |
| `href_regex` | A pattern. Only links whose address matches it are kept. |
| `filter` | Optional. `True` keeps only links whose text contains a retail keyword from the `KEYWORDS` list. Useful for general job boards, not for single-company sites. |

Many Icelandic employers publish on 50skills with addresses like `https://jobs.50skills.com/<company>/is`, so adding one is often just a matter of copying a line and changing the name.

---

## Troubleshooting

**"Fetch new offers" adds nothing for a source.**
Websites change. To fix a source: open its page in your browser, right-click an offer link, choose *Inspect*, and look at the link address. Then adjust `href_regex` so it matches. If the page shows nothing in `requests` but looks fine in your browser, change its `type` from `"html"` to `"js"` (this requires Playwright).

**`needs Playwright: pip install playwright && playwright install chromium`**
You have not installed the optional package (or the Chromium download). See the Optional package section above.

**`No module named tkinter`** (Linux)
`sudo apt install python3-tk`

**`No module named requests` / `bs4`**
Run `pip install requests beautifulsoup4`, and make sure your virtual environment is activated.

---

## Limitations and responsible use

- The scraping rules (`href_regex`) depend on how each website is built. Some of them were written from public page content and have **not been tested against the live sites**, so expect to adjust a few.
- Be considerate: the app only loads each source page once per click on "Fetch". Do not schedule it to run every few seconds.
- Check each website's terms of use. This tool is intended for personal job hunting, not for republishing or mass-collecting data.
- Only offers are collected. The app never submits applications for you: you apply on the employer's own page.

## Project files

| File | Purpose |
|---|---|
| `reykjavik_job_tracker.py` | The whole application. |
| `jobs.db` | Created on first run: your local data. Not part of the repository (add it to `.gitignore`). |
