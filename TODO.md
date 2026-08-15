# TODO — reader redesign

Tracking the implementation of `design_handoff_bookv3_reader` (the Tide-based tablet
reader: shelf, reader, finished). Updated as each step lands.

**Decision, per the handoff's "pick one and say which":** option 2 — the reader is a
React app (`web/`) over a small FastAPI service (`api/`) reading the same
`books/*.json`. Streamlit keeps ingest (`app.py`, `prep.py`); `next_reads.py`,
`all.py` and `dashboard.py` are superseded by the new reader but left in place.

**Ambience decision:** `design_handoff_bookv3_ambience` ships a synthesizer for all five
beds and documents a contract for using real recordings instead. Four recordings were
supplied (forest, river, fireplace, wind), so beds play a recording where one exists and
fall back to the handoff's synthesized recipe where none does — lake and rain are still
synthesized. Wind is a sixth bed, added because a file for it arrived.

---

## Back-end

- [x] `api/library.py` — scan `books/available` + `books/read`, shape a shelf entry
      (title/subtitle split, byline, part count, state, patch)
- [x] `api/patches.py` — map the pipeline's free-text `meta.category` onto patch
      families; the three from the design verbatim, plus extensions and a
      deterministic fallback so no book is patch-less
- [x] `api/positions.py` — persist `{part, page, lastReadAt, startedAt, sittings}`
      per book (atomic writes, `data/positions.json`)
- [x] `api/main.py` — `GET /api/shelf`, `GET /api/books/{key}`,
      `PUT|DELETE /api/books/{key}/position`, `POST /api/books/{key}/finish`
- [x] Derive the resume recap from the previous part instead of authoring it, so it
      is true for all 264 books rather than the three in the demo
- [x] Fix `hardcover/request.py` — the `{title: {<title>}}` comparison was not valid
      GraphQL and the search never worked; now `_ilike` with query variables
- [x] Treat a GraphQL error inside a 200 as a failure, so the finish screen never
      claims "marked read" when Hardcover refused
- [x] `api/enrich.py` — look every book up on Hardcover once, in the background, and
      keep the cover, so jackets appear on the shelf without a per-book "look up"
      button. Read-only: the search queries only, never `insert_user_book`
- [x] Queue on ingest (`api/jobs.py`, the moment the JSON is written) *and* on the first
      `GET /api/shelf` that sees a book with no entry — which backfills the 264 books
      that predate this, and anything `prep.py` writes behind the API's back
- [x] `GET /api/covers/{key}` serves the stored jacket; `GET /api/enrichment` reports how
      far the pass has got, which the library screen shows while it runs
- [ ] **The cover lookup has never run against the live API either.** `image { url }` and
      `cached_image` are what Hardcover's docs and its users describe, not what an
      introspection of the live schema returned — there is no key here to run one with.
      `search_book_details` falls back to the plain search if the richer selection set is
      rejected, so a wrong field name costs the cover and not the lookup, but the first
      real key is the test that settles it
- [ ] Verify the Hardcover path against the live API with a real `HARDCOVER_API_KEY`
      — the query is correct GraphQL now, but has still never round-tripped
- [ ] Serve part bodies pre-paginated so the reader and any future surface agree on
      page boundaries (currently pagination is frontend-only)
- [ ] Re-summarise or hide the 68 books whose JSON predates `meta.category`

### Ingest and collection management

- [x] `api/jobs.py` — upload a PDF into `next/`, queue it, run the same pipeline
      `prep.py` runs (`read_book_pages` → `get_page_chunks` → `get_book_meta` →
      `highlight_chunk`), write to `books/available`, park the original in `pdfs/`
- [x] Per-chunk progress, so the screen can say "summarizing part 3 of 7" rather than
      spinning for several minutes
- [x] The pipeline is imported **inside the worker**, so the reader still starts on a
      machine with no `OPENAI_API_KEY`; a missing key fails the job with that sentence
      instead of taking the server down
- [x] One job at a time on a worker thread — the point is to watch a book finish, not
      to start six and have them all crawl
- [x] Jobs persist to `data/jobs.json`; one interrupted by a restart is marked failed
      on the next boot, since nothing resumes it
- [x] Upload validation: extension, magic bytes (`%PDF`), 200MB ceiling, and collision
      -safe filenames; the server-side path never appears in an API response
- [x] `PATCH /api/books/{key}` to move between available and read, `DELETE` to remove a
      summary (the source PDF in `pdfs/` is left alone)
- [ ] **Nothing resumes an interrupted job.** The part summaries already produced are
      thrown away and the book starts over. Writing partial output would fix that.
- [ ] No way to cancel a running job, and no way to retry a failed one without
      re-uploading the file
- [ ] The chunk count is `ceil(pages / 25)` with no way to choose it from the screen,
      though the API accepts an override
- [ ] Uploading the same book twice produces two summaries under slightly different
      keys; there is no duplicate check
- [ ] Deleting a book does not remove its PDF from `pdfs/`, by design — but nothing
      surfaces the orphans either

## Front-end

- [x] Vite + React scaffold, Tide token layer vendored under `web/src/ds/`
- [x] `lib/reading.js` — front-weighted progress, pagination, highlight allocation
      with the 8-mark cap and the luminance adjust, five palettes
- [x] Normalise the pipeline's `<b style='color: forestgreen;'>` to a bare `<b>`
      boundary — the UI decides how a highlight looks, the pipeline decides what
      is important
- [x] Shelf: category patches, status chips, front-weighted bars, footer
- [x] Reader: header, progress + weight note, resume strip (seam gold), part title,
      body at 19.5px/1.95 46ch, page dots, Next/Previous labels that walk
      page → part → finish
- [x] Finished: status block, "what you kept", far-side recommendation, Show another
- [x] Pointer focus (siblings to 0.28 at 160ms), tap as the touch equivalent
- [x] Persist theme / palette / focusMode / maxHighlights to localStorage
- [x] Register swap is never animated; `prefers-reduced-motion` collapses transitions
- [x] Shelf filter (reading / not started / read) — the design was drawn against
      three books, this shelf holds 264
- [ ] Keyboard navigation (←/→ for pages, Esc to shelf) — the design is touch-first
      but a tablet keyboard is common
- [ ] `maxHighlights` has no control in the UI yet; it persists but only defaults
- [ ] Focus-visible styling audit against the DS rule that focus is louder than hover
- [ ] Empty and error states are plain text; they deserve the same treatment as the
      rest of the surface

### Ambience

- [x] `lib/ambience.js` — the handoff's module, keeping its public contract
      (`play/stop/toggle/setLevel/duck/dispose`, `PROFILES`, `bedForCategory`) and all
      six of its rules: 4s in / 2s out, one master gain, level capped at 0.5
- [x] Recorded beds stream through `MediaElementAudioSourceNode` rather than
      `decodeAudioData` — a 10-minute stereo file decodes to ~200MB of AudioBuffer,
      which is not something to hand a tablet
- [x] Two lanes per recorded bed with an equal-power crossfade, so the loop point is
      never audible. Verified across two passes of the 22s wind file: no dip
- [x] Per-bed `TRIM`, measured with `tools/measure-beds.mjs`. The recordings arrived at
      about -50 dBFS RMS and the synthesized beds ran at -7; without this the same
      slider position is inaudible on one bed and a soundtrack on the next
- [x] Gentle compression on recorded beds — the fireplace file's crackle runs ~35dB
      over its own bed, well past the 12dB the handoff's recording contract allows
- [x] Player UI: quiet `Sound` control in the reader header, suggested bed marked,
      all beds one tap away, level slider, off
- [x] Off by default, one gesture to start, `{bed, level, on}` persisted per book
- [x] Duck -6dB while the resume strip is on screen; restore on page turn
- [x] Silence at the finish screen and on the shelf; stop on unmount and after the tab
      has been hidden for a minute
- [x] Politically charged categories suggest nothing rather than being scored
- [x] Fix the category matcher: the handoff's substring test sent "Business/**Art**up
      Growth" to Forest because `art` is inside `startup`. Single-word keywords now
      match at a word boundary
- [ ] **The trims are calibrated against Chromium's decoder in this sandbox.** They are
      measured, not guessed, but they have never been heard. Listen on the actual
      tablet and adjust `TRIM` before trusting them.
- [ ] The fireplace bed lands ~0.7dB under the others; it is peak-limited by its own
      crackle even after compression. Re-master that file and the trim can come up.
- [ ] Lake and rain are still synthesized — recordings for them would finish the set
- [ ] No control for `maxHighlights` or for ambience on the shelf; both are reader-only
- [ ] Ambience does not survive a page reload mid-book (by design — audio needs a
      gesture — but a "resume sound" affordance would be kinder than silence)

### Library screen

- [x] Drop or choose PDFs, live job progress, and the collection listed with move and
      delete, reachable from the shelf footer
- [x] Filter the collection by title, author or category; 60 rows at a time
- [x] Warn up front when `OPENAI_API_KEY` is missing, rather than letting every upload
      fail silently
- [ ] **This screen has no design file.** It was built in the Tide token language by
      extending the three screens that do. When the real handoff arrives, the layout is
      the part to replace — the API underneath it should survive.
- [x] Covers on the collection rows, and a line saying how far the background lookup has
      got — an automatic thing should be a visible thing
- [ ] Nothing re-runs a lookup by hand. A book Hardcover matched to the wrong edition
      keeps that cover until `data/enrichment.json` is edited; the `force` path exists in
      `enrich.queue` but nothing calls it. A "wrong book" affordance on the row is the
      obvious home for it — and the one place a per-book click would be *earned*
- [ ] Sort options (by title, by date added, by part count) — the order is the shelf's
      order today
- [ ] No bulk selection: moving or deleting twenty books is twenty clicks
- [ ] The collection list is the one place in the app that scrolls a long way; it wants
      either virtualisation or paging once the library outgrows a few hundred books

## DevOps

- [x] Add the three deps the pipeline always needed but never listed (numpy,
      pydantic, requests), plus fastapi + uvicorn
- [x] `dev.sh` (uvicorn + vite with /api proxied) and `build.sh` (bundle into
      `web/dist`, which the API serves)
- [x] `.gitignore` for `web/node_modules`, `web/dist`, `__pycache__`, `/next`
- [x] End-to-end verification in Chromium: shelf → reader → finish, day/night,
      palette cycle, pointer-focus opacities
- [ ] **Self-host the three webfonts.** `tokens/fonts.css` pulls Lexend, Lexend
      Deca, Space Grotesk and IBM Plex Mono from the Google Fonts CDN; that request
      is blocked in some networks (it was in the sandbox this was built in) and the
      reader silently falls back to a system sans — which loses exactly the
      legibility the typeface was chosen for. The DS readme already flags dropping
      real files into `assets/fonts/`.
- [x] Add `python-multipart` (PDF uploads) to requirements
- [x] Verify ingest end to end with the LLM stubbed: a generated 12-page PDF through
      upload → Gaussian chunking → 4 parts → JSON in `books/available` → visible on the
      shelf with the right patch → PDF parked in `pdfs/`, plus the HTTP validation and
      missing-key paths
- [ ] **The ingest pipeline has never run against the real OpenAI API here.** Every
      part of the path is proven except the LLM call itself, which was stubbed. The
      first real book is the test that matters.
- [x] Verify the cover pass with Hardcover and the image host stubbed: the shelf queues
      all 264, the store records found / nocover / missing / failed, a cover is written
      once and served with the right type, a second shelf load re-queues nothing, and the
      download refuses non-images, anything over 6MB, and a name that escapes data/covers
- [ ] No tests anywhere in the repo. The reading model (`weights`, `paginate`,
      `tokensOf`) is pure and the highest-value thing to cover first; the ingest
      harness used for the verification above is a good second, and would have to be
      checked in rather than left in a scratch directory.
- [x] Ship the four ambience recordings under `web/public/ambience/`, served by
      FastAPI from an explicit mount so they get Range support (Safari will not play
      audio without it — verified 206 Partial Content)
- [x] Verify playback for real: signal measured on the master for recorded and
      synthesized beds alike, duck confirmed at exactly -6dB, silence after `stop()`
- [ ] **The audio is 42MB and it is in git history now.** No mp3 encoder was available
      here to re-encode; mono at ~96kbps would be roughly a quarter of the size and
      indistinguishable for a background bed. Worth doing before the repo grows.
- [ ] Add a `web/dist` build step to whatever deploys this; the API serves the
      bundle only if the directory exists
- [ ] Decide the fate of `next_reads.py` / `all.py` / `dashboard.py` — all three are
      now superseded, and `dashboard.py` still points at a folder with no JSON in it
