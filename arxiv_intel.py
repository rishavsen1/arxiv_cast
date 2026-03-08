import arxiv
import sqlite3
import os
from datetime import datetime
from openai import OpenAI
import asyncio
import edge_tts
import subprocess

# --- CORE CONFIGURATION ---
DB_PATH = "/home/rishav/weblogger/intel-stack/arxiv_history.db"
OUTPUT_HTML = "/home/rishav/weblogger/templates/arxiv_intel.html"
CATEGORIES = [
    "cs.LG", "cs.AI", "cs.SY", "cs.RO", "cs.NE", "cs.CE",
    "eess.SY", "eess.SP", "math.OC", "stat.ML", "econ.EM", "physics.soc-ph"
]
PAPERS_PER_TAG = 5

# --- AI CONFIGURATION ---
OPENROUTER_KEY = "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"
LLM_MODEL = "arcee-ai/trinity-large-preview:free" 
AUDIO_OUTPUT = "/home/rishav/weblogger/static/audio/daily_briefing.mp3"
SYNOPSIS_OUTPUT = "/home/rishav/weblogger/templates/arxiv_synopsis.html"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS papers 
                    (id TEXT PRIMARY KEY, title TEXT, url TEXT, date TEXT, category TEXT, abstract TEXT)''')
    conn.close()

def fetch_and_store():
    client = arxiv.Client()
    conn = sqlite3.connect(DB_PATH)
    
    total_found = 0
    new_added = 0
    
    for cat in CATEGORIES:
        print(f"Finding papers in category: {cat}") 
        search = arxiv.Search(
            query=f"cat:{cat}",
            max_results=PAPERS_PER_TAG,
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
    
    # Print the requested statistics
    print(f"\n>> FETCH COMPLETE: Found {total_found} total papers.")
    print(f">> DATABASE: Added {new_added} new papers to the archive.\n")

def generate_html():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT * FROM papers ORDER BY date DESC, category ASC LIMIT 120")
    rows = cursor.fetchall()
    
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
    conn.close()

def generate_podcast_and_synopsis():
    print(f"Initializing AI Analysis using {LLM_MODEL}...")
    conn = sqlite3.connect(DB_PATH)
    
    # NEW LOGIC: Find the most recent date that actually exists in the database
    cursor = conn.execute("SELECT MAX(date) FROM papers")
    latest_date = cursor.fetchone()[0]

    if not latest_date:
        print("Database is empty. No papers to synthesize.")
        conn.close()
        return

    print(f"Targeting papers from the most recent batch: {latest_date}")
    cursor = conn.execute("SELECT title, category, abstract FROM papers WHERE date = ?", (latest_date,))
    papers = cursor.fetchall()
    conn.close()

    intel_data = "\n\n".join([f"Category: {p[1]} | Title: {p[0]} | Abstract: {p[2]}" for p in papers])
    
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
    prompt = f"""
    You are the AI host of the 'ServerDex Intelligence Podcast'. 
    Review the following academic papers from arXiv and write a conversational 
    podcast script summarizing the most exciting breakthroughs.
    Do not use asterisks or sound effect brackets. Write it exactly as it should be spoken.
    Format the output in clear paragraphs.
    
    Papers:
    {intel_data}
    """

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        script_text = response.choices[0].message.content
    except Exception as e:
        print(f"LLM Generation Failed: {e}")
        return

    formatted_html = "".join([f'<p class="mb-4 text-slate-300 leading-relaxed">{p}</p>' for p in script_text.split('\n\n') if p.strip()])
    with open(SYNOPSIS_OUTPUT, "w") as f:
        f.write(formatted_html)

    print("Synthesizing Audio Broadcast...")
    communicate = edge_tts.Communicate(script_text, "en-US-ChristopherNeural") 
    asyncio.run(communicate.save(AUDIO_OUTPUT))
    print("Local Podcast Ready.")

    # --- CLOUD ARCHIVE PIPELINE ---
    today = datetime.now().strftime("%Y-%m-%d") # Still name the file based on the day it was generated
    archive_filename = f"briefing_{today}.mp3"
    gdrive_path = f"gdrive:ServerDex_Audio/{archive_filename}"
    
    print(f">> Executing Rclone transfer to {gdrive_path}...")
    try:
        subprocess.run(["rclone", "copyto", AUDIO_OUTPUT, gdrive_path], check=True)
        print(">> Cloud Backup Complete!")
    except subprocess.CalledProcessError as e:
        print(f">> ERROR: Rclone upload failed. {e}")

if __name__ == "__main__":
    init_db()
    fetch_and_store()
    generate_html()
    generate_podcast_and_synopsis()
