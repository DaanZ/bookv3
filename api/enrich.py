"""Hardcover metadata for a book, cached locally.

The cover, rating, genres and the link out all come from Hardcover, and none of it
belongs in `books/*.json`: that file is the pipeline's output, it is committed, and
mixing somebody else's mutable catalogue into it would churn git every time a rating
moved. This is a cache beside `positions.json` instead — gitignored, disposable, and
rebuildable by asking again.

The cover is stored as Hardcover's URL. Downloading it would mean rehosting their asset,
and it would go stale the moment an edition is re-covered.
"""

import os
import threading

from util.files import json_read_file, json_write_file

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(ROOT, "data")
STORE_PATH = os.path.join(STORE_DIR, "hardcover.json")

_lock = threading.Lock()


def _read():
    stored = json_read_file(STORE_PATH)
    return stored if isinstance(stored, dict) else {}


def all_metadata():
    with _lock:
        return _read()


def get(key):
    return all_metadata().get(key)


def put(key, data):
    with _lock:
        store = _read()
        if data is None:
            store.pop(key, None)
        else:
            store[key] = data
        os.makedirs(STORE_DIR, exist_ok=True)
        json_write_file(STORE_PATH, store)
        return data


def fetch(key, title, author, isbn=None):
    """Look the book up on Hardcover and cache what comes back.

    Imported here rather than at module scope so the reader still starts without a
    Hardcover key — the same rule the ingest pipeline follows.
    """
    from hardcover.request import search_book

    found, error = search_book(title, author, isbn=isbn)
    if error:
        return None, error
    return put(key, found), None
