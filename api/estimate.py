"""What a book will cost to summarize, worked out before a single token is spent.

Reading a PDF is free; summarizing it is not. This prices a book from the text itself
and the shape of the pipeline, so the library screen can ask before it spends.

**The one insight that makes the estimate reliable.** `get_page_chunks` cuts the book
into contiguous, non-overlapping page ranges, and `highlight_chunk` pushes every page of
its range in as a `system` message. So the whole book is sent as input *exactly once*,
whatever the chunk count — the first five pages go twice, because `get_book_meta` sees
them again. Chunk count therefore barely moves the input bill and only scales output.
That is why asking for more parts is cheap and asking for a bigger book is not.

**Where the output numbers come from.** They are measured, not guessed: 254 committed
book summaries, 2,812 parts, with `chunks.format_text`'s HTML turned back into the
markdown the model actually emitted, since the inline styling was never billed.

    first part   mean 673 chars   median 652
    later parts  mean 1017 chars  median 988
    titles       mean  41 chars   median  41

**Token counting is approximate.** `tiktoken` downloads its vocabulary on first use,
which fails behind a TLS-intercepting proxy, so characters over `CHARS_PER_TOKEN` is the
default and tiktoken is used only if it is already available offline. The result says
which method it used; the estimate is a range, and is presented as one.
"""

import os
import threading
import time

import requests

from util.split import page_chunk_bounds

try:  # Same OS-trust-store fix as util/chatgpt.py; the pricing call is HTTPS too.
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover
    pass

# ---------------------------------------------------------------------------
# The cost model. Every number here is an assumption you can change.
# ---------------------------------------------------------------------------

# English prose through pypdf's extractor. Deliberately not clever — see the note above.
CHARS_PER_TOKEN = 4.0

# Measured means, in tokens, from the 2,812 parts of the committed corpus.
FIRST_PART_OUTPUT_TOKENS = 168      # one paragraph  (673 chars)
LATER_PART_OUTPUT_TOKENS = 254      # two paragraphs (1017 chars)
PART_TITLE_OUTPUT_TOKENS = 10       # (41 chars)
META_OUTPUT_TOKENS = 40             # title, author, category, publisher

# The JSON schema, tool framing and role wrappers that ride along with every request.
PER_CALL_INPUT_OVERHEAD = 120
PER_MESSAGE_INPUT_OVERHEAD = 4

# Pages `get_book_meta` re-reads to identify the book.
META_PAGES = 5

# Real books vary; the corpus spread (p10 to p90) is roughly -40%/+50% on the output
# side. Output is the smaller half of the bill, so the band on the total is tighter.
LOW_MULTIPLIER = 0.85
HIGH_MULTIPLIER = 1.25

# Models worth offering. Two filters got them here. They list `structured_outputs` on
# OpenRouter, without which `llm_strict` — the only way a summary gets made — cannot run.
# And they were tried on real book chunks and actually emitted `**` marks.
#
# That second filter removed the cheap end of the list entirely. `gpt-4.1-nano`,
# `mistral-small-3.2-24b`, `llama-3.3-70b` and `deepseek-chat-v3.1` all returned fluent
# summaries containing *zero* highlighting, and several described the book from outside
# ("The text appears to be a philosophical work") instead of summarizing it. They are a
# third of the price and they quietly destroy the thing the reader is for, so offering
# them as a cheap option would be offering a trap.
CANDIDATE_MODELS = [
    "openai/gpt-4o",
    "openai/gpt-4.1",
    "openai/gpt-4.1-mini",
    "openai/gpt-4o-mini",
    "google/gemini-2.5-flash",
]

MODELS_URL = "https://openrouter.ai/api/v1/models"
_PRICE_TTL_SECONDS = 3600

_price_lock = threading.Lock()
_price_cache = {"fetched": 0.0, "models": {}}


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

def _fetch_prices():
    """Live OpenRouter prices, cached for an hour. Returns {} if the call fails —
    the estimate then reports token counts with no dollar figure, which is still
    the useful half."""
    now = time.time()
    with _price_lock:
        if _price_cache["models"] and now - _price_cache["fetched"] < _PRICE_TTL_SECONDS:
            return _price_cache["models"]

    try:
        response = requests.get(MODELS_URL, timeout=20)
        response.raise_for_status()
        entries = response.json().get("data", [])
    except (requests.RequestException, ValueError):
        return _price_cache["models"]

    models = {}
    for entry in entries:
        pricing = entry.get("pricing") or {}
        try:
            models[entry["id"]] = {
                "id": entry["id"],
                "name": entry.get("name") or entry["id"],
                "inputPerMillion": float(pricing["prompt"]) * 1e6,
                "outputPerMillion": float(pricing["completion"]) * 1e6,
                "contextLength": entry.get("context_length") or 0,
                "structured": "structured_outputs" in (entry.get("supported_parameters") or []),
            }
        except (KeyError, TypeError, ValueError):
            continue

    with _price_lock:
        _price_cache["models"] = models
        _price_cache["fetched"] = now
    return models


# ---------------------------------------------------------------------------
# Counting
# ---------------------------------------------------------------------------

def _encoder():
    """tiktoken, but only if it can load without reaching the network."""
    try:
        import tiktoken

        return tiktoken.get_encoding("o200k_base")
    except Exception:
        return None


def count_tokens(texts):
    """Token count for a list of strings, plus the method used to get it."""
    encoder = _encoder()
    if encoder is not None:
        return [len(encoder.encode(text)) for text in texts], "tiktoken"
    return [round(len(text) / CHARS_PER_TOKEN) for text in texts], "characters"


def read_pdf_pages(path):
    """Page texts, read with pypdf directly.

    Not `fragments.read_book_pages`: that module imports `util.chatgpt` at module scope,
    so it needs an API key. Pricing a book must work without one. PyPDFLoader wraps this
    same extractor, so the text is the text the pipeline will send.
    """
    from pypdf import PdfReader

    reader = PdfReader(path)
    return [(page.extract_text() or "") for page in reader.pages]


# ---------------------------------------------------------------------------
# The estimate
# ---------------------------------------------------------------------------

def estimate_tokens(page_texts, chunks=None, pages_per_chunk=25):
    """Token counts for one book at a given number of parts."""
    page_count = len(page_texts)
    if page_count == 0:
        raise ValueError("This PDF has no pages.")

    total = chunks if chunks else -(-page_count // pages_per_chunk)  # ceil
    total = max(1, min(int(total), page_count))

    per_page, method = count_tokens(page_texts)
    bounds = page_chunk_bounds(page_count, total)

    chunk_inputs = []
    for start, end in bounds:
        pages = per_page[start:end]
        chunk_inputs.append(
            sum(pages) + len(pages) * PER_MESSAGE_INPUT_OVERHEAD + PER_CALL_INPUT_OVERHEAD
        )

    meta_pages = per_page[: min(META_PAGES, page_count)]
    meta_input = (
        sum(meta_pages) + len(meta_pages) * PER_MESSAGE_INPUT_OVERHEAD + PER_CALL_INPUT_OVERHEAD
    )

    output = META_OUTPUT_TOKENS + total * PART_TITLE_OUTPUT_TOKENS
    output += FIRST_PART_OUTPUT_TOKENS + max(0, total - 1) * LATER_PART_OUTPUT_TOKENS

    return {
        "pages": page_count,
        "characters": sum(len(text) for text in page_texts),
        "emptyPages": sum(1 for text in page_texts if not text.strip()),
        "chunks": total,
        "calls": total + 1,  # one per part, plus the meta call
        "method": method,
        "inputTokens": sum(chunk_inputs) + meta_input,
        "outputTokens": output,
        "largestChunkTokens": max(chunk_inputs) if chunk_inputs else 0,
    }


def price_options(tokens, models=None):
    """Cost per candidate model, cheapest first."""
    catalogue = _fetch_prices()
    options = []
    for model_id in models or CANDIDATE_MODELS:
        entry = catalogue.get(model_id)
        if entry is None:
            continue
        cost = (
            tokens["inputTokens"] * entry["inputPerMillion"]
            + tokens["outputTokens"] * entry["outputPerMillion"]
        ) / 1e6
        options.append({
            **entry,
            "cost": round(cost, 4),
            "costLow": round(cost * LOW_MULTIPLIER, 4),
            "costHigh": round(cost * HIGH_MULTIPLIER, 4),
            # A part whose pages exceed the context window cannot be summarized at all.
            "fits": entry["contextLength"] >= tokens["largestChunkTokens"],
        })
    options.sort(key=lambda option: option["cost"])
    return options


def estimate_pdf(path, chunks=None, pages_per_chunk=25):
    """Everything the library screen needs to ask 'shall I spend this?'."""
    tokens = estimate_tokens(read_pdf_pages(path), chunks, pages_per_chunk)
    options = price_options(tokens)
    default = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    return {
        **tokens,
        "options": options,
        "defaultModel": default,
        "pricesLive": bool(options),
    }
