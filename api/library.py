"""Reading the books/ tree as a shelf.

The pipeline's storage format is unchanged: one JSON per book, `{"meta": {...},
"parts": [{"title", "body"}]}`, in books/available (unread) or books/read (finished).
This module only reads it, plus the position store, and shapes it for the reader UI.
"""

import os
import re
import shutil
from datetime import datetime, timezone

from api.patches import patch_for, family_of
from api.positions import get_position, all_positions
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


def summarise(key: str, entry: dict, data: dict, position: dict | None,
              with_part_titles: bool = False) -> dict:
    meta = data.get("meta", {}) or {}
    parts = data.get("parts", []) or []
    raw_title = meta.get("title") or key.replace("_", " ")
    title, subtitle = _split_title(raw_title)
    category = meta.get("category")

    at = int((position or {}).get("part", 0) or 0)
    page = int((position or {}).get("page", 0) or 0)
    at = max(0, min(at, max(0, len(parts) - 1)))

    if entry["finished"]:
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
        "author": meta.get("author") or "Unknown author",
        "category": category or "uncategorised",
        "family": family_of(category),
        "pages": meta.get("pages") or 0,
        "partCount": len(parts),
        "patch": patch_for(category),
        "state": state,
        "at": len(parts) - 1 if state == "read" else at,
        "page": 0 if state == "read" else page,
    }

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
    return summary


def shelf() -> list[dict]:
    """Every book, newest activity first, then unread, then finished."""
    positions = all_positions()
    out = []
    for key, entry in index().items():
        data = _load(entry)
        if data is None:
            continue
        out.append(summarise(key, entry, data, positions.get(key)))

    rank = {"reading": 0, "new": 1, "read": 2}
    out.sort(key=lambda b: (rank.get(b["state"], 3), b["title"].lower()))
    return out


def book(key: str) -> dict | None:
    """One book with its parts, plus the recap line the resume strip needs."""
    entry = index().get(key)
    if entry is None:
        return None
    data = _load(entry)
    if data is None:
        return None

    detail = summarise(key, entry, data, get_position(key), with_part_titles=True)
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


def move_to_read(key: str) -> str | None:
    """books/available -> books/read. Returns the new path, or None if not applicable."""
    entry = index().get(key)
    if entry is None or entry["finished"]:
        return None
    os.makedirs(FINISHED_DIR, exist_ok=True)
    target = os.path.join(FINISHED_DIR, os.path.basename(entry["path"]))
    shutil.move(entry["path"], target)
    return target
