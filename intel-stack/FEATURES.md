# ArxivCast — feature ideas

Ideas to make ArxivCast more useful for **academic use** and **general-purpose use**.

---

## Academic use

- **Date range & “batch” selection**  
  Let users pick a date or date range and generate the podcast from that batch only (e.g. “papers from last Monday”), so it matches a specific reading list or seminar.

- **Export reading list**  
  Export selected papers (or the current batch) as BibTeX, RIS, or a simple Markdown list with title, authors, link, and one-line TLDR for citation and sharing.

- **Author / affiliation awareness**  
  Optionally include author names or institutions in the script when relevant (e.g. “from MIT” or “by Smith et al.”) for seminar prep or networking.

- **“Related papers” from a seed**  
  Allow one or more arXiv IDs as input; fetch those papers and use the API (or heuristic) to suggest related papers, then run the usual pipeline on that set.

- **Custom categories / free-text search**  
  Support arbitrary `query` strings (e.g. `all: reinforcement learning`) in addition to `cat:`, so users can build casts around a topic rather than only fixed categories.

- **Slides / bullet summary**  
  Option to output a short bullet-point summary (e.g. for a 5‑minute seminar intro or a slide deck) in addition to the dialogue script.

- **Two voices in TTS**  
  Use two different edge-TTS voices for Alex and Sam so the podcast actually sounds like a two-person show.

---

## General-purpose use

- **RSS / podcast feed**  
  Expose an RSS feed of generated episodes (title, description, enclosure to the audio file) so users can subscribe in any podcast app.

- **Email digest**  
  Optional weekly or daily email with “headlines only” or a short summary plus link to the latest cast.

- **Multiple “shows”**  
  Save presets (e.g. “ML only, brief” vs “all categories, deep dive”) and generate different casts from the same data with one click.

- **Schedule**  
  Cron (or a small scheduler) to auto-fetch and optionally auto-generate a cast on a schedule (e.g. every Monday 8am), so the page always has a fresh default.

- **Public vs private**  
  Option to make the latest cast (or an archive) publicly listenable (e.g. shareable link) while keeping the rest of the dashboard private.

- **Other feeds**  
  Generalize beyond arXiv: plug in other RSS or API sources (e.g. blog feeds, HN, a custom list of URLs) and use the same “headlines + dialogue” pipeline for a more general “digest cast.”

---

## Cross-cutting

- **Caching / idempotency**  
  Avoid re-fetching the same paper in a short window; optionally skip podcast regeneration if the batch and options haven’t changed.

- **Rate limiting & backoff**  
  Respect arXiv and Open Router rate limits with simple backoff so heavy use doesn’t hit errors.

- **Accessibility**  
  Ensure the transcript is the single source of truth (which you already have); add “Download transcript” and consider a simple captions/subtitles export for the audio.
