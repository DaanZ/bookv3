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

# Ingest — now also available in the reader itself, on the library screen
streamlit run app.py          # upload a PDF and summarize it live, chunk by chunk
python prep.py                # batch: summarize every PDF in ./next -> books/available, PDF to ./pdfs

# Superseded by the reader, still present
streamlit run next_reads.py   # old reader: books/available -> books/read + Hardcover
streamlit run all.py          # browse already-finished summaries in books/read
streamlit run dashboard.py    # card grid (reads books/*.json — a stale path, see below)
python homework.py            # scratch script: generates a quiz question from one hardcoded book
python hardcover/request.py   # exercises the Hardcover API against a hardcoded title/author
```

`.env` (gitignored) must provide `OPENROUTER_API_KEY`, and `HARDCOVER_API_KEY` for the Hardcover
integration. `util/chatgpt.py` reads it at import time (falling back to `OPENAI_API_KEY`), so *any*
import of the chunking or meta modules fails without a key — but `api/` does not import them, so the
reader runs without one. `OPENROUTER_MODEL` overrides the default model.

## Architecture

**Pipeline (PDF → JSON summary).** `fragments.read_book_pages` loads a PDF into LangChain `Document`
pages via `PyPDFLoader`. `chunks.get_page_chunks` splits those pages into N contiguous page ranges
using the left half of a Gaussian CDF — chunks are deliberately *uneven*, dense near the front of the
book and wider toward the end. `meta.get_book_meta` asks the LLM to identify title/author/category/
publisher from the first ~5 pages (and raises `UnreadableCharactersError` when the pages have zero
extractable characters, i.e. a scanned PDF). `chunks.highlight_chunk` then summarizes each page range.

**LLM access** goes through `util/chatgpt.py` only, and it points at **OpenRouter**, which speaks the
OpenAI wire protocol — same SDK, different `base_url`. Two consequences: model ids are namespaced
(`openai/gpt-4o`, not `gpt-4o`), and only models whose OpenRouter entry lists `structured_outputs`
can run this pipeline at all, since `llm_strict` is how every summary is made. `llm_strict` uses the
structured-output parse API with a Pydantic model as the response schema; `llm_chat` is the
plain-text variant. Both take an optional `model_name`, threaded from the job so a book can be
summarized by whichever model was chosen and priced on the library screen.

**Choosing a model is not a price decision.** The default is `openai/gpt-4o-mini`, about a
sixteenth of `gpt-4o` and measurably no worse at this job. But the cheap tier below it is a trap:
`gpt-4.1-nano`, `mistral-small-3.2-24b`, `llama-3.3-70b` and `deepseek-chat-v3.1` were all tried on
real chunks and returned fluent summaries containing **zero `**` marks**, with several describing
the book from outside rather than summarizing it. The pipeline's `<b>` tags are what
`web/src/lib/reading.js` colours, so a summary without them renders as a flat wall of text — the
one thing this project exists to avoid. `estimate.CANDIDATE_MODELS` is filtered on that evidence,
not on price; re-test before adding to it. Prompts
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
`POST /api/books/{key}/finish` means two things and profiles pull them apart. It always
records the finish for the reader who asked. For the **owner** it also moves a file between the
two folders: it calls
`hardcover.request.mark_book_as_read` (GraphQL search + `insert_user_book` mutation with
`status_id: 3`), then `shutil.move`s the JSON into `books/read/`. The move happens either way — the
book *was* read — but `markedRead` is only true when Hardcover accepted it, and the finish screen
never paints the green chip otherwise. `next_reads.py` still does the same thing the old way.
`prep.py` feeds the other end, consuming PDFs from `./next` and parking the originals in `./pdfs`
(both gitignored, both absent from a fresh clone — `prep.py` creates the output dirs but expects
`next/` to exist).

## The reader (api/ + web/)

Implements `design_handoff_bookv3_reader`, built on the Tide design system. Five screens — shelf,
reader, finished, library and profiles — sized for a tablet in portrait (an 834px card on a
coloured "desk").

The first three come from the handoff and are high fidelity to it. **The library and profiles
screens have no design file**: both are extensions written in the same token language. The library
deliberately breaks the reader's "one unit of work per screen, never a scroll" rule, because
managing a collection needs an overview that reading does not; profiles keeps the rule, and is
built like the shelf — a column of rows to choose between. Re-skin them, don't reason from them.

**`api/`** is mostly read-only over `books/`. `library.py` scans both folders into shelf entries (the
key is the filename stem, so a lookup never path-joins caller input); `patches.py` collapses the
pipeline's free-text `meta.category` onto a patch family; `positions.py` is the only place reading
history has ever been stored (`data/positions/<profile>.json`: part, page, lastReadAt, startedAt,
sittings, and the Hardcover outcome).

`profiles.py` is who that history belongs to. One file each under `data/positions/`, listed in
`data/profiles.json`, chosen by an `X-Profile` header that every reading endpoint resolves through
one dependency (`reader` in `main.py`). Five rules:

- **The settings are the reader's too.** Register, palette, pointer focus and the highlight cap
  live on the profile row, not in localStorage — `PUT /api/profiles/{id}/prefs`, whitelisted by
  `clean_prefs` because it comes off the wire. The browser keeps a copy for the first paint only:
  the profile's settings arrive a round-trip after mount, and without a cache the app would open
  in the default register and then swap, which is the one thing the design says is never animated.
- **The books are one shelf; the reading is not.** `books/available` and `books/read` are the
  house's filing. A book's `state` is the *reader's* — finished by them, or in progress — while
  `filed` is where the JSON actually sits. The owner is the exception the folder exists for: the
  contents of `books/read` are their history, because they filled it before profiles existed.
- **Hardcover is the owner's.** There is one key and it is one person's account, so only the
  owner's finish calls `mark_book_as_read`, and `/hardcover` (the re-sync) is 403 for anyone else.
  A guest's finish returns `markedRead: null` — nothing was sent, which the finish screen says
  rather than showing them a chip about a call nobody made.
- **The owner cannot be deleted, only renamed.** Their reading is the shelf's own; handing the
  tablet over is a rename.
- **No login.** This is a tablet in a house. Asking who is holding it is the whole model, and
  `resolve` answers an unknown id with the owner — which is exactly what the app did before.

`data/positions.json`, the single store this replaced, is *moved* onto `data/positions/owner.json`
the first time `positions.py` loads, so history from before profiles belongs to whoever made it.

`enrich.py` is the Hardcover cache — cover, rating, genres and the link out, in
`data/hardcover.json`, beside the books and never inside them. Nobody asks for a lookup by hand:
a book is queued the moment `jobs.py` writes its JSON, and everything else is queued by the first
`GET /api/shelf` that sees a book nobody has asked about, which is how books that predate the pass
and anything `prep.py` writes get covers. Four things about that are deliberate:

- **Read-only.** The automatic pass calls `search_book` and nothing else. `insert_user_book` stays
  on the finish screen and `insert_book` behind the contribution confirm — a background pass must
  not write to someone's shelf, still less to a catalogue everyone reads.
- **Once per book.** Every attempt is recorded in `data/hardcover-lookups.json`; `found` and
  `missing` are answers and are never re-asked, and only `failed` is retried, not for
  `RETRY_AFTER_HOURS`. Without that, every shelf load would re-queue the whole library while the
  network was down.
- **A miss is a state.** `summarise` sends `hardcover: null` for a book the pass asked about and
  Hardcover does not have, which is what tells the row apart from one still waiting its turn — and
  what makes "Add to Hardcover" reachable.
- **Never load-bearing.** No key, no network, no match: the library renders on the patch exactly as
  before, and no request handler waits on any of it.

`POST /api/books/{key}/enrich` stays for the one case the pass cannot serve: asking again about a
book it matched to the wrong edition.

`estimate.py` prices a book before anything is spent, and is deliberately free of the pipeline's
imports so it works with no API key: it reads the PDF with `pypdf` directly and shares chunk
boundaries with `chunks.py` through `util/split.py`. The cost model rests on one fact about the
pipeline — chunks are contiguous and non-overlapping, so the whole book is sent as input *exactly
once* whatever the chunk count (the first five pages go twice, for `get_book_meta`). More parts
therefore cost almost nothing extra; a longer book costs linearly more. Output constants are
measured from 254 committed summaries, not guessed; the header of that file shows the figures.

`jobs.py` is the exception — it *writes* books, by running the ingest pipeline for an uploaded PDF.
One thing there is easy to undo by accident: **the pipeline is imported inside the worker, not at
module scope.** `util/chatgpt.py` reads `OPENAI_API_KEY` at import time, so a top-level
`from chunks import ...` in `api/` would take the whole reader down on a machine without a key.
Hoisting that import is the single change that breaks the reader for everyone who only wants to
read. Jobs run one at a time on a worker thread, report progress per chunk, and are recorded in
`data/jobs.json`; a job caught mid-flight by a restart is marked failed on the next boot, because
nothing resumes it.

**One bad response used to cost a whole book.** A model occasionally returns JSON truncated
mid-string, which reaches the caller as a pydantic `ValidationError` reading "Invalid JSON: EOF
while parsing a string" — transport, not a schema the model cannot hold (the same call parsed 12/12
over real chunks when measured). With one call per part and a dozen parts per book, a per-call rate
that rounds to nothing is a real per-book rate, and the job died on part 13 having already paid for
twelve. `llm_strict` now retries three times with backoff, and `jobs.py` names the part that gave
up. Nothing resumes a failed job, so a re-run still pays for every part again.

**`web/`** is Vite + React. `src/lib/reading.js` is the model and the part worth understanding:

- **Front-weighted progress.** The first 40% of parts carry 80% of the bar. `progressOf` uses
  `pageIndex`, not `pageIndex + 1` — the page you are on is in progress, not read, and 100% belongs
  to the finish screen alone.
- **Pagination.** Two sentences to a paragraph, two paragraphs to a page, so a part is two or three
  pages and the bar moves inside a chapter.
- **Highlighting** replaces `chunks.py`'s inline forest-green. The pipeline's `<b>` still decides
  *what* matters; the UI decides *how* it looks. `normaliseBody` strips the baked-in colour, then
  phrases take palette bands in reading order, capped at 8 marks per page by default (counting
  instances, not distinct phrases).

  The palette is **sampled to the page, not sliced**. `paletteFor(name, day, n)` reads the eight
  bands as a gradient and returns `n` stops across the whole of it, so a page with four highlights
  sweeps the entire ramp instead of showing only its dark end — `highlightCount` runs the real
  budget to get `n`, so the count cannot drift from what `tokensOf` assigns.

  Making a band legible is where this is easy to get wrong, and there are two traps:

  - **Do not mix toward ink or cream.** That clears contrast by pulling every band toward grey. At
    night it produced literal greys — sunset opened `#c0bcc7 #c0b4bc #bfa7c6` — with mean saturation
    0.41. Hue is held and chroma raised instead; the same palette now runs 0.71.
  - **Do not pin every stop to the contrast floor.** Bands that differ mainly in lightness collapse
    onto each other: sunrise is four teals then four oranges, and a hard floor put adjacent stops at
    ΔE 2, which is no visible difference. The palette's own lightness spread is rescaled into the
    register's window instead, and the floor is only a backstop. It is deliberately not maximal —
    0.30 at night still measures ~5.5:1, and every point above that is paid for in collapsed stops.

  `node web/tools/check-palettes.mjs` prints contrast, saturation and adjacent ΔE for every palette
  in both registers, against the previous behaviour. Re-run it if these numbers are touched.

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
default, one gesture to start, the choice belongs to the book — persisted per book *and per
profile*, in that reader's position entry (`data/positions/<profile>.json`, under `ambience`), so
it arrives on the book payload and follows the reader to another tablet —
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
- Python validates TLS against `certifi`, not the Windows certificate store, so a TLS-intercepting
  antivirus (AVG's Web Shield, on the main dev machine) makes *every* API call fail with
  `CERTIFICATE_VERIFY_FAILED` while `curl` keeps working. `truststore` is imported and injected in
  `util/chatgpt.py` and `api/estimate.py` to fix it; it also unblocks tiktoken, which downloads its
  vocabulary on first use. Without it the estimator silently falls back to counting characters.

`hardcover/request.py` now works against the live API, which took three attempts. Interpolating
`{title: {<title>}}` was not valid comparison syntax; `_ilike` with variables was valid Hasura and
still refused, because the API answers **403 `ilike and related operations are not permitted on this
schema`** — pattern matching on `books` is not available to a token. The working path is the
`search` root field, which is typesense-backed and returns an untyped JSON blob.

Two things about it are not obvious and were both found the hard way:

- **Sort by `users_count:desc`.** The default ordering is text relevance, under which
  "Summary of Atomic Habits by James Clear" outranks the real book — a search for any well-known
  title returns a page of cash-ins. `users_count` is also the number hardcover.app prints as
  "Readers"; `users_read_count` is a different, smaller number.
- **A hit must agree with the request.** The index always answers, so an unknown title returns its
  nearest neighbour — and the caller's next move is to mark that stranger as read on someone's
  account. `search_book` therefore requires either an author-word match or full title-word
  containment, and reports which via `authorMatched`. A blank `author_names` is treated as missing
  information, not disagreement, because the real *Atomic Habits* has one.

Running the module directly now only searches; `--mark` is required to write.
