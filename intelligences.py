"""Grade books on the nine intelligences: how much each way of thinking a book asks of its reader.

    python intelligences.py                      # list the books it would grade
    python intelligences.py --book coaching      # only books whose file name contains this
    python intelligences.py --write              # grade them: one model call per book
    python intelligences.py --write --force      # grade again books that already have fits

Reads the book's own summary, like spiral.py, and saves to data/intelligences.json
(api/intelligences.py), where the shelf finds it. Needs the API key. The prompt lives in
the Field descriptions, as everywhere else in this pipeline.
"""
import argparse
import os
from datetime import datetime, timezone

from pydantic import BaseModel, Field, create_model

from api import intelligences as store
from spiral import book_paths
from util.files import json_read_file
from util.parts import part_markdown

INTELLIGENCE_MODEL = "openai/gpt-4o-mini"
# The opening parts stand in for the book. On the ten "Ways in" books the first 3 matched
# the canvas as often as the first 12 (October 2026), at about half the cost.
SYNOPSIS_PARTS = 3

FIT = ("How much the book asks its reader to use or build this intelligence, 0 to 3: 0 not "
       "at all, 1 in passing, 2 a real part of it, 3 the heart of the book. Reading the book "
       "does not count: rate what its content asks of the reader, not the act of reading it.")

# One 0-3 field per intelligence, described by its meaning, so the schema itself is the
# prompt; `primary` is chosen after the fits, and `reason` comes first.
Fits = create_model("Fits", **{
    key: (int, Field(ge=0, le=3, description=f"{name}, {meaning}. {FIT}"))
    for key, (name, meaning) in store.INTELLIGENCES.items()
})


class IntelligenceGrade(BaseModel):
    reason: str = Field(description=(
        "One sentence of at most 30 words, in plain English: what the book asks its reader "
        "to do or notice, the evidence for the fits. Written before the fits."))
    fits: Fits
    primary: str = Field(description=(
        "The one intelligence the book most asks of its reader, as its key: "
        + ", ".join(store.INTELLIGENCES) + ". One of the highest fits."))


def grade(book: dict, model: str) -> IntelligenceGrade:
    # Imported here: util/chatgpt reads the API key at import time, and the dry run
    # should work without one.
    from util.chatgpt import llm_strict
    from util.history import History

    meta = book.get("meta", {})
    history = History()
    history.system(f"Summary of the book \"{meta.get('title', '')}\" by {meta.get('author', 'an unknown author')}"
                   f" ({meta.get('category') or 'no category'}).")
    for number, part in enumerate((book.get("parts") or [])[:SYNOPSIS_PARTS], start=1):
        history.system(f"Part {number}: {part.get('title', '')}\n\n{part_markdown(part)}")
    history.user("Rate how much this book asks of each of the nine intelligences.")
    return llm_strict(history, model_name=model, base_model=IntelligenceGrade)


def grade_and_save(key: str, book: dict, model: str = INTELLIGENCE_MODEL) -> dict:
    """Grade one book and save it. A `primary` the model invents, or one it rated below
    the top fit, is replaced by the first of the highest fits."""
    result = grade(book, model)
    if result is None:
        raise ValueError("no answer")
    fits = result.fits.model_dump()
    top = max(fits.values())
    # Lower-cased first: gpt-4o-mini answered "Spatial" for the key "spatial".
    named = result.primary.strip().lower()
    primary = named if fits.get(named) == top else next(k for k, v in fits.items() if v == top)
    saved = {"fits": fits, "primary": primary, "reason": result.reason, "model": model,
             "gradedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    store.save(key, saved)
    return saved


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--book", help="books whose file name contains this (case-insensitive)")
    parser.add_argument("--write", action="store_true", help="grade and save; without it nothing is spent")
    parser.add_argument("--force", action="store_true", help="grade again books that already have fits")
    parser.add_argument("--model", default=INTELLIGENCE_MODEL, help=f"an OpenRouter model id; defaults to {INTELLIGENCE_MODEL}")
    args = parser.parse_args()

    graded = store.load()
    for path in book_paths(args.book):
        key = os.path.splitext(os.path.basename(path))[0]
        if key in graded and not args.force:
            continue
        if not args.write:
            print(f"  would grade  {key[:70]}")
            continue
        try:
            saved = grade_and_save(key, json_read_file(path), args.model)
        except Exception as ex:  # one bad book must not stop the library
            print(f"  failed       {key[:70]}: {type(ex).__name__}: {ex}")
            continue
        name = store.INTELLIGENCES[saved["primary"]][0]
        print(f"  {name:<21} {key[:50]}  -  {saved['reason']}", flush=True)


if __name__ == "__main__":
    main()
