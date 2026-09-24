"""What is on the shelf: re-filing a book between available and read, and deleting one. The owner's."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api import enrich as enriching
from api import library, positions
from api.deps import admin, reader

router = APIRouter()


class MoveIn(BaseModel):
    finished: bool


@router.patch("/api/books/{key}")
def patch_book(key: str, body: MoveIn, profile: dict = Depends(admin)):
    """Move a book between books/available and books/read by hand."""
    if key not in library.index():
        raise HTTPException(status_code=404, detail="No such book.")
    moved = library.move_book(key, body.finished)
    return {"moved": moved is not None, "finished": body.finished}


@router.delete("/api/books/{key}")
def remove_book(key: str, profile: dict = Depends(admin)):
    """Delete a summary. The source PDF, if there is one, stays in pdfs/."""
    if not library.delete_book(key):
        raise HTTPException(status_code=404, detail="No such book.")
    # Every reader's, not just this one's: the summary is gone for the whole house, and
    # a bookmark in a book nobody can open is a row the shelf cannot render.
    positions.forget_everywhere(key)
    enriching.forget(key)
    return {"deleted": True}
