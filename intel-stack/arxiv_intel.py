import arxiv
import sqlite3
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from openai import OpenAI
import asyncio
import edge_tts
import subprocess
import requests

# Load .env from intel-stack directory (safe for cron/cwd)
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# --- CORE CONFIGURATION ---
_INTEL_STACK_DIR = Path(__file__).resolve().parent
DB_PATH = str(_INTEL_STACK_DIR / "arxiv_history.db")
# Generated HTML lives in intel-stack; served on demand by the app.
OUTPUT_HTML = str(_INTEL_STACK_DIR / "arxiv_intel.html")
SYNOPSIS_OUTPUT = str(_INTEL_STACK_DIR / "arxiv_synopsis.html")
# Categories are defined here (intel-stack is the source of truth); /api/arxiv/categories reads this.
CATEGORIES = [
    "cs.LG", "cs.AI", "cs.SY", "cs.RO", "cs.NE", "cs.CE",
    "eess.SY", "eess.SP", "math.OC", "stat.ML", "econ.EM", "physics.soc-ph"
]
PAPERS_PER_TAG = 5

# --- AI CONFIGURATION (key from .env only; never commit .env) ---
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY")
LLM_MODEL = "arcee-ai/trinity-large-preview:free"
AUDIO_OUTPUT = "/home/rishav/weblogger/static/audio/daily_briefing.mp3"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS papers 
                    (id TEXT, category TEXT, title TEXT, url TEXT, date TEXT, abstract TEXT, other_categories TEXT,
                     PRIMARY KEY (id, category))''')
    cursor = conn.execute("PRAGMA table_info(papers)")
    cols = [c[1] for c in cursor.fetchall()]
    if "other_categories" not in cols:
        conn.execute("ALTER TABLE papers ADD COLUMN other_categories TEXT DEFAULT ''")
    # Migrate single-column PK to composite (id, category) so same paper can appear per category
    cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='papers'")
    row = cursor.fetchone()
    if row and row[0] and "PRIMARY KEY (id, category)" not in row[0]:
        try:
            conn.execute("""CREATE TABLE papers_new (
                id TEXT, category TEXT, title TEXT, url TEXT, date TEXT, abstract TEXT, other_categories TEXT,
                PRIMARY KEY (id, category))""")
            conn.execute("""INSERT OR IGNORE INTO papers_new (id, category, title, url, date, abstract, other_categories)
                SELECT id, category, title, url, date, abstract, COALESCE(other_categories, '') FROM papers""")
            conn.execute("DROP TABLE papers")
            conn.execute("ALTER TABLE papers_new RENAME TO papers")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()

# XML namespaces used in arXiv Atom responses
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

def _fetch_by_date_http(category, papers_per_tag, date):
    """
    Fetch papers for a single category and date via direct arXiv API HTTP call.
    Returns list of (entry_id, title, pdf_url, date_str, abstract, other_categories).
    other_categories is comma-separated list of all categories except the primary (for "Secondary tags" column).
    """
    ymd = date.replace("-", "")
    query = f"cat:{category} AND submittedDate:[{ymd}0000 TO {ymd}2359]"
    params = {
        "search_query": query,
        "max_results": papers_per_tag,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    url = "https://export.arxiv.org/api/query"
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    rows = []
    for entry in root.findall(".//atom:entry", _ATOM_NS):
        entry_id = entry.find("atom:id", _ATOM_NS)
        title_el = entry.find("atom:title", _ATOM_NS)
        summary_el = entry.find("atom:summary", _ATOM_NS)
        published_el = entry.find("atom:published", _ATOM_NS)
        link_pdf = None
        for link in entry.findall("atom:link", _ATOM_NS):
            if link.get("title") == "pdf":
                link_pdf = link.get("href")
                break
        primary_el = entry.find("arxiv:primary_category", _ATOM_NS)
        all_cats = [c.get("term") for c in entry.findall("atom:category", _ATOM_NS) if c.get("term")]
        primary_cat = primary_el.get("term", category) if primary_el is not None else (all_cats[0] if all_cats else category)
        other = [t for t in all_cats if t != primary_cat]
        other_categories = ", ".join(sorted(other)) if other else ""
        if entry_id is None or title_el is None:
            continue
        eid = (entry_id.text or "").strip().split("/")[-1]
        title = (title_el.text or "").strip().replace("\n", " ")
        summary = (summary_el.text or "").strip().replace("\n", " ") if summary_el is not None else ""
        published = (published_el.text or "").strip() if published_el is not None else ""
        try:
            dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            date_str = date
        pdf_url = link_pdf or f"https://arxiv.org/pdf/{eid}.pdf"
        rows.append((eid, title, pdf_url, date_str, summary, other_categories))
    return rows

def fetch_and_store(categories=None, papers_per_tag=None, date=None):
    """
    Fetch papers from arXiv and store in DB.
    If date is provided (YYYY-MM-DD), only papers submitted on that day (GMT) are fetched
    via direct API HTTP call (reliable date filter). Otherwise uses arxiv library for latest papers.
    """
    categories = categories or CATEGORIES
    papers_per_tag = papers_per_tag if papers_per_tag is not None else PAPERS_PER_TAG
    conn = sqlite3.connect(DB_PATH)
    total_found = 0
    new_added = 0
    if date:
        # Date-filtered fetch: use direct HTTP so the query is sent exactly as arXiv expects
        for cat in categories:
            print(f"Finding papers in category: {cat} for date {date}")
            try:
                rows = _fetch_by_date_http(cat, papers_per_tag, date)
                for row in rows:
                    total_found += 1
                    # (id, category, title, url, date, abstract, other_categories); composite PK allows same paper under multiple categories
                    conn.execute(
                        "INSERT OR IGNORE INTO papers (id, category, title, url, date, abstract, other_categories) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (row[0], cat, row[1], row[2], row[3], row[4], row[5]),
                    )
                    new_added += conn.execute("SELECT changes()").fetchone()[0]
            except requests.RequestException as e:
                print(f"  Request failed for {cat}: {e}")
    else:
        # No date: use arxiv library (newest papers)
        client = arxiv.Client()
        for cat in categories:
            print(f"Finding papers in category: {cat}")
            search = arxiv.Search(
                query=f"cat:{cat}",
                max_results=papers_per_tag,
                sort_by=arxiv.SortCriterion.SubmittedDate,
            )
            for result in client.results(search):
                total_found += 1
                other = ""
                if hasattr(result, "categories") and result.categories:
                    primary = getattr(result, "primary_category", None) or (result.categories[0] if result.categories else None)
                    other = ", ".join(sorted(c for c in result.categories if c != primary)) if primary else ", ".join(sorted(result.categories))
                conn.execute(
                    "INSERT OR IGNORE INTO papers (id, category, title, url, date, abstract, other_categories) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (result.entry_id, cat, result.title, result.pdf_url, result.published.strftime("%Y-%m-%d"), result.summary, other),
                )
                new_added += conn.execute("SELECT changes()").fetchone()[0]
    conn.commit()
    conn.close()
    print(f"\n>> FETCH COMPLETE: Found {total_found} total papers.")
    print(f">> DATABASE: Added {new_added} new papers to the archive.\n")
    return {"total_found": total_found, "new_added": new_added}

def _build_matrix_table(rows, empty_message):
    """Build the matrix table HTML from rows. New schema: (id, category, title, url, date, abstract, other_categories)."""
    if not rows:
        return empty_message
    # New schema has 7 cols; old (pre-migration) has 6: (id, title, url, date, category, abstract)
    new_schema = len(rows[0]) >= 7
    html = '<div class="overflow-x-auto"><table class="w-full text-left border-collapse">'
    current_date = ""
    for row in rows:
        if new_schema:
            tag, date_val, title, url, abstract, other_cats = row[1], row[4], row[2], row[3], row[5], (row[6] or "").strip()
        else:
            tag, date_val, title, url, abstract, other_cats = row[4], row[3], row[1], row[2], row[5], ""
        tag_class = tag.replace('.', '-')
        if date_val != current_date:
            current_date = date_val
            html += f'''
            <thead>
                <tr class="bg-slate-800/80">
                    <th colspan="4" class="p-3 text-sky-400 uppercase text-xs font-bold tracking-[0.2em] border-b border-slate-700">
                        DATA_LOG: {current_date}
                    </th>
                </tr>
                <tr class="text-slate-500 text-[10px] uppercase border-b border-slate-700 bg-slate-900">
                    <th class="p-4 w-32">Domain</th>
                    <th class="p-4 w-28">Other tags</th>
                    <th class="p-4 w-1/4">Title / Source</th>
                    <th class="p-4">Abstract</th>
                </tr>
            </thead>
            <tbody>'''
        html += f'''
        <tr class="border-b border-slate-800/50 hover:bg-sky-500/5 transition-colors group">
            <td class="p-4 align-top">
                <span class="tag-pill tag-{tag_class}">{tag}</span>
            </td>
            <td class="p-4 align-top text-slate-500 text-xs">'''
        if other_cats:
            for oc in other_cats.split(", "):
                oc_class = oc.replace(".", "-")
                html += f'<span class="tag-pill tag-{oc_class} mr-1">{oc}</span>'
        html += f'''</td>
            <td class="p-4 align-top">
                <a href="{url}" target="_blank" class="text font-semibold text-slate-200 group-hover:text-sky-400 block leading-snug">
                    {title}
                </a>
            </td>
            <td class="p-4 align-top text-slate-400 text leading-relaxed">
                <div class="line-clamp-3 hover:line-clamp-none transition-all duration-300">
                    {abstract}
                </div>
            </td>
        </tr>'''
    html += '</tbody></table></div>'
    return html


def get_matrix_html(limit=120, date=None, categories=None, papers_per_tag=None):
    """
    Return matrix HTML string filtered by date and categories.
    - date=None: use latest date in DB only.
    - categories=None: all categories; else list of category strings (e.g. ['cs.AI', 'cs.LG']).
    - papers_per_tag: if set, show at most this many papers per category (keeps display consistent with fetch).
    """
    conn = sqlite3.connect(DB_PATH)
    empty_msg = '<div class="p-6 text-slate-500 text-sm">No papers match. Run <strong>Search &amp; Populate</strong> or change filters.</div>'
    if date:
        target_date = date
        where = "date = ?"
        params = [date]
    else:
        cursor = conn.execute("SELECT MAX(date) FROM papers")
        target_date = cursor.fetchone()[0]
        if not target_date:
            conn.close()
            return empty_msg
        where = "date = ?"
        params = [target_date]
    if categories:
        placeholders = ",".join("?" * len(categories))
        where += f" AND category IN ({placeholders})"
        params.extend(categories)
    # Fetch all matching rows (up to a generous cap), then apply per-category limit in Python
    cursor = conn.execute(
        f"SELECT * FROM papers WHERE {where} ORDER BY category ASC, id ASC",
        params
    )
    rows = cursor.fetchall()
    conn.close()
    if papers_per_tag is not None and papers_per_tag > 0 and rows:
        from collections import OrderedDict
        by_cat = OrderedDict()
        cat_idx = 1 if len(rows[0]) >= 7 else 4  # new: (id, category, ...); old: (id, title, url, date, category, abstract)
        for row in rows:
            cat = row[cat_idx]
            if cat not in by_cat:
                by_cat[cat] = []
            if len(by_cat[cat]) < papers_per_tag:
                by_cat[cat].append(row)
        rows = []
        for cat in by_cat:
            rows.extend(by_cat[cat])
    else:
        rows = rows[:limit]
    return _build_matrix_table(rows, empty_msg)


def generate_html(limit=120, date=None, papers_per_tag=None):
    """Generate matrix HTML and write to OUTPUT_HTML (used after fetch). Uses latest date when date is None."""
    html = get_matrix_html(limit=limit, date=date, categories=None, papers_per_tag=papers_per_tag)
    if not html or html.startswith("<div class=\"p-6"):
        empty = '<div class="p-6 text-slate-500 text-sm">No papers in the database for this date. Run <strong>Search &amp; Populate</strong> to fetch from arXiv (newest submissions will be stored).</div>'
        with open(OUTPUT_HTML, "w") as f:
            f.write(empty)
        return
    with open(OUTPUT_HTML, "w") as f:
        f.write(html)

# Podcast style and length presets
PODCAST_STYLES = {
    "easy": "Easy to Understand: use plain language, minimal jargon, and simple analogies. Explain concepts as if to a curious non-expert.",
    "deep": "DeepDive: go into technical depth—methods, assumptions, and implications. Suitable for researchers and practitioners.",
    "critique": "Critique: take a critical lens. Discuss limitations, trade-offs, and what the work does not address.",
    "debate": "Debate: two hosts take different angles or gently disagree (e.g. one optimistic, one cautious) and bounce ideas off each other.",
}
LENGTH_WORDS = {"short": "300–500", "medium": "700–1000", "long": "1200–1800"}


def generate_podcast_and_synopsis(style="easy", length="medium", custom_style=None, date=None):
    style_key = style.lower() if isinstance(style, str) else "easy"
    length_key = length.lower() if isinstance(length, str) else "medium"
    word_target = LENGTH_WORDS.get(length_key, LENGTH_WORDS["medium"])
    style_instruction = custom_style.strip() if custom_style and custom_style.strip() else PODCAST_STYLES.get(style_key, PODCAST_STYLES["easy"])

    print(f"Initializing AI Analysis using {LLM_MODEL} (style={style_key}, length={length_key})...")
    conn = sqlite3.connect(DB_PATH)
    if date:
        target_date = date
        cursor = conn.execute("SELECT COUNT(1) FROM papers WHERE date = ?", (date,))
        if cursor.fetchone()[0] == 0:
            conn.close()
            print(f"No papers in database for date {date}.")
            return None
    else:
        cursor = conn.execute("SELECT MAX(date) FROM papers")
        target_date = cursor.fetchone()[0]
        if not target_date:
            print("Database is empty. No papers to synthesize.")
            conn.close()
            return None
    print(f"Targeting papers from batch: {target_date}")
    cursor = conn.execute("SELECT title, category, abstract FROM papers WHERE date = ?", (target_date,))
    papers = cursor.fetchall()
    conn.close()

    if not OPENROUTER_KEY:
        raise RuntimeError(
            "OPENROUTER_KEY not set. Add it to intel-stack/.env (see .env.example). "
            "Do not commit .env to git."
        )
    intel_data = "\n\n".join([f"Category: {p[1]} | Title: {p[0]} | Abstract: {p[2]}" for p in papers])
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
    prompt = f"""You are writing a script for "ArxivCast", a two-host podcast about arXiv papers. The hosts are ALEX and SAM. They speak in turn; keep the conversation natural and concise.

RULES:
- Write the script as a two-person dialogue. Every line must start with exactly "ALEX: " or "SAM: " (capital letters, then a space), then the spoken text. No other formatting (no asterisks, no sound-effect brackets).
- First, write a SHORT HEADLINES ROUND: in a connected, flowing way, each host gives a one-sentence TLDR for a subset of the papers (split between them), so the listener gets a quick round of "what's in this episode" before you go deeper.
- Then continue with the main dialogue, covering the papers in more detail according to the style below.
- Target total length: approximately {word_target} words.
- Style: {style_instruction}

PAPERS:
{intel_data}

Write the full script (headlines round first, then main dialogue) using only "ALEX: " and "SAM: " at the start of each line."""

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        script_text = response.choices[0].message.content
    except Exception as e:
        print(f"LLM Generation Failed: {e}")
        return None

    # Build HTML with speaker styling (ALEX: / SAM:)
    html_parts = []
    for block in script_text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        for line in block.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.upper().startswith("ALEX:"):
                rest = line[5:].strip()
                html_parts.append(f'<p class="mb-2 text-slate-300 leading-relaxed"><span class="font-bold text-sky-400">Alex:</span> {rest}</p>')
            elif line.upper().startswith("SAM:"):
                rest = line[4:].strip()
                html_parts.append(f'<p class="mb-2 text-slate-300 leading-relaxed"><span class="font-bold text-amber-400">Sam:</span> {rest}</p>')
            else:
                html_parts.append(f'<p class="mb-2 text-slate-300 leading-relaxed">{line}</p>')
    with open(SYNOPSIS_OUTPUT, "w") as f:
        f.write("\n".join(html_parts))

    # TTS: strip speaker labels so one voice reads naturally
    tts_lines = []
    for line in script_text.split("\n"):
        line = line.strip()
        if line.upper().startswith("ALEX:"):
            tts_lines.append(line[5:].strip())
        elif line.upper().startswith("SAM:"):
            tts_lines.append(line[4:].strip())
        elif line:
            tts_lines.append(line)
    tts_text = " ".join(tts_lines)

    print("Synthesizing Audio Broadcast...")
    communicate = edge_tts.Communicate(tts_text, "en-US-ChristopherNeural")
    asyncio.run(communicate.save(AUDIO_OUTPUT))
    print("Local Podcast Ready.")

    today = datetime.now().strftime("%Y-%m-%d")
    archive_filename = f"briefing_{today}.mp3"
    gdrive_path = f"gdrive:ArxivCast_Audio/{archive_filename}"
    print(f">> Executing Rclone transfer to {gdrive_path}...")
    try:
        subprocess.run(["rclone", "copyto", AUDIO_OUTPUT, gdrive_path], check=True)
        print(">> Cloud Backup Complete!")
    except subprocess.CalledProcessError as e:
        print(f">> ERROR: Rclone upload failed. {e}")
    return {"script_length": len(script_text), "date": target_date}

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="ArxivCast: fetch arXiv papers and generate podcast")
    p.add_argument("--fetch-only", action="store_true", help="Only fetch and store papers")
    p.add_argument("--categories", type=str, default=None, help="Comma-separated categories (e.g. cs.AI,cs.LG)")
    p.add_argument("--papers-per-tag", type=int, default=None, help="Max papers per category")
    p.add_argument("--date", type=str, default=None, help="Filter view/podcast to this date (YYYY-MM-DD); default today")
    p.add_argument("--limit", type=int, default=120, help="Max rows in generated HTML table")
    p.add_argument("--style", choices=list(PODCAST_STYLES) + ["custom"], default="easy")
    p.add_argument("--length", choices=list(LENGTH_WORDS), default="medium")
    p.add_argument("--custom-style", type=str, default=None)
    args = p.parse_args()
    view_date = args.date or datetime.now().strftime("%Y-%m-%d")
    init_db()
    cats = [c.strip() for c in args.categories.split(",")] if args.categories else None
    fetch_and_store(categories=cats, papers_per_tag=args.papers_per_tag, date=view_date)
    if not args.fetch_only:
        generate_html(limit=args.limit, date=view_date)
        generate_podcast_and_synopsis(style=args.style, length=args.length, custom_style=args.custom_style, date=view_date)
