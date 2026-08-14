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

MARK_READ_MUTATION = """
mutation addBook($bookId: Int!) {
  insert_user_book(object: {book_id: $bookId, status_id: 3}) {
    id
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


def search_book(title, author):
    """Find the most-read Hardcover book matching this title and author."""
    headers = _headers()
    if headers is None:
        return None, "HARDCOVER_API_KEY is not set."

    title, author = _shorten(title, author)

    data, error = _post(
        SEARCH_QUERY, {"title": f"%{title}%", "author": f"%{author}%"}, headers
    )
    if error:
        return None, error

    books = data.get("books") or []
    if not books:
        # The pipeline infers authors from the first pages and often gets "Not specified".
        # Title alone is a weaker match, so it is only a fallback.
        data, error = _post(TITLE_ONLY_QUERY, {"title": f"%{title}%"}, headers)
        if error:
            return None, error
        books = data.get("books") or []

    if not books:
        return None, f"Hardcover has no book matching “{title}”."
    return books[0], None


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
