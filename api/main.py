"""The reader's backend.

Streamlit still owns ingest (`app.py`, `prep.py`); this serves the reading surface —
the shelf, a book's parts, reading position, and finishing a book. It reads the same
`books/*.json` the pipeline writes, and adds nothing to that format.

    uvicorn api.main:app --reload --port 8000
"""

import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api import enrich as enriching
from api import estimate as estimating
from api import jobs, library, positions, profiles
from hardcover.request import contribute_edition, edition_payload, mark_book_as_read

# The reader itself needs no key, but this process reports whether one is present and
# reads OPENROUTER_MODEL for the default estimate. Nothing else here loads .env: the
# pipeline's own load_dotenv lives behind an import the API deliberately does not make.
load_dotenv()

# A book PDF; anything larger than this is very unlikely to be one.
MAX_UPLOAD_BYTES = 200 * 1024 * 1024

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIST = os.path.join(ROOT, "web", "dist")

app = FastAPI(title="bookv3 reader", version="1.0.0")

# Vite's dev server runs on another port; the built app is served from this one.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PositionIn(BaseModel):
    part: int = Field(ge=0)
    page: int = Field(ge=0)


class MoveIn(BaseModel):
    finished: bool


class ProfileIn(BaseModel):
    name: str


class PinIn(BaseModel):
    """`pin` of null removes it; `current` proves you may change one that exists."""

    pin: str | None = None
    current: str | None = None


class UnlockIn(BaseModel):
    pin: str | None = None


class PrefsIn(BaseModel):
    """A patch, so the UI can send the one setting that moved. Every field is optional
    and anything unrecognised is dropped by `profiles.clean_prefs`."""

    theme: str | None = None
    palette: str | None = None
    maxHighlights: int | None = None


class HardcoverIn(BaseModel):
    """`token: null` unlinks the account. The token is never read back out."""

    token: str | None = None


class AmbienceIn(BaseModel):
    bed: str | None = None
    level: float | None = None


def reader(x_profile: str | None = Header(default=None)) -> dict:
    """Whose reading this request is.

    The profile travels in a header rather than the path, because it qualifies every
    endpoint here and none of them is *about* it. An id nobody recognises resolves to
    the guest, so the catalogue answers anyone and nothing personal does.
    """
    return profiles.resolve(x_profile)


def keeper(profile: dict = Depends(reader)) -> dict:
    """A reader who has somewhere to keep things.

    The catalogue is open to read; a page, a finish, a chosen bed are records, and a
    record needs somebody to belong to. The guest is told to pick a profile rather than
    having their reading dropped on the floor silently.
    """
    if profiles.is_guest(profile):
        raise HTTPException(
            status_code=403,
            detail="Pick a profile to keep your place — the catalogue is open, but a bookmark needs a name.",
        )
    return profile


def admin(profile: dict = Depends(reader)) -> dict:
    """The owner, and only them.

    What is *on* the shelf is the house's: adding a book, deleting one, re-filing one,
    and anything that reaches Hardcover. What somebody has *read of* it is the reader's,
    and that is the other dependency.

    The same caveat as the PIN applies and is worth repeating here, where it looks most
    like access control: `X-Profile` is asserted by the client, so this stops the app
    offering the library screen to a guest — not somebody writing an HTTP request. It is
    the house's rule about who adds books, enforced in one place instead of hidden in
    the UI, and it is not a permission system.
    """
    if not profile.get("owner"):
        raise HTTPException(
            status_code=403,
            detail="Only the owner adds, removes or re-files books.",
        )
    return profile


@app.middleware("http")
async def no_store_api(request, call_next):
    """API answers are never cacheable.

    Without this the browser is free to keep one, and it did: a stale server briefly
    answered /api/profiles with the SPA's index.html, the browser cached that under a
    200, and every reload afterwards was served HTML from cache while curl saw correct
    JSON from the same URL. The app reported "Unexpected token '<'" and read as a guest
    with no history, long after the server was fixed.
    """
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/profiles")
def get_profiles():
    """Everyone reading here, with enough of their progress to tell them apart."""
    rows = profiles.all_profiles()
    return {
        "profiles": [{**row, **positions.progress_of(row["id"])} for row in rows],
        "ownerId": profiles.owner()["id"],
    }


@app.post("/api/profiles")
def add_profile(body: ProfileIn):
    row, error = profiles.create(body.name)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return row


@app.patch("/api/profiles/{profile_id}")
def edit_profile(profile_id: str, body: ProfileIn):
    row, error = profiles.rename(profile_id, body.name)
    if error:
        raise HTTPException(status_code=404 if error == "No such profile." else 400, detail=error)
    return row


@app.put("/api/profiles/{profile_id}/pin")
def set_profile_pin(profile_id: str, body: PinIn):
    """Set, change or remove a profile's PIN.

    The digits are hashed in `profiles.set_pin` and never come back out — the response
    says `hasPin`, and that is all a browser is ever told about it.
    """
    row, error = profiles.set_pin(profile_id, body.pin, body.current)
    if error:
        raise HTTPException(status_code=404 if error == "No such profile." else 400, detail=error)
    return row


@app.post("/api/profiles/{profile_id}/unlock")
def unlock_profile(profile_id: str, body: UnlockIn):
    """Check a PIN before the app switches into that profile.

    This is the lock on the picker. It is not access control: `X-Profile` remains a
    header a client asserts about itself, so this stops somebody picking up the tablet
    and reading as you — not somebody writing an HTTP request. Nothing on the reading
    endpoints consults it, and nothing should be built as though it did.
    """
    ok, error = profiles.check_pin(profile_id, body.pin)
    if ok:
        return {"ok": True}
    if error == "No such profile.":
        raise HTTPException(status_code=404, detail=error)
    # 429 for "you are guessing", 401 for "that is wrong" — the screen says different
    # things about them, and the retry-after only makes sense for one.
    raise HTTPException(status_code=429 if "wait" in error.lower() else 401, detail=error)


@app.put("/api/profiles/{profile_id}/prefs")
def set_profile_prefs(profile_id: str, body: PrefsIn):
    """Register, palette, highlight cap — the settings the design calls the reader's
    rather than the app's, kept on the reader.

    By id rather than for whoever the header says, because that is what it is: a change
    to a named profile, which happens to almost always be the one holding the tablet.
    """
    row, error = profiles.set_prefs(profile_id, body.model_dump(exclude_none=True))
    if error:
        raise HTTPException(status_code=404, detail=error)
    return row


@app.put("/api/profiles/{profile_id}/hardcover")
def set_profile_hardcover(profile_id: str, body: HardcoverIn):
    """Link a reader's own Hardcover account, or unlink it.

    Per reader, because a finished book belongs to whoever read it. A profile with no
    token simply never reaches Hardcover — that is a setting, not a failure, and it is
    what makes the marking automatic for the one person who wants it and silent for
    everybody else who reads here.

    Like the PIN, the token goes in and does not come back: the response says
    `hasHardcover` and nothing more.
    """
    row, error = profiles.set_hardcover(profile_id, body.token)
    if error:
        raise HTTPException(status_code=404, detail=error)
    return row


@app.delete("/api/profiles/{profile_id}")
def drop_profile(profile_id: str):
    """Delete a profile and the reading it recorded. The books are untouched — they
    belong to the shelf, not to whoever was holding the tablet."""
    removed, error = profiles.remove(profile_id)
    if error:
        raise HTTPException(status_code=404 if error == "No such profile." else 400, detail=error)
    return {"deleted": removed}


@app.get("/api/shelf")
def get_shelf(profile: dict = Depends(reader)):
    books = library.shelf(profile)

    # Anything nobody has asked Hardcover about goes to the enrichment worker: books
    # that predate the automatic pass, and anything prep.py wrote without going through
    # the API. Returns immediately — the requests happen one at a time on another thread.
    enriching.queue_missing(books)

    return {
        "books": books,
        "counts": {
            "total": len(books),
            "read": sum(1 for b in books if b["state"] == "read"),
        },
        # Who these counts are for. The shelf footer says it out loud, because a shelf
        # that reads "2 read" to one person and "0 read" to another has to.
        "profile": profile,
    }


@app.get("/api/books/{key}")
def get_book(key: str, profile: dict = Depends(reader)):
    detail = library.book(key, profile)
    if detail is None:
        raise HTTPException(status_code=404, detail="No such book.")
    return detail


@app.put("/api/books/{key}/position")
def put_position(key: str, body: PositionIn, profile: dict = Depends(keeper)):
    if key not in library.index():
        raise HTTPException(status_code=404, detail="No such book.")
    return positions.save_position(profile["id"], key, body.part, body.page)


@app.delete("/api/books/{key}/position")
def delete_position(key: str, profile: dict = Depends(keeper)):
    """Start a book again from the beginning — for this reader only."""
    if key not in library.index():
        raise HTTPException(status_code=404, detail="No such book.")
    positions.clear_position(profile["id"], key)
    return {"ok": True}


@app.put("/api/books/{key}/ambience")
def put_ambience(key: str, body: AmbienceIn, profile: dict = Depends(keeper)):
    """Remember the bed this reader chose for this book.

    Beside the bookmark, in the same entry: the handoff's rule is that the choice
    belongs to the book, and profiles make it belong to the book *for this reader*.
    """
    if key not in library.index():
        raise HTTPException(status_code=404, detail="No such book.")
    return positions.save_ambience(profile["id"], key, body.bed, body.level)


@app.post("/api/books/{key}/finish")
def finish_book(key: str, profile: dict = Depends(keeper)):
    """Record the finish for this reader — mark it on their Hardcover if they have one,
    and, for the owner, move the JSON available -> read.

    Finishing means two different things and profiles pull them apart:

    * **"I read this"** is the reader's own record, and always happens.
    * **The shelf entry on Hardcover** belongs to whoever linked their account. It is no
      longer the owner's privilege — each reader brings their own token, so a finish
      lands on the account of the person who actually read the book. A reader who has
      linked nothing never reaches Hardcover, and that is a setting rather than a fault.
    * **Re-filing the house's copy** stays the owner's, because moving a book somebody
      else is halfway through would be answering for them.

    `markedRead` is true only when Hardcover accepted it, so the finish screen never
    paints the green chip on a failed call. It comes back null when nothing was sent at
    all, which is not the same as sending it and being refused.
    """
    detail = library.book(key, profile)
    if detail is None:
        raise HTTPException(status_code=404, detail="No such book.")

    owner = bool(profile.get("owner"))

    # Hardcover follows the *account*, not the office. This used to be the owner's alone
    # because there was one API key and it belonged to them; now a reader links their
    # own, so a finish lands on the shelf of whoever actually read the book and on no
    # other. A reader with no linked account never reaches Hardcover at all, which is
    # what makes this a personal completion list rather than a household one.
    token = profiles.hardcover_token(profile["id"])
    result = {}
    marked = None
    if token:
        result = mark_book_as_read(
            detail["fullTitle"], detail["author"], detail.get("isbn"), token=token
        )
        marked = "error" not in result

    already_read = detail["filed"] == "read"
    moved = None if already_read or not owner else library.move_to_read(key)
    positions.save_position(profile["id"], key, max(0, detail["partCount"] - 1), 0)
    positions.record_finish(profile["id"], key, marked)

    mine = positions.all_positions(profile["id"])
    return {
        "markedRead": marked,
        "hardcoverError": result.get("error"),
        "hardcoverTitle": (result.get("book") or {}).get("title"),
        # True when Hardcover already had it read — the finish still counts, but nothing
        # was written, and the screen should not imply it was.
        "alreadyRead": result.get("alreadyRead"),
        # Matched on title alone; the edition could be wrong.
        "titleOnlyMatch": result.get("book") is not None
        and not (result["book"].get("authorMatched") is True),
        "finishNumber": positions.finish_ordinal(key, mine),
        "finishedTotal": positions.finished_count(mine),
        "moved": moved is not None,
        "movedTo": "books/read" if moved else None,
        # The finish screen says whose count this is, and why nothing went to Hardcover.
        "profile": profile,
    }


@app.get("/api/enrichment")
def get_enrichment():
    """How far the automatic cover pass has got. The library screen shows it while it
    runs, so a thing that happens by itself is still a thing you can watch."""
    return enriching.summary(total=len(library.index()))


@app.post("/api/books/{key}/enrich")
def enrich_book(key: str, profile: dict = Depends(admin)):
    """Fetch cover, rating, genres and the link out from Hardcover, and cache them.

    Read-only against Hardcover: it looks the book up, it does not touch your shelf.

    The automatic pass does this for every book already; this stays for the case it
    cannot serve — asking again about a book it matched to the wrong edition, or one it
    could not reach Hardcover for.
    """
    detail = library.book(key, profiles.owner())
    if detail is None:
        raise HTTPException(status_code=404, detail="No such book.")

    card, error = enriching.fetch(key, detail["fullTitle"], detail["author"], detail.get("isbn"))
    if error:
        raise HTTPException(status_code=404, detail=error)
    return card


@app.get("/api/books/{key}/contribution")
def preview_contribution(key: str, profile: dict = Depends(admin)):
    """What would be submitted to Hardcover for a book it does not have.

    A GET, and it sends nothing: the point is that the payload can be read before anyone
    agrees to publish it.
    """
    detail = library.book(key, profiles.owner())
    if detail is None:
        raise HTTPException(status_code=404, detail="No such book.")

    payload, error = edition_payload(
        detail["fullTitle"], detail["author"], detail.get("isbn"), detail.get("pages")
    )
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {"payload": payload["dto"], "author": detail["author"]}


@app.post("/api/books/{key}/contribution")
def submit_contribution(key: str, profile: dict = Depends(admin)):
    """Add this book to Hardcover's public catalogue.

    Reached only from the confirm step on the library screen. Nothing in ingest calls
    this: the title and author come from a language model reading the first few pages,
    and a shared catalogue is not the place to publish a guess nobody has looked at.
    """
    detail = library.book(key, profiles.owner())
    if detail is None:
        raise HTTPException(status_code=404, detail="No such book.")

    payload, error = edition_payload(
        detail["fullTitle"], detail["author"], detail.get("isbn"), detail.get("pages")
    )
    if error:
        raise HTTPException(status_code=400, detail=error)

    result = contribute_edition(payload, token=profiles.hardcover_token(profile["id"]))
    if "error" in result:
        raise HTTPException(status_code=502, detail=result["error"])

    # It exists on Hardcover now, so the cover and the rest can be fetched.
    card, _ = enriching.fetch(key, detail["fullTitle"], detail["author"], detail.get("isbn"))
    return {"added": True, "hardcover": card}


@app.post("/api/books/{key}/hardcover")
def resync_hardcover(key: str, profile: dict = Depends(keeper)):
    """Ask Hardcover again about a book already finished here.

    A finish that failed for a reason of the moment — no key, a bad query, the network —
    stored `markedRead: false` forever, and nothing ever revisited it. This re-runs the
    lookup and rewrites only that flag, so the book keeps its place in the finished
    order and its finish date.

    The reader's own, like the finish it repairs: it rewrites their record against
    their linked account, so it is not the owner's to run on somebody else's behalf.
    """
    detail = library.book(key, profile)
    if detail is None:
        raise HTTPException(status_code=404, detail="No such book.")

    token = profiles.hardcover_token(profile["id"])
    if not token:
        raise HTTPException(
            status_code=400,
            detail="No Hardcover account is linked to this reader — link one in profiles.",
        )

    result = mark_book_as_read(
        detail["fullTitle"], detail["author"], detail.get("isbn"), token=token
    )
    marked = "error" not in result
    positions.set_marked_read(profile["id"], key, marked)

    return {
        "markedRead": marked,
        "hardcoverError": result.get("error"),
        "hardcoverTitle": (result.get("book") or {}).get("title"),
        "alreadyRead": result.get("alreadyRead"),
        "finishNumber": positions.finish_ordinal(key, positions.all_positions(profile["id"])),
    }


@app.patch("/api/books/{key}")
def patch_book(key: str, body: MoveIn, profile: dict = Depends(admin)):
    """Move a book between books/available and books/read by hand."""
    if key not in library.index():
        raise HTTPException(status_code=404, detail="No such book.")
    moved = library.move_book(key, body.finished)
    return {"moved": moved is not None, "finished": body.finished}


@app.delete("/api/books/{key}")
def remove_book(key: str, profile: dict = Depends(admin)):
    """Delete a summary. The source PDF, if there is one, stays in pdfs/."""
    if not library.delete_book(key):
        raise HTTPException(status_code=404, detail="No such book.")
    # Every reader's, not just this one's: the summary is gone for the whole house, and
    # a bookmark in a book nobody can open is a row the shelf cannot render.
    positions.forget_everywhere(key)
    enriching.forget(key)
    return {"deleted": True}


@app.get("/api/ingest/jobs")
def get_jobs(profile: dict = Depends(admin)):
    has_key = bool(os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    rows = jobs.list_jobs()
    # What a failed job could resume from — parts already bought, and not re-bought.
    for row in rows:
        if row.get("status") == "failed":
            row["partsBought"] = jobs.partial_parts(row["id"])
    return {"jobs": rows, "hasKey": has_key}


async def _read_pdf_upload(file: UploadFile) -> bytes:
    """The same checks for both the estimate and the real upload.

    PDF and EPUB. The extension decides how it will be read, and the first bytes decide
    whether to believe it — an EPUB is a zip, so it opens `PK`.
    """
    name = (file.filename or "book.pdf").lower()
    if not name.endswith((".pdf", ".epub")):
        raise HTTPException(status_code=400, detail="Only PDF and EPUB files can be ingested.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="That file is larger than 200MB.")

    expected, label = (b"PK", "EPUB") if name.endswith(".epub") else (b"%PDF", "PDF")
    if not data.startswith(expected):
        raise HTTPException(status_code=400, detail=f"That file is not a {label}.")
    return data


@app.post("/api/ingest/estimate")
async def estimate_upload(
    file: UploadFile = File(...),
    chunks: int | None = None,
    profile: dict = Depends(admin),
):
    """Price a PDF without running anything.

    The file is read into a temporary path, measured and thrown away — nothing is queued
    and no LLM is called, so this is safe to run on a machine with no API key. The
    browser sends the file again when the estimate is accepted; that second transfer is
    the price of never leaving an unconfirmed PDF sitting in next/.
    """
    import tempfile

    data = await _read_pdf_upload(file)

    # The suffix is not cosmetic: `read_pdf_pages` dispatches on it, so a hardcoded
    # ".pdf" here handed every EPUB to pypdf and it failed as a corrupt PDF.
    suffix = ".epub" if (file.filename or "").lower().endswith(".epub") else ".pdf"
    handle, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(handle, "wb") as temp:
            temp.write(data)
        try:
            result = estimating.estimate_pdf(path, chunks)
        except ValueError as ex:
            raise HTTPException(status_code=400, detail=str(ex))
        except Exception as ex:
            raise HTTPException(status_code=400, detail=f"This file could not be read as a PDF: {ex}")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    return {"filename": file.filename, "bytes": len(data), **result}


@app.post("/api/ingest/upload")
async def upload(
    file: UploadFile = File(...),
    chunks: int | None = None,
    model: str | None = None,
    cost: float | None = None,
    profile: dict = Depends(admin),
):
    """Take a PDF and queue it for the pipeline. The owner's, like everything that
    changes what is on the shelf rather than what somebody has read of it."""
    data = await _read_pdf_upload(file)
    name = file.filename or "book.pdf"
    try:
        return jobs.public(jobs.submit(name, data, chunks, model, {"cost": cost}))
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex))


@app.delete("/api/ingest/jobs")
def clear_jobs(profile: dict = Depends(admin)):
    """Clear finished and failed jobs from the list; the books they made are kept."""
    return {"cleared": jobs.clear_finished()}


@app.post("/api/ingest/jobs/{job_id}/resume")
def resume_job(job_id: str, profile: dict = Depends(admin)):
    """Run a failed job again from the parts it already bought.

    The alternative was re-buying the whole book: "One Nation Under Blackmail" is 39
    parts and died at 20, so nineteen paid-for summaries were thrown away because there
    was nowhere to put them.
    """
    job, error = jobs.resume(job_id)
    if error == "No such job.":
        raise HTTPException(status_code=404, detail=error)
    if error:
        raise HTTPException(status_code=409, detail=error)
    return job


@app.delete("/api/ingest/jobs/{job_id}")
def remove_job(job_id: str, profile: dict = Depends(admin)):
    """Remove one settled job. A running job has to finish or fail first."""
    removed = jobs.remove(job_id)
    if removed is None:
        raise HTTPException(status_code=404, detail="No such job.")
    if removed is False:
        raise HTTPException(status_code=409, detail="That job is still running.")
    return {"removed": True}


# The built frontend, when there is one. Mounted last so /api always wins.
if os.path.isdir(WEB_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(WEB_DIST, "assets")), name="assets")

    # The ambience beds. Mounted explicitly rather than left to the SPA fallback so
    # they are served with Range support — Safari will not play audio without it.
    ambience_dir = os.path.join(WEB_DIST, "ambience")
    if os.path.isdir(ambience_dir):
        app.mount("/ambience", StaticFiles(directory=ambience_dir), name="ambience")

    _DIST_ROOT = os.path.realpath(WEB_DIST)

    @app.get("/{path:path}")
    def spa(path: str):
        index = os.path.join(_DIST_ROOT, "index.html")
        if not path:
            return FileResponse(index)

        # Resolve first, then check the result is still inside web/dist. Joining the
        # URL straight onto the directory would hand out any file the process can read
        # given enough "../" — Starlette normalises the path before it reaches here, so
        # this is not reachable today, but that is its behaviour, not our guarantee.
        candidate = os.path.realpath(os.path.join(_DIST_ROOT, path))
        inside = candidate == _DIST_ROOT or candidate.startswith(_DIST_ROOT + os.sep)
        if inside and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(index)
