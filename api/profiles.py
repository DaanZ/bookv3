"""Who is reading.

Everything this app records about reading — where you stopped, how many sittings it
took, which books you finished and when — lived in one file, and so belonged to whoever
set the tablet up. A second person could read a book but not keep a page in it: opening
it moved somebody else's bookmark.

A profile is that bookmark, per person. `data/profiles.json` is the list; the reading
itself is one file each under `data/positions/`, so profiles are separate by
construction rather than by remembering to filter.

What a reader owns beyond their bookmarks is their **preferences** — register, palette,
how many highlights a page may carry. Those were in the browser's
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

Three kinds of reader, and the difference between them is what they may do rather than
who they are:

* **Guest** — nobody in particular. The catalogue is open: anyone can pick the tablet up
  and read what is on the shelf without saying who they are, and `resolve` answers an
  unknown or absent `X-Profile` with the guest rather than with the owner, so browsing
  anonymously never means browsing *as* somebody. A guest has no store, keeps no page,
  and gets no recommendations, because a recommendation needs a history to come from.
* **A profile** — a reader. Keeps a page in every book, its own settings, its own
  finishes, and gets books suggested from what it has actually read.
* **The owner, who is the admin.** The only one who may add a book, delete one, re-file
  one, or write to Hardcover. Everything that changes what is *on* the shelf is theirs;
  everything that changes what somebody has *read of* it belongs to the reader.

The owner is the profile that already existed: the first one, id `owner`, holding the
history that was in `data/positions.json` before this.

**The PIN is a lock on the picker, not on the API.** A profile can carry one, and then
the app will not switch into it without the four digits — which is the whole of the
problem it is for: somebody else in the house picking up the tablet and reading as you,
by accident or by nosiness. It is deliberately not authentication. `X-Profile` is still
a header a client asserts about itself, so anything that can make an HTTP request can
still read as anyone; making that untrue needs a token the server issues and checks,
which is a bigger change than a lock on a tablet warrants. Do not build anything on the
PIN that would be a problem if it were bypassed.

What it does do properly, because a half-done lock is worse than none: the digits are
never sent to the browser, the stored form is salted and run through a KDF, changing or
removing one needs the old one, and guesses are rate limited — 10,000 combinations is
minutes of scripted tries otherwise.
"""

import hashlib
import hmac
import os
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from util.files import json_read_file, json_write_file

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(ROOT, "data")
STORE_PATH = os.path.join(STORE_DIR, "profiles.json")

# The profile that owns the shelf. A fixed id rather than a generated one, because the
# reading history that predates profiles is migrated onto it and that has to be stable.
OWNER_ID = "owner"
OWNER_NAME = "Reader"

# Not a row in the store and never written to one: the guest is what the server answers
# with when nobody has said who they are. Shaped like a profile so every caller can treat
# it as one, and flagged so the handful that must not — writes — can tell.
GUEST_ID = "guest"
GUEST_NAME = "Guest"

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
    "maxHighlights": 8,
}

THEMES = ("day", "night")

# The palette names live in `web/src/lib/reading.js`, and duplicating the list here
# would be two places to edit for one addition. This stores whatever the UI sends, kept
# short and to a shape a name can have — the UI already falls back on one it cannot use.
MAX_PALETTE = 32

# Digits only, and few of them: this is tapped on a tablet by somebody who wants to read
# a book, not typed on a keyboard by somebody logging in.
PIN_MIN, PIN_MAX = 4, 8

# Guessing. Five tries, then a pause that doubles — 30s, 60s, 120s… to five minutes.
# Held in memory, so a restart forgives everything: the point is to make a script slow,
# not to punish the person who mistyped their own PIN twice.
PIN_TRIES = 5
PIN_LOCKOUT_SECONDS = 30
PIN_LOCKOUT_MAX = 300

_attempts: dict[str, dict] = {}

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


def guest_row() -> dict:
    """Anyone at all. Read-only by construction: nothing here is stored, so there is
    nothing for a write to land in."""
    return {
        "id": GUEST_ID,
        "name": GUEST_NAME,
        "tone": "#4A5A5C",
        "owner": False,
        "guest": True,
        "hasPin": False,
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


def _public(row: dict) -> dict:
    """A profile as everything outside this module sees it.

    The stored PIN never leaves here. Not by being stripped at the edge — by never being
    on a row any other module can reach, so there is no serialiser to forget. What
    callers get instead is `hasPin`, which is the only part of it the UI needs.
    """
    out = {k: v for k, v in row.items() if k not in ("pin", "hardcover", "devices")}
    out["hasPin"] = bool(row.get("pin"))
    # Device tokens are hashes of credentials, so they leave by the same door as the PIN.
    # The count is what the screen needs: "remembered on 2 devices", and a way to undo it.
    out["devices"] = len(_live_devices(row))
    # Same discipline as the PIN, for the same reason: a Hardcover token is a credential
    # that can write to somebody's public shelf. The UI needs to know whether one is set,
    # never what it is.
    out["hasHardcover"] = bool(row.get("hardcover"))
    return out


def all_profiles() -> list:
    with _lock:
        rows = _ensure(_read())
        return [_public(row) for row in rows]


def get(profile_id: str | None) -> dict | None:
    if not profile_id:
        return None
    return next((row for row in all_profiles() if row["id"] == profile_id), None)


def owner() -> dict:
    return next(row for row in all_profiles() if row.get("owner"))


def resolve(profile_id: str | None) -> dict:
    """The reader a request is for.

    An unknown or missing id is the **guest**, not the owner. Reading the catalogue
    needs nobody's permission, so a request that says nothing about who it is gets the
    catalogue and nothing personal — rather than quietly being answered as the person
    who set the tablet up, which would hand their reading to anyone who asked without a
    header.
    """
    if profile_id == GUEST_ID:
        return guest_row()
    return get(profile_id) or guest_row()


def is_guest(profile: dict | None) -> bool:
    return bool((profile or {}).get("guest"))


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
        return _public(row), None


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
        return _public(row), None


def set_hardcover(profile_id: str, token: str | None) -> tuple[dict | None, str | None]:
    """Give a reader their own Hardcover account, or take it away.

    Per reader rather than per app, which is the whole point: a finished book belongs to
    whoever read it, so it should land on *their* shelf and nowhere else. A profile with
    no token is not an error and not a failure — it is somebody who reads here and keeps
    their list somewhere else, or nowhere.

    Stored as given, because unlike a PIN it has to be replayed to Hardcover. It lives in
    `data/profiles.json`, which is gitignored, and `_public` never lets it back out.
    """
    token = (token or "").strip() or None
    with _lock:
        rows = _ensure(_read())
        row = next((r for r in rows if r["id"] == profile_id), None)
        if row is None:
            return None, "No such profile."
        if token:
            row["hardcover"] = token
        else:
            row.pop("hardcover", None)
        _write(rows)
        return _public(row), None


def hardcover_token(profile_id: str | None) -> str | None:
    """The reader's own token, for the code that actually talks to Hardcover.

    Deliberately not on the public row, so reaching it is a decision a caller makes by
    name rather than something that rides along in a response by accident.
    """
    if not profile_id:
        return None
    with _lock:
        row = next((r for r in _ensure(_read()) if r["id"] == profile_id), None)
        return (row or {}).get("hardcover")


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
        return _public(row), None


# --- the PIN --------------------------------------------------------------------

def _hash_pin(pin: str, salt: bytes) -> str:
    """scrypt where the build has it, pbkdf2 where it does not.

    Neither saves four digits from an offline search — 10,000 candidates is 10,000
    candidates — which is why the rate limit above is the part doing the real work. The
    KDF and the salt are here so that the file is not a list of PINs in the clear, and
    so that two readers who chose 1234 do not have the same row.
    """
    try:
        return "scrypt$" + hashlib.scrypt(
            pin.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32
        ).hex()
    except (ValueError, MemoryError):  # pragma: no cover — old or memory-capped builds
        return "pbkdf2$" + hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 240_000).hex()


def _verify_hash(pin: str, stored: dict) -> bool:
    salt = bytes.fromhex(stored.get("salt") or "")
    expected = stored.get("hash") or ""
    if not salt or not expected:
        return False
    algo = expected.split("$", 1)[0]
    if algo == "pbkdf2":
        candidate = "pbkdf2$" + hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 240_000).hex()
    else:
        candidate = _hash_pin(pin, salt)
    # Constant time: the comparison is over a digest, but leaking where two hashes first
    # differ is a habit worth not having.
    return hmac.compare_digest(candidate, expected)


def _clean_pin(pin: str | None) -> str | None:
    pin = (pin or "").strip()
    if not pin.isdigit() or not (PIN_MIN <= len(pin) <= PIN_MAX):
        return None
    return pin


def _blocked_for(profile_id: str) -> int:
    """Seconds left before this profile will take another guess."""
    state = _attempts.get(profile_id)
    if not state:
        return 0
    return max(0, int(state.get("until", 0) - time.monotonic()))


def _note_failure(profile_id: str) -> None:
    state = _attempts.setdefault(profile_id, {"count": 0, "until": 0})
    state["count"] += 1
    if state["count"] >= PIN_TRIES:
        over = state["count"] - PIN_TRIES
        state["until"] = time.monotonic() + min(
            PIN_LOCKOUT_MAX, PIN_LOCKOUT_SECONDS * (2 ** over)
        )


def check_pin(profile_id: str, pin: str | None) -> tuple[bool, str | None]:
    """Is this the profile's PIN? Returns (ok, error).

    The one place the stored form is read. Rate limited per profile, and a profile with
    no PIN answers yes to anything — there is nothing to be wrong about.
    """
    with _lock:
        row = next((r for r in _ensure(_read()) if r["id"] == profile_id), None)
    if row is None:
        return False, "No such profile."
    if not row.get("pin"):
        return True, None

    waiting = _blocked_for(profile_id)
    if waiting:
        return False, f"Too many tries — wait {waiting} seconds."

    if _verify_hash(_clean_pin(pin) or "", row["pin"]):
        _attempts.pop(profile_id, None)
        return True, None

    _note_failure(profile_id)
    waiting = _blocked_for(profile_id)
    return False, (f"That is not the PIN. Wait {waiting} seconds." if waiting else "That is not the PIN.")


# How long a device stays trusted once the PIN has been entered on it.
#
# A PIN that is asked every time on the tablet in your own house is a PIN that gets
# turned off, and then it protects nothing at all. Ninety days is long enough that the
# lock stops being a daily toll, and short enough that a tablet lent out, sold or lost
# stops opening your shelf within a season.
DEVICE_DAYS = 90


def _device_hash(token: str) -> str:
    """Plain SHA-256, unlike the PIN.

    A PIN is four digits and needs a slow KDF to make ten thousand guesses expensive.
    A device token is 256 bits of randomness from `secrets` — there is nothing to guess,
    so the slow hash would only be a tax paid on every app launch.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def _live_devices(row: dict) -> list:
    """Trusted devices with the expired ones dropped."""
    now = _now()
    return [d for d in (row.get("devices") or []) if (d.get("expires") or "") > now]


def remember_device(profile_id: str) -> tuple[str | None, str | None]:
    """Trust this device for `DEVICE_DAYS`, and hand back the only copy of the token.

    Minted after a correct PIN and never again: like the PIN itself, the stored form is a
    hash, so a token lost by the browser cannot be recovered — the reader enters the PIN
    once more and gets a new one.
    """
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=DEVICE_DAYS)).isoformat(
        timespec="seconds"
    )
    with _lock:
        rows = _ensure(_read())
        row = next((r for r in rows if r["id"] == profile_id), None)
        if row is None:
            return None, "No such profile."
        row["devices"] = _live_devices(row) + [
            {"hash": _device_hash(token), "since": _now(), "expires": expires}
        ]
        _write(rows)
    return token, None


def device_trusted(profile_id: str, token: str | None) -> bool:
    """Does this device still count as unlocked?

    Expiry is checked here rather than trusted from the browser: the device holds a copy
    of the date only so it can stop asking, and a copy held by the thing being checked is
    not a check.
    """
    if not token:
        return False
    with _lock:
        rows = _ensure(_read())
        row = next((r for r in rows if r["id"] == profile_id), None)
        if row is None:
            return False
        live = _live_devices(row)
        if len(live) != len(row.get("devices") or []):
            row["devices"] = live
            _write(rows)
    wanted = _device_hash(token)
    return any(hmac.compare_digest(d.get("hash") or "", wanted) for d in live)


def forget_devices(profile_id: str) -> tuple[dict | None, str | None]:
    """Stop trusting every device, everywhere. What you reach for when one goes missing."""
    with _lock:
        rows = _ensure(_read())
        row = next((r for r in rows if r["id"] == profile_id), None)
        if row is None:
            return None, "No such profile."
        row["devices"] = []
        _write(rows)
        return _public(row), None


def set_pin(profile_id: str, pin: str | None, current: str | None) -> tuple[dict | None, str | None]:
    """Set, change or remove a profile's PIN. `pin` of None removes it.

    Changing or removing needs the current one; setting a first PIN does not, because
    a profile without one is already open to whoever is holding the tablet — requiring
    proof of something that protects nothing would only be ceremony.
    """
    with _lock:
        rows = _ensure(_read())
        row = next((r for r in rows if r["id"] == profile_id), None)
        if row is None:
            return None, "No such profile."
        existing = row.get("pin")

    if existing:
        ok, error = check_pin(profile_id, current)
        if not ok:
            return None, error or "That is not the PIN."

    wanted = _clean_pin(pin)
    if pin is not None and str(pin).strip() and wanted is None:
        return None, f"A PIN is {PIN_MIN} to {PIN_MAX} digits."

    with _lock:
        rows = _ensure(_read())
        row = next((r for r in rows if r["id"] == profile_id), None)
        if row is None:
            return None, "No such profile."
        if wanted is None:
            row.pop("pin", None)
        else:
            salt = secrets.token_bytes(16)
            row["pin"] = {"salt": salt.hex(), "hash": _hash_pin(wanted, salt), "setAt": _now()}
        _write(rows)
        _attempts.pop(profile_id, None)
        return _public(row), None


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
