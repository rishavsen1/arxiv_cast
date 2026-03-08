import arxiv
import sqlite3
import os
from datetime import datetime
from pathlib import Path
from openai import OpenAI
import asyncio
import edge_tts
import subprocess

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
                    (id TEXT PRIMARY KEY, title TEXT, url TEXT, date TEXT, category TEXT, abstract TEXT)''')
    conn.close()

def fetch_and_store(categories=None, papers_per_tag=None):
    categories = categories or CATEGORIES
    papers_per_tag = papers_per_tag if papers_per_tag is not None else PAPERS_PER_TAG
    client = arxiv.Client()
    conn = sqlite3.connect(DB_PATH)
    total_found = 0
    new_added = 0
    for cat in categories:
        print(f"Finding papers in category: {cat}")
        search = arxiv.Search(
            query=f"cat:{cat}",
            max_results=papers_per_tag,
            sort_by=arxiv.SortCriterion.SubmittedDate
        )
        for result in client.results(search):
            total_found += 1
            try:
                conn.execute("INSERT INTO papers VALUES (?, ?, ?, ?, ?, ?)",
                             (result.entry_id, result.title, result.pdf_url,
                              result.published.strftime("%Y-%m-%d"),
                              result.primary_category, result.summary))
                new_added += 1
            except sqlite3.IntegrityError:
                pass
    conn.commit()
    conn.close()
    print(f"\n>> FETCH COMPLETE: Found {total_found} total papers.")
    print(f">> DATABASE: Added {new_added} new papers to the archive.\n")
    return {"total_found": total_found, "new_added": new_added}

def generate_html(limit=120, date=None):
    conn = sqlite3.connect(DB_PATH)
    if date:
        cursor = conn.execute(
            "SELECT * FROM papers WHERE date = ? ORDER BY category ASC LIMIT ?",
            (date, limit)
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM papers ORDER BY date DESC, category ASC LIMIT ?",
            (limit,)
        )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        html = f'<div class="p-6 text-slate-500 text-sm">No papers in the database for this date. Run <strong>Search &amp; Populate</strong> to fetch from arXiv (newest submissions will be stored).</div>'
        with open(OUTPUT_HTML, "w") as f:
            f.write(html)
        return

    html = '<div class="overflow-x-auto"><table class="w-full text-left border-collapse">'
    current_date = ""

    for row in rows:
        tag = row[4]
        tag_class = tag.replace('.', '-')
        
        if row[3] != current_date:
            current_date = row[3]
            html += f'''
            <thead>
                <tr class="bg-slate-800/80">
                    <th colspan="3" class="p-3 text-sky-400 uppercase text-xs font-bold tracking-[0.2em] border-b border-slate-700">
                        DATA_LOG: {current_date}
                    </th>
                </tr>
                <tr class="text-slate-500 text-[10px] uppercase border-b border-slate-700 bg-slate-900">
                    <th class="p-4 w-32">Domain</th>
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
            <td class="p-4 align-top">
                <a href="{row[2]}" target="_blank" class="text font-semibold text-slate-200 group-hover:text-sky-400 block leading-snug">
                    {row[1]}
                </a>
            </td>
            <td class="p-4 align-top text-slate-400 text leading-relaxed">
                <div class="line-clamp-3 hover:line-clamp-none transition-all duration-300">
                    {row[5]}
                </div>
            </td>
        </tr>'''
    
    html += '</tbody></table></div>'
    with open(OUTPUT_HTML, "w") as f:
        f.write(html)

# Podcast style and length presets
PODCAST_STYLES = {
    "easy": "Easy to Understand: use plain language, minimal jargon, and simple analogies. Explain concepts as if to a curious non-expert.",
    "deep": "DeepDive: go into technical depth—methods, assumptions, and implications. Suitable for researchers and practitioners.",
    "brief": "Brief: keep it short. Headlines and one-sentence takeaways only; minimal commentary.",
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
    fetch_and_store(categories=cats, papers_per_tag=args.papers_per_tag)
    if not args.fetch_only:
        generate_html(limit=args.limit, date=view_date)
        generate_podcast_and_synopsis(style=args.style, length=args.length, custom_style=args.custom_style, date=view_date)
