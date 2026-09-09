"""Ingest jobs: a PDF going through the pipeline, watchable while it happens.

Summarizing a book is minutes of LLM calls, one per chunk, so an upload cannot be a
request/response — the job is queued, a worker thread runs it, and the screen polls.

Two constraints shape this module:

* `util/chatgpt.py` reads `OPENROUTER_API_KEY` at import time, so importing `chunks` or
  `meta` fails outright without a key. The reader must keep working without one, so the
  pipeline is imported inside the worker rather than at module scope — an ingest job
  fails, the shelf does not. `api/estimate.py` is deliberately free of that dependency,
  so a book can be priced on a machine with no key at all.
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

from util.files import json_write_file, sanitize_filename

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX_DIR = os.path.join(ROOT, "next")          # where prep.py looks for PDFs
ARCHIVE_DIR = os.path.join(ROOT, "pdfs")        # where the original is parked
OUTPUT_DIR = os.path.join(ROOT, "books", "available")
STORE_PATH = os.path.join(ROOT, "data", "jobs.json")

# Pages per chunk, matching prep.py's `ceil(len(pages) / 25)`.
PAGES_PER_CHUNK = 25

# How many parts may come back with nothing highlighted before the model is judged unable
# to do it. Front matter, an index or a page of references can honestly have nothing worth
# marking, so one is not evidence; three is.
UNHIGHLIGHTED_LIMIT = 3

# Parts finished so far, kept on disk while the job runs.
#
# A book is one API call per part and they are paid for one at a time, so a failure at
# part 20 of 39 used to throw away nineteen parts that were bought, correct and already
# written — the only way forward was to buy all thirty-nine again. The parts are check-
# pointed as they land, and a resumed job reads them back and starts where it stopped.
PARTIAL_DIR = os.path.join(ROOT, "data", "partials")


def _partial_path(job_id):
    return os.path.join(PARTIAL_DIR, f"{job_id}.json")


def _save_partial(job_id, book_info):
    """Best effort: losing a checkpoint costs money, not correctness."""
    try:
        os.makedirs(PARTIAL_DIR, exist_ok=True)
        json_write_file(_partial_path(job_id), book_info)
    except OSError:
        pass


def _load_partial(job_id):
    from util.files import json_read_file

    stored = json_read_file(_partial_path(job_id))
    if isinstance(stored, dict) and isinstance(stored.get("parts"), list):
        return stored
    return None


def _drop_partial(job_id):
    try:
        os.remove(_partial_path(job_id))
    except OSError:
        pass

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


def remove(job_id):
    """Drop one settled job, and take its abandoned upload with it.

    A job that failed left its PDF in next/ — 22MB for the one that prompted this — and
    nothing ever collected it, so re-uploading the same book stacked up `-2`, `-3` copies
    beside it. A job that succeeded has already had its PDF moved to pdfs/ by `_run`, and
    that archive is deliberately not touched: the summary came from it, and the point of
    pdfs/ is to keep it.
    """
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        if job["status"] in ("queued", "running"):
            return False
        path = job.get("_path")
        del _jobs[job_id]
        _persist()
    _drop_partial(job_id)

    # Only ever the staged copy under next/, never the archive.
    if path and os.path.dirname(os.path.abspath(path)) == os.path.abspath(INBOX_DIR):
        try:
            os.remove(path)
        except OSError:
            pass
    return True


def clear_finished():
    """Drop done/failed jobs from the list. The books they produced are untouched."""
    # Ids first, then remove outside the lock: `remove` takes it too, and it is not
    # reentrant.
    with _lock:
        settled = [job["id"] for job in _jobs.values() if job["status"] in ("done", "failed")]
    return sum(1 for job_id in settled if remove(job_id))


def submit(filename: str, data: bytes, chunks: int | None = None, model: str | None = None,
           estimate: dict | None = None) -> dict:
    """Save an uploaded PDF into next/ and queue it."""
    os.makedirs(INBOX_DIR, exist_ok=True)

    safe = sanitize_filename(filename) or "book.pdf"
    # Keep the extension the file arrived with: it is what `_read_pages` dispatches on,
    # so an EPUB saved as .pdf would be handed to pypdf and fail as a corrupt PDF.
    if not safe.lower().endswith((".pdf", ".epub")):
        safe += ".epub" if (filename or "").lower().endswith(".epub") else ".pdf"
    path = os.path.join(INBOX_DIR, safe)
    stem, ext = os.path.splitext(path)
    counter = 2
    while os.path.exists(path):
        path = f"{stem}-{counter}{ext}"
        counter += 1

    try:
        with open(path, "wb") as handle:
            handle.write(data)
    except OSError as ex:
        # The name is bounded by sanitize_filename now, but the repo could sit somewhere
        # deep enough that even a bounded one does not fit. Say so, rather than letting a
        # FileNotFoundError become a 500 that reads as the server being broken.
        raise ValueError(f"Could not save the upload as {os.path.basename(path)}: {ex}") from ex

    job = {
        "id": uuid.uuid4().hex[:12],
        "filename": os.path.basename(path),
        # The name as uploaded. The saved one is sanitised and length-bounded, which
        # drops exactly the tail a library filename keeps its ISBN in.
        "originalName": filename,
        "bytes": len(data),
        "status": "queued",
        "step": "waiting for the worker",
        "chunksRequested": chunks,
        "chunksDone": 0,
        "chunksTotal": None,
        "chunkBounds": None,
        "model": model,
        # What the library screen quoted before this was queued, kept so the finished job
        # can be read back against it.
        "estimatedCost": (estimate or {}).get("cost"),
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


def resume(job_id, model=None):
    """Run a failed job again, continuing from the parts it already bought.

    `model` replaces the one the job was queued with. The common reason a job fails is
    that its model cannot produce highlighting, and retrying with the same one would fail
    the same way — so the retry has to be able to change it, and any parts already bought
    from the old model are dropped rather than mixed with the new one.

    The same job rather than a new one, deliberately: the checkpoint is keyed by id, and
    the point of resuming is that the nineteen parts already paid for are still there. A
    job whose upload has been cleaned up cannot be resumed — say so rather than starting
    a run that will fail on the first read.
    """
    job = get_job(job_id)
    if job is None:
        return None, "No such job."
    if job["status"] in ("queued", "running"):
        return None, "That job is already running."
    if not job.get("_path") or not os.path.exists(job["_path"]):
        return None, "The uploaded PDF is no longer there — upload it again."

    if model and model != job.get("model"):
        # Half a book in one voice and half in another is worse than paying twice.
        _drop_partial(job_id)
        _update(job_id, model=model, chunksDone=0)

    _update(job_id, status="queued", step="waiting for the worker", error=None)
    _executor.submit(_run, job_id)
    return public(get_job(job_id)), None


def partial_parts(job_id):
    """How many parts a failed job has already bought, for the screen to offer."""
    stored = _load_partial(job_id)
    return len(stored.get("parts", [])) if stored else 0


class _Page:
    """What the pipeline expects a page to be: something with `.page_content`.

    PyPDFLoader hands back LangChain Documents; an EPUB is read as plain strings. The
    chunker only ever reads this one attribute, so wrapping is enough and no part of the
    pipeline below needs to know which format it is working on.
    """

    def __init__(self, content):
        self.page_content = content


def _read_pages(path):
    """The book as pages, from a PDF or an EPUB."""
    if str(path).lower().endswith(".epub"):
        from util.epub import read_epub_pages

        return [_Page(text) for text in read_epub_pages(path)]

    from fragments import read_book_pages

    return read_book_pages(path)


def _declared_metadata(path):
    """The title and author the file carries about itself.

    Typed by whoever produced the file rather than inferred from a page, and present far
    more often than a readable title page is — all three books here had it, including the
    ebook whose text never names itself.
    """
    if str(path).lower().endswith(".epub"):
        from util.epub import epub_metadata

        return {k: v for k, v in epub_metadata(path).items() if k in ("title", "author")}

    try:
        from pypdf import PdfReader

        info = PdfReader(path).metadata or {}
        return {
            key: str(info.get(f"/{key.capitalize()}")).strip()
            for key in ("title", "author")
            if info.get(f"/{key.capitalize()}")
        }
    except Exception:
        # Never worth failing an ingest over: it is a hint, and the pages are still there.
        return {}


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
        from meta import UnreadableCharactersError, get_book_meta
        from util.chatgpt import RETRY_ATTEMPTS
    except KeyError:
        _update(
            job_id,
            status="failed",
            step="",
            error="OPENROUTER_API_KEY is not set — the pipeline cannot run without it.",
        )
        return
    except Exception as ex:
        _update(job_id, status="failed", step="", error=f"Could not load the pipeline: {ex}")
        return

    try:
        model = job.get("model") or None
        _update(job_id, status="running", step="reading the PDF")
        pages = _read_pages(path)
        if not pages:
            raise UnreadableCharactersError(details="no pages")

        requested = job.get("chunksRequested")
        total = int(requested) if requested else int(math.ceil(len(pages) / PAGES_PER_CHUNK))
        total = max(1, min(total, len(pages)))
        page_chunks = get_page_chunks(pages, total)
        # The waiting state names the pages each part covers. They come from here rather
        # than being recomputed in the browser: the split is a Gaussian CDF, and a second
        # implementation of that curve would drift from the one that cut this book.
        from util.split import page_chunk_bounds

        _update(
            job_id,
            pages=len(pages),
            chunksTotal=len(page_chunks),
            chunkBounds=page_chunk_bounds(len(pages), total),
            step="identifying the book",
        )

        # What the file says about itself, which beats reading page one: an ebook opens
        # on cover art and the publisher's advertising, so the first readable page is
        # often "Thank you for buying this <imprint> ebook".
        declared = _declared_metadata(path)

        meta_info = get_book_meta(pages, min(5, len(pages)), model=model, declared=declared)

        # Read off the page or the filename, never asked of the model: an ISBN is a
        # checksummed fact and a model will happily invent a plausible one. It turns the
        # Hardcover lookup from "a book with a similar title" into "this edition".
        from util.isbn import find_isbn, find_isbn_in_name

        # Best source first, and each one is weaker than the last:
        #
        #   the EPUB's own manifest — the publisher stating its number
        #   the copyright page      — the book stating it, checksum-validated
        #   the whole text          — a last resort; mid-book numbers are usually
        #                             citations, and belong to a book being referenced
        #   the download's filename — library filenames often carry it
        #   Open Library            — somebody else's catalogue, author-checked
        #
        # Worth all five because an ISBN is the difference between identifying an edition
        # and guessing from a title: without one, matching sends "Atomic Habits" to a
        # workbook. Ingest is the only moment the full text is in hand, so anything not
        # taken here is gone once the PDF is archived.
        isbn = (
            declared.pop("isbn", None)
            or find_isbn(page.page_content for page in pages)
            or find_isbn((page.page_content for page in pages), deep=True)
            or find_isbn_in_name(job.get("originalName") or job.get("filename"))
        )
        if not isbn:
            from util.booklookup import isbn_from_openlibrary

            isbn = isbn_from_openlibrary(meta_info.get("title"), meta_info.get("author"))
        if isbn:
            meta_info["isbn"] = isbn

        # When this book joined the library. Recorded here because nowhere downstream can
        # work it out later: a git restore rewrites every file's timestamps, so the 266
        # books that predate this field had to have their dates dug out of git history
        # (tools/backfill_added.py). Written once, at ingest, and never touched again.
        meta_info["addedAt"] = datetime.now(timezone.utc).isoformat()
        meta_info["addedFrom"] = "ingest"

        # Parts already bought on an earlier attempt. Their page ranges come from the same
        # split, so part N is the same pages it was — the checkpoint is only reused when
        # the chunk count matches, because a different count is a different book shape.
        resumed = _load_partial(job_id) or {}
        done_parts = resumed.get("parts", []) if resumed.get("chunks") == len(page_chunks) else []

        book_info = {"meta": meta_info, "parts": list(done_parts), "chunks": len(page_chunks)}
        _update(
            job_id,
            title=meta_info.get("title"),
            author=meta_info.get("author"),
            step=f"summarizing part {len(done_parts) + 1} of {len(page_chunks)}",
            chunksDone=len(done_parts),
            resumedFrom=len(done_parts) or None,
        )

        first_chunk = True
        unhighlighted = 0
        empty_chunks = 0
        for index, page_chunk in enumerate(page_chunks):
            # Already bought on an earlier run. Nothing is sent and nothing is charged.
            if index < len(done_parts):
                first_chunk = False
                continue

            # A stretch of the book with no extractable text at all — scanned plates, a
            # photo section, an image-only insert. Sending it produces a request with no
            # content, which the provider rejects outright: "One Nation Under Blackmail"
            # has 48 such pages in the middle and died there at part 20 of 39, after
            # paying for nineteen. There is nothing to summarize, so there is nothing to
            # send; the part is skipped and counted.
            if not any(page.page_content.strip() for page in page_chunk):
                empty_chunks += 1
                _update(job_id, chunksDone=index + 1, emptyChunks=empty_chunks)
                continue
            try:
                highlighted = highlight_chunk(page_chunk, first_chunk, model=model)
            except Exception as ex:
                # `llm_strict` has already retried. Say which part gave up and keep the
                # reason short: a pydantic ValidationError stringifies to the whole
                # truncated response, which fills the screen and says nothing.
                reason = str(ex).split("\n")[0][:160]
                raise RuntimeError(
                    f"Part {index + 1} of {len(page_chunks)} failed after "
                    f"{RETRY_ATTEMPTS} attempts — {type(ex).__name__}: {reason}"
                ) from ex
            # A model that returns no highlighting is the failure this pipeline cannot
            # survive: the summary reads fine and renders as a flat wall of text, because
            # `reading.js` colours what the pipeline marks as bold and there is nothing to
            # colour. It is silent, so it has to be caught here rather than by a reader.
            #
            # But a single bare part is not that failure. A chunk of front matter, an
            # index, a page of references — there are parts of a real book with nothing in
            # them worth marking, and stopping on the first one throws away a model that
            # would have done the rest properly. Three is the line: two can be the book,
            # three is the model.
            if "<b" not in highlighted["body"]:
                unhighlighted += 1
                if unhighlighted >= UNHIGHLIGHTED_LIMIT:
                    raise RuntimeError(
                        f"{model or 'The default model'} left {unhighlighted} of "
                        f"{index + 1} parts with no highlighted words, which would render "
                        "as flat text. Nothing further was spent. "
                        "google/gemini-2.5-flash has produced highlighted books here — "
                        "pick that and run it again."
                    )
            book_info["parts"].append(highlighted)
            # Checkpointed the moment it lands, because it has been paid for. A crash,
            # a restart or a provider error after this point costs the parts still to
            # come, never the ones already bought.
            _save_partial(job_id, book_info)
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
        _drop_partial(job_id)

        # Indexing: rescan both folders so the written book is checked against the rest
        # of the library before the job reports done. The seam state on the library
        # screen is showing this step, and gold means two sources meeting — so the step
        # has to be real work, not a label over a pause.
        from api import enrich, library

        _update(job_id, step="indexing")
        indexed = library.index()
        if key not in indexed:
            raise RuntimeError("The summary was written but did not appear in the library index.")

        # Ask Hardcover for the cover now, off this thread. The title, author and ISBN
        # were just read off the first pages, which is everything the search needs — so
        # the book arrives on the library screen with a jacket rather than a row waiting
        # to be clicked. Read-only, and nothing here waits for it.
        enrich.queue(key, meta_info.get("title") or key, meta_info.get("author"), isbn)

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
