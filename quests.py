"""Make three quests for a finished book: one small, one medium, one large.

    python quests.py --book perfum            # list the books it would make quests for
    python quests.py --book perfum --write    # make them: one model call per book
    python quests.py --book perfum --write --force   # make them again

Reads the book's own summary, not the PDF, so a quest can only use what the reader has
actually read. Saves to data/quests/<book key>.json (api/quests.py), where the finish
screen finds them. Needs the API key, like the rest of the pipeline.

The rule that keeps a quest honest is the done-when: something that exists or has
happened, which you could show someone. "Reflect on your fears" is not a quest; "write
down this week's worst worry and its worst realistic outcome, before dinner" is. The
prompt lives in the Field descriptions, as everywhere else in this pipeline.
"""
import argparse
import glob
import os
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from api import quests as quest_store
from util.files import json_read_file
from util.parts import part_markdown

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

QUEST = (
    "Specific to this book: it uses a named idea, method, recipe or example from the summary, "
    "not general self-improvement advice. Safe for an ordinary adult at home: say any precaution "
    "the materials need, and never anything to swallow, inject or set alight carelessly."
)


class Quest(BaseModel):
    title: str = Field(..., description="A short name for the quest, at most six words, plain text without markdown.")
    action: str = Field(..., description="What to do, in at most two short sentences, concrete enough to start without reading anything else. " + QUEST)
    done_when: str = Field(..., description="One sentence naming what exists or has happened when the quest is done: something you could check or show someone. Never 'reflect on', 'think about' or 'understand'.")
    minutes: int = Field(..., description="A realistic estimate of the time it takes, in minutes.")


class BookQuests(BaseModel):
    small: Quest = Field(..., description="A small quest: 10 to 20 minutes, today, using only things most homes already have, such as kitchen spices, citrus fruit, herbs or flowers from outside, paper and a jar. No specialist ingredient.")
    medium: Quest = Field(..., description="A medium quest: one to three hours, an evening this week. It may need one simple purchase from a supermarket or a chemist.")
    large: Quest = Field(..., description="A large quest spread over several days, a weekend or a week of short sessions, at least four hours in all: a real project that combines at least two of the book's methods or ideas.")


def book_paths(substring):
    paths = sorted(glob.glob(os.path.join(REPO_ROOT, "books", "available", "*.json")) +
                   glob.glob(os.path.join(REPO_ROOT, "books", "read", "*.json")))
    return [p for p in paths if substring.lower() in os.path.basename(p).lower()]


def make_quests(book, model=None):
    # Imported here: util/chatgpt reads the API key at import time, and the dry run
    # should work without one.
    from util.chatgpt import MODEL, llm_strict
    from util.history import History

    meta = book.get("meta", {})
    history = History()
    history.system(f"Summary of the book \"{meta.get('title', '')}\" by {meta.get('author', 'an unknown author')}.")
    for part in book.get("parts", []):
        history.system(f"{part.get('title', '')}\n\n{part_markdown(part)}")
    # The sizes have to mean something, and the first run on The Art of Perfumery showed
    # they need checking: its "small" quest needed cascarilla bark, and its "large" one
    # took three hours. An answer whose sizes do not rise is asked for once more.
    for _ in range(2):
        answer = llm_strict(history, model_name=model, base_model=BookQuests)
        if answer.small.minutes <= 30 < answer.medium.minutes < answer.large.minutes and answer.large.minutes >= 240:
            break
        print(f"  sizes did not rise ({answer.small.minutes}/{answer.medium.minutes}/{answer.large.minutes} min); asking again")
    quests = {
        size: {
            "title": q.title.replace("**", "").strip(),
            "action": q.action.replace("**", "").strip(),
            "doneWhen": q.done_when.replace("**", "").strip(),
            "minutes": q.minutes,
        }
        for size, q in (("small", answer.small), ("medium", answer.medium), ("large", answer.large))
    }
    return quests, model or MODEL


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--book", required=True, help="books whose file name contains this (case-insensitive)")
    parser.add_argument("--write", action="store_true", help="make and save the quests; without it nothing is spent")
    parser.add_argument("--force", action="store_true", help="make them again for a book that already has quests")
    parser.add_argument("--model", default=None, help="an OpenRouter model id; defaults to OPENROUTER_MODEL")
    args = parser.parse_args()

    for path in book_paths(args.book):
        key = os.path.splitext(os.path.basename(path))[0]
        if quest_store.load(key) and not args.force:
            print(f"  has quests  {key[:70]}")
            continue
        if not args.write:
            print(f"  would make  {key[:70]}")
            continue
        quests, model = make_quests(json_read_file(path), args.model)
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        saved = quest_store.save(key, quests, model=model, generated_at=stamp)
        print(f"  made        {key[:70]}  ({model})")
        for size in quest_store.SIZES:
            q = quests[size]
            print(f"    {size:<6} {q['minutes']:>4} min  {q['title']}")
            print(f"           {q['action']}")
            print(f"           Done when: {q['doneWhen']}")
        print(f"  saved to {os.path.relpath(saved, REPO_ROOT)}")


if __name__ == "__main__":
    main()
