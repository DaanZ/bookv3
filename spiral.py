"""Grade books on Spiral Dynamics: which value system, 3.0 to 8.0, each one speaks from.

    python spiral.py                      # list the books it would grade
    python spiral.py --book perfum        # only books whose file name contains this
    python spiral.py --write              # grade them: three model calls per book, combined
    python spiral.py --write --force      # grade again books that already have a level

Reads the book's own summary, like quests.py, and saves to data/spiral.json (api/spiral.py),
where the shelf finds it. Needs the API key. The prompt lives in the Field descriptions.
"""
import argparse
import glob
import os
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from api import spiral as store
from util.files import json_read_file
from util.parts import part_markdown

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
# Benchmarked on ten books (October 2026) against GPT-4o and Gemini 2.5 Flash: GPT-4o
# called a quarter of the library Yellow, Gemini swung by up to 2.4 between identical
# runs, and gpt-4o-mini was the steadiest and the cheapest, about $0.001 for three runs.
SPIRAL_MODEL = "openai/gpt-4o-mini"
# Each book is graded this many times and the runs combined (`combine`), because a single
# run moves by up to a whole level on some books.
RUNS = 3
# A run this far from the other two is an outlier and is left out of the average.
OUTLIER_GAP = 0.5
# The opening parts carry a book's argument; the rest is mostly worked examples. Capped
# so a 40-part book costs what a 12-part one does.
MAX_PARTS = 12


class SpiralGrade(BaseModel):
    reason: str = Field(description=(
        "One sentence of at most 30 words, in plain English, naming what this book values "
        "and asks of its reader: the evidence for the level. Written before choosing the "
        "level, and without naming a level or colour. About the book's stance, not its "
        "topic: a book can describe any value system while arguing from another."))
    level: float = Field(ge=3.0, le=8.0, description=(
        "The Spiral Dynamics level the book speaks from and asks its reader to take up, "
        "as a decimal with one place. The whole number is the level that carries most of "
        "the book; the tenths say how far it reaches toward the next one: 5.0 is pure "
        "Orange, 5.3 Orange with a little Green, 5.7 Orange well on the way to Green. "
        "Use the tenths for every book, so books that share a level can be told apart: "
        "a whole number like 5.0 only for a book that shows nothing of the next level. "
        "Never answer exactly .5; a book is always nearer one level than the other, so "
        "choose .4 or .6. The tenths are not for hedging between two levels. "
        "3 Red, power: strength, dominance, winning now, respect through force, heroes. "
        "4 Blue, order: duty, discipline, rules, one right way, tradition, sacrifice now "
        "for reward later, faith in an authority or a canon. "
        "5 Orange, achievement: success, strategy, competition, measurable results, "
        "science and reason as tools to get ahead, self-improvement for performance. "
        "6 Green, community: equality, feelings, belonging, consensus, care for people and "
        "the planet, questioning hierarchy, inclusion. "
        "7 Yellow, integration: systems and complexity, holding several value systems at "
        "once and using each where it works, flexibility, competence over status. "
        "8 Turquoise, wholeness: the world as one living system, collective and spiritual "
        "awareness grounded in that whole, acting for life on earth as a whole. "
        "Choose the level that carries the most of the book, and grade conservatively: "
        "most popular non-fiction is 4, 5 or 6. Innovation, strategy, growth and "
        "self-improvement are 5, even when the book talks about systems or flexibility. "
        "Virtue, self-discipline, duty and living by principle are 4, even when the book "
        "frames them as personal growth: Stoic writing (Marcus Aurelius, Seneca, Epictetus "
        "and books retelling them) asks the reader to master themselves, do their duty "
        "and live by fixed virtues, and grades about 4.2, below 4.5, not as Orange "
        "self-improvement. Choose 7 only when the "
        "book itself sets several value systems side by side and teaches when each one "
        "works; choose 8 only when its whole argument is the unity of all life. "
        "Reference books, textbooks and how-to manuals with no stance of their own are "
        "usually 4 if they teach a correct method and 5 if they teach how to get results."))


def book_paths(substring: str | None):
    paths = sorted(glob.glob(os.path.join(REPO_ROOT, "books", "available", "*.json"))
                   + glob.glob(os.path.join(REPO_ROOT, "books", "read", "*.json")))
    needle = (substring or "").lower()
    return [p for p in paths if needle in os.path.basename(p).lower()]


def combine(scores: list[float]) -> float:
    """Three runs into one grade: the average of all three, unless one sits far from the
    other two (more than OUTLIER_GAP from the nearer of them, and further than they are
    from each other), in which case it is left out and the other two are averaged.
    Measured: the Stoic letters ran 4.6, 4.6, 5.5 and Nietzsche 5.6, 6.4, 5.6; one odd
    run would otherwise drag the grade across a level."""
    low, mid, high = sorted(scores)
    # Gaps compared in whole tenths: 6.2 - 5.6 is 0.6000000000000005 in floating point,
    # which made an even spread look like an outlier.
    up, down = round((high - mid) * 10), round((mid - low) * 10)
    if up > OUTLIER_GAP * 10 and up > down:
        kept = [low, mid]
    elif down > OUTLIER_GAP * 10 and down > up:
        kept = [mid, high]
    else:
        kept = [low, mid, high]
    return round(sum(kept) / len(kept), 1)


def grade(book: dict, model: str) -> SpiralGrade:
    # Imported here: util/chatgpt reads the API key at import time, and the dry run
    # should work without one.
    from util.chatgpt import llm_strict
    from util.history import History

    meta = book.get("meta", {})
    history = History()
    history.system(f"Summary of the book \"{meta.get('title', '')}\" by {meta.get('author', 'an unknown author')}"
                   f" ({meta.get('category') or 'no category'}).")
    for number, part in enumerate((book.get("parts") or [])[:MAX_PARTS], start=1):
        history.system(f"Part {number}: {part.get('title', '')}\n\n{part_markdown(part)}")
    history.user("Grade this book on Spiral Dynamics.")
    return llm_strict(history, model_name=model, base_model=SpiralGrade)


class NoGrade(Exception):
    """The model gave fewer answers than runs asked for; nothing is saved."""


def grade_and_save(key: str, book: dict, model: str = SPIRAL_MODEL) -> dict:
    """Grade one book RUNS times, combine the runs and save the grade. Returns what was
    saved. Used by the command below and by the reader's ingest (api/jobs.py), which
    grades every new book as its last step so it arrives on the shelf with a pill."""
    results = [r for r in (grade(book, model) for _ in range(RUNS)) if r is not None]
    if len(results) < RUNS:
        raise NoGrade(f"{len(results)} of {RUNS} runs answered")
    runs = [round(r.level, 1) for r in results]
    score = combine(runs)
    # The reason from the run nearest the combined grade.
    result = min(results, key=lambda r: abs(r.level - score))
    saved = {"level": score, "runs": runs, "reason": result.reason, "model": model,
             "gradedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    store.save(key, saved)
    return saved


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--book", help="books whose file name contains this (case-insensitive)")
    parser.add_argument("--write", action="store_true", help="grade and save; without it nothing is spent")
    parser.add_argument("--force", action="store_true", help="grade again books that already have a level")
    parser.add_argument("--model", default=SPIRAL_MODEL, help=f"an OpenRouter model id; defaults to {SPIRAL_MODEL}")
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
        score = saved["level"]
        label = store.label_of(store.band_of(score))
        print(f"  {score:.1f} {label:<24} {key[:50]}  -  {saved['reason']}", flush=True)


if __name__ == "__main__":
    main()
