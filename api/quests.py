"""Three quests per book, for its finish screen: one small, one medium, one large.

Made once per book by `quests.py` (the top-level script, which needs the API key) and
kept in `data/quests/<book key>.json`, beside the books and never inside them, the way
`enrich.py` keeps Hardcover's answers. This module only reads them, so the reader never
waits on a model and runs without a key.

A quest has a title and a one-line `short` for its card, then the plan the card opens
into: the `source` in the book, what it `needs`, its `steps`, a `doneWhen` that can be
checked, and an estimate in minutes. The three are moments rather than sizes, so a goal
says when: `small` is the reader's next break, `medium` tonight, `large` this weekend.
The keys kept their old names because starts, reflections and passed lists use them.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(ROOT, "data", "quests")

SIZES = ("small", "medium", "large")
TEXT_FIELDS = ("title", "short", "source", "doneWhen")


def path_for(key: str) -> str:
    # Only ever called with a key that came out of library.index(), never caller input.
    return os.path.join(STORE_DIR, f"{key}.json")


def _clean(quest) -> dict | None:
    if not isinstance(quest, dict):
        return None
    if not all(isinstance(quest.get(f), str) and quest[f].strip() for f in TEXT_FIELDS):
        return None
    steps = [s.strip() for s in quest.get("steps") or [] if isinstance(s, str) and s.strip()]
    if not steps:
        # A set from before the plan had steps (one paragraph of "action") is no set: the
        # card would have nothing to open into.
        return None
    minutes = quest.get("minutes")
    direction = quest.get("direction")
    return {
        **{f: quest[f].strip() for f in TEXT_FIELDS},
        "needs": [n.strip() for n in quest.get("needs") or [] if isinstance(n, str) and n.strip()],
        "steps": steps,
        "minutes": minutes if isinstance(minutes, int) and minutes > 0 else None,
        # The direction the reader asked for when this quest was made, if any.
        **({"direction": direction.strip()[:DIRECTION_MAX]} if isinstance(direction, str) and direction.strip() else {}),
    }


def load(key: str) -> dict | None:
    """{"small": {...}, "medium": {...}, "large": {...}}, or None if there are none yet.

    A file that is missing, unreadable or incomplete is the same as no quests: the
    finish screen then shows what it showed before, rather than half a set.
    """
    try:
        with open(path_for(key), encoding="utf-8") as file:
            stored = json.load(file)
    except (FileNotFoundError, ValueError, OSError):
        return None
    quests = {size: _clean(stored.get(size)) for size in SIZES}
    if not all(quests.values()):
        return None
    return quests


# Which quests a reader has started, one file per profile like positions.py. This is the
# hand-off: a daily quest list, here or in another app (docs/roads-project.md), reads what
# was started rather than the book's three suggestions.
STARTED_DIR = os.path.join(ROOT, "data", "quests-started")

# Which quests a reader has done, and what they made of it. Finishing a quest is not
# ticking a box: the reader says what happened, what went wrong and why they think the
# book asks for it this way, because doing it and learning from the mistakes is where
# the reading turns into knowing. A separate file from the starts, so a done quest keeps
# its reflection even if its start is undone, and the started file keeps its old shape.
DONE_DIR = os.path.join(ROOT, "data", "quests-done")

# The three questions, in the order they are asked. The keys are the stored field names.
REFLECTION_FIELDS = ("happened", "wentWrong", "why")
REFLECTION_MAX = 2000

# The reader's own steer for a reroll, as in "indoor plants". Short: a direction, not a brief.
DIRECTION_MAX = 120


def _profile_path(folder: str, profile_id: str) -> str:
    # Profile ids come from profiles.json via the reader dependency, never from the URL.
    return os.path.join(folder, f"{profile_id}.json")


def _read(folder: str, profile_id: str) -> dict:
    try:
        with open(_profile_path(folder, profile_id), encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _put(folder: str, profile_id: str, key: str, size: str, value) -> dict:
    """Set (value) or clear (None) one size of one book; returns that book's entries."""
    data = _read(folder, profile_id)
    book = dict(data.get(key) or {})
    if value is not None:
        book[size] = value
    else:
        book.pop(size, None)
    if book:
        data[key] = book
    else:
        data.pop(key, None)
    os.makedirs(folder, exist_ok=True)
    path = _profile_path(folder, profile_id)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)
    os.replace(tmp, path)
    return book


def started(profile_id: str) -> dict:
    """{"<book key>": {"<size>": "<startedAt>"}} for one reader."""
    return _read(STARTED_DIR, profile_id)


def set_started(profile_id: str, key: str, size: str, at: str | None) -> dict:
    """Start (at = a timestamp) or un-start (at = None) one quest; returns that book's starts."""
    return _put(STARTED_DIR, profile_id, key, size, at or None)


def done(profile_id: str) -> dict:
    """{"<book key>": {"<size>": {"doneAt", "happened", "wentWrong", "why"}}} for one reader."""
    return _read(DONE_DIR, profile_id)


def set_done(profile_id: str, key: str, size: str, reflection: dict | None, at: str | None = None) -> dict:
    """Record a quest as done with its reflection, or undo that (reflection = None).

    Editing a reflection keeps the date it was first done: the day you did the thing
    does not move because you later wrote more about it.
    """
    if reflection is None:
        return _put(DONE_DIR, profile_id, key, size, None)
    before = (done(profile_id).get(key) or {}).get(size) or {}
    record = {"doneAt": before.get("doneAt") or at}
    record.update({field: reflection[field] for field in REFLECTION_FIELDS})
    return _put(DONE_DIR, profile_id, key, size, record)


def open_count(profile_id: str) -> dict:
    """{"<book key>": n} — quests this reader started and has not yet reflected on."""
    starts, dones = started(profile_id), done(profile_id)
    counts = {}
    for key, sizes in starts.items():
        n = sum(1 for size in sizes if size not in (dones.get(key) or {}))
        if n:
            counts[key] = n
    return counts


def passed(key: str) -> list[dict]:
    """The quests readers passed on for this book: replaced by a reroll before anyone
    started them. Every later reroll is told to stay away from them, so "none of these"
    is a signal that carries forward instead of a dice throw that can land on them again."""
    try:
        with open(path_for(key), encoding="utf-8") as file:
            stored = json.load(file)
    except (FileNotFoundError, ValueError, OSError):
        return []
    found = stored.get("passed") if isinstance(stored, dict) else None
    return [p for p in found if isinstance(p, dict) and p.get("title")] if isinstance(found, list) else []


def claimed_sizes(key: str) -> set[str]:
    """Sizes of this book that any reader has started or done.

    A reroll keeps these. The set is one per book while starts and reflections are per
    reader, and both point at a size: replacing a quest somebody started would quietly
    hand their start, or their reflection, to a different quest.
    """
    claimed = set()
    for folder in (STARTED_DIR, DONE_DIR):
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            if name.endswith(".json"):
                claimed.update((_read(folder, name[:-5]).get(key) or {}).keys())
    return claimed & set(SIZES)


def merge_reroll(old: dict | None, fresh: dict, claimed: set, by: str, at: str) -> tuple[dict, list]:
    """The new set — claimed sizes from the old one, the rest fresh — and the quests passed on."""
    quests, gone = {}, []
    for size in SIZES:
        if old and size in claimed:
            quests[size] = old[size]
            continue
        quests[size] = fresh[size]
        # The very same quest when its start was undone while the new set was being made:
        # it was kept going in, so nobody passed on it. Identity, not equality — a fresh
        # quest that happens to match an old one was still a quest the reader turned down.
        if old and fresh[size] is not old[size]:
            gone.append({"size": size, "title": old[size]["title"], "short": old[size]["short"],
                         "source": old[size]["source"], "passedAt": at, "by": by})
    return quests, gone


def save(key: str, quests: dict, model: str | None = None, generated_at: str | None = None,
         passed_on: list | None = None) -> str:
    """Write a book's set. `passed_on` replaces the passed list; None keeps the one on disk,
    so making a set again from the command line does not forget what readers turned down."""
    keep_passed = passed(key) if passed_on is None else passed_on
    os.makedirs(STORE_DIR, exist_ok=True)
    path = path_for(key)
    record = {size: quests[size] for size in SIZES}
    record["model"] = model
    record["generatedAt"] = generated_at
    record["passed"] = keep_passed
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(record, file, indent=4)
    os.replace(tmp, path)
    return path
