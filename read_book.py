from langchain_community.document_loaders import PyPDFLoader
from pydantic import BaseModel, Field

from util.chatgpt import llm_strict, llm_chat
from util.history import History

loader = PyPDFLoader("books/effective_communication.pdf")
pages = []

for page in loader.load():
    pages.append(page)

found_index = None


class ContainsIndexPage(BaseModel):
    found: bool = Field(..., description="Boolean describing if current page does includes an table of contents of the book.")


for index in range(10):
    history = History()
    history.system(pages[index].page_content)
    history.user("Does this page contain a table of contents?")
    result = llm_strict(history, base_model=ContainsIndexPage)
    print("finding", index)
    if result.found:
        found_index = index
        print("found index: ", found_index)
        break

end_index = None


class IntroductionFound(BaseModel):
    found: bool = Field(..., description="Boolean describing if current page does include an introduction chapter of the book.")


if found_index:
    for index in range(found_index+1, found_index+11):
        history = History()
        history.system(pages[index].page_content)
        history.user("Does this page contain the introduction?")
        result = llm_strict(history, base_model=IntroductionFound)
        print("checking", index)
        if result.found:
            end_index = index - 1
            print("end index: ", end_index)
            break
else:
    # exit
    pass

print(found_index, end_index)
if found_index and end_index:
    history = History()
    for page in pages[found_index: end_index-1]:
        history.system(page.page_content)

    query: str = "What are the names of the chapters that are available?"
    history.user(query)
    print(history)
    answer = llm_chat(history)
    print(answer)