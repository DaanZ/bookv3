"""Covers, fetched once per book, without anyone asking.

The pipeline knows a book's title and author — it read them off the first pages — but
nothing in `books/*.json` says what the jacket looks like. Hardcover does. So every book
gets looked up once, in the background, and the cover is downloaded and kept; the shelf
shows it next time it loads. There is no per-book "look up" button, because a button is
a thing to click 264 times.

Three rules hold this in place:

* **Read-only.** Only the search queries are ever called from here — never
  `insert_user_book`. Marking a book read stays where it was: a deliberate act on the
  finish screen. An automatic background pass must not be able to write to someone's
  reading history.
* **Once per book, and slowly.** One worker thread, one request at a time, a pause
  between them. The outcome is written to `data/enrichment.json` — found, missing or
  failed — and a book that has an outcome is never looked up again. Only failures are
  retried, and not for `RETRY_AFTER_HOURS`.
* **Never load-bearing.** No key, no network, no match, a 500 from the image host: the
  shelf renders exactly as it did before, on the category patch. Nothing here is
  awaited by a request handler.

Covers are downloaded rather than hotlinked so the reader keeps working on a tablet
that is offline, or on a network where the image host is blocked — the same failure the
webfonts already have.
"""

import json
import os
import queue
import re
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

from hardcover.request import cover_url_of, search_book_details

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(ROOT, "data")
STORE_PATH = os.path.join(STORE_DIR, "enrichment.json")
COVER_DIR = os.path.join(STORE_DIR, "covers")

# Hardcover asks for a courteous rate. Nothing is waiting on this — a full library takes
# a few minutes to work through and no one is watching it happen.
REQUEST_INTERVAL_SECONDS = 1.5

# A lookup that failed (network down, key missing) is worth trying again later. One that
# came back "no such book" is not: the answer will not change on its own.
RETRY_AFTER_HOURS = 6

# Covers are a few hundred KB. Anything past this is not a jacket.
MAX_COVER_BYTES = 6 * 1024 * 1024
COVER_TIMEOUT = 20

_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
}

_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")

_lock = threading.Lock()
_work: "queue.Queue[tuple[str, str, str]]" = queue.Queue()
_pending: set[str] = set()
_worker: threading.Thread | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def enabled() -> bool:
    """Without a key the search returns an error for every book; queueing 264 of those
    is just a slow way to write the same sentence 264 times."""
    return bool(os.environ.get("HARDCOVER_API_KEY"))


# --- the store -------------------------------------------------------------------

def _read() -> dict:
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write(data: dict) -> None:
    os.makedirs(STORE_DIR, exist_ok=True)
    # Atomic, for the same reason positions.py is: a half-written store would lose
    # every book's lookup at once, and they are minutes of someone else's API quota.
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=STORE_DIR, prefix=".enrichment-", suffix=".tmp", delete=False
    )
    try:
        with handle:
            json.dump(data, handle, indent=2)
        os.replace(handle.name, STORE_PATH)
    except Exception:
        os.unlink(handle.name)
        raise


def all_entries() -> dict:
    with _lock:
        return _read()


def entry(key: str) -> dict | None:
    return all_entries().get(key)


def _save(key: str, record: dict) -> dict:
    with _lock:
        data = _read()
        data[key] = record
        _write(data)
        return record


def forget(key: str) -> None:
    """Drop a book's lookup and its cover file — for when the book itself is deleted."""
    with _lock:
        data = _read()
        record = data.pop(key, None)
        if record is not None:
            _write(data)
    _remove_cover(record)


# --- covers on disk --------------------------------------------------------------

def _cover_name(key: str, extension: str) -> str:
    """A filename derived from the key, which is itself a filename stem. Sanitised
    again anyway: this string is about to become a path."""
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", key).strip("._-") or "cover"
    return f"{stem[:120]}{extension}"


def _remove_cover(record: dict | None) -> None:
    name = (record or {}).get("coverFile")
    if not name or not _SAFE_NAME.match(name):
        return
    try:
        os.remove(os.path.join(COVER_DIR, name))
    except OSError:
        pass


def cover_path(key: str) -> str | None:
    """The stored jacket for a book, or None. The name comes from our own store, never
    from the caller, and the result is checked to be inside COVER_DIR regardless."""
    name = (entry(key) or {}).get("coverFile")
    if not name or not _SAFE_NAME.match(name):
        return None

    root = os.path.realpath(COVER_DIR)
    candidate = os.path.realpath(os.path.join(root, name))
    if not candidate.startswith(root + os.sep):
        return None
    return candidate if os.path.isfile(candidate) else None


def _download_cover(key: str, url: str) -> tuple[str | None, str | None]:
    """Fetch the jacket. Returns (filename, error)."""
    try:
        response = requests.get(url, timeout=COVER_TIMEOUT, stream=True)
    except requests.RequestException as ex:
        return None, f"Could not fetch the cover: {ex}"

    with response:
        if response.status_code != 200:
            return None, f"The cover host returned {response.status_code}."

        content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        if not content_type.startswith("image/"):
            return None, f"The cover URL served {content_type or 'no content type'}."

        data = bytearray()
        for block in response.iter_content(64 * 1024):
            data.extend(block)
            if len(data) > MAX_COVER_BYTES:
                return None, "The cover is larger than 6MB, which no jacket is."

    if not data:
        return None, "The cover URL served an empty file."

    name = _cover_name(key, _EXTENSIONS.get(content_type, ".img"))
    os.makedirs(COVER_DIR, exist_ok=True)
    path = os.path.join(COVER_DIR, name)
    try:
        # Written beside the target and moved, so a half-downloaded file is never
        # served: the store points at a name that either exists whole or not at all.
        handle = tempfile.NamedTemporaryFile(
            "wb", dir=COVER_DIR, prefix=".cover-", suffix=".tmp", delete=False
        )
        with handle:
            handle.write(bytes(data))
        os.replace(handle.name, path)
    except OSError as ex:
        return None, f"Could not save the cover: {ex}"

    return name, None


# --- the lookup ------------------------------------------------------------------

def _lookup(key: str, title: str, author: str) -> dict:
    previous = entry(key)
    book, error = search_book_details(title, author)

    if error:
        # A re-check that failed must not throw away a jacket already on disk — only a
        # successful lookup is allowed to replace one.
        if previous and previous.get("coverFile"):
            return _save(key, {**previous, "checkedAt": _now(), "error": error})

        # "No book matching X" is an answer; the rest are failures worth retrying.
        missing = "has no book matching" in error
        record = {
            "status": "missing" if missing else "failed",
            "checkedAt": _now(),
            "error": error,
        }
        return _save(key, record)

    record = {
        "status": "found",
        "checkedAt": _now(),
        "hardcoverId": book.get("id"),
        "slug": book.get("slug"),
        "matchedTitle": book.get("title"),
        "releaseYear": book.get("release_year"),
        "coverUrl": cover_url_of(book),
        "coverFile": None,
        "error": None,
    }

    if record["coverUrl"]:
        name, cover_error = _download_cover(key, record["coverUrl"])
        record["coverFile"] = name
        if cover_error:
            # The match is still worth keeping; only the jacket is missing, and the
            # status says so rather than pretending the book was never found.
            record["status"] = "nocover"
            record["error"] = cover_error
    else:
        record["status"] = "nocover"
        record["error"] = "Hardcover has no cover image for this edition."

    saved = _save(key, record)
    if previous and previous.get("coverFile") != record.get("coverFile"):
        _remove_cover(previous)
    return saved


def _drain():
    last_request = 0.0
    while True:
        key, title, author = _work.get()
        try:
            wait = REQUEST_INTERVAL_SECONDS - (time.monotonic() - last_request)
            if wait > 0:
                time.sleep(wait)
            last_request = time.monotonic()
            _lookup(key, title, author)
        except Exception as ex:  # a background pass must not take its own thread down
            _save(key, {"status": "failed", "checkedAt": _now(), "error": f"{type(ex).__name__}: {ex}"})
        finally:
            with _lock:
                _pending.discard(key)
            _work.task_done()


def _ensure_worker():
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_drain, name="enrich", daemon=True)
            _worker.start()


def _stale(record: dict | None) -> bool:
    """Is this book worth (re-)looking up?"""
    if record is None:
        return True
    if record.get("status") in ("found", "nocover", "missing"):
        return False
    checked = record.get("checkedAt")
    if not checked:
        return True
    try:
        then = datetime.fromisoformat(checked)
    except ValueError:
        return True
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - then > timedelta(hours=RETRY_AFTER_HOURS)


def _enqueue(key: str, title: str, author: str | None) -> bool:
    if not key or not title:
        return False
    with _lock:
        if key in _pending:
            return False
        _pending.add(key)

    _ensure_worker()
    _work.put((key, title, author or ""))
    return True


def queue(key: str, title: str, author: str | None = None, force: bool = False) -> bool:
    """Ask for one book to be looked up. Returns whether it was actually queued."""
    if not enabled():
        return False
    if not force and not _stale(entry(key)):
        return False
    return _enqueue(key, title, author)


def queue_missing(books) -> int:
    """Queue every book that has never been looked up. Called with the shelf, so a
    library that predates this module fills in by itself rather than staying blank —
    the alternative is covers only on books ingested from today on.

    One read of the store for the whole shelf, and the work happens on the worker; the
    request this was called from does not wait for any of it.
    """
    if not enabled():
        return 0
    known = all_entries()
    queued = 0
    for book in books:
        key = book.get("key")
        if not key or not _stale(known.get(key)):
            continue
        title = book.get("fullTitle") or book.get("title") or ""
        if _enqueue(key, title, book.get("author")):
            queued += 1
    return queued


def summary(total: int | None = None) -> dict:
    """What the library screen reports while this is happening."""
    entries = all_entries()
    counts = {"found": 0, "nocover": 0, "missing": 0, "failed": 0}
    for record in entries.values():
        status = record.get("status")
        if status in counts:
            counts[status] += 1
    with _lock:
        pending = len(_pending)
    return {
        "enabled": enabled(),
        "checked": len(entries),
        "pending": pending,
        "total": total,
        **counts,
    }
