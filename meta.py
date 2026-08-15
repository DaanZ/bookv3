from typing import List

from langchain_core.documents import Document
from pydantic import Field, BaseModel

from util.chatgpt import llm_strict
from util.history import History


class UnreadableCharactersError(Exception):
    def __init__(self, message="The characters in the book cannot be read.", details=None):
        super().__init__(message)
        self.details = details


class BookMeta(BaseModel):
    title: str = Field(..., description="Title of the book")
    author: str = Field(..., description="Author of the book")
    category: str = Field(..., description="Category of the book")
    publisher: str = Field(..., description="Publisher of the book")


# Pages worth showing before giving up on finding a title page.
META_SEARCH_DEPTH = 14

# Under this a page is a cover, a blank, or a dedication — never the page that names the
# book. Skipping them is what lets the search reach real front matter within its budget.
MEANINGFUL_PAGE_CHARS = 120


def _front_pages(pages: List[Document], n: int):
    """The first `n` pages with enough text to identify a book.

    A print scan opens on a title page; an ebook opens on cover art that extracts as
    nothing, then the publisher's own advertising. Taking pages[:5] literally is how
    "The Gardener and the Carpenter" was filed as "Farrar, Straus and Giroux ebook" —
    the model was shown a thank-you-for-buying page and answered the question honestly.
    """
    chosen = [p for p in pages[:META_SEARCH_DEPTH] if len(p.page_content.strip()) >= MEANINGFUL_PAGE_CHARS]
    # Nothing substantial up front: fall back to whatever is there rather than refusing,
    # so a genuinely sparse book still gets its shot at the model.
    return (chosen or [p for p in pages[:META_SEARCH_DEPTH]])[:n]


def get_book_meta(pages: List[Document], n: int = 5, model: str = None, declared: dict = None):
    """Identify the book.

    `declared` is what the PDF says about itself — its own /Title and /Author. That is
    typed by whoever made the file rather than inferred from a page image, so it is the
    better source when it exists, and it is free. It is passed to the model rather than
    used directly because the model is good at the part it is good at: "Flow : the
    psychology of optimal experience" becoming "Flow: The Psychology of Optimal
    Experience", and "Gopnik, Alison" becoming "Alison Gopnik".
    """
    history = History()

    if declared:
        stated = ", ".join(f"{field} {value!r}" for field, value in declared.items() if value)
        if stated:
            history.system(f"The file states: {stated}. Trust this over the page text below.")

    total_characters = 0
    for page in _front_pages(pages, n):
        history.system(page.page_content)
        total_characters += len(page.page_content)
    if total_characters == 0 and not declared:
        raise UnreadableCharactersError(details="Unable to read characters in book")

    history.user(
        "What is the name of the book? Give the title as it is printed on the cover, not "
        "the publisher's imprint or a line from the front matter."
    )
    meta: BookMeta = llm_strict(history, model_name=model, base_model=BookMeta)
    return {"title": meta.title, "author": meta.author, "category": meta.category,
            "publisher": meta.publisher, "pages": len(pages)}
