"""Make three quests for a finished book: one small, one medium, one large.

    python quests.py --book perfum            # list the books it would make quests for
    python quests.py --book perfum --write    # make them: one model call per book
    python quests.py --book perfum --write --force   # make them again; started ones are kept

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
import re
from types import SimpleNamespace
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from api import quests as quest_store
from util.files import json_read_file
from util.parts import part_markdown

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

# Writes the quests as well as listing the methods and judging them. Not OPENROUTER_MODEL:
# that is the summariser's default, Gemini Flash, which built quests on topics the summary
# only names. GPT-4o was the writer for every set that was kept.
QUEST_MODEL = "openai/gpt-4o"

# Words that say nothing about what a quest is, left out when comparing two titles.
STOP_WORDS = {"a", "an", "and", "the", "of", "to", "for", "your", "with", "in", "on", "my", "from", "at", "own"}


def title_words(title):
    return {w for w in re.findall(r"[a-z]+", title.lower()) if w not in STOP_WORDS}


def too_close(title, passed_titles):
    """The passed title this one repeats, or None. Half the words in common is a repeat:
    "Make Citrus Peel Oil" against "Extract Citrus Peel Oil" shares three of four."""
    mine = title_words(title)
    for other in passed_titles:
        theirs = title_words(other)
        if mine and theirs and len(mine & theirs) / len(mine | theirs) >= 0.5:
            return other
    return None


# What a kept quest with no estimate counts as when the sizes are checked.
TYPICAL_MINUTES = {"small": 15, "medium": 90, "large": 300}


# Steps that ask for thought instead of an act. The step description already forbids them,
# and The Invincible Company's quests still opened steps with "Think of" and "Consider".
THINKING = re.compile(r"^\s*(think|consider|reflect|understand|appreciate|acknowledge|imagine|explore)\b", re.I)


def thinking_steps(steps):
    """The steps that start with a verb of thinking rather than doing."""
    return [step for step in steps if THINKING.match(step)]


def method_key(name):
    """A method's name as compared: case and spacing aside, and without the "(part 3)" the
    model copies from the list it was shown, which failed every attempt of one reroll."""
    return re.sub(r"\s*\(part \d+\)\s*$", "", name.strip(), flags=re.I).lower()


# What each moment allows, in minutes, and what to call it in a message back to the model.
MOMENT_MINUTES = {"small": (1, 20), "medium": (45, 180), "large": (240, 5000)}
MOMENT_NAMES = {"small": "the next-break quest", "medium": "tonight's quest", "large": "the weekend quest"}


def quest_problems(size, quest, names, passed_titles):
    """Everything code can say is wrong with one quest, as sentences for the retry."""
    found = []
    low, high = MOMENT_MINUTES[size]
    if not low <= quest.minutes <= high:
        span = f"at least {low}" if size == "large" else f"{low} to {high}"
        found.append(f"{MOMENT_NAMES[size]} must take {span} minutes, not {quest.minutes}")
    if not 3 <= len(quest.steps) <= 6 or len(quest.short.split()) > 16:
        found.append("it needs three to five steps and a short line of at most twelve words")
    if method_key(quest.method) not in names:
        found.append(f"'{quest.method}' is not on the list; name a method or topic from it exactly")
    vague = thinking_steps(quest.steps)
    if vague:
        found.append("every step must be something to do, make, send or decide; rewrite "
                     + "; ".join(f"'{step}'" for step in vague))
    repeat = too_close(quest.title, passed_titles)
    if repeat:
        found.append(f"the reader passed on '{repeat}' already")
    return found


def stored_as_answer(quest, size):
    """A saved quest in the shape the checks read, for a size a reroll keeps."""
    return SimpleNamespace(
        method=quest["source"].rsplit(", part ", 1)[0],
        title=quest["title"], short=quest["short"], needs=quest["needs"], steps=quest["steps"],
        done_when=quest["doneWhen"], minutes=quest.get("minutes") or TYPICAL_MINUTES[size],
    )

QUEST = (
    "About this book's subject: it builds on one method or topic from the list above, and it "
    "may go beyond what the summary itself describes as long as it stays with that subject; "
    "never general self-improvement advice. It is something to practise or make, never "
    "decoration or display: Homesteading for Health's first small quest was arranging spice "
    "jars on a shelf, where the book's point about jars is preserving food. It fits the time "
    "of year given above: the same run planted corn, beans and squash in October. "
    "It happens where the book's subject is really practised: for a business, career, "
    "productivity or self-help book that is the reader's own work, job, side project or "
    "habits, never a household chore dressed in the book's words (The Invincible Company "
    "produced a risk audit of the reader's internet subscription). "
    "Safe for an ordinary adult: say any precaution "
    "the materials need, and never anything to swallow, inject or set alight carelessly. "
    "Food is only ever preserved by a complete, safe method, such as refrigerator pickles, "
    "drying or freezing, with its storage stated; never raw food sealed in a jar and kept at "
    "room temperature, which Homesteading for Health's second run proposed and which spoils. "
    "Never promise a benefit the book does not support, such as houseplants purifying the "
    "air of a room (the Homesteading for Health run with 'indoor plants' did). "
    "Not medical advice: nothing about treating, diagnosing or preventing an illness, changing "
    "a diet or medication for health reasons, or eating raw or unpasteurised food, whatever the "
    "book argues."
)


# The finish screen shows three cards side by side, each with a title and one short
# line, and opens the chosen one into its plan: where in the book it comes from, what you
# need, a few steps, and when it is done. So the answer is in those pieces rather than
# one paragraph, which the first version was, and which made the page scroll.
# What a quest is about is listed first, from the summary alone, and every quest must name
# one entry; code checks the name and that the three are different. The list started as
# methods only, because a worm bin and a cold frame were proposed for Homesteading for
# Health, whose summary names "building living soil" once and describes neither. Daan
# decided against that strictness: a quest should fit the book's subject, not re-enact a
# page, so the book's topics are on the list too and a quest may go past the summary.
class Method(BaseModel):
    name: str = Field(..., description="A short name for the method or topic, as in 'Three Sisters planting', 'oats as a winter cover crop' or 'building living soil'.")
    part: int = Field(..., description="The number of the part that describes it.")
    detail: str = Field(..., description="What the summary itself says about it, in one or two sentences.")


class BookMethods(BaseModel):
    methods: list[Method] = Field(..., description="Going through every part: every practical method, technique, recipe or skill the summary describes, and every topic of the book a reader could act on, even one the summary only names. Usually eight or more. Include small ones, such as one companion-planting pair or one way to save seed. Not history, not opinion, policy or health claims.")


class Quest(BaseModel):
    method: str = Field(..., description="The name of the method or topic from the list above that this quest builds on, copied exactly.")
    title: str = Field(..., description="A short name for the quest, at most six words, plain text without markdown.")
    short: str = Field(..., description="What the quest is, in one plain line of at most twelve words, for a small card.")
    needs: list[str] = Field(..., description="The things you need, each in a few words, such as 'a clean glass jar with a lid'. Empty only if nothing is needed.")
    steps: list[str] = Field(..., description="Three to five steps in order, each one short sentence that is something to do, make, send or decide, never 'understand', 'acknowledge', 'appreciate' or 'consider'. For tonight and the weekend, say when where it helps, as in 'After dinner:' or 'Saturday morning:'. " + QUEST)
    done_when: str = Field(..., description="One sentence naming something you could check or show someone by the end of its moment (the break, tonight, Sunday evening), as in 'A strained bottle of oil that smells of the peel, not of plain oil.' Never 'reflect on', 'think about' or 'understand', and never just the task restated in the past tense.")
    minutes: int = Field(..., description="A realistic estimate of the time it takes, in minutes.")


# The three are moments in the reader's week rather than sizes: a goal is concrete when it
# says when. The fields keep the names small, medium and large because starts, reflections
# and passed lists are stored under them.
class BookQuests(BaseModel):
    small: Quest = Field(..., description="For the reader's next break today: 5 to 15 minutes, started straight away, wherever they are, with only what is already to hand there: the kitchen and a jar for a craft or garden book, a notebook, a phone or their own work for a business or self-help book. Nothing to buy, nothing to wait for.")
    medium: Quest = Field(..., description="For tonight: one evening at home after the day's work, 45 minutes to three hours, with what is in the house or one simple purchase on the way home. Steps that need daylight or open shops do not belong here.")
    large: Quest = Field(..., description="For this weekend: Saturday and Sunday, at least four hours in all, in one or two sessions, and it may start with a shop visit on Saturday morning. A real project that combines at least two of the book's methods or topics, and ends in something done, not only a plan.")


# Written rules were not enough. Told the month, the safety rules and "practise, never
# decorate" in the descriptions, Gemini 2.5 Flash still proposed fresh herbs kept in oil
# in a cupboard for a week (a botulism risk) and Three Sisters planting in October, and
# GPT-4o proposed the same planting and a jar of herbs to look at. A second call judges
# each quest against those three rules alone, which is a narrower question than writing
# one, and a set with a failing quest is asked for again with the reasons attached.
class Verdict(BaseModel):
    size: str = Field(..., description="Which quest this is about: small, medium or large.")
    in_season: bool = Field(..., description="True if the season does not matter to it, or it can really be done in the month given above in a temperate northern climate; false if it sows, plants, harvests or forages anything out of season.")
    fits_moment: bool = Field(..., description="True if it fits its moment: small is the next break today (minutes, nothing to buy or wait for), medium is tonight (one evening at home, no daylight or open shops needed), large is this weekend and ends in something done, made or changed, not only a plan, list or sketch. False otherwise.")
    food_safe: bool = Field(..., description="True if it involves no food at all, or handles the food it involves safely; 'not applicable' is true; false for fresh herbs, garlic or raw produce kept in oil or sealed in a jar at room temperature, or anything preserved without refrigeration, freezing, drying or proper heat processing.")
    practises_book: bool = Field(..., description="True if doing it is real practice of the method or topic it names, even beyond what the summary describes, or follows the direction the reader asked for while connecting to that method or topic; false for decoration, display, organising or labelling things, a step that only plans to research something, or a business or work method applied to household chores.")
    problem: str = Field(..., description="If any of the three is false, one sentence naming what is wrong; otherwise empty.")


class QuestReview(BaseModel):
    verdicts: list[Verdict] = Field(..., description="Exactly one verdict for each quest: small, medium and large.")


def review(history, answer, model, sizes=("small", "medium", "large")):
    """Problems the judge finds in the given sizes. A kept quest was judged when it was made."""
    from util.chatgpt import llm_strict
    from util.history import History

    judge = History()
    judge.logs = list(history.logs)
    for size, q in (("small", answer.small), ("medium", answer.medium), ("large", answer.large)):
        judge.system(f"{size} quest: {q.title}. Needs: {'; '.join(q.needs)}. Steps: {' '.join(q.steps)}")
    verdicts = llm_strict(judge, model_name=model, base_model=QuestReview).verdicts
    return [(v.size, v.problem or "failed a check") for v in verdicts
            if v.size in sizes and not (v.in_season and v.fits_moment and v.food_safe and v.practises_book)]


def book_paths(substring):
    paths = sorted(glob.glob(os.path.join(REPO_ROOT, "books", "available", "*.json")) +
                   glob.glob(os.path.join(REPO_ROOT, "books", "read", "*.json")))
    return [p for p in paths if substring.lower() in os.path.basename(p).lower()]


class QuestsRejected(Exception):
    """No set passed the checks; nothing is saved."""


def make_quests(book, model=QUEST_MODEL, judge_model=QUEST_MODEL, keep=None, avoid=None, direction=None):
    """Three quests for a book: {size: quest}, and the model that wrote them.

    `keep` is {size: saved quest} for sizes a reroll must not touch, because a reader
    started or finished them; they come back unchanged and the others are built around
    them (different methods, sizes still rising). `avoid` is quests readers passed on,
    which no new quest may repeat — asked in words and then checked, because asked in
    words alone a model rewords its favourite instead of leaving it. `direction` is the
    reader's own steer ("indoor plants" for a homesteading book): followed even past what
    the book covers, as long as each quest still ties back to something the book says.
    """
    keep = keep or {}
    avoid = avoid or []
    # Imported here: util/chatgpt reads the API key at import time, and the dry run
    # should work without one.
    from util.chatgpt import MODEL, llm_strict
    from util.history import History

    meta = book.get("meta", {})
    history = History()
    history.system(f"Summary of the book \"{meta.get('title', '')}\" by {meta.get('author', 'an unknown author')}.")
    # The season, so a garden book does not send someone out to sow corn in October. A
    # temperate northern climate is assumed: the reader this was built for is Dutch.
    # The weekday too, since the quests are for the next break, tonight and this weekend.
    history.system(f"Today is {datetime.now():%A %d %B %Y}, in a temperate northern climate. "
                   "Every quest must be doable at this time of year.")
    for number, part in enumerate(book.get("parts", []), start=1):
        history.system(f"Part {number}: {part.get('title', '')}\n\n{part_markdown(part)}")

    methods = llm_strict(history, model_name=judge_model, base_model=BookMethods).methods
    if not methods:
        raise QuestsRejected("the summary names no method or topic to practise")
    names = {method_key(m.name): m for m in methods}
    print(f"  {len(methods)} methods and topics in the summary: " + "; ".join(f"{m.name} (part {m.part})" for m in methods))
    history.system("Methods and topics of this book. Every quest builds on one of them, and may go "
                   "beyond what the summary says about it:\n" + "\n".join(
        f"- {m.name} (part {m.part}): {m.detail}" for m in methods))
    if direction:
        history.system(f"The reader asked for quests in this direction: \"{direction}\". Follow it, "
                       "even where the book does not cover it, but tie every quest back to the book: "
                       "it names the method or topic from the list it relates to, and at least one "
                       "step uses what the book says about that method or topic. It is still practice: "
                       "growing, making, testing, repairing or caring for something, never only arranging or "
                       "displaying it. Choosing counts when it tests something first, such as measuring "
                       "the light at a window before picking a plant that suits it.")
    if keep:
        history.system("The reader already started these, and they stay exactly as they are; "
                       "your answer for these sizes is ignored, and the other quests must build on "
                       "different methods or topics:\n" + "\n".join(
                           f"- {size}: {q['title']} ({q['source']})" for size, q in keep.items()))
    if avoid:
        history.system("The reader passed on these quests. Do not propose any of them again, nor "
                       "the same activity under another name; find a different way to use the book:\n"
                       + "\n".join(f"- {q['title']}: {q['short']}" for q in avoid))
    fresh_sizes = tuple(size for size in ("small", "medium", "large") if size not in keep)
    passed_titles = [q["title"] for q in avoid]
    # The sizes have to mean something, and the first run on The Art of Perfumery showed
    # they need checking: its "small" quest needed cascarilla bark, and its "large" one
    # took three hours. Then the judge (`review`) on season, food safety and practice.
    answer = None
    # Quests the judge passed on an earlier attempt. They stay for the next one, so a retry
    # rewrites only what failed: on Homesteading for Health with "indoor plants", medium
    # and large passed three times over while each retry rewrote all three and the small
    # one kept failing, so nothing was saved.
    locked = {}
    for attempt in range(1, 4):
        answer = llm_strict(history, model_name=model, base_model=BookQuests)
        for size, quest in keep.items():
            setattr(answer, size, stored_as_answer(quest, size))
        for size, quest in locked.items():
            setattr(answer, size, quest)
        three = (answer.small, answer.medium, answer.large)
        judged = tuple(size for size in fresh_sizes if size not in locked)
        failing = {size: quest_problems(size, getattr(answer, size), names, passed_titles) for size in judged}
        failing = {size: found for size, found in failing.items() if found}
        # Three ways to use a book, not one way at three sizes: the first run on
        # Homesteading for Health sowed oats in all three. A direction waives it.
        spread = []
        if not direction and len(names) >= 3 and len({method_key(q.method) for q in three}) < 3:
            spread.append("the three quests must each build on a different method or topic from the list")
        # The judge only sees quests that passed the code, so its calls are not spent on them.
        clean = tuple(size for size in judged if size not in failing)
        if clean:
            for size, problem in review(history, answer, judge_model, clean):
                failing.setdefault(size, []).append(problem)
        if not failing and not spread:
            break
        problems = [f"{size}: {problem}" for size, found in failing.items() for problem in found] + spread
        titles = ", ".join(f"{size} '{getattr(answer, size).title}'" for size in judged)
        print(f"  attempt {attempt} rejected ({titles}): " + " | ".join(problems))
        # Every quest that passed stays, so a retry rewrites only what failed: rewriting all
        # three let a new "Consider…" step turn up somewhere else on every attempt.
        if not spread:
            locked.update({size: getattr(answer, size) for size in judged if size not in failing})
        history.system("Passed and staying exactly as they are, so your answer for them is ignored: "
                       + (", ".join(f"the {size} quest '{getattr(answer, size).title}'" for size in locked) or "none")
                       + ". Write the others again, keeping the rule each one broke: " + " ".join(problems))
    else:
        raise QuestsRejected("; ".join(problems))

    def plain(text):
        return text.replace("**", "").strip()

    def source(q):
        method = names.get(method_key(q.method))
        return f"{method.name}, part {method.part}" if method else q.method

    quests = {
        size: keep[size] if size in keep else {
            "title": plain(q.title),
            "short": plain(q.short),
            # The source comes from the method list, not from the quest's own claim.
            "source": source(q),
            "needs": [plain(n) for n in q.needs if plain(n)],
            "steps": [plain(s) for s in q.steps if plain(s)],
            "doneWhen": plain(q.done_when),
            "minutes": q.minutes,
            **({"direction": direction} if direction else {}),
        }
        for size, q in (("small", answer.small), ("medium", answer.medium), ("large", answer.large))
    }
    return quests, model or MODEL


def reroll(key, book, by, model=QUEST_MODEL, direction=None):
    """Make a book's quests, or make them again, and save them.

    The one way a set is written, for the command line and the finish screen alike. Sizes
    any reader started or finished are kept; the rest are replaced and recorded as passed
    on, and no new quest may repeat anything passed on before. Who started what is read
    again just before saving, since the model calls take a minute and someone may have
    started a quest in the meantime. Raises QuestsRejected when nothing could be saved.
    """
    old = quest_store.load(key)
    claimed = quest_store.claimed_sizes(key) if old else set()
    if len(claimed) == len(quest_store.SIZES):
        raise QuestsRejected("every quest here is started or done, so there is nothing to replace")
    keep = {size: old[size] for size in claimed}
    avoid = quest_store.passed(key) + [old[size] for size in quest_store.SIZES if old and size not in claimed]
    fresh, model = make_quests(book, model, keep=keep, avoid=avoid, direction=direction)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    claimed_now = quest_store.claimed_sizes(key) if old else set()
    quests, gone = quest_store.merge_reroll(old, fresh, claimed_now, by, stamp)
    path = quest_store.save(key, quests, model=model, generated_at=stamp,
                            passed_on=quest_store.passed(key) + gone)
    return quests, model, path


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--book", required=True, help="books whose file name contains this (case-insensitive)")
    parser.add_argument("--write", action="store_true", help="make and save the quests; without it nothing is spent")
    parser.add_argument("--force", action="store_true", help="make them again for a book that already has quests")
    parser.add_argument("--model", default=QUEST_MODEL, help=f"an OpenRouter model id; defaults to {QUEST_MODEL}")
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
            quests, model, saved = reroll(key, json_read_file(path), "cli", args.model)
        except QuestsRejected as rejected:
            print(f"  not saved   {key[:70]}: {rejected}")
            continue
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
