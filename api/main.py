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
    focusMode: bool | None = None
    maxHighlights: int | None = None


class AmbienceIn(BaseModel):
    bed: str | None = None
    level: float | None = None


def reader(x_profile: str | None = Header(default=None)) -> dict:
    """Whose reading this request is.

    The profile travels in a header rather than the path, because it qualifies every
    endpoint here and none of them is *about* it. An id nobody recognises resolves to
    the owner: a browser that has never picked a profile is the person who set the
    tablet up, which is exactly what this app assumed before profiles existed.
    """
    return profiles.resolve(x_profile)


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
    """Register, palette, pointer focus, highlight cap — the settings the design calls
    the reader's rather than the app's, kept on the reader.

    By id rather than for whoever the header says, because that is what it is: a change
    to a named profile, which happens to almost always be the one holding the tablet.
    """
    row, error = profiles.set_prefs(profile_id, body.model_dump(exclude_none=True))
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
def put_position(key: str, body: PositionIn, profile: dict = Depends(reader)):
    if key not in library.index():
        raise HTTPException(status_code=404, detail="No such book.")
    return positions.save_position(profile["id"], key, body.part, body.page)


@app.delete("/api/books/{key}/position")
def delete_position(key: str, profile: dict = Depends(reader)):
    """Start a book again from the beginning — for this reader only."""
    if key not in library.index():
        raise HTTPException(status_code=404, detail="No such book.")
    positions.clear_position(profile["id"], key)
    return {"ok": True}


@app.put("/api/books/{key}/ambience")
def put_ambience(key: str, body: AmbienceIn, profile: dict = Depends(reader)):
    """Remember the bed this reader chose for this book.

    Beside the bookmark, in the same entry: the handoff's rule is that the choice
    belongs to the book, and profiles make it belong to the book *for this reader*.
    """
    if key not in library.index():
        raise HTTPException(status_code=404, detail="No such book.")
    return positions.save_ambience(profile["id"], key, body.bed, body.level)


@app.post("/api/books/{key}/finish")
def finish_book(key: str, profile: dict = Depends(reader)):
    """Record the finish for this reader — and, for the owner, mark it read on
    Hardcover and move the JSON available -> read.

    Finishing means two different things and profiles pull them apart. It always means
    "I read this", which is the reader's own record. For the owner it *also* means the
    house's copy is finished with and their Hardcover shelf should say so; for anyone
    else it does not, because there is one API key and it is not theirs, and because
    re-filing a book somebody else is halfway through would be answering for them.

    The move happens either way for the owner — the book *was* read — but `markedRead`
    only comes back true when Hardcover actually accepted it, so the finish screen never
    paints the green chip on a failed call. For a guest it comes back null: nothing was
    sent, which is not the same as sending it and being refused.
    """
    detail = library.book(key, profile)
    if detail is None:
        raise HTTPException(status_code=404, detail="No such book.")

    owner = bool(profile.get("owner"))
    result = {}
    marked = None
    if owner:
        result = mark_book_as_read(detail["fullTitle"], detail["author"], detail.get("isbn"))
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
def enrich_book(key: str):
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
def preview_contribution(key: str):
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
def submit_contribution(key: str):
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

    result = contribute_edition(payload)
    if "error" in result:
        raise HTTPException(status_code=502, detail=result["error"])

    # It exists on Hardcover now, so the cover and the rest can be fetched.
    card, _ = enriching.fetch(key, detail["fullTitle"], detail["author"], detail.get("isbn"))
    return {"added": True, "hardcover": card}


@app.post("/api/books/{key}/hardcover")
def resync_hardcover(key: str, profile: dict = Depends(reader)):
    """Ask Hardcover again about a book already finished here.

    A finish that failed for a reason of the moment — no key, a bad query, the network —
    stored `markedRead: false` forever, and nothing ever revisited it. This re-runs the
    lookup and rewrites only that flag, so the book keeps its place in the finished
    order and its finish date.

    The owner's, like the finish it repairs: the key belongs to one account.
    """
    if not profile.get("owner"):
        raise HTTPException(
            status_code=403,
            detail="Only the owner profile writes to Hardcover — there is one key, and it is theirs.",
        )

    detail = library.book(key, profile)
    if detail is None:
        raise HTTPException(status_code=404, detail="No such book.")

    result = mark_book_as_read(detail["fullTitle"], detail["author"], detail.get("isbn"))
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
def patch_book(key: str, body: MoveIn):
    """Move a book between books/available and books/read by hand."""
    if key not in library.index():
        raise HTTPException(status_code=404, detail="No such book.")
    moved = library.move_book(key, body.finished)
    return {"moved": moved is not None, "finished": body.finished}


@app.delete("/api/books/{key}")
def remove_book(key: str):
    """Delete a summary. The source PDF, if there is one, stays in pdfs/."""
    if not library.delete_book(key):
        raise HTTPException(status_code=404, detail="No such book.")
    # Every reader's, not just this one's: the summary is gone for the whole house, and
    # a bookmark in a book nobody can open is a row the shelf cannot render.
    positions.forget_everywhere(key)
    enriching.forget(key)
    return {"deleted": True}


@app.get("/api/ingest/jobs")
def get_jobs():
    has_key = bool(os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    return {"jobs": jobs.list_jobs(), "hasKey": has_key}


async def _read_pdf_upload(file: UploadFile) -> bytes:
    """The same four checks for both the estimate and the real upload."""
    name = file.filename or "book.pdf"
    if not name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files can be ingested.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="That file is larger than 200MB.")
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="That file is not a PDF.")
    return data


@app.post("/api/ingest/estimate")
async def estimate_upload(file: UploadFile = File(...), chunks: int | None = None):
    """Price a PDF without running anything.

    The file is read into a temporary path, measured and thrown away — nothing is queued
    and no LLM is called, so this is safe to run on a machine with no API key. The
    browser sends the file again when the estimate is accepted; that second transfer is
    the price of never leaving an unconfirmed PDF sitting in next/.
    """
    import tempfile

    data = await _read_pdf_upload(file)

    handle, path = tempfile.mkstemp(suffix=".pdf")
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
):
    """Take a PDF and queue it for the pipeline."""
    data = await _read_pdf_upload(file)
    name = file.filename or "book.pdf"
    return jobs.public(jobs.submit(name, data, chunks, model, {"cost": cost}))


@app.delete("/api/ingest/jobs")
def clear_jobs():
    """Clear finished and failed jobs from the list; the books they made are kept."""
    return {"cleared": jobs.clear_finished()}


@app.delete("/api/ingest/jobs/{job_id}")
def remove_job(job_id: str):
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
