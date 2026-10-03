"""Three quests per book, for its finish screen: one small, one medium, one large.

Made once per book by `quests.py` (the top-level script, which needs the API key) and
kept in `data/quests/<book key>.json`, beside the books and never inside them, the way
`enrich.py` keeps Hardcover's answers. This module only reads them, so the reader never
waits on a model and runs without a key.

A quest has a title, an action, a "done when" that can be checked, and an estimate in
minutes. The sizes are fixed so the finish screen can always offer a way in that fits
the day: a few minutes now, an evening this week, or a weekend project.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(ROOT, "data", "quests")

SIZES = ("small", "medium", "large")
FIELDS = ("title", "action", "doneWhen", "minutes")


def path_for(key: str) -> str:
    # Only ever called with a key that came out of library.index(), never caller input.
    return os.path.join(STORE_DIR, f"{key}.json")


def _clean(quest) -> dict | None:
    if not isinstance(quest, dict):
        return None
    if not all(isinstance(quest.get(f), str) and quest[f].strip() for f in ("title", "action", "doneWhen")):
        return None
    minutes = quest.get("minutes")
    return {
        "title": quest["title"].strip(),
        "action": quest["action"].strip(),
        "doneWhen": quest["doneWhen"].strip(),
        "minutes": minutes if isinstance(minutes, int) and minutes > 0 else None,
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


def save(key: str, quests: dict, model: str | None = None, generated_at: str | None = None) -> str:
    os.makedirs(STORE_DIR, exist_ok=True)
    path = path_for(key)
    record = {size: quests[size] for size in SIZES}
    record["model"] = model
    record["generatedAt"] = generated_at
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(record, file, indent=4)
    os.replace(tmp, path)
    return path
