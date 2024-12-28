from typing import List

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document

from util.chatgpt import llm_chat
from util.history import History


def read_book_pages(path: str):
    loader = PyPDFLoader(path)
    pages = []
    for page in loader.load():
        pages.append(page)
    return pages


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

