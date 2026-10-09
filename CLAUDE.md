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
./dev.sh                      # FastAPI :8001 + Vite :5173 with /api proxied; open :5173
./build.sh                    # bundle web/ into web/dist
uvicorn api.main:app --port 8001   # serves the API *and* web/dist when it exists

# Ingest — now also available in the reader itself, on the library screen
streamlit run app.py          # upload a PDF and summarize it live, chunk by chunk
python prep.py                # batch: summarize every PDF in ./next -> books/available, PDF to ./pdfs

# Tests. Two suites, both run by hand — there is no CI. Read the counts, not just the colour:
cd web && npm test                      # the reading model's rules (Node's runner; asks Python for the coals)
python -m unittest discover tests       # who may change a profile (stdlib; runs against a temp data/)

# Scratch
python homework.py            # scratch script: generates a quiz question from one hardcoded book
python hardcover/request.py   # exercises the Hardcover API against a hardcoded title/author
```

`.env` (gitignored) must provide `OPENROUTER_API_KEY`, and `HARDCOVER_API_KEY` for the Hardcover
integration. `util/chatgpt.py` reads it at import time (falling back to `OPENAI_API_KEY`), so *any*
import of the chunking or meta modules fails without a key — but `api/` does not import them, so the
reader runs without one. `OPENROUTER_MODEL` overrides the default model.

Three more, all optional and all about this machine rather than the app: `BOOKS_PORT`
and `BOOKS_BIND` for the Windows autostart (`deploy/windows/`), and
`BOOKS_TRUSTED_PROFILE`, which logs requests from this computer in as that reader with
no PIN. The last is opt-in for a reason - behind nginx every proxied request arrives
from 127.0.0.1, so setting it on a public deployment would hand the owner's account to
the internet. `api/profiles.py`'s `trusted_profile_for` says so at length.

`BOOKS_ACTIVITY_KEY` switches on `GET /api/activity/today` for other apps: send it as
`Authorization: Bearer <key>`. Unset, the route answers 404, so a deployment that never
asked for it has no new way in. See "Activity for other apps" below.

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

**Every summary is checked before it is kept** (`util/summary_checks.py`, applied in
`highlight_chunk`). The descriptions set a length (120 words for the first part, 220 after)
because "two paragraphs" alone let a few parts run past 1,300 words, which the reader then
packed five walls deep. Over `MAX_SUMMARY_WORDS` (350, just past the library's 99th
percentile) a summary gets one `condense` call; a result that is cut off mid-sentence or
keeps under a quarter of the words is retried once and otherwise discarded, because two
parts of *One Nation Under Blackmail* came back truncated and were nearly saved that way.
A summary **cut off mid-sentence** parses fine, so `llm_strict`'s retries never see it: 14
parts were saved that way, one ending "he concludes that **passion is". It is asked for
once more and then trimmed to its last complete sentence (`trim_to_last_sentence`), and the
reader drops any `**` left unpaired.
A summary that reports on the text ("This text explores…", "In this section…", 12% of the
library) gets `make_direct`, which is **surgical, never a rewrite**: the model returns only
the offending sentences with replacements, and the swap is refused if a paragraph, a `**`
pair or any HTML tag would change. A whole-summary rewrite was tried first and dropped the
point of *Deep Work* part 2. References to the book's layout ("In CHAPTER FIVE", "(Figure 21)", "Page 87 elaborates";
99 parts) are fixed the same way, by `points_at_layout`. **A sentence may only change if the
checks themselves flag it, and its replacement must pass them** — told in words to leave
attribution alone, the model still turned "He also suggests that perhaps…" into "Perhaps…".
Two rules in `DIRECT`/`HEDGES` pull against each other on
purpose: drop the text-as-document framing, **keep every hedge and attribution** ("alleged",
"Grabbe suggests"). Without the second, "the suspicious circumstances of Vince Foster's
death" became a flat claim about a real person.

`tidy_parts.py` applies the same checks to books already on the shelf: dry run by default,
`--write` to spend, `--only cutoff|long|openers`, `--book <substring>`. It backs every file
up to `data/backups/tidy-<time>/` before writing. **Do not rely on git for that** — a book
ingested since the last commit is not in git, and *The Art of Perfumery* was rewritten in
that state with no way back. On the structured format every fix replaces or drops whole
sentences, so there is no HTML to convert back and nothing to skip.

Conversation state is a `util.history.History` — a thin list of `{role, content}` dicts. The pattern
throughout is to push each page's raw text as a `system` message, then a single `user` instruction.

**Storage format: paragraphs of sentences, no HTML.** Each book is one JSON file, named
`sanitize_filename(title).json`:

```json
{"meta": {"title", "author", "category", "publisher", "pages"},
 "parts": [{"title": "...",
            "paragraphs": [{"sentences": ["Grit beats **talent**.", "..."]},
                           {"heading": "Lessons from Experience", "sentences": ["..."]}]}]}
```

A highlight is `**` inside one sentence, and that is the only markup. The model returns this
shape directly (`summary_paragraphs` in `chunks.py`), so **sentence boundaries are the
model's, never guessed**. Until October 2026 a part was one HTML `body` from
`chunks.format_text`, and the reader cut it into sentences itself: every wrong cut (an
abbreviation, a closing quote, a `<br>`, an `<h3>`, a highlight spanning a full stop) became
a paragraph break in the middle of a sentence. `web/tools/migrate-structured.mjs` converted
the library using the reader's own splitter, so every book read exactly as before, and
checked each part kept its words. A part that still has only a `body` is read through
`util/parts.py` (Python) and `partParagraphs` (`web/src/lib/pages.js`), which every
consumer goes through: the API, reader, print sheet, Streamlit and `homework.py`.

**Book lifecycle.** `books/available/` holds unread summaries, `books/read/` holds finished ones.
`POST /api/books/{key}/finish` means two things and profiles pull them apart. It always
records the finish for the reader who asked. For the **owner** it also moves a file between the
two folders: it calls
`hardcover.request.mark_book_as_read` (GraphQL search + `insert_user_book` mutation with
`status_id: 3`), then `shutil.move`s the JSON into `books/read/`. The move happens either way — the
book *was* read — but `markedRead` is only true when Hardcover accepted it, and the finish screen
never paints the green chip otherwise.
`prep.py` feeds the other end, consuming PDFs from `./next` and parking the originals in `./pdfs`
(both gitignored, both absent from a fresh clone — `prep.py` creates the output dirs but expects
`next/` to exist).

## The reader (api/ + web/)

Implements `design_handoff_bookv3_reader`, built on the Tide design system. Five screens — shelf,
reader, finished, library and profiles — sized for a tablet in portrait (an 834px card on a
coloured "desk").

The first three come from the handoff and are high fidelity to it. The library's row
components (estimates, jobs, the collection, covers) live in `web/src/screens/library/`, with
their shared formatting in `format.js`; `screens/Library.jsx` is the screen that composes them.
**The library and profiles screens have no design file**: both are extensions written in the same token language. The library
deliberately breaks the reader's "one unit of work per screen, never a scroll" rule, because
managing a collection needs an overview that reading does not; profiles keeps the rule, and is
built like the shelf — a column of rows to choose between. Re-skin them, don't reason from them.

**`api/`** is mostly read-only over `books/`. `main.py` is only the app — middleware, the
routers, the built frontend — and the routes live in `api/routes/`, one module per area:
`session` (health, who this machine answers as), `profiles`, `reading` (shelf, book,
position, ambience, finish), `hardcover`, `collection` (re-file, delete) and `ingest`. A
route's permission is its `Depends(reader)`, `Depends(admin)` or `Depends(self_or_owner)` from
`api/deps.py`; a route with none is open, which is right for health, session, the picker and
unlock and is worth checking before anything else is added to that list. `library.py` scans both folders into shelf entries (the
key is the filename stem, so a lookup never path-joins caller input); `patches.py` collapses the
pipeline's free-text `meta.category` onto a patch family; `positions.py` is the only place reading
history has ever been stored (`data/positions/<profile>.json`: part, page, lastReadAt, startedAt,
sittings, and the Hardcover outcome).

`profiles.py` is who that history belongs to. One file each under `data/positions/`, listed in
`data/profiles.json`, chosen by an `X-Profile` header that every reading endpoint resolves through
one dependency (`reader` in `api/deps.py`).

**Two kinds of reader, and the difference is what they may do.** `api/deps.py` says it in three
dependencies rather than in scattered `if` statements:

- `reader` — a named profile that has proved it. There is no anonymous access and no guest:
  every endpoint under `/api` except health, session, the picker (`GET /api/profiles`),
  `unlock` and the cover counts (`/api/enrichment`) refuses a request that names nobody. `X-Profile` says who, `X-Device` proves it, and a profile with a
  PIN is refused without a live token from its unlock. A profile with no PIN is still taken at
  its word — the house model where it still makes sense — so on a public deployment every
  profile should carry one.
- `admin` — the owner. Everything that changes what is *on* the shelf: ingest, delete, re-file,
  the Hardcover re-sync, the contribution — and adding a reader, since a new profile has no PIN
  and would otherwise be anybody's way in. Everything that changes what somebody has *read of*
  it is the reader's.
- `self_or_owner` — changing one profile: its name, PIN, settings, Hardcover link, remembered
  devices, or deleting it. Only that profile's own proven reader, or the owner. These were open
  until the public deploy made that a hole (anyone could delete a reader, or point somebody's
  finishes at their own Hardcover account); `tests/test_profile_permissions.py` pins it, and
  the picker only offers Rename, Delete and Add where the server would allow them.

There used to be a third, `keeper`, separating "the catalogue is open to read" from "a record
needs a name". Both halves of that distinction collapsed when the catalogue stopped being open:
every reader is named now, so `keeper` had nothing left to check and is gone.

**This is no longer only the house's rule.** The older note here said `X-Profile` is asserted by
the client and therefore not a permission system. That was true and is not any more. The device
token — 32 bytes from `secrets`, stored as a SHA-256 hash with an expiry, minted only by a
correct PIN — is checked on every request, so a locked profile cannot be claimed by anyone who
cannot open it. Guesses are rate limited against the profile *and* the caller's address, in
`data/pin-attempts.json` rather than in memory, because a restart used to forgive everything and
a deploy is a restart.

Five more rules, about the readers themselves:

- **The settings are the reader's too.** Register, palette, pointer focus, the highlight cap,
  and how they left the shelf (its order, `shelfSort`, and the spiral band per filter,
  `spiralBands`) live on the profile row, not in localStorage — `PUT /api/profiles/{id}/prefs`, whitelisted by
  `clean_prefs` because it comes off the wire. The browser keeps a copy for the first paint only:
  the profile's settings arrive a round-trip after mount, and without a cache the app would open
  in the default register and then swap, which is the one thing the design says is never animated.
  Saves wait half a second after the last change (`SAVE_DELAY`), because the spiral slider
  sends one for every tenth it passes.
- **The books are one shelf; the reading is not.** `books/available` and `books/read` are the
  house's filing. A book's `state` is the *reader's* — finished by them, or in progress — while
  `filed` is where the JSON actually sits. The owner is the exception the folder exists for: the
  contents of `books/read` are their history, because they filled it before profiles existed.
- **Hardcover is the owner's.** There is one key and it is one person's account, so only the
  owner's finish calls `mark_book_as_read`, and `/hardcover` (the re-sync) is 403 for anyone else.
  Another reader's finish returns `markedRead: null` — nothing was sent, which the finish screen
  says rather than showing them a chip about a call nobody made.
- **The owner cannot be deleted, only renamed.** Their reading is the shelf's own; handing the
  tablet over is a rename.
- **The PIN is the login now.** It did not start that way. This was a tablet in a house, the PIN
  guarded the picker rather than the API, and the note here said plainly that anything able to
  make an HTTP request could still read as anyone — so do not build on it. Going onto a public
  URL is exactly the change that made that unacceptable, and the "next tier" it described is
  what is now built: the server issues a token and every reading endpoint checks it.

  How it holds together. A correct PIN mints a device token — 32 bytes from `secrets`, stored
  only as a SHA-256 hash, with an expiry the server keeps rather than the browser. Unlock always
  mints one, because the token *is* the session; "remember this tablet" chooses ninety days
  instead of twelve hours, not whether you get one. `resolve` checks it on every request for any
  profile carrying a PIN, so `X-Profile` is a claim and `X-Device` is the proof.

  The rest, because a half-done lock is worse than none: the digits are never sent to a browser
  (`profiles._public` strips them, so there is no serialiser to forget), the stored form is
  salted and run through scrypt, changing or removing one needs the old one, and guesses are
  counted against two budgets — five per profile and twelve per address, each with a doubling
  pause — in `data/pin-attempts.json`, on disk, because 10,000 combinations is otherwise a
  minute of scripted tries and an in-memory counter forgives them all at the next restart.

  A profile with no PIN is still taken at its word. That is the house model surviving where it
  costs nothing, and it is also the one thing to check before a public deploy: an unlocked
  profile on a public URL is an open door with a name on it.

  **One address may skip the PIN.** `BOOKS_TRUSTED_PROFILE=owner` answers requests from this
  computer as the owner without asking: the machine serving the library does not need to
  prove to itself who is sitting at it. `GET /api/session` is how the app learns that before
  painting a lock screen it does not need - `reader` cannot answer it, because its answer to
  "nobody" is a 401. Measured both ways: from loopback the shelf answers 200 with no headers
  at all, and from the LAN address the same request is 401, so the tablet still enters a PIN.

`data/positions.json`, the single store this replaced, is *moved* onto `data/positions/owner.json`
the first time `positions.py` loads, so history from before profiles belongs to whoever made it.

**Activity for other apps.** `routes/activity.py` is the one route that is not a reader's: a
calendar or dashboard has no tablet and no PIN, so it authenticates with `BOOKS_ACTIVITY_KEY`
instead of `Depends(reader)` (the "a route with none is open" check above does not apply —
the key is its guard). Read-only, 404 when the key is unset. `?tz=Europe/Amsterdam` cuts the
day (default: this machine's clock), `?profile=<id>|all` picks readers (default `owner`),
`?date=YYYY-MM-DD` asks about another day. What it can say is bounded by `positions.py`,
which keeps only `lastReadAt` and `finishedAt`: `finished` is exact for any day, but
`touched` is only trustworthy for today, because a later save overwrites the date and there
is no per-day log. `tests/test_activity.py` pins this.

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

**Quests on the finish screen.** `quests.py --book <substring> --write` makes three quests
per book, one for each moment: the reader's **next break** (5 to 15 minutes, nothing to
buy), **tonight** (one evening at home) and **this weekend** (four hours or more, ending in
something done). A goal is concrete when it says when; Daan asked for moments over sizes.
They are stored as `small`, `medium` and `large`, the keys starts, reflections and passed
lists already use, and the model is given the weekday so "tonight" is a real night. The
judge checks `fits_moment` beside season, food safety and practice. It first lists the book's *methods and topics*, with their parts, and every
quest must name one, checked in code, plus three different ones when the list has three.
A quest may go past what the summary describes as long as it stays on that subject: the
list was methods-only at first (a worm bin was proposed from "building living soil" once),
and Daan chose topic over page. A quest happens where the subject is practised: for a
business or self-help book the reader's own work and projects, never household chores in
the book's words, which is what The Invincible Company got until the prompt said so. Steps
that open with a verb of thought ("Think of", "Consider") are rejected in code
(`thinking_steps`), because the description forbidding them was ignored. A second call (`review`, GPT-4o) then
judges season, food safety and practice-not-decoration, and a failing set is asked for
again with the reasons, three tries, else nothing is saved. It still lets an out-of-season
quest through sometimes (Three Sisters in October). Stored in `data/quests/<key>.json`
(`api/quests.py`): title and a one-line `short` for the card, then `source`, `needs`,
`steps` and `doneWhen` for the plan the card opens into. `Finished.jsx` shows them as a
row of three; the picked one joins its plan like a tab. "Start this quest" records the
start per reader in `data/quests-started/<profile>.json`: the hand-off a daily quest list,
here or in Roads, will read. Nothing generates quests when a book is finished yet.

**Rerolling keeps what was taken up and remembers what was turned down.** The owner can
ask for new quests on the finish screen (`POST /api/books/{key}/quests/reroll`, 202, then
the screen polls `GET .../quests` for `reroll`); a book with no set gets its first one the
same way. It runs `quests.reroll` on its own one-thread worker (`api/quest_reroll.py`,
pipeline imported inside, as in `jobs.py`). Sizes **any** reader started or finished are
kept, re-read just before saving, because starts and reflections point at a size and
replacing one would hand them to a different quest. The replaced quests go into the book
file's `passed` list, and every later reroll is told them and checked against them in code
(`too_close`: half the title words in common), since asked in words alone a model rewords
its favourite. The refresh icon first asks for an optional **direction** ("indoor plants"
for Homesteading for Health): the model follows it past what the book covers but must tie
each quest to a listed method or topic, the three-different-anchors rule is waived, and the
quest keeps `direction` so the plan can say so. Each quest is checked on its own
(`quest_problems`: its moment's minutes, steps, a listed anchor, no thinking verbs, no
repeat; then the judge), and a retry keeps every quest that passed and rewrites only the
rest (`locked`). Rewriting all three let one stubborn quest sink sets whose other two had
passed three times, and let a new "Consider…" step turn up somewhere else each attempt.
Anchors match by `method_key`, ignoring the "(part 3)" the model copies from the list. Eight live runs took
10 to 64 seconds, the spread being retries, so the screen says "usually 15 to 60 seconds"
and counts up. `quests.py --force` goes through the same function. GPT-4o writes as well as
judging (`QUEST_MODEL`), not `OPENROUTER_MODEL`: Gemini Flash built quests on topics the
summary only names.

**A quest ends in a reflection, not a tick.** "I did it" opens three questions inside the
plan: what happened, what went wrong, and why the book asks for it this way. All three
are required (the route answers 422 on a blank one), because the product's bet is that
doing, getting it wrong and asking why is what turns a summary into knowing; a bare
checkbox would reward finishing over learning. Stored per reader in
`data/quests-done/<profile>.json`, apart from the starts, and an edit keeps the day it
was first done. The way back days later is the book: the shelf sends `questsOpen` per
book and swaps a read book's chip for "quest open", and opening a read book lands on its
finish screen.

**Every book has a Spiral Dynamics level**, 3 Red (power) to 8 Turquoise (wholeness),
shown as a pill (a dot in the level's colour and its canonical name, StriveDrive for Orange, or both names between two levels) on the shelf row, the reader header, the finish screen and the "More like
this" cards. `spiral.py --write` grades from the summary (gpt-4o-mini, three calls a book, about
$0.001 together; `--book`, `--force`), and `api/spiral.py` keeps the grades in
`data/spiral.json`, beside the books like the Hardcover cache; the shelf sends
`book.spiral`. It grades the value system a book *argues from*, not its subject. The first
descriptions let the model call strategy books Yellow and the Stoics Yellow; it now
grades conservatively (most non-fiction is 4, 5 or 6; innovation and self-improvement are
5, virtue and discipline 4; 7 and 8 only when the book itself integrates worldviews or
argues the unity of life). Grades are decimals, 3.0 to 8.0, so a progression inside a
level shows (5.6 is Orange well on the way to Green). The pill names a band
(`band_of`): a level's core runs from .8 below it to .2 above (4.8 to 5.2 is
StriveDrive), and between two cores a transition names both (5.3 to 5.7 is "StriveDrive →
HumanBond", the dot in the higher level's colour). Daan chose these bands after a
whole-number pill put 200 of 280 books under StriveDrive; rounding to the nearest level
before that showed books the grader called "Green reaching toward Yellow" as Yellow. The
slider's track is solid across each core and blends across each transition. A rank in the
library ("top 20%") was tried after the name and removed: it made the pill too long, and
the grades take few distinct values (100 books are exactly 5.5), so it separated groups
on steps inside the grader's own noise. Each book is graded three
times on gpt-4o-mini, and `combine` averages the runs unless one is more than 0.5 from
the other two, which is dropped: single runs moved by up to a whole level. A new book is graded as the last step of ingest (`api/jobs.py`, and `prep.py`) by the
same `grade_and_save`, so it arrives with its pill; a failure there leaves it ungraded,
never fails the job, and `spiral.py --write` picks it up later.

**Each book has a fit with the nine intelligences**: Gardner's eight plus existential,
named and explained as on the canvas's "Ways in" page and in `docs/roads-project.md`
(linguistic, logical-mathematical, visual-spatial, musical, bodily-kinesthetic,
naturalist, interpersonal, intrapersonal, existential). `intelligences.py --write` rates
each 0 to 3 from the summary's first three parts (`SYNOPSIS_PARTS`; as good as twelve on
the benchmark, at half the cost) and picks a `primary`, one gpt-4o-mini call a book; `api/intelligences.py` keeps them in
`data/intelligences.json` and the shelf sends `book.intelligence`. The pill (outlined, no
dot, so it never reads as the spiral one) shows the primary on the shelf, the reader and
the finish screen. A select beside the order narrows the shelf to books with a fit of 2
or 3 for one intelligence, those with a 3 first, saved per reader as `shelfIntelligence`;
it is hidden until books are graded. Benchmarked on the ten "Ways in" books (October
2026): Gemini 2.5 Flash matched the canvas's intelligence on 7, gpt-4o-mini on 6, and
gpt-4o-mini rated linguistic 3 on most books whatever they were about.

`POST /api/books/{key}/enrich` stays for the one case the pass cannot serve: asking again about a
book it matched to the wrong edition.

`estimate.py` prices a book before anything is spent, and is deliberately free of the pipeline's
imports so it works with no API key: it reads the PDF with `pypdf` directly and shares chunk
boundaries with `chunks.py` through `util/split.py`. The cost model rests on one fact about the
pipeline — chunks are contiguous and non-overlapping, so the whole book is sent as input *exactly
once* whatever the chunk count (the first five pages go twice, for `get_book_meta`). More parts
therefore cost almost nothing extra; a longer book costs linearly more. Output constants are
measured from 254 committed summaries, not guessed; the header of that file shows the figures.

**A book is cut into one part per 25 pages, never more than 20** (`util/split.py`
`default_parts`, used by the estimate, `jobs.py` and `prep.py`; a part count somebody
chooses still stands). Without the cap Godel, Escher, Bach (821 pages) came out as 33
parts and 10,000 words. Its first part was also 2,684 words, because `condense` refused
any answer under a quarter of the original, which a real shortening of a very long part
always is; the floor is now a quarter or a third of `MAX_SUMMARY_WORDS`, whichever is
smaller (`CONDENSE_FLOOR`), which still refuses the 65-from-374 cut-off it was for. GEB
was then mended by hand: part 1 redone from page 5, past the cover, copyright and
dedication, and the parts merged pairwise from 33 to 17 (4,336 words).

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

**`web/`** is Vite + React.

`src/lib/recommend.js` holds the finish screen's suggestion, `recommendations`, which offers
the book *furthest* from the one just put down, because switching topics beats stopping.
`uncategorised` is a stop word there: it is `library.py`'s fallback for the 68 books with no
category, and two books sharing it share nothing. Above it, **More like this** offers up to
three unread books *nearest* the finished one, so the screen ends in a choice: a quest, a
book on the same subject, or a switch. Nearness comes from `api/similar.py`
(`GET /api/books/{key}/similar`): a TF-IDF vector over each summary's words, highlights
and title counting extra, compared by cosine, built once and rebuilt when a file changes.
Category words could not do it: 67 books have none, and "Homesteading" or "Stoicism" stand
alone, so a category match found nothing for exactly the books that needed it. The shelf has no suggestion any more — it
had `fromLibrary`, the unread book nearest what the reader had finished, and it was removed in
favour of shuffling: the shelf's default order is `shuffled` (App.jsx), a new order each time
the app opens and a stable one while filters change, so there is always something new in
view. "Recently added" is the other order, and "Spiral, low to high" / "high to low" sort by the
Spiral Dynamics grade (ungraded books last); A–Z is gone. The order is a select now, not a
swap button. On "Not started" and "Read" a two-handled slider, its band kept per filter, (`components/SpiralRange.jsx`,
in tenths, from the lowest grade among that filter's books to the highest, the band coloured by
level; a histogram above it was tried and removed) narrows them to a band of the spiral; a narrowed band leaves out
ungraded books, and "Whole spiral" resets it. On a phone (`useNarrow`, below
600px) the shelf drops its introduction and the order toggle, leaving the three filters.

`src/lib/reading.js` is the model and the part worth understanding. It is an index over four
modules — `colour.js` (conversion, linear-light blending, `legible`), `palettes.js` (the five
palettes and `paletteFor`), `coals.js` (the reading page's highlights) and `pages.js`
(pagination, the progress curve, the highlight budget) — and callers import from it, not from
them. `web/test/reading.test.mjs` pins the rules below; run `npm test` in `web/` after touching
any of them. There is no CI: a suite that collected zero tests, or failed to start, would also
look quiet, so read the `tests N / pass N` line rather than the absence of a red one.

- **Front-weighted progress.** The first 40% of parts carry 80% of the bar. `progressOf` uses
  `pageIndex`, not `pageIndex + 1` — the page you are on is in progress, not read, and 100% belongs
  to the finish screen alone.
- **Pagination.** Two sentences to a paragraph, two paragraphs to a page, so a part is two or three
  pages and the bar moves inside a chapter. At most `MAX_PAGES_PER_PART` (5) pages; past that
  pages get denser, which is why an overlong summary reads as walls of text. A last page under
  `LAST_PAGE_MIN_SHARE` of the one before is a fragment and is folded into it.
- **Highlighting.** The pipeline's `**` decides *what* matters; the UI decides *how* it looks.
  `partParagraphs` turns each `**` into the `<b>` the reader's tokens use, then
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

  **In the reader, colour and heat are separate.** The colour of a highlight is the
  reader's palette swept across the page — `paletteFor(prefs.palette, day, n)` with `n` the
  page's distinct phrases, so the first is the start of the ramp and the last its end and
  every page shows the whole spectrum. Until October 2026 the colour came from three
  *coals* per book category (`COALS` in `api/patches.py`, red/orange/gold for most
  shelves), and the palette reached only the progress bar; Daan asked for the full
  spectrum. `book.coals` is still sent and `coalsFor` still exists, but the reader no
  longer draws from them. Heat comes from `phraseCounter`: how often the book mentions the
  phrase anywhere, so a subject burns hot and an aside smoulders. The pipeline's `<b>` is
  binary and carries no importance of its own; this is the proxy, and it is relative to the
  page (`heatsOf`: top quarter hot, bottom quarter smouldering). Heat now decides only how
  hard a phrase burns: at night a layered glow in the phrase's own colour (`glowOf`) that
  breathes (`.coal-*` in `app.css`, off under reduced motion), by day its weight.
  `paletteFor` already moves every stop into the register's legible window.

  `patches.py`'s keyword list is first-match-wins, so order is precedence: `engineer` sits
  above the technology needles or "Technology & Engineering" would never reach its family.

  `node web/tools/check-palettes.mjs` prints contrast, saturation and adjacent ΔE for every palette
  in both registers, against the previous behaviour. Re-run it if these numbers are touched.

  `node web/tools/export-theme.mjs` writes `docs/colour-themes.md`, which is how another project
  takes these colours: the register tokens, the raw bands, and — the part that cannot be copied by
  hand — the eight stops each palette is actually painted in, computed by calling `paletteFor`
  rather than transcribed. Generated and idempotent, so regenerate it rather than editing it, and
  regenerate it whenever a palette or a constant above changes.

Colours, type and spacing come from the vendored token layer in `web/src/ds/` — edit tokens, not
hard-coded values. **The screens follow 60-30-10** (October 2026; before it every screen
measured about 93 · 5 · 1.5, one ground with nothing in the 30; after, across six screens at
tablet size, 57 · 33 · 4.5, with text and highlights the rest): the **sheet** you read on is
graphite (`--bg-sheet`, `#1C1C1C`; paper by day), the **frame** round it, meaning the card's
header, footer and margins plus the desk, is indigo (`--bg-frame` `#1A1C48`, `--bg-desk`
`#0E1030`; lavender by day), taken from the sunset palette's darkest band and darkened so cream
text and the progress bar stay clear, and the **one next action** on a screen wears the
accent, the mark's orange `#F68318`: the book you are reading on the shelf, Next part in the
reader, the next-break quest on the finish screen. `Sheet` in `components/ui.jsx` is the
graphite panel; the reader's swipe surface is its own sheet because it also clips the page
turn. The sheet stays neutral on purpose, so the coals are still the only colour in the text.
The library and profiles screens put their working area on a sheet too (the drop target
through the collection; the readers and the add form). The frame and desk carry an
**aura**: three soft blobs from the start, middle and end of the reader's palette, at
16% alpha by night and 20% by day, drifting over a minute or more (`.aura` in `app.css`,
colours set in `App.jsx`). It moves by transform only, so it composites instead of
repainting, and it holds still under reduced motion. The sheet never gets it: the text
sits on a still, neutral page.

**The design canvas** is https://claude.ai/artifact/CvG6T9GPCVny3YnfwWrqYQ ("Snippers
design"): every screen as built, captured from the running reader, on a page per feature
(shelf, reading, quests, library, profiles), then the unbuilt ideas (quests through the
reader, choosing quests, Roads) and the 60-30-10 history the frame was chosen on. It
replaced three earlier canvases; recapture its screens when a screen changes. The desk is its own token,
`--bg-desk`, painted on `<body>` by `app.css`; for that to flip, `.shore` goes on `<body>` as
well as on the app's root (`App.jsx`, `Design.jsx`), because the desk sits outside the card.
Screens use the semantic tokens (`--text-*`, `--border-*`, `--bg-*`), which follow the
register by themselves — no `day ? … : …` for a colour. The print sheet is the exception:
it is always ink on paper, so it uses the raw palette (`--ink-*`, `--seam-*`).

**The mark** is an S from Space Grotesk Bold with the pages it came from fanned out behind it,
cooling orange → red → purple → indigo. `web/src/lib/mark.js` is its source of truth — the glyph
is stored as an outline so no icon depends on a webfont — and `components/Mark.jsx` draws it.
`node web/tools/export-mark.mjs` regenerates every icon file from it (favicons, maskable icon,
`assets/bookv3.ico`, and `assets/tray-mark.png`); it needs Python with cairosvg and Pillow.
Page count drops with size by design: five pages from 128px, one from 32px, none below.
`scripts/tray.py` paints its own tile in the state colour and lays the mark on it, so the
state never has to be separated back out of a multi-colour icon. Two rules from the design system are easy to break by accident: **gold is only
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
placeholders captured into session state are reused as render slots. `app.py`
additionally pre-computes the *next* chunk's summary during the current rerun (`next_highlighted`) to
hide LLM latency behind the user's reading time.

## Known rough edges

Don't treat these as intentional design when editing nearby code:

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
