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
        entry["finishedAt"] = _now()
        entry["markedRead"] = bool(marked_read)
        data[key] = entry
        _write(data)
        return entry


def clear_position(key: str) -> None:
    with _lock:
        data = _read()
        if key in data:
            del data[key]
            _write(data)
