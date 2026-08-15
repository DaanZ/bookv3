"""Where you stopped, per book, per profile.

One small JSON file per profile under `data/positions/` (already gitignored) holding
`{key: {part, page, lastReadAt, startedAt, sittings}}`. The resume strip, the
"paused N days ago" line and the finish screen's "read in N sittings over M days"
are all computed from this — nothing else in the repo records reading history.

The ambience a reader chose for a book rides in the same entry, under `ambience`. It
belongs there for the reason the handoff gives for storing it per book at all — the bed
is a property of *this book for this reader*, not of the app — and keeping it here means
one store, one file, and a choice that follows the person to another tablet instead of
staying on the glass they happened to pick it on.

Every function takes the profile whose reading it is. There is no "current" profile
here on purpose: a module-level one would be a single global on a server two people can
be using from two tablets at once, and the bug it caused would be somebody else's
bookmark moving. The profile arrives with the request (`X-Profile`) and is threaded
down.

`data/positions.json` — the single store this replaced — is moved onto the owner's
profile the first time this module loads, so the history from before profiles existed
belongs to the person who made it.
"""

import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(ROOT, "data")
PROFILE_DIR = os.path.join(STORE_DIR, "positions")
LEGACY_PATH = os.path.join(STORE_DIR, "positions.json")

# A gap longer than this starts a new sitting rather than continuing the last one.
SITTING_GAP_HOURS = 4

# Profile ids are generated (uuid hex, or the literal "owner"), so this only ever
# rejects a caller that made one up — but it is checked anyway, because the id is about
# to become a path.
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _path(profile: str) -> str:
    if not _SAFE_ID.match(profile or ""):
        raise ValueError(f"Not a profile id: {profile!r}")
    return os.path.join(PROFILE_DIR, f"{profile}.json")


def _migrate_legacy() -> None:
    """Move the pre-profile store onto the owner's profile, once.

    Moved rather than copied: two stores holding the same reading, one of them never
    read again, is the kind of leftover that gets edited by mistake a year later.
    """
    from api.profiles import OWNER_ID

    if not os.path.exists(LEGACY_PATH):
        return
    os.makedirs(PROFILE_DIR, exist_ok=True)
    target = os.path.join(PROFILE_DIR, f"{OWNER_ID}.json")
    if os.path.exists(target):
        return
    try:
        os.replace(LEGACY_PATH, target)
    except OSError:
        pass


_migrate_legacy()


def _read(profile: str) -> dict:
    try:
        with open(_path(profile), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write(profile: str, data: dict) -> None:
    os.makedirs(PROFILE_DIR, exist_ok=True)
    # Atomic: a half-written store would lose every book's position at once.
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=PROFILE_DIR, prefix=".positions-", suffix=".tmp", delete=False
    )
    try:
        with handle:
            json.dump(data, handle, indent=2)
        os.replace(handle.name, _path(profile))
    except Exception:
        os.unlink(handle.name)
        raise


def all_positions(profile: str) -> dict:
    with _lock:
        return _read(profile)


def get_position(profile: str, key: str) -> dict | None:
    return all_positions(profile).get(key)


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


def save_position(profile: str, key: str, part: int, page: int) -> dict:
    with _lock:
        data = _read(profile)
        entry = dict(data.get(key) or {})
        now = _now()

        if not entry.get("startedAt"):
            entry["startedAt"] = now
        if _hours_since(entry.get("lastReadAt")) >= SITTING_GAP_HOURS:
            entry["sittings"] = int(entry.get("sittings") or 0) + 1

        entry.update({"part": max(0, int(part)), "page": max(0, int(page)), "lastReadAt": now})
        data[key] = entry
        _write(profile, data)
        return entry


def record_finish(profile: str, key: str, marked_read: bool | None) -> dict:
    """Remember how the Hardcover call went, so re-opening a finished book reports
    what actually happened rather than guessing (or claiming) an outcome.

    `marked_read` is None for a profile that is not the owner: nothing was sent to
    Hardcover on their behalf, which is not the same as sending it and being refused.
    """
    with _lock:
        data = _read(profile)
        entry = dict(data.get(key) or {})
        # The first finish is the one that counts. Overwriting this on a re-finish would
        # renumber the shelf — a book read months ago would jump to the end of the
        # order the moment it was opened again.
        entry.setdefault("finishedAt", _now())
        entry["markedRead"] = None if marked_read is None else bool(marked_read)
        data[key] = entry
        _write(profile, data)
        return entry


# The ambience handoff's own shape: which bed, and how loud. `on` is deliberately not
# kept — nothing may autoplay, so a bed that was playing when the book closed is restored
# as a choice and not as sound, which is what the reader already does with it.
def save_ambience(profile: str, key: str, bed: str | None, level: float | None) -> dict:
    """Remember the bed this reader chose for this book."""
    with _lock:
        data = _read(profile)
        entry = dict(data.get(key) or {})
        ambience = dict(entry.get("ambience") or {})

        if bed is not None:
            ambience["bed"] = str(bed)[:32]
        if level is not None:
            try:
                ambience["level"] = max(0.0, min(1.0, float(level)))
            except (TypeError, ValueError):
                pass

        entry["ambience"] = ambience
        data[key] = entry
        _write(profile, data)
        return entry


def set_marked_read(profile: str, key: str, marked_read: bool) -> dict | None:
    """Update only the Hardcover outcome, leaving the finish date — and so the book's
    place in the completed order — alone."""
    with _lock:
        data = _read(profile)
        entry = data.get(key)
        if entry is None:
            return None
        entry["markedRead"] = bool(marked_read)
        _write(profile, data)
        return entry


def finish_ordinal(key: str, positions: dict) -> int | None:
    """Which number this book was to be finished, for the profile these positions
    belong to. None if it never was.

    Counted over the books this app recorded a finish for, in the order they were
    finished. It deliberately does not count the contents of books/read: those arrived
    by other routes — a hand move, or the pipeline's own history — with no date to place
    them in the order, and inventing one would make the number a guess.
    """
    entry = positions.get(key) or {}
    finished = entry.get("finishedAt")
    if not finished:
        return None

    earlier = sum(
        1
        for other, value in positions.items()
        if other != key and (value or {}).get("finishedAt") and value["finishedAt"] <= finished
    )
    return earlier + 1


def finished_count(positions: dict) -> int:
    return sum(1 for value in positions.values() if (value or {}).get("finishedAt"))


def clear_position(profile: str, key: str) -> None:
    with _lock:
        data = _read(profile)
        if key in data:
            del data[key]
            _write(profile, data)


def forget_everywhere(key: str) -> None:
    """Drop a book from every profile's history — for when the book itself is deleted.

    A deleted summary is gone for the whole house, so leaving one reader holding a page
    in it would put a bookmark in a book nobody can open.
    """
    for profile in stored_profiles():
        clear_position(profile, key)


def forget_profile(profile: str) -> None:
    """Delete a profile's reading, when the profile itself is deleted."""
    try:
        os.remove(_path(profile))
    except (OSError, ValueError):
        pass


def stored_profiles() -> list[str]:
    """The profile ids that have a store on disk. Not the same list as `profiles.py`
    keeps — a profile that has never opened a book has no file yet."""
    try:
        return [name[:-5] for name in os.listdir(PROFILE_DIR) if name.endswith(".json")]
    except FileNotFoundError:
        return []


def progress_of(profile: str) -> dict:
    """What the profile picker shows under each name."""
    data = all_positions(profile)
    return {
        "read": finished_count(data),
        "reading": sum(
            1
            for value in data.values()
            if not (value or {}).get("finishedAt")
            and ((value or {}).get("part") or (value or {}).get("page"))
        ),
        "lastReadAt": max((v.get("lastReadAt") or "" for v in data.values()), default="") or None,
    }
