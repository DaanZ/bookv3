"""Reading the books/ tree as a shelf.

The pipeline's storage format is unchanged: one JSON per book, `{"meta": {...},
"parts": [{"title", "body"}]}`, in books/available (unread) or books/read (finished).
This module only reads it, plus the position store, and shapes it for the reader UI.
"""

import os
import re
import shutil
from datetime import datetime, timezone

from api import enrich
from api.patches import patch_for, family_of
from api.positions import all_positions, finish_ordinal
from util.files import json_read_file

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AVAILABLE_DIR = os.path.join(ROOT, "books", "available")
FINISHED_DIR = os.path.join(ROOT, "books", "read")

_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _plain(html: str) -> str:
    return _WS.sub(" ", _TAGS.sub("", html or "")).strip()


def _split_title(title: str) -> tuple[str, str | None]:
    """`Balinese Textiles: A Journey Through...` -> title + subtitle, as the design shows."""
    if ": " in title:
        head, tail = title.split(": ", 1)
        # Only treat it as a subtitle if the head can stand on its own.
        if len(head) >= 4 and len(tail) >= 4:
            return head.strip(), tail.strip()
    return title.strip(), None


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - then).days)


def _scan_dir(folder: str, finished: bool) -> dict[str, dict]:
    out: dict[str, dict] = {}
    try:
        names = sorted(os.listdir(folder))
    except FileNotFoundError:
        return out
    for name in names:
        if not name.endswith(".json"):
            continue
        out[name[:-5]] = {"path": os.path.join(folder, name), "finished": finished}
    return out


def index() -> dict[str, dict]:
    """key -> {path, finished}. The key is the filename stem, so lookups never
    path-join caller input and traversal is impossible by construction."""
    found = _scan_dir(AVAILABLE_DIR, False)
    found.update(_scan_dir(FINISHED_DIR, True))
    return found


def _load(entry: dict) -> dict | None:
    data = json_read_file(entry["path"])
    if not isinstance(data, dict) or "parts" not in data:
        return None
    return data


# Name fragments that stay lowercase inside a name. Dutch and German surnames arrive
# with them often enough to be worth the twelve lines.
PARTICLES = {"van", "der", "den", "de", "di", "da", "du", "del", "della", "von", "zu",
             "la", "le", "el", "bin", "ibn", "af", "av"}

ROMAN = re.compile(r"^[IVXLCDM]+$")


def tidy_name(name: str | None) -> str | None:
    """Fix an author read off a title page in capitals.

    `meta.py` takes the author from the first pages, so a book whose title page shouts
    gives "MIHALY CSIKSZENTMIHALYI". Only strings with no lowercase at all are touched:
    a name that already has case is somebody's own spelling — "bell hooks", "danah
    boyd", "Peter C. Brown" — and re-casing it would be the same mistake in reverse.
    """
    if not name or any(character.islower() for character in name):
        return name

    def word(token: str, first: bool) -> str:
        if not token or not token[0].isalpha():
            return token
        # II, III, IV after a name are not words to title-case.
        if ROMAN.match(token) and len(token) > 1:
            return token
        if not first and token.lower() in PARTICLES:
            return token.lower()
        return token[0].upper() + token[1:].lower()

    # Split on the separators inside names, keeping them: hyphens, apostrophes and the
    # periods in initials all start a new capital.
    pieces = re.split(r"([\s\-'’.]+)", name)
    out = []
    seen_word = False
    for piece in pieces:
        if re.fullmatch(r"[\s\-'’.]+", piece):
            out.append(piece)
            continue
        out.append(word(piece, not seen_word))
        if piece.strip():
            seen_word = True
    return "".join(out)


def summarise(key: str, entry: dict, data: dict, position: dict | None,
              with_part_titles: bool = False, everyone: dict | None = None,
              looked_up: dict | None = None, owner: bool = True) -> dict:
    """`position` and `everyone` are one profile's reading, so every field derived from
    them — state, progress, sittings, the finish number — is that reader's and nobody
    else's. `owner` says whether they are the profile the shelf itself belongs to.

    `looked_up` is the whole lookup ledger, read once by the caller — the shelf would
    otherwise re-read it for every book."""
    meta = data.get("meta", {}) or {}
    parts = data.get("parts", []) or []
    raw_title = meta.get("title") or key.replace("_", " ")
    title, subtitle = _split_title(raw_title)
    category = meta.get("category")

    at = int((position or {}).get("part", 0) or 0)
    page = int((position or {}).get("page", 0) or 0)
    at = max(0, min(at, max(0, len(parts) - 1)))

    # Whose shelf this is decides what "read" means. A profile that recorded a finish
    # has read the book; for the owner, so does a book sitting in books/read, because
    # that folder *is* their history — it predates profiles and was filled by their
    # finishes. A guest inherits none of it: the house has read Sapiens, they have not.
    if (position or {}).get("finishedAt") or (owner and entry["finished"]):
        state = "read"
    elif at > 0 or page > 0:
        state = "reading"
    else:
        state = "new"

    summary = {
        "key": key,
        "title": title,
        "subtitle": subtitle,
        "fullTitle": raw_title,
        "author": tidy_name(meta.get("author")) or "Unknown author",
        "category": category or "uncategorised",
        "family": family_of(category),
        "pages": meta.get("pages") or 0,
        "isbn": meta.get("isbn"),
        "partCount": len(parts),
        "patch": patch_for(category),
        "state": state,
        # Where the file actually sits, which is the house's filing rather than this
        # reader's progress. The library screen moves books by it; the shelf does not
        # use it at all.
        "filed": "read" if entry["finished"] else "available",
        "at": len(parts) - 1 if state == "read" else at,
        "page": 0 if state == "read" else page,
    }

    # Cover, rating and the link out, when this book has been looked up. Absent is a
    # normal state — it means nobody has asked Hardcover about it yet, not that it failed.
    card = enrich.get(key)
    if card:
        summary["hardcover"] = card
        summary["cover"] = card.get("cover")
        summary["coverColor"] = card.get("coverColor")
    elif (looked_up if looked_up is not None else enrich.lookups()).get(key, {}).get(
        "status"
    ) == "missing":
        # Asked, and Hardcover does not have it. An explicit null rather than an absent
        # key, because those are different rows: one has been answered for and can be
        # contributed, the other is still waiting its turn in the background pass.
        summary["hardcover"] = None

    # Only the finish screen lists them, and the shelf carries 250+ books.
    if with_part_titles:
        summary["partTitles"] = [p.get("title", "") for p in parts]

    if position:
        summary["lastReadAt"] = position.get("lastReadAt")
        summary["pausedDays"] = _days_since(position.get("lastReadAt"))
        summary["sittings"] = position.get("sittings")
        summary["days"] = _days_since(position.get("startedAt"))
        # None means "never recorded", which is not the same as "the call failed".
        summary["markedRead"] = position.get("markedRead")
        summary["finishedAt"] = position.get("finishedAt")
        # The bed this reader chose for this book, so the reader screen restores it
        # without a second request — it is stored beside the bookmark and travels with it.
        if position.get("ambience"):
            summary["ambience"] = position["ambience"]
        # Which number this book was to be finished. Needs every book's finish date, not
        # just this one's, so it is only filled in when the caller had them all.
        if position.get("finishedAt") and everyone is not None:
            summary["finishNumber"] = finish_ordinal(key, everyone)
    return summary


def shelf(profile: dict) -> list[dict]:
    """Every book as one reader sees it, newest activity first, then unread, then
    finished."""
    positions = all_positions(profile["id"])
    owner = bool(profile.get("owner"))
    looked_up = enrich.lookups()
    out = []
    for key, entry in index().items():
        data = _load(entry)
        if data is None:
            continue
        out.append(
            summarise(key, entry, data, positions.get(key), everyone=positions,
                      looked_up=looked_up, owner=owner)
        )

    rank = {"reading": 0, "new": 1, "read": 2}
    out.sort(key=lambda b: (rank.get(b["state"], 3), b["title"].lower()))
    return out


def book(key: str, profile: dict) -> dict | None:
    """One book with its parts, plus the recap line the resume strip needs."""
    entry = index().get(key)
    if entry is None:
        return None
    data = _load(entry)
    if data is None:
        return None

    everyone = all_positions(profile["id"])
    detail = summarise(key, entry, data, everyone.get(key), with_part_titles=True,
                       everyone=everyone, owner=bool(profile.get("owner")))
    detail["parts"] = [
        {"title": p.get("title", ""), "body": p.get("body", "")}
        for p in data.get("parts", [])
    ]

    # "Last part: ..." — derived from the previous part rather than authored, so it
    # stays true for every book in the shelf, not just the three in the design.
    at = detail["at"]
    if at > 0 and at - 1 < len(detail["parts"]):
        detail["resumeRecap"] = recap_of(detail["parts"][at - 1])
    else:
        detail["resumeRecap"] = None
    return detail


def recap_of(part: dict, limit: int = 190) -> str:
    text = _plain(part.get("body", ""))
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    recap = ""
    for sentence in sentences:
        if recap and len(recap) + len(sentence) + 1 > limit:
            break
        recap = f"{recap} {sentence}".strip()
    return f"Last part: {recap}"


def move_book(key: str, finished: bool) -> str | None:
    """Move a book between books/available and books/read by hand.

    The reader moves a book when you finish it; this is for correcting the shelf —
    putting back something marked read by mistake, or filing one read elsewhere.
    """
    entry = index().get(key)
    if entry is None or entry["finished"] == finished:
        return None
    target_dir = FINISHED_DIR if finished else AVAILABLE_DIR
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, os.path.basename(entry["path"]))
    shutil.move(entry["path"], target)
    return target


def delete_book(key: str) -> bool:
    """Remove a summary from the library. The source PDF in pdfs/ is left alone."""
    entry = index().get(key)
    if entry is None:
        return False
    os.remove(entry["path"])
    return True


def move_to_read(key: str) -> str | None:
    """books/available -> books/read. Returns the new path, or None if not applicable."""
    entry = index().get(key)
    if entry is None or entry["finished"]:
        return None
    os.makedirs(FINISHED_DIR, exist_ok=True)
    target = os.path.join(FINISHED_DIR, os.path.basename(entry["path"]))
    shutil.move(entry["path"], target)
    return target
