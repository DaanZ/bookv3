import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

api_url = "https://api.hardcover.app/v1/graphql"

TIMEOUT = 20

# Hasura comparison syntax. The previous version interpolated the title straight into
# the document as `{title: {<title>}}`, which is not a valid comparison expression —
# the search never worked. Values are passed as variables now, so a title containing a
# quote or a brace cannot break (or rewrite) the query.
SEARCH_QUERY = """
query findBook($title: String!, $author: String!) {
  books(
    where: {
      _and: [
        {title: {_ilike: $title}},
        {contributions: {author: {name: {_ilike: $author}}}}
      ]
    },
    order_by: {users_read_count: desc},
    limit: 5
  ) {
    id
    title
    contributions { author { name } }
  }
}
"""

TITLE_ONLY_QUERY = """
query findBookByTitle($title: String!) {
  books(where: {title: {_ilike: $title}}, order_by: {users_read_count: desc}, limit: 5) {
    id
    title
    contributions { author { name } }
  }
}
"""

# The same two searches again, asking for what a shelf entry wants: the cover, the
# slug that links back to Hardcover, the year. Kept separate from the pair above rather
# than folded into it, because those two are on the path that marks a book read and a
# richer selection set is one more thing that can be rejected.
_DETAIL_FIELDS = """
    id
    slug
    title
    release_year
    image { url }
    cached_image
    contributions { author { name } }
"""

DETAILS_QUERY = """
query findBookDetails($title: String!, $author: String!) {
  books(
    where: {
      _and: [
        {title: {_ilike: $title}},
        {contributions: {author: {name: {_ilike: $author}}}}
      ]
    },
    order_by: {users_read_count: desc},
    limit: 5
  ) {%s}
}
""" % _DETAIL_FIELDS

DETAILS_TITLE_ONLY_QUERY = """
query findBookDetailsByTitle($title: String!) {
  books(where: {title: {_ilike: $title}}, order_by: {users_read_count: desc}, limit: 5) {%s}
}
""" % _DETAIL_FIELDS

MARK_READ_MUTATION = """
mutation addBook($bookId: Int!) {
  insert_user_book(object: {book_id: $bookId, status_id: 3}) {
    id
  }
}
"""

# A GraphQL error inside a 200 — the one failure that means "this document is wrong",
# as opposed to "the network is down", and so the one worth retrying differently.
REJECTED = "Hardcover rejected the query"


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
        return None, f"{REJECTED}: {message}"

    return payload.get("data") or {}, None


def _shorten(title, author):
    """The pipeline's titles carry subtitles and joint authors; Hardcover's do not."""
    if ":" in title:
        title = title.split(":")[0]
    for separator in (" and ", " & ", ", "):
        if separator in author:
            author = author.split(separator)[0]
    return title.strip(), author.strip()


def _find(pair_query, title_query, title, author):
    """Most-read match for a title and author, by whichever pair of queries is asked
    for. Read-only — nothing on this path writes to Hardcover."""
    headers = _headers()
    if headers is None:
        return None, "HARDCOVER_API_KEY is not set."

    title, author = _shorten(title, author)

    data, error = _post(
        pair_query, {"title": f"%{title}%", "author": f"%{author}%"}, headers
    )
    if error:
        return None, error

    books = data.get("books") or []
    if not books:
        # The pipeline infers authors from the first pages and often gets "Not specified".
        # Title alone is a weaker match, so it is only a fallback.
        data, error = _post(title_query, {"title": f"%{title}%"}, headers)
        if error:
            return None, error
        books = data.get("books") or []

    if not books:
        return None, f"Hardcover has no book matching “{title}”."
    return books[0], None


def search_book(title, author):
    """Find the most-read Hardcover book matching this title and author."""
    return _find(SEARCH_QUERY, TITLE_ONLY_QUERY, title, author)


def search_book_details(title, author):
    """`search_book` plus the cover and the slug.

    If Hardcover rejects the richer selection set — a field renamed, a relation gone —
    this falls back to the plain search, so a schema change costs the cover rather than
    the whole lookup.
    """
    book, error = _find(DETAILS_QUERY, DETAILS_TITLE_ONLY_QUERY, title, author)
    if error and error.startswith(REJECTED):
        return search_book(title, author)
    return book, error


def cover_url_of(book):
    """The jacket, from whichever of the two image shapes this record carries.
    `image` is a relation; `cached_image` is jsonb, and has arrived as a JSON string."""
    if not isinstance(book, dict):
        return None

    image = book.get("image")
    if isinstance(image, dict) and image.get("url"):
        return image["url"]

    cached = book.get("cached_image")
    if isinstance(cached, str):
        try:
            cached = json.loads(cached)
        except ValueError:
            return None
    if isinstance(cached, dict) and cached.get("url"):
        return cached["url"]
    return None


def mark_book_as_read(title, author):
    """Search for a book by title and author, then mark it read (status_id 3).

    Returns the API response on success, or `{"error": ...}` — callers must not
    report success without checking for that key.
    """
    book, error = search_book(title, author)
    if error:
        return {"error": error}

    data, error = _post(MARK_READ_MUTATION, {"bookId": int(book["id"])}, _headers())
    if error:
        return {"error": error}

    return {"data": data, "book": {"id": book["id"], "title": book.get("title")}}


if __name__ == "__main__":
    # Example usage
    book_title = "Programming Kubernetes"
    book_author = "Michael Hausenblas"

    result = mark_book_as_read(book_title, book_author)
    print(result)
