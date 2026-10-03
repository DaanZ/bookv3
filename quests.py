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
    "not general self-improvement advice. It practises something the book teaches, never "
    "decoration or display: Homesteading for Health's first small quest was arranging spice "
    "jars on a shelf, where the book's point about jars is preserving food. It fits the time "
    "of year given above: the same run planted corn, beans and squash in October. Safe for an ordinary adult at home: say any precaution "
    "the materials need, and never anything to swallow, inject or set alight carelessly. "
    "Food is only ever preserved by a complete, safe method, such as refrigerator pickles, "
    "drying or freezing, with its storage stated; never raw food sealed in a jar and kept at "
    "room temperature, which Homesteading for Health's second run proposed and which spoils. "
    "Not medical advice: nothing about treating, diagnosing or preventing an illness, changing "
    "a diet or medication for health reasons, or eating raw or unpasteurised food, whatever the "
    "book argues."
)


# The finish screen shows three cards side by side, each with a title and one short
# line, and opens the chosen one into its plan: where in the book it comes from, what you
# need, a few steps, and when it is done. So the answer is in those pieces rather than
# one paragraph, which the first version was, and which made the page scroll.
# "Practises something the book teaches" could not be left to judgement: asked in words,
# both the generator and a judge accepted a worm bin and a cold frame for Homesteading for
# Health, whose summary names "building living soil" once and describes neither. So the
# methods are listed first, from the summary alone, and every quest must name one of them;
# code checks the name.
class Method(BaseModel):
    name: str = Field(..., description="A short name for the method, as in 'Three Sisters planting' or 'oats as a winter cover crop'.")
    part: int = Field(..., description="The number of the part that describes it.")
    detail: str = Field(..., description="What the summary itself says about how to do it, in one or two sentences.")


class BookMethods(BaseModel):
    methods: list[Method] = Field(..., description="Every practical method, technique, recipe or skill the summary describes in enough detail to try, going through every part: usually six or more in a practical book. Include small ones, such as one companion-planting pair or one way to save seed. Not a topic it only names, not history, not opinion, policy or health claims.")


class Quest(BaseModel):
    method: str = Field(..., description="The name of the method from the list above that this quest practises, copied exactly.")
    title: str = Field(..., description="A short name for the quest, at most six words, plain text without markdown.")
    short: str = Field(..., description="What the quest is, in one plain line of at most twelve words, for a small card.")
    needs: list[str] = Field(..., description="The things you need, each in a few words, such as 'a clean glass jar with a lid'. Empty only if nothing is needed.")
    steps: list[str] = Field(..., description="Three to five steps in order, each one short sentence that is something to do with your hands or your calendar, never 'understand', 'acknowledge', 'appreciate' or 'consider'. " + QUEST)
    done_when: str = Field(..., description="One sentence naming something you could check or show someone once it is done, as in 'A strained bottle of oil that smells of the peel, not of plain oil.' Never 'reflect on', 'think about' or 'understand', and never just the task restated in the past tense.")
    minutes: int = Field(..., description="A realistic estimate of the time it takes, in minutes.")


class BookQuests(BaseModel):
    small: Quest = Field(..., description="A small quest: 10 to 20 minutes, today, using only things most homes already have, such as kitchen spices, citrus fruit, herbs or flowers from outside, paper and a jar. No specialist ingredient.")
    medium: Quest = Field(..., description="A medium quest: one to three hours, an evening this week. It may need one simple purchase from a supermarket or a chemist.")
    large: Quest = Field(..., description="A large quest spread over several days, a weekend or a week of short sessions, at least four hours in all: a real project that combines at least two of the book's methods or ideas.")


# Written rules were not enough. Told the month, the safety rules and "practise, never
# decorate" in the descriptions, Gemini 2.5 Flash still proposed fresh herbs kept in oil
# in a cupboard for a week (a botulism risk) and Three Sisters planting in October, and
# GPT-4o proposed the same planting and a jar of herbs to look at. A second call judges
# each quest against those three rules alone, which is a narrower question than writing
# one, and a set with a failing quest is asked for again with the reasons attached.
class Verdict(BaseModel):
    size: str = Field(..., description="Which quest this is about: small, medium or large.")
    in_season: bool = Field(..., description="True if it can really be done in the month given above in a temperate northern climate; false if it sows, plants, harvests or forages anything out of season.")
    food_safe: bool = Field(..., description="True if any food it involves is handled safely; false for fresh herbs, garlic or raw produce kept in oil or sealed in a jar at room temperature, or anything preserved without refrigeration, freezing, drying or proper heat processing.")
    practises_book: bool = Field(..., description="True if doing it practises the method it names; false for decoration, display, organising or labelling things, or a step that only plans to research something.")
    problem: str = Field(..., description="If any of the three is false, one sentence naming what is wrong; otherwise empty.")


class QuestReview(BaseModel):
    verdicts: list[Verdict] = Field(..., description="Exactly one verdict for each quest: small, medium and large.")


def review(history, answer, model):
    from util.chatgpt import llm_strict
    from util.history import History

    judge = History()
    judge.logs = list(history.logs)
    for size, q in (("small", answer.small), ("medium", answer.medium), ("large", answer.large)):
        judge.system(f"{size} quest: {q.title}. Needs: {'; '.join(q.needs)}. Steps: {' '.join(q.steps)}")
    verdicts = llm_strict(judge, model_name=model, base_model=QuestReview).verdicts
    return [f"{v.size}: {v.problem or 'failed a check'}" for v in verdicts
            if not (v.in_season and v.food_safe and v.practises_book)]


def book_paths(substring):
    paths = sorted(glob.glob(os.path.join(REPO_ROOT, "books", "available", "*.json")) +
                   glob.glob(os.path.join(REPO_ROOT, "books", "read", "*.json")))
    return [p for p in paths if substring.lower() in os.path.basename(p).lower()]


class QuestsRejected(Exception):
    """No set passed the checks; nothing is saved."""


def make_quests(book, model=None, judge_model="openai/gpt-4o"):
    # Imported here: util/chatgpt reads the API key at import time, and the dry run
    # should work without one.
    from util.chatgpt import MODEL, llm_strict
    from util.history import History

    meta = book.get("meta", {})
    history = History()
    history.system(f"Summary of the book \"{meta.get('title', '')}\" by {meta.get('author', 'an unknown author')}.")
    # The season, so a garden book does not send someone out to sow corn in October. A
    # temperate northern climate is assumed: the reader this was built for is Dutch.
    history.system(f"Today is {datetime.now():%B %Y}, in a temperate northern climate. "
                   "Every quest must be doable at this time of year.")
    for number, part in enumerate(book.get("parts", []), start=1):
        history.system(f"Part {number}: {part.get('title', '')}\n\n{part_markdown(part)}")

    methods = llm_strict(history, model_name=judge_model, base_model=BookMethods).methods
    if not methods:
        raise QuestsRejected("the summary describes no method in enough detail to practise")
    names = {m.name.strip().lower(): m for m in methods}
    print(f"  {len(methods)} methods in the summary: " + "; ".join(f"{m.name} (part {m.part})" for m in methods))
    history.system("Methods this summary describes, the only ones a quest may practise:\n" + "\n".join(
        f"- {m.name} (part {m.part}): {m.detail}" for m in methods))
    # The sizes have to mean something, and the first run on The Art of Perfumery showed
    # they need checking: its "small" quest needed cascarilla bark, and its "large" one
    # took three hours. Then the judge (`review`) on season, food safety and practice.
    answer = None
    for attempt in range(1, 4):
        answer = llm_strict(history, model_name=model, base_model=BookQuests)
        three = (answer.small, answer.medium, answer.large)
        problems = []
        if not (answer.small.minutes <= 30 < answer.medium.minutes < answer.large.minutes and answer.large.minutes >= 240):
            problems.append(f"sizes must rise: small at most 30 minutes, large at least 240; got {[q.minutes for q in three]}")
        if not all(3 <= len(q.steps) <= 6 and len(q.short.split()) <= 16 for q in three):
            problems.append("each quest needs three to five steps and a short line of at most twelve words")
        unknown = [q.method for q in three if q.method.strip().lower() not in names]
        if unknown:
            problems.append(f"every quest must name a method from the list exactly; not on it: {unknown}")
        # Three ways to use a book, not one way at three sizes: the first run on
        # Homesteading for Health sowed oats in all three.
        if len(names) >= 3 and len({q.method.strip().lower() for q in three}) < 3:
            problems.append("the three quests must each practise a different method from the list")
        if not problems:
            problems = review(history, answer, judge_model)
        if not problems:
            break
        print(f"  attempt {attempt} rejected: " + " | ".join(problems))
        history.system("A previous answer was rejected. Replace the quests that failed and keep the rule each "
                       "one broke: " + " ".join(problems))
    else:
        raise QuestsRejected("; ".join(problems))

    def plain(text):
        return text.replace("**", "").strip()

    quests = {
        size: {
            "title": plain(q.title),
            "short": plain(q.short),
            # The source comes from the method list, not from the quest's own claim.
            "source": f"{names[q.method.strip().lower()].name}, part {names[q.method.strip().lower()].part}",
            "needs": [plain(n) for n in q.needs if plain(n)],
            "steps": [plain(s) for s in q.steps if plain(s)],
            "doneWhen": plain(q.done_when),
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
        try:
            quests, model = make_quests(json_read_file(path), args.model)
        except QuestsRejected as rejected:
            print(f"  not saved   {key[:70]}: no set passed the checks in three tries ({rejected})")
            continue
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        saved = quest_store.save(key, quests, model=model, generated_at=stamp)
        print(f"  made        {key[:70]}  ({model})")
        for size in quest_store.SIZES:
            q = quests[size]
            print(f"    {size:<6} {q['minutes']:>4} min  {q['title']}  -  {q['short']}")
            print(f"           from: {q['source']}")
            print(f"           needs: {'; '.join(q['needs']) or '(nothing)'}")
            for n, step in enumerate(q["steps"], start=1):
                print(f"           {n}. {step}")
            print(f"           done when: {q['doneWhen']}")
        print(f"  saved to {os.path.relpath(saved, REPO_ROOT)}")


if __name__ == "__main__":
    main()
