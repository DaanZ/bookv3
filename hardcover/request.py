import os
import re

import requests
from dotenv import load_dotenv

try:  # Trust the OS certificate store — see the note in util/chatgpt.py. Without this,
    # running this module on its own fails with CERTIFICATE_VERIFY_FAILED on a machine
    # whose antivirus intercepts TLS. Inside the API process something else has usually
    # injected already, which is exactly why the gap is easy to miss here.
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover
    pass

load_dotenv()

api_url = "https://api.hardcover.app/v1/graphql"

TIMEOUT = 20

# Hardcover's own search index, not a `books(where:)` filter.
#
# Two earlier versions of this never worked. The first interpolated the title into the
# document as `{title: {<title>}}`, which is not a comparison expression at all. The
# second used `_ilike` with variables, which is valid Hasura and still refused: the API
# answers 403 `ilike and related operations are not permitted on this schema`. Pattern
# matching on the books table is simply not available to an API token.
#
# `search` is, and it is typesense-backed, so it tolerates the pipeline's approximate
# titles. It returns an untyped JSON blob rather than selectable fields.
SEARCH_QUERY = """
query findBook($query: String!, $perPage: Int!, $sort: String) {
  search(query: $query, query_type: "Book", per_page: $perPage, sort: $sort) {
    results
  }
}
"""

# The site's search puts the real book first; the API's default does not, and the
# difference is this parameter. Left to itself the index sorts on text relevance, where
# "Summary of Atomic Habits by James Clear" beats "Atomic habits: An Easy & Proven
# Way..." because it matches the query more literally. Sorting on how many people have
# the book puts the real one on top, which is what hardcover.app itself shows.
SEARCH_SORT = "users_count:desc"

MARK_READ_MUTATION = """
mutation addBook($bookId: Int!) {
  insert_user_book(object: {book_id: $bookId, status_id: 3}) {
    id
  }
}
"""

# What the signed-in account already says about this book. `me` needs no user id — the
# token carries it.
STATUS_QUERY = """
query bookStatus($bookId: Int!) {
  me {
    user_books(where: {book_id: {_eq: $bookId}}) {
      id
      status_id
    }
  }
}
"""

# Hardcover's own id for "read".
STATUS_READ = 3

# Contributing a book Hardcover does not have. This writes to a catalogue everyone using
# Hardcover reads, so it is never called as part of ingest — only from an explicit
# action, with the exact payload shown first. See `propose_edition`.
INSERT_BOOK_MUTATION = """
mutation addEdition($edition: EditionInput!) {
  insert_book(edition: $edition) {
    id
    book_id
  }
}
"""


def _headers():
    token = os.environ.get("HARDCOVER_API_KEY")
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}


def _post(query, variables, headers):
    """Returns (data, error). A GraphQL error arrives inside a 200, so status alone
    is not enough to call this a success."""
    try:
        response = requests.post(
            api_url, json={"query": query, "variables": variables}, headers=headers, timeout=TIMEOUT
        )
    except requests.RequestException as ex:
        return None, f"Could not reach Hardcover: {ex}"

    if response.status_code != 200:
        return None, f"Hardcover returned {response.status_code}: {response.text[:200]}"

    try:
        payload = response.json()
    except ValueError:
        return None, "Hardcover returned a response that was not JSON."

    if payload.get("errors"):
        message = "; ".join(e.get("message", "unknown error") for e in payload["errors"])
        return None, f"Hardcover rejected the query: {message}"

    return payload.get("data") or {}, None


def _shorten(title, author):
    """The pipeline's titles carry subtitles and joint authors; Hardcover's do not."""
    if ":" in title:
        title = title.split(":")[0]
    for separator in (" and ", " & ", ", "):
        if separator in author:
            author = author.split(separator)[0]
    return title.strip(), author.strip()


def _author_matches(author, names):
    """True when any search hit's author shares a word with the one we were given.

    Compared word by word rather than whole-string: the pipeline reads "Peter C. Brown"
    off a title page where Hardcover has "Peter C. Brown, Henry L. Roediger III, Mark A.
    McDaniel", and initials and punctuation differ freely between the two.
    """
    wanted = {word for word in re.split(r"[^\w]+", author.lower()) if len(word) > 2}
    if not wanted:
        return False
    have = {word for name in names for word in re.split(r"[^\w]+", name.lower()) if len(word) > 2}
    return bool(wanted & have)


STOPWORDS = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "how", "your", "you"}


def _words(text):
    return {w for w in re.split(r"[^\w]+", text.lower()) if len(w) > 2 and w not in STOPWORDS}


def _title_agrees(wanted, found):
    """Every word of the asked-for title must appear in the found one.

    Strict, because this is only consulted when the author did not match, and that is
    the path that goes wrong quietly: "100 Days of Growth" shares two words out of three
    with "100 Days of Sunlight", which is not the same book by any margin worth taking.
    """
    asked = _words(wanted)
    if not asked:
        return False
    return asked <= _words(found)


def normalise_isbn(value):
    """Strip an ISBN to digits (and a trailing X), or None if it is not one."""
    if not value:
        return None
    cleaned = re.sub(r"[^0-9Xx]", "", str(value)).upper()
    return cleaned if len(cleaned) in (10, 13) else None


def _isbn_matches(isbn, document):
    """The strongest signal there is: the same edition, not a similar title."""
    wanted = normalise_isbn(isbn)
    if not wanted:
        return False
    return any(normalise_isbn(candidate) == wanted for candidate in document.get("isbns") or [])


def _score(hit, author):
    """Rank a search hit: readers first, with books by a demonstrably different author
    pushed below everything else.

    Read count leads because it is the strongest signal available. A search for a
    well-known book returns "Summary of the Key Ideas" cash-ins among its top relevance
    hits, and those have no readers.

    Author is a veto, not a bonus. Making it a bonus picked "The Atomic Habits Workbook"
    (9 readers, James Clear credited) over Atomic Habits itself, whose search document
    lists no authors at all — a blank author field is missing information, and must not
    be read as disagreement.
    """
    document = hit.get("document") or {}
    names = document.get("author_names") or []
    wrong_author = bool(names) and not _author_matches(author, names)
    return (
        0 if wrong_author else 1,
        # users_count, not users_read_count: this is the number hardcover.app prints as
        # "Readers" (6,070 for Atomic Habits, where the read count is 3,570), so ranking
        # on it agrees with what the site shows rather than quietly disagreeing.
        int(document.get("users_count") or 0),
    )


def _describe(document, matched_author, matched_isbn):
    """The fields worth keeping off a search hit.

    The cover is kept as Hardcover's own URL rather than downloaded: it is their asset
    on their CDN, it changes when an edition is re-covered, and copying it into this repo
    would be rehosting someone else's image for no benefit.
    """
    image = document.get("image") or {}
    return {
        "id": document["id"],
        "slug": document.get("slug"),
        "url": f"https://hardcover.app/books/{document['slug']}" if document.get("slug") else None,
        "title": document.get("title"),
        "subtitle": document.get("subtitle"),
        "authors": document.get("author_names") or [],
        "cover": image.get("url"),
        # The cover's dominant colour, which the shelf can use as a ground while the
        # image loads instead of flashing an empty box.
        "coverColor": image.get("color"),
        "isbns": document.get("isbns") or [],
        "rating": round(document["rating"], 2) if document.get("rating") else None,
        "ratingsCount": document.get("ratings_count"),
        "readers": document.get("users_count"),
        "genres": document.get("genres") or [],
        "moods": document.get("moods") or [],
        "hasAudiobook": document.get("has_audiobook"),
        "hasEbook": document.get("has_ebook"),
        "authorMatched": matched_author,
        "isbnMatched": matched_isbn,
    }


def search_book(title, author, isbn=None):
    """Find the Hardcover book that best matches this title and author.

    An `isbn` short-circuits the guesswork: a hit carrying the same ISBN is the same
    edition, so it wins outright regardless of how its title reads.
    """
    headers = _headers()
    if headers is None:
        return None, "HARDCOVER_API_KEY is not set."

    title, author = _shorten(title, author)

    data, error = _post(
        SEARCH_QUERY,
        {"query": f"{title} {author}".strip(), "perPage": 25, "sort": SEARCH_SORT},
        headers,
    )
    if error:
        return None, error

    hits = ((data.get("search") or {}).get("results") or {}).get("hits") or []
    if not hits:
        return None, f"Hardcover has no book matching “{title}”."

    # An ISBN hit is the same physical edition, so it skips the title/author reasoning
    # entirely — that reasoning exists only because we usually have nothing this solid.
    exact = next((h for h in hits if _isbn_matches(isbn, h.get("document") or {})), None)
    if exact is not None:
        return _describe(exact["document"], True, True), None

    best = max(hits, key=lambda hit: _score(hit, author))
    document = best.get("document") or {}
    if document.get("id") is None:
        return None, f"Hardcover returned no usable match for “{title}”."

    # The index always answers. Asked for a title that does not exist it returns its
    # nearest neighbour, which is a stranger — and the caller's next move is to mark
    # that stranger as read on someone's account. So a hit has to agree with what was
    # asked for on *something*: the author, or at least half the words of the title.
    matched_author = _author_matches(author, document.get("author_names") or [])
    if not matched_author and not _title_agrees(title, document.get("title") or ""):
        return None, f"Hardcover has no book matching “{title}”."

    # `authorMatched` false means the match was made on title alone — the pipeline often
    # reads the author as "Not specified" — so a caller can tell a confident match from a
    # hopeful one before putting it on a public shelf.
    return _describe(document, matched_author, False), None


def read_status(book_id):
    """The signed-in account's status for a book: `status_id`, or None if it is not on
    their shelf at all. Returns (status_id, error)."""
    headers = _headers()
    if headers is None:
        return None, "HARDCOVER_API_KEY is not set."

    data, error = _post(STATUS_QUERY, {"bookId": int(book_id)}, headers)
    if error:
        return None, error

    rows = (data.get("me") or [{}])[0].get("user_books") or []
    if not rows:
        return None, None
    return rows[0].get("status_id"), None


def mark_book_as_read(title, author, isbn=None):
    """Search for a book by title and author, then mark it read (status_id 3).

    Returns the API response on success, or `{"error": ...}` — callers must not
    report success without checking for that key.

    Asks Hardcover what it already thinks before writing. That makes this safe to call
    again: a book already marked read reports success without inserting a second
    user_book, so retrying a finish that failed for an unrelated reason cannot duplicate
    a shelf entry — and a book marked read outside this app is recognised rather than
    re-added.
    """
    book, error = search_book(title, author, isbn=isbn)
    if error:
        return {"error": error}

    found = {
        "id": book["id"],
        "title": book.get("title"),
        "authorMatched": book["authorMatched"],
        "isbnMatched": book.get("isbnMatched", False),
    }

    status, error = read_status(book["id"])
    if error:
        return {"error": error}
    if status == STATUS_READ:
        return {"data": None, "book": found, "alreadyRead": True}

    data, error = _post(MARK_READ_MUTATION, {"bookId": int(book["id"])}, _headers())
    if error:
        return {"error": error}

    return {"data": data, "book": found, "alreadyRead": False}


def edition_payload(title, author, isbn, pages=None, subtitle=None):
    """Exactly what would be sent to Hardcover, so it can be shown before it is sent.

    Separate from `contribute_edition` on purpose: a write to a shared catalogue should
    be reviewable, and a function that builds the payload without sending it is what
    makes that possible.
    """
    isbn13 = normalise_isbn(isbn)
    if not isbn13 or len(isbn13) != 13:
        return None, "A 13-digit ISBN is needed to add a book to Hardcover."

    dto = {"isbn_13": isbn13, "title": title}
    if subtitle:
        dto["subtitle"] = subtitle
    if pages:
        dto["page_count"] = int(pages)
    return {"dto": dto, "author": author}, None


def contribute_edition(payload):
    """Add an edition to Hardcover's public catalogue.

    Only ever called from an explicit user action. The pipeline reads title and author
    off the first pages with a language model, and pushing that into a database other
    people rely on without someone looking at it first would be publishing guesses.
    """
    headers = _headers()
    if headers is None:
        return {"error": "HARDCOVER_API_KEY is not set."}

    data, error = _post(INSERT_BOOK_MUTATION, {"edition": {"dto": payload["dto"]}}, headers)
    if error:
        return {"error": error}
    return {"data": data}


if __name__ == "__main__":
    # Search only. This used to call mark_book_as_read, so running the file to "see if
    # the API works" silently added a book to the account of whoever ran it. Checking
    # the connection should not write to someone's shelf; pass --mark to do that.
    import sys

    book_title = "Atomic Habits"
    book_author = "James Clear"

    if "--mark" in sys.argv:
        print(mark_book_as_read(book_title, book_author))
    else:
        found, failure = search_book(book_title, book_author)
        print(failure if failure else found)
