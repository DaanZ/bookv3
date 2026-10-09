"""Each book's Spiral Dynamics level: the value system it argues from.

Spiral Dynamics (Graves, Beck and Cowan) orders value systems as levels, each named by a
colour. A grade is a decimal, 3.0 to 8.0: the whole number is the level that carries the
book, the tenths how far it reaches toward the next, so 5.6 is Orange well on the way to
Green and a progression from one book to the next can be seen inside a level. The pill
shows the whole number, the level that carries the book, so 5.6 shows as 5, Orange: it
rounded to the nearest level at first, and that showed a book the grader had called
"Orange on the way to Green" as Green. A book is graded on the one it speaks from and asks its reader to take up, not on
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


def level_of(score: float) -> int:
    """The level a score shows as: its whole number, the level that carries the book; the
    tenths are only how far it reaches toward the next. 5.9 is still Orange. Taken in
    tenths first, since an average can arrive as 5.999999999999999 for 6.0."""
    return int(math.floor(round(score * 10) / 10))


def badge(key: str, grades: dict | None = None) -> dict | None:
    """What the shelf sends for one book: {"score", "level", "name", "meme", "theme", "reason"},
    `score` the decimal grade and `level` the whole level it shows as; or None."""
    grade = (load() if grades is None else grades).get(key)
    score = grade.get("level") if isinstance(grade, dict) else None
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 3 <= score <= 8:
        return None
    level = level_of(score)
    name, theme = LEVELS[level]
    return {"score": round(float(score), 1), "level": level, "name": name, "meme": MEMES[level],
            "theme": theme, "reason": grade.get("reason", "")}


def save(key: str, grade: dict) -> None:
    """Write one grade; the file is replaced whole, so a crash never leaves half of it."""
    grades = load()
    grades[key] = grade
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STORE), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(grades, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STORE)
