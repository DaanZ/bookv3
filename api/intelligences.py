"""Each book's fit with the nine intelligences: which ways of thinking it asks the reader to use.

Gardner's multiple intelligences, his eight plus existential, as `docs/roads-project.md`
and the "Ways in" page of the design canvas name them, with the one-line meanings written
there. A book gets a fit of 0 to 3 for each (0 none, 3 the heart of it) and one
`primary`, the intelligence it most asks of its reader; the shelf filters and sorts by
the fits, and the pill shows the primary.

Graded by `intelligences.py` from the summary and kept here, in data/intelligences.json,
beside the books and never inside them, like the spiral grades. Read-only for the reader.
"""
import json
import os
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(ROOT, "data", "intelligences.json")

# key -> (name, meaning), in the order the canvas lists them.
INTELLIGENCES = {
    "linguistic": ("Linguistic", "thinking in words: reading, writing, saying it well"),
    "logical": ("Logical-mathematical", "thinking in steps and evidence: cause, effect, numbers"),
    "spatial": ("Visual-spatial", "thinking in pictures and places: maps, layouts, how things look"),
    "musical": ("Musical", "thinking in sound and rhythm: tone, tempo, what you hear"),
    "bodily": ("Bodily-kinesthetic", "thinking by doing: the body, movement, the hands"),
    "naturalist": ("Naturalist", "noticing patterns in the living world, and in yourself"),
    "interpersonal": ("Interpersonal", "understanding other people: what they want, how they feel"),
    "intrapersonal": ("Intrapersonal", "understanding yourself: moods, motives, what drives you"),
    "existential": ("Existential", "the big questions: why it matters, what a life is for"),
}


def load() -> dict:
    """{book key: {"fits", "primary", "reason", "model", "gradedAt"}}, empty when none."""
    try:
        with open(STORE, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def badge(key: str, grades: dict | None = None) -> dict | None:
    """What the shelf sends for one book: {"primary", "name", "fits", "reason"}, the fits
    only for the nine known keys and only 0 to 3; or None when it is not graded."""
    grade = (load() if grades is None else grades).get(key)
    if not isinstance(grade, dict) or grade.get("primary") not in INTELLIGENCES:
        return None
    raw = grade.get("fits") if isinstance(grade.get("fits"), dict) else {}
    fits = {k: v for k, v in raw.items()
            if k in INTELLIGENCES and isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 3}
    return {"primary": grade["primary"], "name": INTELLIGENCES[grade["primary"]][0],
            "fits": fits, "reason": grade.get("reason", "")}


def save(key: str, grade: dict) -> None:
    """Write one book's fits; the file is replaced whole, so a crash never leaves half."""
    grades = load()
    grades[key] = grade
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STORE), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(grades, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STORE)
