import re

from pydantic import Field, BaseModel

from util.chatgpt import llm_strict
from util.history import History
from util.split import page_chunk_bounds


# Define the number of chunks
def get_page_chunks(pages, num_chunks: int = 10):
    # The boundaries live in util/split.py so api/estimate.py can price a book without
    # importing this module, which needs an API key at import time.
    bounds = page_chunk_bounds(len(pages), num_chunks)
    return [pages[start:end] for start, end in bounds]


class DisabilityBookFirstChunk(BaseModel):
    summary_chunk: str = Field(..., description="First summarize the chunk without title into one paragraph for people with ADHD / Dyslexia highlighting important words using markdown **.")
    summary_title: str = Field(..., description="Title that belongs to the summary")


class DisabilityBookNextChunk(DisabilityBookFirstChunk):
    summary_chunk: str = Field(..., description="First summarize the chunk without title into two paragraphs for people with ADHD / Dyslexia highlighting important words using markdown **.")


def format_text(answer):
    if "```html" in answer:
        answer = answer.replace("```html", "").replace("```")

    if "**" in answer:
        # Replace **text** with <b>text</b>
        answer = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', answer)

    if "###" in answer:
        answer = re.sub(r'### (.*)', r'<h3>\1</h3>', answer)

    if "_" in answer:
        answer = re.sub(r'_(.*?)_', r'<em>\1</em>', answer)

    return answer\
        .replace("<b>", "<b style='color: forestgreen;'>")\
        .replace("<h3>", "<h3 style='color: forestgreen;'>")\
        .replace("<em>", "<em style='color: forestgreen;'>")


def highlight_chunk(pages, first=True, model=None):
    history = History()
    for page in pages:
        history.system(page.page_content)

    chunk_model = DisabilityBookFirstChunk
    if not first:
        chunk_model = DisabilityBookNextChunk
    print(chunk_model.__name__)
    response = llm_strict(history, model_name=model, base_model=chunk_model)
    return {"title": response.summary_title, "body": format_text(response.summary_chunk)}

