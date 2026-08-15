"""Ingest jobs: a PDF going through the pipeline, watchable while it happens.

Summarizing a book is minutes of LLM calls, one per chunk, so an upload cannot be a
request/response — the job is queued, a worker thread runs it, and the screen polls.

Two constraints shape this module:

* `util/chatgpt.py` reads `OPENAI_API_KEY` at import time, so importing `chunks` or
  `meta` fails outright without a key. The reader must keep working without one, so the
  pipeline is imported inside the worker rather than at module scope — an ingest job
  fails, the shelf does not.
* The pipeline is synchronous and blocking, so it runs on a worker thread rather than
  the event loop.
"""

import os
import threading
import traceback
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from api import enrich
from util.files import json_write_file, sanitize_filename

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX_DIR = os.path.join(ROOT, "next")          # where prep.py looks for PDFs
ARCHIVE_DIR = os.path.join(ROOT, "pdfs")        # where the original is parked
OUTPUT_DIR = os.path.join(ROOT, "books", "available")
STORE_PATH = os.path.join(ROOT, "data", "jobs.json")

# Pages per chunk, matching prep.py's `ceil(len(pages) / 25)`.
PAGES_PER_CHUNK = 25

# One at a time: each job is a long run of API calls, and the point of the screen is to
# watch a book finish, not to start six and have all of them crawl.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ingest")
_lock = threading.Lock()
_jobs: "OrderedDict[str, dict]" = OrderedDict()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _persist():
    """Best effort: the job list is a record of what happened, not the source of truth
    for the library — that is always the books/ tree."""
    try:
        os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
        json_write_file(STORE_PATH, list(_jobs.values()))
    except OSError:
        pass


def _load():
    from util.files import json_read_file

    stored = json_read_file(STORE_PATH)
    if not isinstance(stored, list):
        return
    for job in stored:
        if not isinstance(job, dict) or "id" not in job:
            continue
        # A job that was mid-flight when the server stopped did not survive it.
        if job.get("status") in ("queued", "running"):
            job["status"] = "failed"
            job["error"] = "Interrupted — the server stopped while this was running."
        _jobs[job["id"]] = job


_load()


def _update(job_id, **fields):
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        job.update(fields)
        job["updatedAt"] = _now()
        _persist()
        return dict(job)


def public(job):
    """Everything except the server-side path, which is nobody's business but ours."""
    return {k: v for k, v in job.items() if not k.startswith("_")} if job else None


def list_jobs(limit=40):
    with _lock:
        return [public(j) for j in list(_jobs.values())[-limit:][::-1]]


def get_job(job_id):
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def clear_finished():
    """Drop done/failed jobs from the list. The books they produced are untouched."""
    with _lock:
        removed = [j for j in _jobs.values() if j["status"] in ("done", "failed")]
        for job in removed:
            del _jobs[job["id"]]
        _persist()
        return len(removed)


def submit(filename: str, data: bytes, chunks: int | None = None) -> dict:
    """Save an uploaded PDF into next/ and queue it."""
    os.makedirs(INBOX_DIR, exist_ok=True)

    safe = sanitize_filename(filename) or "book.pdf"
    if not safe.lower().endswith(".pdf"):
        safe += ".pdf"
    path = os.path.join(INBOX_DIR, safe)
    stem, ext = os.path.splitext(path)
    counter = 2
    while os.path.exists(path):
        path = f"{stem}-{counter}{ext}"
        counter += 1

    with open(path, "wb") as handle:
        handle.write(data)

    job = {
        "id": uuid.uuid4().hex[:12],
        "filename": os.path.basename(path),
        "bytes": len(data),
        "status": "queued",
        "step": "waiting for the worker",
        "chunksRequested": chunks,
        "chunksDone": 0,
        "chunksTotal": None,
        "pages": None,
        "title": None,
        "author": None,
        "bookKey": None,
        "error": None,
        "createdAt": _now(),
        "updatedAt": _now(),
        "_path": path,
    }
    with _lock:
        _jobs[job["id"]] = job
        _persist()

    _executor.submit(_run, job["id"])
    return dict(job)


def _run(job_id):
    job = get_job(job_id)
    if job is None:
        return
    path = job["_path"]

    try:
        # Imported here, not at module scope: util/chatgpt.py wants OPENAI_API_KEY at
        # import time, and the reader has to keep working without one.
        import math

        from pypdf.errors import PdfStreamError

        from chunks import get_page_chunks, highlight_chunk
        from fragments import read_book_pages
        from meta import UnreadableCharactersError, get_book_meta
    except KeyError:
        _update(
            job_id,
            status="failed",
            step="",
            error="OPENAI_API_KEY is not set — the pipeline cannot run without it.",
        )
        return
    except Exception as ex:
        _update(job_id, status="failed", step="", error=f"Could not load the pipeline: {ex}")
        return

    try:
        _update(job_id, status="running", step="reading the PDF")
        pages = read_book_pages(path)
        if not pages:
            raise UnreadableCharactersError(details="no pages")

        requested = job.get("chunksRequested")
        total = int(requested) if requested else int(math.ceil(len(pages) / PAGES_PER_CHUNK))
        total = max(1, min(total, len(pages)))
        page_chunks = get_page_chunks(pages, total)
        _update(job_id, pages=len(pages), chunksTotal=len(page_chunks), step="identifying the book")

        meta_info = get_book_meta(pages, min(5, len(pages)))
        book_info = {"meta": meta_info, "parts": []}
        _update(
            job_id,
            title=meta_info.get("title"),
            author=meta_info.get("author"),
            step=f"summarizing part 1 of {len(page_chunks)}",
        )

        first_chunk = True
        for index, page_chunk in enumerate(page_chunks):
            highlighted = highlight_chunk(page_chunk, first_chunk)
            book_info["parts"].append(highlighted)
            first_chunk = False
            _update(
                job_id,
                chunksDone=index + 1,
                step=(
                    f"summarizing part {index + 2} of {len(page_chunks)}"
                    if index + 1 < len(page_chunks)
                    else "writing the summary"
                ),
            )

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        key = sanitize_filename(meta_info["title"])
        output_path = os.path.join(OUTPUT_DIR, f"{key}.json")
        json_write_file(output_path, book_info)

        # Look the cover up now, off this thread — the title and author were just read
        # off the first pages, which is everything the search needs. By the time the
        # shelf reloads the jacket is usually there, and no one had to ask for it.
        enrich.queue(key, meta_info.get("title") or key, meta_info.get("author"))

        # The original PDF is parked in pdfs/, exactly as prep.py does it.
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        try:
            os.replace(path, os.path.join(ARCHIVE_DIR, os.path.basename(path)))
        except OSError:
            pass

        _update(job_id, status="done", step="", bookKey=key, error=None)

    except PdfStreamError:
        _update(
            job_id,
            status="failed",
            step="",
            error="This file could not be read as a PDF.",
        )
    except UnreadableCharactersError:
        _update(
            job_id,
            status="failed",
            step="",
            error="No text could be extracted — this looks like a scanned PDF.",
        )
    except Exception as ex:
        traceback.print_exc()
        _update(job_id, status="failed", step="", error=f"{type(ex).__name__}: {ex}")
