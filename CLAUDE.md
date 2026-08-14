# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Python scripts that turn book PDFs into short, ADHD/dyslexia-friendly summaries with highlighted
keywords, plus a React reading app served by a small FastAPI backend. Two halves that meet at the
`books/*.json` files: **Streamlit owns ingest**, **the React app owns reading**. The pipeline half
has no package, no tests and no build step — every entry point is a top-level script run directly.

## Commands

```bash
pip install -r requirements.txt

# Reading (the redesigned tablet reader — see design/ handoff and TODO.md)
./dev.sh                      # FastAPI :8000 + Vite :5173 with /api proxied; open :5173
./build.sh                    # bundle web/ into web/dist
uvicorn api.main:app --port 8000   # serves the API *and* web/dist when it exists

# Ingest (unchanged)
streamlit run app.py          # upload a PDF and summarize it live, chunk by chunk
python prep.py                # batch: summarize every PDF in ./next -> books/available, PDF to ./pdfs

# Superseded by the reader, still present
streamlit run next_reads.py   # old reader: books/available -> books/read + Hardcover
streamlit run all.py          # browse already-finished summaries in books/read
streamlit run dashboard.py    # card grid (reads books/*.json — a stale path, see below)
python homework.py            # scratch script: generates a quiz question from one hardcoded book
python hardcover/request.py   # exercises the Hardcover API against a hardcoded title/author
```

`.env` (gitignored) must provide `OPENAI_API_KEY`, and `HARDCOVER_API_KEY` for the Hardcover
integration. `util/chatgpt.py` reads `OPENAI_API_KEY` at import time, so *any* import of the chunking
or meta modules fails without it — but `api/` does not import them, so the reader runs without it.

## Architecture

**Pipeline (PDF → JSON summary).** `fragments.read_book_pages` loads a PDF into LangChain `Document`
pages via `PyPDFLoader`. `chunks.get_page_chunks` splits those pages into N contiguous page ranges
using the left half of a Gaussian CDF — chunks are deliberately *uneven*, dense near the front of the
book and wider toward the end. `meta.get_book_meta` asks the LLM to identify title/author/category/
publisher from the first ~5 pages (and raises `UnreadableCharactersError` when the pages have zero
extractable characters, i.e. a scanned PDF). `chunks.highlight_chunk` then summarizes each page range.

**LLM access** goes through `util/chatgpt.py` only. `llm_strict` uses the OpenAI structured-output
parse API with a Pydantic model as the response schema; `llm_chat` is the plain-text variant. Prompts
are not written as prompt strings — they live in the Pydantic `Field(description=...)` text. That's
why `chunks.py` has two nearly identical models: `DisabilityBookFirstChunk` (one paragraph) vs
`DisabilityBookNextChunk` (two paragraphs), swapped by the `first` flag so the opening chunk is
shorter. `homework.py` uses the same trick for multiple choice: four models, `HomeworkAModel` through
`HomeworkDModel`, differing only in which answer field is described as correct, picked at random by
`random_answer_model()` so the correct letter is uniformly distributed.

Conversation state is a `util.history.History` — a thin list of `{role, content}` dicts. The pattern
throughout is to push each page's raw text as a `system` message, then a single `user` instruction.

**Highlighting.** `chunks.format_text` converts the model's markdown (`**bold**`, `###`, `_em_`) into
inline-styled HTML with `color: forestgreen`. Summary bodies are therefore stored as HTML and every
renderer passes `unsafe_allow_html=True`.

**Storage format.** Each book is one JSON file, named `sanitize_filename(title).json`:

```json
{"meta": {"title", "author", "category", "publisher", "pages"},
 "parts": [{"title": "...", "body": "<html>"}]}
```

**Book lifecycle.** `books/available/` holds unread summaries, `books/read/` holds finished ones.
`POST /api/books/{key}/finish` moves a file between them: it calls
`hardcover.request.mark_book_as_read` (GraphQL search + `insert_user_book` mutation with
`status_id: 3`), then `shutil.move`s the JSON into `books/read/`. The move happens either way — the
book *was* read — but `markedRead` is only true when Hardcover accepted it, and the finish screen
never paints the green chip otherwise. `next_reads.py` still does the same thing the old way.
`prep.py` feeds the other end, consuming PDFs from `./next` and parking the originals in `./pdfs`
(both gitignored, both absent from a fresh clone — `prep.py` creates the output dirs but expects
`next/` to exist).

## The reader (api/ + web/)

Implements `design_handoff_bookv3_reader`, built on the Tide design system. Three screens — shelf,
reader, finished — sized for a tablet in portrait (an 834px card on a coloured "desk").

**`api/`** is read-mostly over `books/`. `library.py` scans both folders into shelf entries (the key
is the filename stem, so a lookup never path-joins caller input); `patches.py` collapses the
pipeline's free-text `meta.category` onto a patch family; `positions.py` is the only place reading
history has ever been stored (`data/positions.json`: part, page, lastReadAt, startedAt, sittings,
and the Hardcover outcome).

**`web/`** is Vite + React. `src/lib/reading.js` is the model and the part worth understanding:

- **Front-weighted progress.** The first 40% of parts carry 80% of the bar. `progressOf` uses
  `pageIndex`, not `pageIndex + 1` — the page you are on is in progress, not read, and 100% belongs
  to the finish screen alone.
- **Pagination.** Two sentences to a paragraph, two paragraphs to a page, so a part is two or three
  pages and the bar moves inside a chapter.
- **Highlighting** replaces `chunks.py`'s inline forest-green. The pipeline's `<b>` still decides
  *what* matters; the UI decides *how* it looks. `normaliseBody` strips the baked-in colour, then
  phrases take palette bands in reading order, capped at 8 marks per page (counting instances, not
  distinct phrases), each band mixed toward ink or cream until it clears a luminance threshold.

Colours, type and spacing come from the vendored token layer in `web/src/ds/` — edit tokens, not
hard-coded values. Two rules from the design system are easy to break by accident: **gold is only
ever a join** (the resume strip, nothing else), and **the day/night register swap is never
animated** — it is a different room, it loads.

**Ambience** (`web/src/lib/ambience.js`) plays one of six natural beds under the reader. Forest,
river, fireplace and wind are recordings in `web/public/ambience/`; lake and rain are synthesized
with the Web Audio API by the recipes from the ambience handoff. Three things about it are load
bearing and not obvious:

- **Recordings stream, they are never decoded.** `decodeAudioData` on a 10-minute stereo file
  produces roughly 200MB of AudioBuffer. Beds run through `MediaElementAudioSourceNode` instead.
- **Two lanes crossfade.** A recorded bed builds two media elements and hands over with an
  equal-power fade before the file ends, because `loop = true` leaves an audible seam — which the
  22-second wind file would hit every 22 seconds.
- **`TRIM` is measured, not chosen.** The supplied recordings sit near -50 dBFS RMS while the
  synthesized beds run at -7, so each bed carries a trim that brings it to a common level.
  Re-derive them with `web/tools/measure-beds.mjs` if a recording is ever replaced; the header of
  that file explains the procedure, including that trims must be reset to 1 before measuring.

The wiring rules come from the handoff and are enforced in `web/src/lib/useAmbience.js`: off by
default, one gesture to start, the choice belongs to the book (persisted per book, not per app),
duck while the resume strip shows, and silence at the finish screen.

**Streamlit state.** Each script is a `if __name__ == "__main__"` block that re-executes top to bottom
on every interaction, so all cross-rerun state lives in `st.session_state`, and `st.empty()`
placeholders captured into session state are reused as render slots (`next_reads.py`). `app.py`
additionally pre-computes the *next* chunk's summary during the current rerun (`next_highlighted`) to
hide LLM latency behind the user's reading time.

## Known rough edges

Don't treat these as intentional design when editing nearby code:

- `dashboard.py` and `all.py` duplicate `get_json_files`/`extract_book_details` from `next_reads.py`,
  and `dashboard.py` points at `books/` (no JSON at that level) rather than a subfolder.
- Both dict literals in `extract_book_details` contain a stray `""` element between keys.
- `chunks.format_text` calls `.replace("```")` with one argument — raises `TypeError` if a response
  ever contains a ```` ```html ```` fence.
- `app.py` writes uploads to `uploaded_files/` but creates `pdfs/`.
- Broad `except Exception: print(ex)` blocks in `app.py` swallow errors into the console.
- 68 of the book JSONs predate `meta.category` and have none; `patches.py` falls back deterministically.
- The webfonts load from the Google Fonts CDN (`web/src/ds/tokens/fonts.css`). Where that is blocked
  the reader silently falls back to a system sans, losing the legibility Lexend was chosen for.

`hardcover/request.py` used to interpolate title/author into GraphQL as `{title: {<title>}}`, which
is not valid comparison syntax — that is fixed (`_ilike` with variables), but the path has still
never round-tripped against the live API. See TODO.md.
