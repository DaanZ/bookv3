# TODO — reader redesign

Tracking the implementation of `design_handoff_bookv3_reader` (the Tide-based tablet
reader: shelf, reader, finished). Updated as each step lands.

**Decision, per the handoff's "pick one and say which":** option 2 — the reader is a
React app (`web/`) over a small FastAPI service (`api/`) reading the same
`books/*.json`. Streamlit keeps ingest (`app.py`, `prep.py`); `next_reads.py`,
`all.py` and `dashboard.py` are superseded by the new reader but left in place.

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
- [ ] Verify the Hardcover path against the live API with a real `HARDCOVER_API_KEY`
      — the query is correct GraphQL now, but has still never round-tripped
- [ ] Serve part bodies pre-paginated so the reader and any future surface agree on
      page boundaries (currently pagination is frontend-only)
- [ ] Re-summarise or hide the 68 books whose JSON predates `meta.category`

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
- [ ] No tests anywhere in the repo. The reading model (`weights`, `paginate`,
      `tokensOf`) is pure and the highest-value thing to cover first.
- [ ] Add a `web/dist` build step to whatever deploys this; the API serves the
      bundle only if the directory exists
- [ ] Decide the fate of `next_reads.py` / `all.py` / `dashboard.py` — all three are
      now superseded, and `dashboard.py` still points at a folder with no JSON in it
