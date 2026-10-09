"""Books like this one, judged by what their summaries say.

The finish screen offers the books nearest the one just finished. Category text alone
could not carry that: 67 books have no category at all, and many that do stand alone
("Homesteading", "Stoicism"), so a word match found nothing for them. What every book does
have is its summary, and the highlighted phrases in it are the pipeline's own choice of
what matters. So each book becomes a TF-IDF vector over the words of its summary, with
the highlights, title and category counting extra, and nearness is the cosine between two.

Built once over the whole library and rebuilt when a file is added, moved or rewritten
(the signature is every key with its file's mtime). Pure Python: 279 books take about a
second to read, and nothing here is worth a dependency.
"""
import math
import os
import re
import threading
from collections import Counter

from api import library
from util.parts import all_sentences

WORD = re.compile(r"[a-z][a-z'-]{3,}")
HIGHLIGHT = re.compile(r"\*\*(.+?)\*\*")
# Words that say how a summary is written rather than what it is about.
STOP = set("""
also about after again against because been before being between both could does doing
down during each even every from further have having here into just like made make makes
many more most much must only other over same should some such than that their them then
there these they this those through under until very were what when where which while
whom with within without would your yours author book books chapter chapters part parts
reader readers explains explores discusses describes suggests argues shows says states
emphasizes highlights notes points important example examples often well good great
people person thing things ways another first second third still around across among
""".split())
# Doubled for what the pipeline marked, tripled for what the book is called and filed as.
HIGHLIGHT_WEIGHT = 2
LABEL_WEIGHT = 3
# A word in more than this share of books says nothing about any one of them.
MAX_DOC_SHARE = 0.4

_lock = threading.Lock()
_cache: dict = {"signature": None, "vectors": {}}


def _words(text: str) -> list[str]:
    return [w.strip("'-") for w in WORD.findall(text.lower()) if w.strip("'-") not in STOP]


def terms(data: dict) -> Counter:
    """The weighted word counts one book is compared on."""
    counts: Counter = Counter()
    meta = data.get("meta") or {}
    for part in data.get("parts") or []:
        for sentence in all_sentences(part):
            counts.update(_words(sentence.replace("**", "")))
            for phrase in HIGHLIGHT.findall(sentence):
                for word in _words(phrase):
                    counts[word] += HIGHLIGHT_WEIGHT
    for label in (meta.get("title"), meta.get("category")):
        for word in _words(label or ""):
            counts[word] += LABEL_WEIGHT
    return counts


def vectors(books: dict[str, Counter]) -> dict[str, dict[str, float]]:
    """key -> unit-length TF-IDF vector, sublinear in term frequency."""
    total = len(books)
    df: Counter = Counter()
    for counts in books.values():
        df.update(counts.keys())
    idf = {w: math.log(total / n) for w, n in df.items() if n / total <= MAX_DOC_SHARE and n > 1}
    out = {}
    for key, counts in books.items():
        vec = {w: (1 + math.log(c)) * idf[w] for w, c in counts.items() if w in idf}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        out[key] = {w: v / norm for w, v in vec.items()}
    return out


def _signature(entries: dict) -> tuple:
    stamps = []
    for key, entry in entries.items():
        try:
            stamps.append((key, os.path.getmtime(entry["path"])))
        except OSError:
            continue
    return tuple(sorted(stamps))


def _library_vectors() -> dict[str, dict[str, float]]:
    entries = library.index()
    signature = _signature(entries)
    with _lock:
        if _cache["signature"] != signature:
            books = {}
            for key, entry in entries.items():
                data = library._load(entry)
                if data is not None:
                    books[key] = terms(data)
            _cache["vectors"] = vectors(books)
            _cache["signature"] = signature
        return _cache["vectors"]


def nearest(key: str, limit: int = 20, vecs: dict | None = None) -> list[tuple[str, float]]:
    """The books whose summaries are closest to this one's, nearest first, with the score."""
    vecs = _library_vectors() if vecs is None else vecs
    mine = vecs.get(key)
    if not mine:
        return []
    scored = []
    for other, vec in vecs.items():
        if other == key:
            continue
        small, large = (mine, vec) if len(mine) < len(vec) else (vec, mine)
        score = sum(v * large.get(w, 0.0) for w, v in small.items())
        if score > 0:
            scored.append((other, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]
