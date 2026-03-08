# ArxivCast — Intelligence Briefing: Full Description

This document describes exactly how the arXiv paper viewer and podcast generation work, including backend and frontend.

---

## 1. What the feature does (user perspective)

**ArxivCast — Intelligence Briefing** is a single page under `/intel` that lets you:

1. **View arXiv papers** in a filterable table (the “data matrix”): choose categories (arXiv-style: topic → subject), optionally a specific date or “latest,” set “papers per tag,” then **Search & Populate** to fetch from arXiv and show papers. Each row has a **Use** checkbox for podcast selection, **Domain** (category), **Other tags** (secondary arXiv categories), **Title/Source** (link), and **Abstract**.
2. **Clear the table** with **Clear table** (confirmation required): deletes all rows in the papers DB; you can repopulate with Search & Populate.
3. **Generate a two-host audio podcast** from the sidebar: choose **Style** (Easy, DeepDive, Critique, Debate, Custom) and **Length** (Short/Medium/Long), then **Generate podcast**. The podcast uses only the papers that are currently **checked** in the matrix (or all visible rows if none are checked). You get an **interactive two-voice dialogue** (Alex + Sam, Notebook LM style) and a **transcript** in the sidebar; the audio file is played in the page and can be backed up to Google Drive via rclone.

The page has **no subtabs**: one layout with the matrix as main content and the audio controls + transcript + archive list in a **sidebar** on the right (or below on small screens).

---

## 2. Frontend (templates/intel.html)

- **Route**: Rendered by Flask at `/intel`; the template is `intel.html`.
- **Layout**:
  - **Header**: Title “ArxivCast — Intelligence Briefing” and “Return to Dashboard” link.
  - **Main area (flex-1)**:
    - **Filters**: Categories (two-layer checkboxes: topic → subject, from `/api/arxiv/categories` tree), Date (toggle “Use specific date” + date picker, max = today), Papers per tag (number), **Search & Populate**, **Clear table**.
    - **Color legend**: Tag pills for cs.LG, cs.AI, etc.
    - **Matrix container** (`#matrix-container`): Receives HTML from `/api/arxiv/matrix-html` (see below). Table has columns: Use (checkbox), Domain, Other tags, Title/Source, Abstract; each row has `data-paper-id` and checkbox `name="matrix-paper"` for podcast selection.
  - **Sidebar (aside, lg:w-96)**:
    - **Audio** section: Style dropdown, Length dropdown, **Generate podcast** button, status text, `<audio>` player (source: `static/audio/daily_briefing.mp3`).
    - **GDrive Vault**: List of archive filenames from `/api/archive` (buttons to play).
    - **Transcript**: Content from `/api/arxiv/synopsis-html` (refreshed after podcast generation).

- **JavaScript behavior**:
  - **Categories**: On load, `GET /api/arxiv/categories` → build two-layer checkboxes (topic → subject); change on category/date/papers-per-tag triggers `loadMatrixHtml()`.
  - **loadMatrixHtml()**: Reads selected categories (checked `arxiv-category`), date (use-date checkbox + `arxiv-date` or `'latest'`), and papers-per-tag. Calls `GET /api/arxiv/matrix-html?categories=...&date=...&papers_per_tag=...` and injects the returned HTML into `#matrix-container`.
  - **Search & Populate**: POST `/api/arxiv/fetch` with `categories`, `papers_per_tag`, `date` (null = latest). On success, calls `loadMatrixHtml()` and shows “Added N new papers…”
  - **Clear table**: Confirm → POST `/api/arxiv/clear` → on success replace matrix content with placeholder and show “Table cleared.”
  - **Generate podcast**: Reads style, length, custom_style; builds `paper_ids` from checked `#matrix-container input[name=matrix-paper]:checked`, or from all `#matrix-container tr[data-paper-id]` if none checked. POST `/api/arxiv/podcast` with `style`, `length`, `custom_style`, `date` (same as matrix: specific or null), `paper_ids`. On success, calls `loadSynopsis()` and `podcast-player.load()`.
  - **loadSynopsis()**: GET `/api/arxiv/synopsis-html` → inject HTML into `#synopsis-container`.
  - **Archive list**: On load, GET `/api/archive` → render list of play buttons for each filename.

- **Styling**: Tailwind; dark theme (slate/sky/amber); tag pills per category; spinner for loading states.

---

## 3. Backend — Flask app (app.py)

- **Routes**:
  - `GET /intel`: Serves `intel.html`.
  - `GET /api/arxiv/categories`: Returns `{ "categories": [...], "tree": { "cs": ["AI","LG",...], ... } }` from the intel-stack module (or fallback list/tree if module fails).
  - `GET /api/arxiv/matrix-html`: Query params `categories` (comma-separated), `date` (`"latest"` or YYYY-MM-DD), `papers_per_tag` (integer). If any is provided, calls `arxiv_intel.get_matrix_html(..., categories=..., date=..., papers_per_tag=...)` and returns that HTML. Otherwise serves the static file `intel-stack/arxiv_intel.html` if it exists, else a placeholder.
  - `GET /api/arxiv/synopsis-html`: Serves `intel-stack/arxiv_synopsis.html` if present, else placeholder.
  - `POST /api/arxiv/clear`: Calls `arxiv_intel.clear_papers()`; returns `{ "ok": true }` or error.
  - `POST /api/arxiv/fetch`: JSON body: `categories`, `papers_per_tag`, `date`, `limit`. Validates date (no future); calls `arxiv_intel.init_db()`, `fetch_and_store(...)`, `generate_html(..., papers_per_tag=...)`; returns `{ "ok": true, "total_found", "new_added" }` or error.
  - `POST /api/arxiv/podcast`: JSON body: `style`, `length`, `custom_style`, `date`, `paper_ids` (optional list). Normalizes `paper_ids`; calls `arxiv_intel.generate_podcast_and_synopsis(..., paper_ids=paper_ids)`; returns `{ "ok": true, "result": {...} }` or error.
  - `GET /api/archive`: Returns JSON list of `.mp3` filenames from `static/archive/` (for the GDrive Vault list; may differ from rclone backup path).

- **Intel-stack loading**: `_arxiv_intel()` dynamically imports `intel-stack/arxiv_intel.py` and returns the module so all arxiv/DB logic lives in one place.

---

## 4. Backend — Intel-stack (intel-stack/arxiv_intel.py)

### 4.1 Configuration and data model

- **Paths**: `DB_PATH` = `intel-stack/arxiv_history.db`; `OUTPUT_HTML` = `intel-stack/arxiv_intel.html`; `SYNOPSIS_OUTPUT` = `intel-stack/arxiv_synopsis.html`. `.env` in intel-stack is loaded for `OPENROUTER_KEY` etc.
- **Categories**: Two-layer tree `CATEGORIES_TREE` (e.g. `cs` → [AI, LG, SY, RO, NE, CE]; eess, math, stat, econ, physics). Flat list `CATEGORIES` = all `"layer1.layer2"` (e.g. cs.AI, cs.LG).
- **PODCAST_STYLES** and **LENGTH_WORDS** define style/length presets for the LLM and TTS.
- **TTS voices**: Configurable engine. **Default (edge, free)**: Alex = `en-US-AndrewMultilingualNeural`, Sam = `en-US-EmmaMultilingualNeural` for more natural, conversational flow; override with `EDGE_TTS_VOICE_ALEX` / `EDGE_TTS_VOICE_SAM`. **Optional (openai, paid)**: `TTS_ENGINE=openai` and `OPENAI_API_KEY` for ChatGPT-style voices. Audio is TTS-only; script text comes from the LLM, then each segment is synthesized by the chosen engine.
- **DB schema (papers table)**:
  - Columns: `id`, `category`, `title`, `url`, `date`, `abstract`, `other_categories`.
  - Primary key: `(id, category)` so the same paper can appear under multiple categories (e.g. one row for cs.AI, one for cs.LG).
  - `other_categories`: comma-separated secondary arXiv categories for the “Other tags” column (excluding the displayed domain so it doesn’t duplicate).

- **init_db()**: Creates the table if missing; adds `other_categories` if absent; migrates old single-column PK to composite `(id, category)` if needed.
- **clear_papers()**: `DELETE FROM papers`.

### 4.2 Fetching papers from arXiv

- **Date-specific fetch**: `_fetch_by_date_http(category, papers_per_tag, date)`:
  - Builds query `cat:{category} AND submittedDate:[YYYYMMDD0000 TO YYYYMMDD2359]`, calls `GET https://export.arxiv.org/api/query` with `search_query`, `max_results`, `sortBy=submittedDate`, `sortOrder=descending`.
  - Parses Atom XML: for each entry, extracts id, title, summary, published, pdf link, all `<category term="..."/>`, primary category; builds `other_categories` as all categories except the requested `category` (so the main domain doesn’t appear in Other tags).
  - Returns list of `(eid, title, pdf_url, date_str, summary, other_categories)`.

- **fetch_and_store(categories, papers_per_tag, date)**:
  - If `date` is set: for each category, calls `_fetch_by_date_http(cat, papers_per_tag, date)`; for each row inserts `(id, category, title, url, date, abstract, other_categories)` with `category` = the requested `cat`; uses `INSERT OR IGNORE` and counts `changes()` for `new_added`.
  - If `date` is None: uses the `arxiv` Python library: `Search(query=f"cat:{cat}", max_results=papers_per_tag, sort_by=SubmittedDate)`; for each result inserts same columns, with `other_categories` = all result categories except `cat`.
  - Returns `{ "total_found", "new_added" }`.

### 4.3 Matrix HTML (paper viewer)

- **get_matrix_html(limit, date, categories, papers_per_tag)**:
  - Resolves date: if `date` is None, uses `MAX(date)` from DB (“latest”).
  - Builds `WHERE date = ?` and optionally `AND category IN (...)` from `categories`.
  - Runs `SELECT * FROM papers WHERE ... ORDER BY category ASC, id ASC` (no LIMIT yet).
  - If `papers_per_tag` is set: in Python, groups rows by category and keeps at most `papers_per_tag` rows per category (order preserved); flattens back to one list. Else caps total rows with `limit`.
  - Calls `_build_matrix_table(rows, empty_msg)` and returns the HTML string.

- **_build_matrix_table(rows, empty_message)**:
  - Rows are 7-tuple: `(id, category, title, url, date, abstract, other_categories)` (or 6-tuple for legacy).
  - Emits a table: for each date block, header row “DATA_LOG: {date}” and column headers **Use**, **Domain**, **Other tags**, **Title / Source**, **Abstract**. For each row: checkbox `name="matrix-paper"` value=`id` (checked by default), Domain pill, Other tags pills, title link, abstract. Row has `data-paper-id="{id}"`.

- **generate_html(limit, date, papers_per_tag)**: Calls `get_matrix_html(...)` with `categories=None` and writes the result to `OUTPUT_HTML` (used after a fetch so the static file is updated).

### 4.4 Podcast generation (script + transcript + two-voice audio)

- **generate_podcast_and_synopsis(style, length, custom_style, date, paper_ids)**:
  - **Paper set**:
    - If `paper_ids` is non-empty: `SELECT title, category, abstract, date FROM papers WHERE id IN (...)`; deduplicates by `(title, category)`; `target_date` = max of those dates.
    - Else: if `date` given, uses that date and selects all papers for that date; else uses `MAX(date)` and selects all papers for that date. Loads `(title, category, abstract)` for the chosen set.
  - **LLM**: Builds a prompt asking for a two-host script (ALEX and SAM), interactive and conversational (Notebook LM style), with a short headlines round then main dialogue; word target from `LENGTH_WORDS`; style from `PODCAST_STYLES` or custom. Sends papers as “Category | Title | Abstract” to OpenRouter (`LLM_MODEL`). Expects script where every line starts with `ALEX: ` or `SAM: `.
  - **Transcript HTML**: Parses script into lines; for each line starting with `ALEX:` or `SAM:` emits a `<p>` with styled “Alex:” / “Sam:” and the rest; writes to `SYNOPSIS_OUTPUT` (served as synopsis-html).
  - **Two-voice TTS**:
    - Splits script into segments: list of `(speaker, text)` with speaker in `{"ALEX","SAM"}` (unlabeled lines assigned to previous speaker or ALEX).
    - **Engine**: If `TTS_ENGINE=openai` and `OPENAI_API_KEY` is set, uses OpenAI TTS (ChatGPT-style natural voices); otherwise uses **Edge TTS**. For each segment, `_synthesize_segment(engine, speaker, text, path)` writes a temp MP3.
    - Uses **pydub** to load each segment as `AudioSegment.from_mp3(...)`, concatenates in order, exports to `AUDIO_OUTPUT` (`static/audio/daily_briefing.mp3`).
    - Deletes temp files and temp dir.
  - **Optional rclone**: Uploads `AUDIO_OUTPUT` to `gdrive:ArxivCast_Audio/briefing_{today}.mp3` if rclone is available.
  - Returns `{ "script_length", "date": target_date }`.

---

## 5. Data flow summary

| User action           | Frontend                                      | Backend (Flask → intel-stack)                                                                 | Result |
|-----------------------|-----------------------------------------------|------------------------------------------------------------------------------------------------|--------|
| Open /intel           | Load categories, load matrix, load synopsis  | GET categories, GET matrix-html (params from UI), GET synopsis-html                          | Page with filters, table, sidebar     |
| Change filters        | loadMatrixHtml() with new params              | GET matrix-html?categories=&date=&papers_per_tag= → get_matrix_html → _build_matrix_table     | Table HTML updated                   |
| Search & Populate     | POST /api/arxiv/fetch                         | fetch_and_store (arXiv API or library), generate_html                                         | DB filled; matrix HTML file + view    |
| Clear table           | POST /api/arxiv/clear                         | clear_papers()                                                                                 | DB empty; placeholder in matrix      |
| Generate podcast      | POST /api/arxiv/podcast + paper_ids           | generate_podcast_and_synopsis (DB → LLM → transcript file + two-voice TTS → MP3)              | Transcript + audio; player reloads  |

---

## 6. External dependencies

- **arXiv**: `https://export.arxiv.org/api/query` (GET with search_query, max_results, sortBy, submittedDate filter for date-specific fetch).
- **OpenRouter**: LLM for script generation (OPENROUTER_KEY in intel-stack/.env).
- **TTS**: **edge-tts** (default, free) or **OpenAI TTS** when `TTS_ENGINE=openai` and `OPENAI_API_KEY` set; two voices (Alex/Sam); outputs MP3. **Free, more natural Edge voices**: defaults use `en-US-AndrewMultilingualNeural` and `en-US-EmmaMultilingualNeural`; override with `EDGE_TTS_VOICE_ALEX` / `EDGE_TTS_VOICE_SAM` in `.env` (e.g. `en-US-AriaNeural`, `en-US-BrianMultilingualNeural`). **Other free options** (not wired in yet): **Piper** (offline, CPU-friendly, `piper-tts`); **Dia TTS** / **Coqui XTTS** (natural dialogue / voice clone, need GPU or separate server with OpenAI-compatible API); **Nvidia Magpie** via NIM.
- **pydub**: Concatenate per-segment MP3s into one file (may require ffmpeg on the system).
- **rclone** (optional): Backup MP3 to Google Drive.

---

## 7. Files involved

| File | Role |
|------|------|
| `app.py` | Flask app; routes for /intel, /api/arxiv/*; loads intel-stack module. |
| `templates/intel.html` | Single-page UI: filters, matrix container, sidebar (audio + transcript + archive). |
| `intel-stack/arxiv_intel.py` | DB init/migration, arXiv fetch (HTTP + library), matrix HTML building, podcast (LLM + transcript + two-voice TTS + rclone). |
| `intel-stack/arxiv_history.db` | SQLite DB: papers table (id, category, title, url, date, abstract, other_categories). |
| `intel-stack/arxiv_intel.html` | Static matrix HTML written after a fetch (fallback when matrix-html has no params). |
| `intel-stack/arxiv_synopsis.html` | Transcript HTML written after podcast generation. |
| `static/audio/daily_briefing.mp3` | Final two-host podcast audio. |
| `intel-stack/.env` | OPENROUTER_KEY (and any other secrets). |

This is the exact description of how the arXiv paper viewer and podcast generation are implemented end-to-end, with backend and frontend behavior.
