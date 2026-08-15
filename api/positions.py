"""Where you stopped, per book.

One small JSON file under data/ (already gitignored) holding
`{key: {part, page, lastReadAt, startedAt, sittings}}`. The resume strip, the
"paused N days ago" line and the finish screen's "read in N sittings over M days"
are all computed from this — nothing else in the repo records reading history.
"""

import json
import os
import tempfile
import threading
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(ROOT, "data")
STORE_PATH = os.path.join(STORE_DIR, "positions.json")

# A gap longer than this starts a new sitting rather than continuing the last one.
SITTING_GAP_HOURS = 4

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read() -> dict:
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write(data: dict) -> None:
    os.makedirs(STORE_DIR, exist_ok=True)
    # Atomic: a half-written store would lose every book's position at once.
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=STORE_DIR, prefix=".positions-", suffix=".tmp", delete=False
    )
    try:
        with handle:
            json.dump(data, handle, indent=2)
        os.replace(handle.name, STORE_PATH)
    except Exception:
        os.unlink(handle.name)
        raise


def all_positions() -> dict:
    with _lock:
        return _read()


def get_position(key: str) -> dict | None:
    return all_positions().get(key)


def _hours_since(iso: str | None) -> float:
    if not iso:
        return float("inf")
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return float("inf")
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).total_seconds() / 3600


def save_position(key: str, part: int, page: int) -> dict:
    with _lock:
        data = _read()
        entry = dict(data.get(key) or {})
        now = _now()

        if not entry.get("startedAt"):
            entry["startedAt"] = now
        if _hours_since(entry.get("lastReadAt")) >= SITTING_GAP_HOURS:
            entry["sittings"] = int(entry.get("sittings") or 0) + 1

        entry.update({"part": max(0, int(part)), "page": max(0, int(page)), "lastReadAt": now})
        data[key] = entry
        _write(data)
        return entry


def record_finish(key: str, marked_read: bool) -> dict:
    """Remember how the Hardcover call went, so re-opening a finished book reports
    what actually happened rather than guessing (or claiming) an outcome."""
    with _lock:
        data = _read()
        entry = dict(data.get(key) or {})
        # The first finish is the one that counts. Overwriting this on a re-finish would
        # renumber the shelf — a book read months ago would jump to the end of the
        # order the moment it was opened again.
        entry.setdefault("finishedAt", _now())
        entry["markedRead"] = bool(marked_read)
        data[key] = entry
        _write(data)
        return entry


def set_marked_read(key: str, marked_read: bool) -> dict | None:
    """Update only the Hardcover outcome, leaving the finish date — and so the book's
    place in the completed order — alone."""
    with _lock:
        data = _read()
        entry = data.get(key)
        if entry is None:
            return None
        entry["markedRead"] = bool(marked_read)
        _write(data)
        return entry


def finish_ordinal(key: str, positions: dict | None = None) -> int | None:
    """Which number this book was to be finished. None if it never was.

    Counted over the books this app recorded a finish for, in the order they were
    finished. It deliberately does not count the contents of books/read: those arrived
    by other routes — a hand move, or the pipeline's own history — with no date to place
    them in the order, and inventing one would make the number a guess.
    """
    data = positions if positions is not None else all_positions()
    entry = data.get(key) or {}
    finished = entry.get("finishedAt")
    if not finished:
        return None

    earlier = sum(
        1
        for other, value in data.items()
        if other != key and (value or {}).get("finishedAt") and value["finishedAt"] <= finished
    )
    return earlier + 1


def finished_count(positions: dict | None = None) -> int:
    data = positions if positions is not None else all_positions()
    return sum(1 for value in data.values() if (value or {}).get("finishedAt"))


def clear_position(key: str) -> None:
    with _lock:
        data = _read()
        if key in data:
            del data[key]
            _write(data)
