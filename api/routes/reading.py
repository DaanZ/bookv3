"""A reader's own reading: the shelf, a book, where they are in it, its ambience, and finishing it."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api import enrich as enriching
from api import library, positions, profiles
from api.deps import reader
from hardcover.request import mark_book_as_read

router = APIRouter()


class PositionIn(BaseModel):
    part: int = Field(ge=0)
    page: int = Field(ge=0)


class AmbienceIn(BaseModel):
    bed: str | None = None
    level: float | None = None


@router.get("/api/shelf")
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


@router.get("/api/books/{key}")
def get_book(key: str, profile: dict = Depends(reader)):
    detail = library.book(key, profile)
    if detail is None:
        raise HTTPException(status_code=404, detail="No such book.")
    return detail


@router.put("/api/books/{key}/position")
def put_position(key: str, body: PositionIn, profile: dict = Depends(reader)):
    if key not in library.index():
        raise HTTPException(status_code=404, detail="No such book.")
    return positions.save_position(profile["id"], key, body.part, body.page)


@router.delete("/api/books/{key}/position")
def delete_position(key: str, profile: dict = Depends(reader)):
    """Start a book again from the beginning — for this reader only."""
    if key not in library.index():
        raise HTTPException(status_code=404, detail="No such book.")
    positions.clear_position(profile["id"], key)
    return {"ok": True}


@router.put("/api/books/{key}/ambience")
def put_ambience(key: str, body: AmbienceIn, profile: dict = Depends(reader)):
    """Remember the bed this reader chose for this book.

    Beside the bookmark, in the same entry: the handoff's rule is that the choice
    belongs to the book, and profiles make it belong to the book *for this reader*.
    """
    if key not in library.index():
        raise HTTPException(status_code=404, detail="No such book.")
    return positions.save_ambience(profile["id"], key, body.bed, body.level)


@router.post("/api/books/{key}/finish")
def finish_book(key: str, profile: dict = Depends(reader)):
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


@router.post("/api/books/{key}/unfinish")
def unfinish_book(key: str, profile: dict = Depends(reader)):
    """Undo a finish: this reader has not read it after all.

    The mirror of `finish`, and it undoes the same two things that one did. The reader's
    record goes — the bookmark, the finish and its place in the numbering — and for the
    **owner** the JSON moves back from `books/read` to `books/available`, because for
    them the folder *is* the history and leaving the file behind would leave the shelf
    still calling it read.

    One thing it deliberately does not undo: **nothing is sent to Hardcover.** A finish
    writes `status_id: 3` to a real, public shelf that other people read, and quietly
    retracting that on a local correction is a bigger act than the mistake it is fixing.
    Hardcover is edited on Hardcover. The response says so, so the screen can too.
    """
    if key not in library.index():
        raise HTTPException(status_code=404, detail="No such book.")

    positions.clear_position(profile["id"], key)
    refiled = library.move_book(key, False) if profile.get("owner") else None
    return {
        "reset": True,
        "refiled": refiled is not None,
        # Whether a finish was ever sent to Hardcover for this book is not knowable from
        # here once the record is gone, so the screen says the general truth instead:
        # nothing was retracted.
        "hardcoverUntouched": True,
    }
