"""Give every book an ISBN, so adding one to Hardcover is a fact rather than a guess.

    python tools/backfill_isbns.py            # report only
    python tools/backfill_isbns.py --write    # write meta.isbn into books/*/*.json

An ISBN identifies an edition. Without one, matching a summary to Hardcover is inference
from a title and an author — which is how "Atomic Habits" finds a workbook and "Flow"
finds a different book with the same first word. With one, it is exact.

Two sources, in order of how much they can be trusted:

1. **The book itself**, when the PDF or EPUB is still on disk. Read off the copyright
   page or the EPUB manifest and checksum-validated, so it is a fact about that file.
2. **Hardcover's search index**, matched on title and author. Good enough to act on, but
   it is somebody else's record of a similar book, so it is marked as such.
3. **Open Library**, for the books Hardcover has never heard of — which is precisely the
   set worth contributing, and the set Hardcover cannot help with by definition.

A book that gets neither is reported rather than guessed at. That is the honest answer
for a summary whose source file is long gone and which Hardcover has never heard of —
and those are exactly the books worth contributing, so the list is the useful output.
"""

import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from util.files import json_write_file  # noqa: E402
from util.isbn import find_isbn, find_isbn_in_name, normalise, valid  # noqa: E402

# Hardcover is somebody else's server and this walks the whole shelf.
PAUSE_SECONDS = 0.35


def source_files():
    """Whatever originals are still around, by lowercase name for loose matching."""
    found = {}
    for path in glob.glob("pdfs/*.pdf") + glob.glob("next/*.pdf") + glob.glob(
        "pdfs/*.epub"
    ) + glob.glob("next/*.epub"):
        found[os.path.basename(path).lower()] = path
    return found


def matching_source(title, sources):
    """The original for this book, if it is still here.

    Matched on the first few words of the title against the filename — the pipeline named
    the summary from the title and the download was named from it too, so they share a
    prefix far more often than they share anything else.
    """
    stem = "".join(c for c in title.lower() if c.isalnum() or c == " ").split()
    if not stem:
        return None
    probe = "_".join(stem[:4])[:40]
    loose = probe.replace("_", "")
    for name, path in sources.items():
        flat = "".join(c for c in name if c.isalnum())
        if loose[:18] and loose[:18] in flat:
            return path
    return None


def from_file(path):
    if path.lower().endswith(".epub"):
        from util.epub import epub_metadata, read_epub_pages

        declared = epub_metadata(path).get("isbn")
        if declared:
            return declared
        return find_isbn(read_epub_pages(path))

    from pypdf import PdfReader

    try:
        pages = [(p.extract_text() or "") for p in PdfReader(path).pages]
    except Exception:
        return None
    return find_isbn(pages) or find_isbn_in_name(os.path.basename(path))


def from_hardcover(title, author, token):
    from hardcover.request import search_book

    book, error = search_book(title, author, token=token)
    if error or not book:
        return None, None
    for candidate in book.get("isbns") or []:
        digits = normalise(candidate)
        if valid(digits) and len(digits) == 13:
            return digits, book
    return None, book


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write the ISBNs into the books")
    parser.add_argument("--limit", type=int, default=0, help="stop after N books")
    args = parser.parse_args()

    from api.profiles import all_profiles, hardcover_token

    token = next((hardcover_token(p["id"]) for p in all_profiles() if p.get("hasHardcover")), None)
    sources = source_files()
    print(f"{len(sources)} source files on disk, Hardcover token: {'yes' if token else 'no'}\n")

    counts = {}
    already = missing = 0
    unmatched = []

    paths = sorted(glob.glob("books/*/*.json"))
    if args.limit:
        paths = paths[: args.limit]

    for path in paths:
        with open(path, encoding="utf-8") as handle:
            book = json.load(handle)
        meta = book.get("meta") or {}
        title, author = meta.get("title") or "", meta.get("author") or ""

        if meta.get("isbn"):
            already += 1
            continue

        isbn, origin = None, None
        source = matching_source(title, sources)
        if source:
            isbn = from_file(source)
            origin = "file"

        if not isbn and token:
            isbn, _ = from_hardcover(title, author, token)
            origin = "hardcover"
            time.sleep(PAUSE_SECONDS)

        if not isbn:
            # A different catalogue. Asked last because it is the only one of the three
            # that knows nothing about this library, but it is the one that can answer
            # for a book Hardcover is missing.
            from util.booklookup import isbn_from_openlibrary

            isbn = isbn_from_openlibrary(title, author)
            origin = "openlibrary"
            time.sleep(PAUSE_SECONDS)

        if not isbn:
            missing += 1
            unmatched.append(title)
            continue

        counts[origin] = counts.get(origin, 0) + 1

        if args.write:
            meta["isbn"] = isbn
            # Where it came from, because the two are not equally trustworthy and a later
            # reader of this file deserves to know which one they have.
            meta["isbnSource"] = origin
            book["meta"] = meta
            json_write_file(path, book)

    print(f"already had one   : {already}")
    for origin, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"from {origin:<13}: {n}")
    print(f"no ISBN found     : {missing}")
    if unmatched:
        print("\nthese need one by hand — no source file, and Hardcover has no match:")
        for title in unmatched[:25]:
            print(f"  {title[:70]}")
        if len(unmatched) > 25:
            print(f"  ... and {len(unmatched) - 25} more")
    if not args.write:
        print("\nnothing written — run again with --write")


if __name__ == "__main__":
    main()
