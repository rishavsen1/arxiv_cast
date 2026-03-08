# ArxivCast (intel-stack)

Fetch arXiv papers by category, store them in SQLite, and generate a **two-host AI podcast** (headlines + dialogue) with configurable style and length. Uses Open Router for the script and Edge TTS for audio.

Runs standalone: clone this repo, add your keys, run the script. Can also be used inside a weblogger dashboard.

## Quick start

1. **Requirements:** Python 3.9+, `arxiv`, `openai`, `edge_tts`.
   ```bash
   pip install arxiv openai edge-tts
   ```
2. **Secrets:** Copy `.env.example` to `.env` and set `OPENROUTER_KEY` (get one at [openrouter.ai](https://openrouter.ai)).
3. **Run:**
   ```bash
   python arxiv_intel.py
   ```
   Options: `--categories cs.AI,cs.LG`, `--papers-per-tag 5`, `--date 2025-03-08`, `--style easy`, `--length medium`, `--fetch-only`.

## What it does

- Fetches newest papers per category from arXiv and stores them in `arxiv_history.db`.
- Writes a papers table to `arxiv_intel.html` and (with an Open Router key) generates a dialogue script + synopsis HTML + MP3. Optional rclone upload to a cloud folder.

When used inside weblogger, the dashboard serves the HTML and provides a UI for categories, date, style, and length.

## Files

- `arxiv_intel.py` — main script (fetch, DB, HTML, podcast).
- `.env.example` — template for `.env` (never commit `.env`).
- `FEATURES.md` — ideas for academic and general use.

Generated (gitignored): `.env`, `*.db`, `arxiv_intel.html`, `arxiv_synopsis.html`.
