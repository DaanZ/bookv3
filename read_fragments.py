import re
from typing import List

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from pydantic import BaseModel, Field

from util.chatgpt import llm_strict, llm_chat
from util.files import json_write_file
from util.history import History


def read_book_pages(path: str):
    loader = PyPDFLoader(path)
    pages = []
    for page in loader.load():
        pages.append(page)
    return pages


class BookMeta(BaseModel):
    title: str = Field(..., description="Title of the book")
    author: str = Field(..., description="Author of the book")
    publisher: str = Field(..., description="Publisher of the book")


def get_book_meta(pages: List[Document], n: int = 5):
    history = History()
    for page in pages[:n]:
        history.system(page.page_content)
    history.user("What is the name of the book?")
    meta: BookMeta = llm_strict(history, base_model=BookMeta)
    return meta


def summarize_book(pages: List[Document], n: int = 10):
    number_pages = len(pages)
    parts = []
    for index in range(0, number_pages, n):
        subpages = pages[index:index+n]
        history = History()
        for page in subpages:
            history.system(page.page_content)
        history.user("Summarize the above chunk of the book into a couple of paragraphs, "
                     "don't refer to the summary or the book itself just focus on the chunk "
                     "of the book that is being summarized")
        answer = llm_chat(history)
        parts.append(answer)
    return parts


def summarize_chunk(pages):
    history = History()
    for page in pages:
        history.system(page.page_content)
    history.user("Summarize the above chunk of the book into a one paragraph, "
                 "don't refer to the summary or the book itself just focus on the chunk "
                 "of the book that is being summarized")
    return llm_chat(history)


class DisabilityBookFirstChunk(BaseModel):
    summary_chunk: str = Field(..., description="First summarize the chunk into one paragraph for people with ADHD / Dyslexia.")
    summary_title: str = Field(..., description="Title that belongs to the summary")
    dyslextic_highlighted_html: str = Field(..., description="Second formatted the one paragraph in HTML format highlighting important words using bold <b>")


class DisabilityBookNextChunk(DisabilityBookFirstChunk):
    summary_chunk: str = Field(..., description="First summarize the chunk into three paragraphs for people with ADHD / Dyslexia.")




def format_text(answer):
    if "```html" in answer:
        answer = answer.replace("```html", "").replace("```")

    if "**" in answer:
        # Replace **text** with <b>text</b>
        answer = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', answer)

    return answer.replace("<b>", "<b style='color: forestgreen;'>")


def highlight_chunk(pages, first=True):
    history = History()
    for page in pages:
        history.system(page.page_content)

    chunk_model = DisabilityBookFirstChunk
    if not first:
        chunk_model = DisabilityBookNextChunk
    print(chunk_model.__name__)
    response = llm_strict(history, base_model=chunk_model)
    return {"title": response.summary_title, "body": format_text(response.dyslextic_highlighted_html)}


def summarize_book_highlighted(pages: List[Document], n: int = 10):
    number_pages = len(pages)
    parts = []
    for index in range(0, number_pages, n):
        subpages = pages[index:index+n]
        history = History()
        for page in subpages:
            history.system(page.page_content)
        history.user("Summarize the above chunk of the book into one paragraph, "
                     "don't refer to the summary or the book itself just focus on the chunk "
                     "of the book that is being summarized")
        answer = llm_chat(history)
        history = History()
        history.system(answer)
        history.user("Highlight words in the above summary and only output HTML format that makes the highlighted words bold and colour them forest green.")
        answer = llm_chat(history)
        if "```html" in answer:
            answer = answer.replace("```html", "").replace("```", "")
        parts.append(answer)
    return parts


if __name__ == "__main__":
    path = "books/effective_communication.pdf"

    pages = read_book_pages(path)

    meta = get_book_meta(pages)
    parts = summarize_book(pages)

    data = {
        "meta": {
            "title": meta.title,
            "author": meta.author,
            "publisher": meta.publisher,
            "pages": len(pages),
        },
        "content": [{"summary": part} for part in parts]
    }
    json_write_file(path.replace(".pdf", ".json"), data)
