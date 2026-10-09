"""Each book's Spiral Dynamics level: the value system it argues from.

Spiral Dynamics (Graves, Beck and Cowan) orders value systems as levels, each named by a
colour. A grade is a decimal, 3.0 to 8.0: the whole number is the level that carries the
book, the tenths how far it reaches toward the next, so 5.6 is Orange well on the way to
Green and a progression from one book to the next can be seen inside a level.

The pill names a band, not a number (`band_of`). Around each level sits its core, from
.8 below to .2 above (4.8 to 5.2 is Orange, StriveDrive), and between two cores a
transition named by both (5.3 to 5.7 is "StriveDrive → HumanBond"). Daan chose this
after a whole-number pill put 200 of 280 books under one name; rounding to the nearest
level before that showed books the grader called "Orange on the way to Green" as Green.

A book is graded on the one it speaks from and asks its reader to take up, not on
its subject: a business book can be Orange (win, optimise) or Green (people before
profit), and a book about history can be written from any of them. Levels 1 and 2 (Beige
survival, Purple tribe) are left out: nothing on a reading shelf argues from them.

Grades are made by `spiral.py` from the summary and kept here, in data/spiral.json, beside
the books and never inside them, like the Hardcover cache. Read-only for the reader.
"""
import json
import math
import os
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(ROOT, "data", "spiral.json")

# level -> (colour, theme). The colour is the level's name in Spiral Dynamics.
LEVELS = {
    3: ("Red", "power"),
    4: ("Blue", "order"),
    5: ("Orange", "achievement"),
    6: ("Green", "community"),
    7: ("Yellow", "integration"),
    8: ("Turquoise", "wholeness"),
}

# Each level's canonical name, Beck and Cowan's (Spiral Dynamics, 1996), spelled as they
# spell it. The pill shows this beside a dot in the level's colour, so neither the number
# nor the colour word needs to be written out.
MEMES = {3: "PowerGods", 4: "TruthForce", 5: "StriveDrive", 6: "HumanBond",
         7: "FlexFlow", 8: "GlobalView"}


def load() -> dict:
    """{book key: {"level", "reason", "model", "gradedAt"}}, empty when nothing is graded."""
    try:
        with open(STORE, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def band_of(score: float) -> tuple[int, int]:
    """The band a score shows as, (low, high): the same level twice for a core band, two
    neighbours for a transition. Cores run .8 below a level to .2 above it, transitions
    .3 to .7 between two levels: 5.2 is (5, 5), 5.3 (5, 6), 5.8 (6, 6). Taken in whole
    tenths, since an average can arrive as 5.199999999999999 for 5.2."""
    tenths = round(score * 10)
    whole, tenth = divmod(tenths, 10)
    if tenth <= 2:
        return whole, whole
    if tenth >= 8:
        return whole + 1, whole + 1
    return whole, whole + 1


def label_of(band: tuple[int, int]) -> str:
    """The pill's text: the level's own name, or both for a transition."""
    low, high = band
    return MEMES[low] if low == high else f"{MEMES[low]} → {MEMES[high]}"


def _score(grade) -> float | None:
    """A stored grade's score, or None for anything that is not one."""
    score = grade.get("level") if isinstance(grade, dict) else None
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 3 <= score <= 8:
        return None
    return round(float(score), 1)


def badge(key: str, grades: dict | None = None) -> dict | None:
    """What the shelf sends for one book, or None: `score` the decimal grade, `band` the
    two levels it shows between (the same twice for a core), `label` the pill's text,
    `dot` the level whose colour the dot wears (the higher of a transition), and `name`
    and `theme` of the band's levels for the hover."""
    grades = load() if grades is None else grades
    grade = grades.get(key)
    score = _score(grade)
    if score is None:
        return None
    low, high = band_of(score)
    names = [LEVELS[low][0]] if low == high else [LEVELS[low][0], LEVELS[high][0]]
    themes = [LEVELS[low][1]] if low == high else [LEVELS[low][1], LEVELS[high][1]]
    return {"score": score, "band": [low, high], "label": label_of((low, high)),
            "dot": high, "name": " to ".join(names), "theme": " to ".join(themes),
            "reason": grade.get("reason", "")}


def save(key: str, grade: dict) -> None:
    """Write one grade; the file is replaced whole, so a crash never leaves half of it."""
    grades = load()
    grades[key] = grade
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STORE), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(grades, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STORE)
