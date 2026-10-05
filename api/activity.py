"""Which books were read on a given day — the question other apps ask.

Everything here is derived from `positions.py`, which keeps two dates per book per
reader: `lastReadAt` (the last time a page was saved) and `finishedAt` (the first finish).
Those are the only reading history there is, and they set what this can honestly say:

* **`finished` is exact for any day.** `finishedAt` is written once and never moved.
* **`touched` is exact for today and best-effort for the past.** `lastReadAt` is the
  *latest* save, so a book read on Monday and again on Wednesday answers to Wednesday only.
  There is no per-day log to rebuild Monday from, and inventing one would make the
  answer a guess.

A day is a calendar day in a timezone, because "today" for somebody in Amsterdam ends at
a different instant than it does on a server set to UTC.
"""

from datetime import date, datetime, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from api import library, positions


def zone_named(name: str | None) -> tzinfo:
    """The timezone to cut days by. Falls back to this machine's own clock, which is
    what a person reading on it means by "today"."""
    if not name:
        return datetime.now().astimezone().tzinfo
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError) as error:
        raise ValueError(f"Unknown timezone: {name!r}") from error


def _local_day(iso: str | None, zone: tzinfo) -> date | None:
    if not iso:
        return None
    try:
        moment = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(zone).date()


def read_on(day: date, zone: tzinfo, readers: list[dict]) -> list[dict]:
    """The books each of `readers` touched or finished on `day`, newest first.

    One row per reader per book: two people finishing the same book is two rows, since
    "who read it" is half of what a caller wants to know.
    """
    index = library.index()
    rows = []
    for reader in readers:
        owner = bool(reader.get("owner"))
        mine = positions.all_positions(reader["id"])
        for key, position in mine.items():
            position = position or {}
            touched = _local_day(position.get("lastReadAt"), zone) == day
            finished = _local_day(position.get("finishedAt"), zone) == day
            entry = index.get(key)
            if not (touched or finished) or entry is None:
                continue
            data = library._load(entry)
            if data is None:
                continue
            book = library.summarise(key, entry, data, position, owner=owner)
            rows.append(
                {
                    "key": key,
                    "title": book["title"],
                    "subtitle": book["subtitle"],
                    "author": book["author"],
                    "category": book["category"],
                    "profile": {"id": reader["id"], "name": reader.get("name")},
                    "lastReadAt": position.get("lastReadAt"),
                    "finished": finished,
                    "finishedAt": position.get("finishedAt") if finished else None,
                }
            )
    rows.sort(key=lambda row: row["lastReadAt"] or "", reverse=True)
    return rows
