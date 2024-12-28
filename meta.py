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


def get_book_meta(pages: List[Document], n: int = 5):
    history = History()
    total_characters = 0
    for page in pages[:n]:
        print("characters", len(page.page_content))
        history.system(page.page_content)
        total_characters += len(page.page_content)
    print("total", total_characters)
    if total_characters == 0:
        raise UnreadableCharactersError(details="Unable to read characters in book")
    history.user("What is the name of the book?")
    meta: BookMeta = llm_strict(history, base_model=BookMeta)
    return {"title": meta.title, "author": meta.author, "category": meta.category,
            "publisher": meta.publisher, "pages": len(pages)}
