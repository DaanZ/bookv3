"""Find the ISBN printed in a book.

Worth the effort because it turns a guess into a fact: matching Hardcover by title and
author is inference that can land on a workbook or a summary cash-in, while an ISBN is
the same physical edition or nothing.

Only checksum-valid numbers are returned. A copyright page is dense with digits — the
Library of Congress control number, the printing line, a phone number — and a regex
alone will happily hand back any of them.
"""

import re

# "ISBN 978-0-06-133920-2", "ISBN-13: 9780061876721", "eISBN 0061548154". The label is
# required: a bare 13-digit run on a copyright page is as likely to be something else.
#
# Separators exclude line breaks on purpose. With `\s` in the class the match ran past
# the end of the line and took the first digit of whatever followed — a copyright page
# reads "ISBN 978-0-674-72901-8\n1.  Learning", which came back as a 14-digit string,
# failed its checksum, and was dropped without a word. Half the books silently had no
# ISBN because of it.
SEPARATORS = r"0-9\-–—‐  "
LABELLED = re.compile(
    rf"(?:^|\W)(?:e|p)?ISBN(?:-?1[03])?\s*:?[  ]*([0-9][{SEPARATORS}]{{8,20}}[0-9Xx])", re.I
)

# Where it is printed: the copyright page at the front, occasionally the back cover.
FRONT_PAGES = 14
BACK_PAGES = 4


def normalise(value):
    return re.sub(r"[^0-9Xx]", "", value or "").upper()


def valid_isbn10(digits):
    if len(digits) != 10:
        return False
    total = 0
    for i, character in enumerate(digits):
        if character == "X":
            if i != 9:
                return False
            value = 10
        elif character.isdigit():
            value = int(character)
        else:
            return False
        total += value * (10 - i)
    return total % 11 == 0


def valid_isbn13(digits):
    if len(digits) != 13 or not digits.isdigit():
        return False
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits))
    return total % 10 == 0


def valid(digits):
    return valid_isbn13(digits) or valid_isbn10(digits)


def to_isbn13(digits):
    """A 10-digit ISBN is the same book as its 13-digit form; Hardcover indexes both."""
    if len(digits) == 13:
        return digits
    if not valid_isbn10(digits):
        return None
    core = "978" + digits[:9]
    check = (10 - sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(core)) % 10) % 10
    return core + str(check)


def find_isbn_in_name(filename):
    """An ISBN sitting in the download's filename.

    Library filenames routinely carry one — "… (Alison Gopnik) [2016] 9780374229702" —
    and for an ebook that is often the only one there is: the ebook the publisher ships
    has no copyright page, so nothing in the text ever says it. Bare digits are accepted
    here without a label, which the page scanner refuses, because the checksum is doing
    the work and a filename has far less passing numeric noise than a copyright page.
    """
    for candidate in re.findall(r"(?<!\d)(97[89]\d{10}|\d{9}[\dXx])(?!\d)", filename or ""):
        digits = normalise(candidate)
        if valid(digits):
            return to_isbn13(digits) or digits
    return None


def find_isbn(page_texts, deep=False):
    """The best ISBN in a book, preferring 13-digit. Returns None when there is none.

    The front and back are searched first because that is where a book states its own
    number. `deep` then reads the whole text, and is a last resort rather than the
    default: an ISBN in the middle of a book is usually in a bibliography, and belongs to
    a book being cited rather than to this one. Worth trying only once the honest places
    have come up empty — some editions put their copyright page somewhere unexpected, and
    a cited ISBN is still better than filing the book with none.
    """
    pages = list(page_texts)
    looked_at = pages[:FRONT_PAGES] + pages[-BACK_PAGES:]
    if deep:
        looked_at = pages

    found = []
    for text in looked_at:
        for raw in LABELLED.findall(text or ""):
            digits = normalise(raw)
            if valid(digits):
                found.append(digits)

    if not found:
        return None
    # A book lists several editions on one page — hardback, paperback, ebook. Any of them
    # identifies the work to Hardcover, so take the first 13-digit one and fall back.
    thirteen = [d for d in found if len(d) == 13]
    return thirteen[0] if thirteen else to_isbn13(found[0]) or found[0]
