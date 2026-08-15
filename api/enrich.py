"""Hardcover metadata for a book, cached locally.

The cover, rating, genres and the link out all come from Hardcover, and none of it
belongs in `books/*.json`: that file is the pipeline's output, it is committed, and
mixing somebody else's mutable catalogue into it would churn git every time a rating
moved. This is a cache beside `positions.json` instead — gitignored, disposable, and
rebuildable by asking again.

The cover is stored as Hardcover's URL. Downloading it would mean rehosting their asset,
and it would go stale the moment an edition is re-covered.

Nobody asks for a lookup by hand. A book is queued the moment ingest writes its JSON,
and everything else is queued by the first `GET /api/shelf` that sees a book nobody has
asked about — which is how books that predate this, and anything `prep.py` writes behind
the API's back, end up with covers. `POST /api/books/{key}/enrich` still exists for the
one case the automatic pass cannot serve: asking again about a book it got wrong.

Three rules hold the automatic half in place:

* **Read-only.** It calls `search_book` and nothing else. `insert_user_book` and
  `insert_book` stay where a person asked for them — a background pass must not write to
  someone's shelf, still less to a catalogue everyone reads.
* **Once per book, and slowly.** One worker thread, one request at a time, a pause
  between them. Every attempt is recorded in `data/hardcover-lookups.json`; found and
  missing are answers and are never re-asked. Only a failure is retried, and not for
  `RETRY_AFTER_HOURS` — without that, every shelf load would re-queue the whole library
  while the network was down.
* **Never load-bearing.** No key, no network, no match: the library renders on the
  patch, exactly as it does today. No request handler waits on any of it.
"""

import os
import queue
import threading
import time
from datetime import datetime, timedelta, timezone

from util.files import json_read_file, json_write_file

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(ROOT, "data")
STORE_PATH = os.path.join(STORE_DIR, "hardcover.json")

# What was asked and how it went, which the card store cannot say: it only holds
# answers, and "Hardcover does not have this book" is an answer with no card.
LOOKUPS_PATH = os.path.join(STORE_DIR, "hardcover-lookups.json")

# Hardcover asks for a courteous rate, and nothing is waiting on this.
REQUEST_INTERVAL_SECONDS = 1.5

# A lookup that failed — no key, no network — is worth trying again later. One that came
# back "no such book" is not: that answer will not change on its own.
RETRY_AFTER_HOURS = 6

_lock = threading.Lock()
_ledger_lock = threading.Lock()
_queue_lock = threading.Lock()
_work: "queue.Queue[tuple[str, str, str, str | None]]" = queue.Queue()
_pending: set[str] = set()
_worker: threading.Thread | None = None


def _read():
    stored = json_read_file(STORE_PATH)
    return stored if isinstance(stored, dict) else {}


def all_metadata():
    with _lock:
        return _read()


def get(key):
    return all_metadata().get(key)


def put(key, data):
    with _lock:
        store = _read()
        if data is None:
            store.pop(key, None)
        else:
            store[key] = data
        os.makedirs(STORE_DIR, exist_ok=True)
        json_write_file(STORE_PATH, store)
        return data


def fetch(key, title, author, isbn=None):
    """Look the book up on Hardcover and cache what comes back.

    Imported here rather than at module scope so the reader still starts without a
    Hardcover key — the same rule the ingest pipeline follows.
    """
    from hardcover.request import search_book

    found, error = search_book(title, author, isbn=isbn)
    _record(key, error)
    if error:
        return None, error
    return put(key, found), None


def forget(key):
    """Drop everything remembered about a book, for when the book itself is deleted —
    otherwise a re-ingest under the same key inherits the old book's cover."""
    put(key, None)
    with _ledger_lock:
        ledger = _read_lookups()
        if ledger.pop(key, None) is not None:
            _write_lookups(ledger)


# --- what has been asked, and how it went -----------------------------------------

def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_lookups():
    stored = json_read_file(LOOKUPS_PATH)
    return stored if isinstance(stored, dict) else {}


def _write_lookups(ledger):
    os.makedirs(STORE_DIR, exist_ok=True)
    json_write_file(LOOKUPS_PATH, ledger)


def lookups():
    with _ledger_lock:
        return _read_lookups()


def _record(key, error):
    """`search_book` reports two different things as an error string. "No book matching"
    is an answer — Hardcover does not have this book — and asking again will not change
    it. Everything else is a failure of the moment and can be retried."""
    if error is None:
        status = "found"
    elif "no book matching" in error or "no usable match" in error:
        status = "missing"
    else:
        status = "failed"

    with _ledger_lock:
        ledger = _read_lookups()
        ledger[key] = {"status": status, "checkedAt": _now(), "error": error}
        _write_lookups(ledger)
    return status


def _stale(record):
    """Is this book worth (re-)asking about?"""
    if record is None:
        return True
    if record.get("status") in ("found", "missing"):
        return False
    try:
        then = datetime.fromisoformat(record.get("checkedAt") or "")
    except ValueError:
        return True
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - then > timedelta(hours=RETRY_AFTER_HOURS)


# --- the automatic pass ------------------------------------------------------------

def enabled():
    """Without a key every lookup returns the same sentence; queueing the library to
    collect it 264 times is just a slow way to write it down."""
    return bool(os.environ.get("HARDCOVER_API_KEY"))


def _drain():
    last_request = 0.0
    while True:
        key, title, author, isbn = _work.get()
        try:
            wait = REQUEST_INTERVAL_SECONDS - (time.monotonic() - last_request)
            if wait > 0:
                time.sleep(wait)
            last_request = time.monotonic()
            fetch(key, title, author, isbn)
        except Exception as ex:  # a background pass must not take its own thread down
            _record(key, f"{type(ex).__name__}: {ex}")
        finally:
            with _queue_lock:
                _pending.discard(key)
            _work.task_done()


def _enqueue(key, title, author, isbn):
    global _worker

    if not key or not title:
        return False
    with _queue_lock:
        if key in _pending:
            return False
        _pending.add(key)
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_drain, name="enrich", daemon=True)
            _worker.start()
    _work.put((key, title, author or "", isbn))
    return True


def queue(key, title, author=None, isbn=None, force=False):
    """Ask for one book to be looked up, off the caller's thread. Returns whether it was
    actually queued — a book already answered for is not asked about again."""
    if not enabled():
        return False
    if not force and (get(key) or not _stale(lookups().get(key))):
        return False
    return _enqueue(key, title, author, isbn)


def queue_missing(books):
    """Queue every book nobody has asked about yet. Called with the shelf, so a library
    that predates this fills itself in rather than waiting to be clicked through.

    One read of each store for the whole shelf, and the requests happen on the worker —
    the handler this was called from does not wait for any of them.
    """
    if not enabled():
        return 0

    cards = all_metadata()
    ledger = lookups()
    queued = 0
    for book in books:
        key = book.get("key")
        if not key or cards.get(key) or not _stale(ledger.get(key)):
            continue
        title = book.get("fullTitle") or book.get("title") or ""
        if _enqueue(key, title, book.get("author"), book.get("isbn")):
            queued += 1
    return queued


def summary(total=None):
    """How far the pass has got — the line the library screen shows while it runs."""
    counts = {"found": 0, "missing": 0, "failed": 0}
    for record in lookups().values():
        status = record.get("status")
        if status in counts:
            counts[status] += 1
    with _queue_lock:
        pending = len(_pending)
    return {"enabled": enabled(), "pending": pending, "total": total, **counts}
