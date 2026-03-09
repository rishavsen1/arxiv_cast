# ArxivCast

Fetch arXiv papers by category, store them in SQLite, and generate a **two-host AI podcast** (headlines + dialogue) with configurable style and length. Uses Open Router for the script and Edge TTS (or optional OpenAI TTS) for audio.

Runs as part of the weblogger app (dashboard link at `/intel`) or standalone via CLI.

## Layout

- `core.py` — fetch, DB, matrix HTML, podcast (LLM + TTS), synopsis. All paths under `data/`.
- `routes.py` — Flask blueprint: `/intel`, `/api/arxiv/*`.
- `data/` — generated: `arxiv_history.db`, `arxiv_intel.html`, `arxiv_synopsis.html`. Audio MP3 is written to weblogger `static/audio/daily_briefing.mp3`.

## Quick start

1. **Requirements:** Python 3.9+, `arxiv`, `openai`, `edge_tts`, `pydub`.
   ```bash
   pip install arxiv openai edge-tts pydub
   ```
2. **Secrets:** Copy `arxvicast/.env.example` to `arxvicast/.env` and set `OPENROUTER_KEY` (get one at [openrouter.ai](https://openrouter.ai)).
3. **Run from weblogger:** Start the Flask app; open dashboard and click ArxivCast, or go to `/intel`.
4. **CLI (standalone):**
   ```bash
   python -m arxvicast.core
   ```
   Options: `--categories cs.AI,cs.LG`, `--papers-per-tag 5`, `--date 2025-03-08`, `--style easy`, `--length medium`, `--fetch-only`.

## Migrating from intel-stack

If you had data in `intel-stack/`: copy `intel-stack/.env` to `arxvicast/.env`, and optionally copy `intel-stack/arxiv_history.db` to `arxvicast/data/arxiv_history.db`.

## Files

- `core.py` — main logic (fetch, DB, HTML, podcast).
- `routes.py` — Flask routes for the weblogger app.
- `.env.example` — template for `.env` (never commit `.env`).
- `FEATURES.md` — ideas for academic and general use.

Generated (gitignored): `.env`, `data/*.db`, `data/arxiv_intel.html`, `data/arxiv_synopsis.html`.
