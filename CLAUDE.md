# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A set of Python scripts that turn book PDFs into short, ADHD/dyslexia-friendly summaries with
forest-green highlighted keywords, then serve them through Streamlit readers. There is no package,
no test suite, and no build step — every entry point is a top-level script run directly.

## Commands

```bash
pip install -r requirements.txt   # note: numpy, pydantic and requests are used but NOT listed

streamlit run app.py          # upload a PDF and summarize it live, chunk by chunk
streamlit run next_reads.py   # main reader: read books/available, then move to books/read + Hardcover
streamlit run all.py          # browse/read already-finished summaries in books/read
streamlit run dashboard.py    # card grid of books (reads books/*.json — a stale path, see below)

python prep.py                # batch: summarize every PDF in ./next -> books/available, move PDF to ./pdfs
python homework.py            # scratch script: generates a quiz question from one hardcoded book
python hardcover/request.py   # exercises the Hardcover API against a hardcoded title/author
```

`.env` (gitignored) must provide `OPENAI_API_KEY`, and `HARDCOVER_API_KEY` for the Hardcover
integration. `util/chatgpt.py` reads `OPENAI_API_KEY` at import time, so *any* import of the chunking
or meta modules fails without it.

## Architecture

**Pipeline (PDF → JSON summary).** `fragments.read_book_pages` loads a PDF into LangChain `Document`
pages via `PyPDFLoader`. `chunks.get_page_chunks` splits those pages into N contiguous page ranges
using the left half of a Gaussian CDF — chunks are deliberately *uneven*, dense near the front of the
book and wider toward the end. `meta.get_book_meta` asks the LLM to identify title/author/category/
publisher from the first ~5 pages (and raises `UnreadableCharactersError` when the pages have zero
extractable characters, i.e. a scanned PDF). `chunks.highlight_chunk` then summarizes each page range.

**LLM access** goes through `util/chatgpt.py` only. `llm_strict` uses the OpenAI structured-output
parse API with a Pydantic model as the response schema; `llm_chat` is the plain-text variant. Prompts
are not written as prompt strings — they live in the Pydantic `Field(description=...)` text. That's
why `chunks.py` has two nearly identical models: `DisabilityBookFirstChunk` (one paragraph) vs
`DisabilityBookNextChunk` (two paragraphs), swapped by the `first` flag so the opening chunk is
shorter. `homework.py` uses the same trick for multiple choice: four models, `HomeworkAModel` through
`HomeworkDModel`, differing only in which answer field is described as correct, picked at random by
`random_answer_model()` so the correct letter is uniformly distributed.

Conversation state is a `util.history.History` — a thin list of `{role, content}` dicts. The pattern
throughout is to push each page's raw text as a `system` message, then a single `user` instruction.

**Highlighting.** `chunks.format_text` converts the model's markdown (`**bold**`, `###`, `_em_`) into
inline-styled HTML with `color: forestgreen`. Summary bodies are therefore stored as HTML and every
renderer passes `unsafe_allow_html=True`.

**Storage format.** Each book is one JSON file, named `sanitize_filename(title).json`:

```json
{"meta": {"title", "author", "category", "publisher", "pages"},
 "parts": [{"title": "...", "body": "<html>"}]}
```

**Book lifecycle.** `books/available/` holds unread summaries, `books/read/` holds finished ones.
`next_reads.py` is the piece that moves a file between them: when the reader reaches the last part it
calls `hardcover.request.mark_book_as_read` (GraphQL search + `insert_user_book` mutation with
`status_id: 3`) and then `shutil.move`s the JSON into `books/read/`. `prep.py` feeds the other end,
consuming PDFs from `./next` and parking the originals in `./pdfs` (both gitignored, both absent from
a fresh clone — `prep.py` creates the output dirs but expects `next/` to exist).

**Streamlit state.** Each script is a `if __name__ == "__main__"` block that re-executes top to bottom
on every interaction, so all cross-rerun state lives in `st.session_state`, and `st.empty()`
placeholders captured into session state are reused as render slots (`next_reads.py`). `app.py`
additionally pre-computes the *next* chunk's summary during the current rerun (`next_highlighted`) to
hide LLM latency behind the user's reading time.

## Known rough edges

Don't treat these as intentional design when editing nearby code:

- `dashboard.py` and `all.py` duplicate `get_json_files`/`extract_book_details` from `next_reads.py`,
  and `dashboard.py` points at `books/` (no JSON at that level) rather than a subfolder.
- Both dict literals in `extract_book_details` contain a stray `""` element between keys.
- `chunks.format_text` calls `.replace("```")` with one argument — raises `TypeError` if a response
  ever contains a ```` ```html ```` fence.
- `app.py` writes uploads to `uploaded_files/` but creates `pdfs/`.
- `hardcover/request.py` interpolates the title/author directly into GraphQL as
  `{title: {<title>}}`, which is not valid GraphQL comparison syntax; the search path is unproven.
- Broad `except Exception: print(ex)` blocks in `app.py` swallow errors into the console.
