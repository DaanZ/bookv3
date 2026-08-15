"""Who is reading.

Everything this app records about reading — where you stopped, how many sittings it
took, which books you finished and when — lived in one file, and so belonged to whoever
set the tablet up. A second person could read a book but not keep a page in it: opening
it moved somebody else's bookmark.

A profile is that bookmark, per person. `data/profiles.json` is the list; the reading
itself is one file each under `data/positions/`, so profiles are separate by
construction rather than by remembering to filter.

What a reader owns beyond their bookmarks is their **preferences** — register, palette,
pointer focus, how many highlights a page may carry. Those were in the browser's
localStorage, which made them the tablet's rather than the reader's: two people sharing
one tablet shared one theme, and the same person on a second tablet started over. They
live on the profile row now, and the browser keeps only a copy for the first paint.

Two things are deliberately *not* per profile:

* **The books themselves.** `books/available` and `books/read` are one shelf in one
  house. A guest finishing a book records their own finish; it does not re-file the
  house's copy or change what anyone else sees on the shelf. Only the owner's finish
  moves the file, exactly as it did before profiles existed.
* **Hardcover.** There is one `HARDCOVER_API_KEY`, and it is one person's account.
  Marking a book read there is the owner's finish and nobody else's — a guest's finish
  says so rather than quietly writing to a stranger's shelf.

The owner is the profile that already existed: the first one, id `owner`, holding the
history that was in `data/positions.json` before this. There is no login and no
password. This is a reading app on a tablet in a house, and asking who is holding it is
the whole of the security model.
"""

import os
import threading
import uuid
from datetime import datetime, timezone

from util.files import json_read_file, json_write_file

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(ROOT, "data")
STORE_PATH = os.path.join(STORE_DIR, "profiles.json")

# The profile that owns the shelf. A fixed id rather than a generated one, because the
# reading history that predates profiles is migrated onto it and that has to be stable.
OWNER_ID = "owner"
OWNER_NAME = "Reader"

# A tone each, so a profile is recognisable before the name is read — the same job the
# category patch does for a book. Assigned in order and wrapped, never chosen.
TONES = ["#1F6F6B", "#B4592B", "#4B5FA8", "#7A6A2F", "#8C3F63", "#3C7A45"]

# A house, not a service. The cap keeps the picker one screen and the store one file.
MAX_PROFILES = 12
MAX_NAME = 40

# What a reader owns. The same four the design lists as settings belonging to the reader
# rather than the app — and the same defaults `web/src/lib/prefs.js` started from, so a
# profile that has never changed anything looks exactly like the app did before.
PREF_DEFAULTS = {
    "theme": "night",
    "palette": "sunset",
    "focusMode": True,
    "maxHighlights": 8,
}

THEMES = ("day", "night")

# The palette names live in `web/src/lib/reading.js`, and duplicating the list here
# would be two places to edit for one addition. This stores whatever the UI sends, kept
# short and to a shape a name can have — the UI already falls back on one it cannot use.
MAX_PALETTE = 32

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read() -> list:
    stored = json_read_file(STORE_PATH)
    if isinstance(stored, dict):
        stored = stored.get("profiles")
    return [p for p in stored if isinstance(p, dict) and p.get("id")] if isinstance(stored, list) else []


def _write(rows: list) -> None:
    os.makedirs(STORE_DIR, exist_ok=True)
    json_write_file(STORE_PATH, {"profiles": rows})


def _owner_row() -> dict:
    return {
        "id": OWNER_ID,
        "name": OWNER_NAME,
        "tone": TONES[0],
        "owner": True,
        "createdAt": _now(),
        "prefs": dict(PREF_DEFAULTS),
    }


def clean_prefs(patch: dict | None) -> dict:
    """Keep the four settings, drop everything else, and make each one the shape it is
    meant to be.

    A whitelist rather than a merge: this comes off the wire, it is written to a file
    the whole app reads, and a browser is free to send anything at all.
    """
    out = {}
    if not isinstance(patch, dict):
        return out

    if patch.get("theme") in THEMES:
        out["theme"] = patch["theme"]
    palette = patch.get("palette")
    if isinstance(palette, str) and palette.strip():
        out["palette"] = palette.strip()[:MAX_PALETTE]
    if "focusMode" in patch:
        out["focusMode"] = bool(patch["focusMode"])
    if "maxHighlights" in patch:
        try:
            # 0 is meaningful — it turns highlighting off — so the floor is 0, not 1.
            out["maxHighlights"] = max(0, min(24, int(patch["maxHighlights"])))
        except (TypeError, ValueError):
            pass
    return out


def _ensure(rows: list) -> list:
    """There is always an owner. A store with none — deleted by hand, or never written
    — gets one rather than leaving the app with nobody to be.

    Also fills in preferences: rows written before they existed have none, and a reader
    with no theme is not a reader who chose the dark one.
    """
    if not any(row.get("owner") for row in rows):
        rows = [_owner_row()] + rows
    for row in rows:
        row["prefs"] = {**PREF_DEFAULTS, **clean_prefs(row.get("prefs"))}
    return rows


def all_profiles() -> list:
    with _lock:
        rows = _ensure(_read())
        return [dict(row) for row in rows]


def get(profile_id: str | None) -> dict | None:
    if not profile_id:
        return None
    return next((row for row in all_profiles() if row["id"] == profile_id), None)


def owner() -> dict:
    return next(row for row in all_profiles() if row.get("owner"))


def resolve(profile_id: str | None) -> dict:
    """The profile a request is for. An unknown or missing id is the owner — a request
    from a browser that has never picked one is the person who set the tablet up, which
    is what the app did before profiles existed."""
    return get(profile_id) or owner()


def _clean_name(name: str | None) -> str:
    return " ".join((name or "").split())[:MAX_NAME]


def create(name: str) -> tuple[dict | None, str | None]:
    """Add a reader. Returns (profile, error)."""
    clean = _clean_name(name)
    if not clean:
        return None, "A profile needs a name."

    with _lock:
        rows = _ensure(_read())
        if len(rows) >= MAX_PROFILES:
            return None, f"There is room for {MAX_PROFILES} profiles."
        if any(row["name"].casefold() == clean.casefold() for row in rows):
            return None, f"There is already a profile called “{clean}”."

        row = {
            # Generated, never derived from the name: this id becomes a filename under
            # data/positions/, and a name is whatever someone types.
            "id": uuid.uuid4().hex[:12],
            "name": clean,
            "tone": TONES[len(rows) % len(TONES)],
            "owner": False,
            "createdAt": _now(),
            # A new reader starts from the defaults, never from whoever was here last.
            "prefs": dict(PREF_DEFAULTS),
        }
        rows.append(row)
        _write(rows)
        return dict(row), None


def rename(profile_id: str, name: str) -> tuple[dict | None, str | None]:
    clean = _clean_name(name)
    if not clean:
        return None, "A profile needs a name."

    with _lock:
        rows = _ensure(_read())
        row = next((r for r in rows if r["id"] == profile_id), None)
        if row is None:
            return None, "No such profile."
        if any(other["id"] != profile_id and other["name"].casefold() == clean.casefold()
               for other in rows):
            return None, f"There is already a profile called “{clean}”."
        row["name"] = clean
        _write(rows)
        return dict(row), None


def set_prefs(profile_id: str, patch: dict) -> tuple[dict | None, str | None]:
    """Change some of a reader's settings. A patch, not a replacement: the UI sends the
    one thing that moved, and a key this version does not know is dropped rather than
    stored for a version that might."""
    with _lock:
        rows = _ensure(_read())
        row = next((r for r in rows if r["id"] == profile_id), None)
        if row is None:
            return None, "No such profile."
        row["prefs"] = {**row["prefs"], **clean_prefs(patch)}
        _write(rows)
        return dict(row), None


def remove(profile_id: str) -> tuple[bool, str | None]:
    """Delete a profile and the reading it recorded.

    The owner cannot be deleted: their history is the shelf's own, and the books in
    `books/read` are theirs. Renaming is the way to hand the tablet over.
    """
    with _lock:
        rows = _ensure(_read())
        row = next((r for r in rows if r["id"] == profile_id), None)
        if row is None:
            return False, "No such profile."
        if row.get("owner"):
            return False, "The owner profile cannot be deleted — rename it instead."

        _write([r for r in rows if r["id"] != profile_id])

    from api import positions

    positions.forget_profile(profile_id)
    return True, None
