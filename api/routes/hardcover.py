"""Hardcover: the cover cache, asking again about one book, contributing an edition, and re-syncing a finish."""

from fastapi import APIRouter, Depends, HTTPException

from api import enrich as enriching
from api import library, positions, profiles
from api.deps import admin, reader
from hardcover.request import contribute_edition, edition_payload, mark_book_as_read

router = APIRouter()


@router.get("/api/enrichment")
def get_enrichment():
    """How far the automatic cover pass has got. The library screen shows it while it
    runs, so a thing that happens by itself is still a thing you can watch."""
    return enriching.summary(total=len(library.index()))


@router.post("/api/books/{key}/enrich")
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


@router.get("/api/books/{key}/contribution")
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


@router.post("/api/books/{key}/contribution")
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


@router.post("/api/books/{key}/hardcover")
def resync_hardcover(key: str, profile: dict = Depends(reader)):
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
