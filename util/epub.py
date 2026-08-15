"""Reading an EPUB as if it had pages.

An EPUB is a zip of XHTML in reading order, with no pages in it at all — pagination is
the reading device's business, not the file's. The whole pipeline downstream is built on
a list of pages: `get_page_chunks` cuts page ranges, the estimator prices per page, the
waiting state names the pages a part covers. So the text is cut into page-sized blocks
here, once, and everything after this point cannot tell the difference.

Parsed with `zipfile` and BeautifulSoup rather than a new dependency: EPUB is a zip, its
manifest is XML, and bs4 is already here for the pipeline.
"""

import posixpath
import re
import zipfile

from bs4 import BeautifulSoup

# Characters to a synthesized page. A printed page of prose is roughly 1,800–2,500, and
# this decides how many parts a book is cut into and what page numbers the reader shows,
# so it is chosen to make an EPUB's part count resemble the same book in print.
PAGE_CHARS = 2000

CONTAINER = "META-INF/container.xml"

# Chrome that carries no book text. An EPUB's spine usually opens with several of these,
# and left in they become the first "pages" — which is what the meta step reads.
SKIP_NAMES = re.compile(r"(cover|title|copyright|colophon|nav|toc|contents)", re.I)


def _opf_path(archive):
    """Where the manifest lives, per the container. Never assume `content.opf`."""
    try:
        soup = BeautifulSoup(archive.read(CONTAINER), "xml")
        rootfile = soup.find("rootfile")
        if rootfile and rootfile.get("full-path"):
            return rootfile["full-path"]
    except (KeyError, zipfile.BadZipFile):
        pass
    for name in archive.namelist():
        if name.lower().endswith(".opf"):
            return name
    return None


def _spine_documents(archive):
    """The book's XHTML files, in reading order.

    Reading order matters more here than anywhere else: chunks are contiguous ranges, so
    a book assembled out of order would be summarized out of order and nobody would be
    able to say why it made no sense.
    """
    opf = _opf_path(archive)
    if not opf:
        return []

    soup = BeautifulSoup(archive.read(opf), "xml")
    base = posixpath.dirname(opf)

    manifest = {}
    for item in soup.find_all("item"):
        if item.get("id") and item.get("href"):
            manifest[item["id"]] = posixpath.normpath(
                posixpath.join(base, item["href"])
            ) if base else item["href"]

    order = [
        manifest[ref["idref"]]
        for ref in soup.find_all("itemref")
        if ref.get("idref") in manifest
    ]
    # A file with no spine is still readable: fall back to every document in the archive.
    if not order:
        order = [n for n in archive.namelist() if n.lower().endswith((".xhtml", ".html", ".htm"))]
    return order


def _text_of(archive, name):
    try:
        raw = archive.read(name)
    except KeyError:
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(" ")
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def read_epub_pages(path, page_chars=PAGE_CHARS):
    """The book as a list of page-sized strings, in reading order."""
    with zipfile.ZipFile(path) as archive:
        documents = _spine_documents(archive)
        # Front matter is dropped only when there is a book behind it — a short EPUB that
        # is *all* front matter would otherwise read as empty.
        body = [n for n in documents if not SKIP_NAMES.search(posixpath.basename(n))]
        chosen = body if body else documents
        text = "\n\n".join(t for t in (_text_of(archive, name) for name in chosen) if t)

    if not text:
        return []
    return [text[i:i + page_chars] for i in range(0, len(text), page_chars)]


def epub_metadata(path):
    """Title, author and ISBN as the file declares them.

    Better than the PDF equivalent: an EPUB states these in its manifest rather than
    leaving them to be read off a title page that may not exist.
    """
    out = {}
    try:
        with zipfile.ZipFile(path) as archive:
            opf = _opf_path(archive)
            if not opf:
                return out
            soup = BeautifulSoup(archive.read(opf), "xml")

            title = soup.find("dc:title") or soup.find("title")
            creator = soup.find("dc:creator") or soup.find("creator")
            if title and title.get_text(strip=True):
                out["title"] = title.get_text(strip=True)
            if creator and creator.get_text(strip=True):
                out["author"] = creator.get_text(strip=True)

            for identifier in soup.find_all(["dc:identifier", "identifier"]):
                from util.isbn import normalise, valid

                digits = normalise(identifier.get_text(strip=True))
                if valid(digits):
                    out["isbn"] = digits
                    break
    except (zipfile.BadZipFile, KeyError, OSError):
        return out
    return out


def is_epub(path):
    try:
        with zipfile.ZipFile(path) as archive:
            return any(n.lower().endswith(".opf") for n in archive.namelist())
    except (zipfile.BadZipFile, OSError):
        return False
