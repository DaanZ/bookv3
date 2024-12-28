import re
from math import floor

import numpy as np
from pydantic import Field, BaseModel

from util.chatgpt import llm_strict
from util.history import History


# Define the number of chunks
def get_page_chunks(pages, num_chunks: int = 10):
    amount_pages: int = len(pages)
    # Define the range of the left side of the Gaussian distribution (0 to 1)
    x = np.linspace(0, 1, 1000)

    # Compute the Gaussian probability density function (normalized)
    mean = 0
    std_dev = 1
    gaussian_pdf = (1 / (std_dev * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mean) / std_dev) ** 2)

    # Calculate the cumulative distribution function (CDF)
    gaussian_cdf = np.cumsum(gaussian_pdf)
    gaussian_cdf /= gaussian_cdf[-1]  # Normalize the CDF to [0, 1]

    # Divide the CDF into 10 equal probability chunks and find the corresponding x ranges
    chunk_edges = np.linspace(0, 1, num_chunks + 1)
    chunk_ranges = []

    for i in range(num_chunks):
        lower_bound = chunk_edges[i]
        upper_bound = chunk_edges[i + 1]
        lower_x = x[np.searchsorted(gaussian_cdf, lower_bound)]
        upper_x = x[np.searchsorted(gaussian_cdf, upper_bound)]
        chunk_ranges.append((lower_x, upper_x))

    page_chunks = []
    for chunk in chunk_ranges:
        start_index = floor(chunk[0]*amount_pages)
        end_index = floor(chunk[1]*amount_pages)
        print(start_index, end_index)
        page_chunks.append(pages[start_index:end_index])
    return page_chunks


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


def highlight_chunk(pages, first=True):
    history = History()
    for page in pages:
        history.system(page.page_content)

    chunk_model = DisabilityBookFirstChunk
    if not first:
        chunk_model = DisabilityBookNextChunk
    print(chunk_model.__name__)
    response = llm_strict(history, base_model=chunk_model)
    return {"title": response.summary_title, "body": format_text(response.summary_chunk)}

