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
      GraphQL and the search never worked; then `_ilike` with query variables, which
      was valid and *also* never worked: the API answers 403 `ilike and related
      operations are not permitted on this schema`. Now the `search` root field
      (typesense), sorted `users_count:desc`
- [x] Treat a GraphQL error inside a 200 as a failure, so the finish screen never
      claims "marked read" when Hardcover refused
- [x] Verify the Hardcover path against the live API with a real `HARDCOVER_API_KEY`
      — round-tripped at last: search resolves 7/7 real titles to the right book, and
      `insert_user_book` created user_book 17413683 (Make It Stick), read back as
      `status_id: 3`
- [ ] Decide what the finish screen should do when `authorMatched` is false — the
      match was made on title alone and could be the wrong edition
- [x] Enrich automatically, so a cover is not a per-book "Look up" click: `enrich.queue`
      on ingest the moment the JSON is written, and `enrich.queue_missing` on the first
      `GET /api/shelf` that sees a book nobody has asked about — which backfills the
      books that predate the pass and anything `prep.py` wrote past the API. One worker
      thread, 1.5s apart, read-only (`search_book` only, never a mutation)
- [x] Record every attempt in `data/hardcover-lookups.json`, so `found` and `missing`
      are never re-asked and only `failed` retries, after six hours. Without the ledger
      a shelf load during an outage re-queues the whole library
- [x] `GET /api/enrichment` reports how far the pass has got; the library screen shows
      it while it runs. A book Hardcover does not have now reports `hardcover: null`,
      which is what makes "Add to Hardcover" reachable
- [x] `api/profiles.py` + one positions store per profile, so a second person can read
      here without moving somebody else's bookmark. `X-Profile` on every reading
      endpoint, resolved once in `main.reader` (which answered an unknown id with the
      owner at first, and with the guest since the catalogue was opened — see below)
- [x] Migrate `data/positions.json` onto `data/positions/owner.json` on first load — the
      reading from before profiles belongs to whoever made it
- [x] A book's `state` is the reader's; `filed` is where the JSON sits. Only the owner's
      finish re-files it, and only the owner's finish reaches Hardcover — one key, one
      account — so a guest's finish returns `markedRead: null` and the screen says so
- [x] Preferences belong to the reader, not the tablet: theme, palette, focusMode and
      `maxHighlights` are on the profile row (`PUT /api/profiles/{id}/prefs`,
      whitelisted server-side). localStorage keeps a copy for the first paint only, so
      the app never opens in the default register and then swaps
- [x] The ambience bed is per book *per profile*, stored in that reader's position entry
      and delivered on the book payload — two people reading the same book keep their
      own bed, and either keeps it on whichever tablet they pick up
- [x] An optional PIN per profile: set it on your own row, and the app will not switch
      into that profile without it, opens onto the picker instead of that reader's
      shelf, and offers a Lock in the shelf footer. Salted scrypt, never returned to a
      browser, the old one needed to change or remove it, five tries then a doubling
      lockout
- [ ] **The PIN locks the picker, not the API.** `X-Profile` is still self-asserted, so
      `curl -H 'X-Profile: <id>'` reads a locked profile's shelf. Making it real means
      the server issuing a token on unlock and every reading endpoint checking it —
      worth doing only if this ever leaves the house
- [ ] No idle auto-lock: a locked profile stays open until somebody presses Lock or the
      app is reopened. A timer is the obvious next turn of the screw
- [ ] A locked profile can still be renamed, and a guest's can be deleted, without the
      PIN. Deleting destroys rather than reveals, so it is not a way *in* — but it is a
      way to lose somebody's reading
- [ ] The profile is chosen in the browser and sent as a header, so two tabs on one
      tablet can be two readers. That is either a feature or a surprise; nothing tests
      which
- [x] Three kinds of reader, as three dependencies in `main.py`: `reader` (anyone, the
      catalogue is open), `keeper` (a profile, for anything kept) and `admin` (the owner,
      for anything that changes what is on the shelf)
- [x] An absent or unknown `X-Profile` now resolves to a **guest**, not the owner. It
      used to hand the owner's reading to any request that left the header off
- [x] A guest may read the whole catalogue and keep nothing: positions, finishes and
      beds 403 with the sentence that says what to do, and the app does not offer them —
      the last page reads "Back to the shelf" rather than "Finish book"
- [x] Only the owner may upload, price, delete, re-file, look up, contribute or re-sync.
      Enforced server-side; the Library link is hidden for everyone else, which is the
      label on the rule and not the rule
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
- [x] Persist theme / palette / focusMode / maxHighlights — on the profile, with
      localStorage as a first-paint cache rather than the source of truth
- [x] Register swap is never animated; `prefers-reduced-motion` collapses transitions
- [x] Shelf filter (reading / not started / read) — the design was drawn against
      three books, this shelf holds 264
- [x] "Because you read X" on the shelf's not-started filter: the unread book nearest
      this reader's finished ones, named with the book it came from. Nothing for a guest
- [ ] The suggestion reads one signal — category words, with the patch family as a
      tie-break. It has no idea what a reader *abandoned*, which is at least as strong
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
- [x] Off by default, one gesture to start, `{bed, level}` persisted per book per
      profile (`on` is not kept — nothing may autoplay, so a bed is restored as a
      choice and never as sound)
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

### Profiles screen

- [x] Pick, add, rename and remove readers; each row carries a tone, a name and what
      they have read, so the list is scannable before it is read
- [x] The owner can be renamed but not deleted — their reading is the shelf's own
- [ ] **No design file.** Built in the Tide token language from the shelf's shape.
- [ ] No avatars or per-profile ambience; a tone square and an initial is the whole of
      the identity
- [ ] Switching reader mid-book drops you back on the shelf. Resuming where *that*
      reader stopped in the same book would be kinder, and is one `getBook` away

- [x] An optional PIN, set from your own row: a lock mark on the name, an inline prompt
      when somebody picks that reader, and Set / Change / Remove on the row itself
- [ ] The lock screen is the profiles screen with the way out removed. It reads well
      enough, but a screen whose whole job is one PIN could be drawn as one

### Library screen

- [x] Drop or choose PDFs, live job progress, and the collection listed with move and
      delete, reachable from the shelf footer
- [x] Filter the collection by title, author or category; 60 rows at a time
- [x] Warn up front when `OPENAI_API_KEY` is missing, rather than letting every upload
      fail silently
- [ ] **This screen has no design file.** It was built in the Tide token language by
      extending the three screens that do. When the real handoff arrives, the layout is
      the part to replace — the API underneath it should survive.
- [ ] "Look up" is now a retry, not the way covers arrive — but nothing on the row says
      which books the automatic pass got *wrong*. A cover matched on title alone
      (`authorMatched` false) looks exactly like a right one, and `enrich.queue(force=True)`
      is written and uncalled. A "wrong book" affordance is the obvious home for it, and
      the one place a per-book click would be earned
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
- [x] **A test suite, where there was none.** 104 tests over the pure logic: the
      reading model (weights, progress, pagination, highlight budget, palettes), the
      ambience category mapping, the patch families, the library's text helpers, and
      the reading-history store. `./test.sh` runs both halves; neither needs a
      dependency that is not already here (`unittest` is stdlib, `node:test` is built
      in) and neither needs an API key.
- [ ] The tests cover pure functions only. Nothing exercises the FastAPI endpoints,
      the React components, or `library.shelf()` against a real books/ tree — those
      need fixtures and a client, which is a bigger piece of work.
- [ ] The ingest harness used to verify the pipeline still lives in a scratch
      directory rather than the repo. It needs a checked-in sample PDF and a stubbed
      LLM to become a real test.
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
