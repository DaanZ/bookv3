"""Asking somebody else what a book's ISBN is.

The book itself is the best source and `util/isbn.py` reads it. This is for when it
cannot: a summary whose source file is long gone, or an edition whose copyright page
never made it through text extraction.

Open Library rather than Hardcover, deliberately. Hardcover is already consulted, and it
has an obvious blind spot for this job — a book it has never heard of is exactly the book
worth adding to it, and asking it about one returns nothing by definition. Open Library
is a different catalogue, needs no key, and has no rate limit worth working around at
this scale.

The answer is treated as a claim, not a fact: an author word must line up before an ISBN
is accepted, because a title search for "Humankind" will cheerfully return a book by
somebody else entirely.
"""

import re

import requests

try:  # The same OS-trust-store fix the rest of the project needs on this machine.
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover
    pass

SEARCH_URL = "https://openlibrary.org/search.json"
TIMEOUT = 20

# Enough rows to get past a same-titled book by another author, few enough to stay quick.
ROWS = 5


def _words(text):
    return {w for w in re.split(r"[^\w]+", (text or "").lower()) if len(w) > 2}


def _author_agrees(wanted, names):
    """One shared word is enough — "Peter C. Brown" against "Peter Brown" — but some
    overlap is required. A title alone is not an identification."""
    mine = _words(wanted)
    if not mine:
        # Nothing to check against. The pipeline often reads the author as "Not
        # specified", and accepting anything there is how the wrong book gets filed.
        return False
    return any(mine & _words(name) for name in names or [])


def isbn_from_openlibrary(title, author):
    """A 13-digit ISBN for this book, or None.

    Returns the first valid one from the best-matching edition. Which edition is not
    something this can know — any ISBN of the work is enough to identify it to Hardcover,
    which is what this is for.
    """
    from util.isbn import normalise, to_isbn13, valid

    short = (title or "").split(":")[0].strip()
    if not short:
        return None

    try:
        response = requests.get(
            SEARCH_URL,
            params={
                "title": short,
                "author": (author or "").split(",")[0].strip() or None,
                "fields": "title,author_name,isbn",
                "limit": ROWS,
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        docs = response.json().get("docs") or []
    except (requests.RequestException, ValueError):
        return None

    for doc in docs:
        if not _author_agrees(author, doc.get("author_name")):
            continue
        for candidate in doc.get("isbn") or []:
            digits = normalise(candidate)
            if valid(digits):
                return to_isbn13(digits) or digits
    return None
