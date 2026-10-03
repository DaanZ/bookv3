"""Bring parts already on the shelf up to what the pipeline now produces.

`chunks.highlight_chunk` checks every new summary: one cut off mid-sentence is asked for
again or trimmed to its last sentence, an overlong one is condensed, one that describes
the text ("This text explores...", "In this section, ...") or points at its layout
("In CHAPTER FIVE", "(Figure 21)") has those sentences rewritten to say it directly, and markdown is stripped from the title. This applies the same checks to books
summarised before that. Condensing and rewriting cost one model call each; trimming a
cut-off part and cleaning a title cost nothing.

    python tidy_parts.py                        # list what would change, spend nothing
    python tidy_parts.py --write                # fix and save everything listed
    python tidy_parts.py --write --book perfum  # only books whose file name contains this
    python tidy_parts.py --write --only cutoff  # one kind only: cutoff, long or openers

Every file is copied to `data/backups/tidy-<time>/` before it is written, and that copy is
the way back. Do not count on git for it: a book ingested since the last commit is not in
git at all, and The Art of Perfumery was rewritten in exactly that state.
"""
import argparse
import glob
import os
import re
import shutil
from datetime import datetime

from util.files import json_read_file, json_write_file
from util.summary_checks import (
    MAX_SUMMARY_WORDS,
    clean_title,
    is_finished,
    needs_direct,
    trim_to_last_sentence,
    word_count,
)

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


# Only the highlights change form, <b> to ** and back; every other tag (<br>, <h3>, <em>)
# stays as it is. A full HTML-to-markdown round trip cannot be exact: it dropped 267
# parts' headings, glued paragraphs broken with <br><br>, and read `<b[^>]*>` as matching
# <br>. This one is checked to give back the stored body byte for byte, and a part where
# it would not (a literal ** in the text, a highlight with another style) is left alone.
HIGHLIGHT = "<b style='color: forestgreen;'>"


def to_markdown(body):
    return re.sub(r"<b style='color: forestgreen;'>(.*?)</b>", r"**\1**", body, flags=re.S)


def from_markdown(text):
    return re.sub(r"\*\*(.*?)\*\*", HIGHLIGHT + r"\1</b>", text, flags=re.S)


def round_trips(body):
    return "**" not in body and from_markdown(to_markdown(body)) == body


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="fix and save; without it nothing is spent or changed")
    parser.add_argument("--book", default="", help="only books whose file name contains this (case-insensitive)")
    parser.add_argument("--only", choices=["cutoff", "long", "openers"], help="fix one kind of problem only (openers covers layout references too)")
    args = parser.parse_args()
    do_cutoff = args.only in (None, "cutoff")
    do_long = args.only in (None, "long")
    do_openers = args.only in (None, "openers")

    if args.write:
        # Imported only here: chunks pulls in util/chatgpt, which needs the API key, and
        # the dry run should not.
        from chunks import condense, format_text, make_direct

    backup_dir = os.path.join(REPO_ROOT, "data", "backups", "tidy-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    paths = sorted(glob.glob(os.path.join(REPO_ROOT, "books", "*", "*.json")))
    paths = [p for p in paths if args.book.lower() in os.path.basename(p).lower()]

    counts = {"cutoff": 0, "long": 0, "openers": 0, "titles": 0, "skipped": 0}
    for path in paths:
        book = json_read_file(path)
        if not book:
            continue
        name = os.path.basename(path)[:60]
        changed = False
        for index, part in enumerate(book.get("parts", [])):
            where = f"{name} part {index + 1}"

            title = clean_title(part.get("title", ""))
            if title != part.get("title", ""):
                counts["titles"] += 1
                print(f"  title    {where}: {title[:70]}")
                part["title"] = title
                changed = True

            body = part.get("body", "")
            if do_cutoff and not is_finished(body):
                # Free and done first, so the checks below see a body that ends properly.
                # The source text is not here, so the unfinished tail is dropped, not completed.
                trimmed, dropped = trim_to_last_sentence(body)
                if trimmed != body:
                    counts["cutoff"] += 1
                    print(f"  cutoff   {where}: drops \"{dropped[:70]}\"")
                    part["body"] = body = trimmed
                    changed = True

            before = word_count(body)
            is_long = do_long and before > MAX_SUMMARY_WORDS
            is_opener = do_openers and needs_direct(body)
            if not (is_long or is_opener):
                continue
            if not round_trips(body):
                counts["skipped"] += 1
                print(f"  skipped  {where}: its highlights cannot be converted back exactly")
                continue
            if is_long:
                counts["long"] += 1
            if is_opener:
                counts["openers"] += 1
            kind = "long" if is_long else "opener"
            if not args.write:
                print(f"  {kind:<8} {where}: {before} words, \"{re.sub(r'<[^>]+>', '', body)[:50]}...\"")
                continue

            # Condensing already applies the same "say it directly" rule, so a part that is
            # both long and an opener needs one call, not two. A condense is a new text and
            # goes through the pipeline's own formatting; a direct fix only swapped
            # sentences, so it goes back exactly the way it came.
            if is_long:
                markdown = to_markdown(body)
                shorter = condense(markdown)
                # condense hands back its input when no attempt looked finished.
                part["body"] = body if shorter == markdown else format_text(shorter)
            else:
                part["body"] = from_markdown(make_direct(to_markdown(body)))
            if part["body"] == body:
                print(f"  {kind:<8} {where}: unchanged, no fix passed the checks")
                continue
            after = re.sub(r"<[^>]+>", "", part["body"])
            print(f"  {kind:<8} {where}: {before} -> {word_count(part['body'])} words, \"{after[:50]}...\"")
            changed = True

        if changed and args.write:
            os.makedirs(backup_dir, exist_ok=True)
            shutil.copy2(path, os.path.join(backup_dir, os.path.basename(path)))
            json_write_file(path, book)

    verb = "Changed" if args.write else "Would change"
    print(f"{verb}: {counts['cutoff']} cut-off part(s), {counts['long']} overlong part(s), "
          f"{counts['openers']} opener(s), {counts['titles']} title(s); "
          f"{counts['skipped']} left alone because they cannot be converted back exactly.")
    if not args.write and any(counts.values()):
        print("Run again with --write to apply.")
    if args.write and os.path.isdir(backup_dir):
        print(f"Originals saved in {backup_dir}")


if __name__ == "__main__":
    main()
