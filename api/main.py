"""The reader's backend.

Streamlit still owns ingest (`app.py`, `prep.py`); this serves the reading surface —
the shelf, a book's parts, reading position, and finishing a book. It reads the same
`books/*.json` the pipeline writes, and adds nothing to that format.

    uvicorn api.main:app --reload --port 8000
"""

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api import library, positions
from hardcover.request import mark_book_as_read

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


@app.get("/api/shelf")
def get_shelf():
    books = library.shelf()
    return {
        "books": books,
        "counts": {
            "total": len(books),
            "read": sum(1 for b in books if b["state"] == "read"),
        },
    }


@app.get("/api/books/{key}")
def get_book(key: str):
    detail = library.book(key)
    if detail is None:
        raise HTTPException(status_code=404, detail="No such book.")
    return detail


@app.put("/api/books/{key}/position")
def put_position(key: str, body: PositionIn):
    if key not in library.index():
        raise HTTPException(status_code=404, detail="No such book.")
    return positions.save_position(key, body.part, body.page)


@app.delete("/api/books/{key}/position")
def delete_position(key: str):
    """Start a book again from the beginning."""
    if key not in library.index():
        raise HTTPException(status_code=404, detail="No such book.")
    positions.clear_position(key)
    return {"ok": True}


@app.post("/api/books/{key}/finish")
def finish_book(key: str):
    """Mark read on Hardcover, then move the JSON available -> read.

    The move happens either way — the book *was* read — but `markedRead` only comes
    back true when Hardcover actually accepted it, so the finish screen never paints
    the green chip on a failed call.
    """
    detail = library.book(key)
    if detail is None:
        raise HTTPException(status_code=404, detail="No such book.")

    already_read = detail["state"] == "read"
    result = mark_book_as_read(detail["fullTitle"], detail["author"])
    marked = "error" not in result

    moved = None if already_read else library.move_to_read(key)
    positions.save_position(key, max(0, detail["partCount"] - 1), 0)
    positions.record_finish(key, marked)

    return {
        "markedRead": marked,
        "hardcoverError": result.get("error"),
        "moved": moved is not None,
        "movedTo": "books/read" if moved else None,
    }


# The built frontend, when there is one. Mounted last so /api always wins.
if os.path.isdir(WEB_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(WEB_DIST, "assets")), name="assets")

    # The ambience beds. Mounted explicitly rather than left to the SPA fallback so
    # they are served with Range support — Safari will not play audio without it.
    ambience_dir = os.path.join(WEB_DIST, "ambience")
    if os.path.isdir(ambience_dir):
        app.mount("/ambience", StaticFiles(directory=ambience_dir), name="ambience")

    @app.get("/{path:path}")
    def spa(path: str):
        candidate = os.path.join(WEB_DIST, path)
        if path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(WEB_DIST, "index.html"))
