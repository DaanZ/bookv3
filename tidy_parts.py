"""Bring parts already on the shelf up to what the pipeline now produces.

`chunks.highlight_chunk` checks every new summary: a last sentence cut off mid-way is
asked for again and otherwise dropped, an overlong summary is condensed, sentences that
report on the text ("This text explores...") or point at its layout ("In CHAPTER FIVE",
"(Figure 21)") are rewritten one by one, and markdown is stripped from the title. This
applies the same checks to books summarised before that. Condensing and rewriting cost one
model call each; dropping a cut-off sentence and cleaning a title cost nothing.

    python tidy_parts.py                        # list what would change, spend nothing
    python tidy_parts.py --write                # fix and save everything listed
    python tidy_parts.py --write --book perfum  # only books whose file name contains this
    python tidy_parts.py --write --only cutoff  # one kind only: cutoff, long or openers

Works on the structured format (paragraphs of sentences). A part still stored as an HTML
`body` is reported and left alone: run `node web/tools/migrate-structured.mjs --write`
first. Since the sentences are stored, every fix replaces or drops whole sentences, and
no conversion back to HTML can go wrong.

Every file is copied to `data/backups/tidy-<time>/` before it is written, and that copy is
the way back. Do not count on git for it: a book ingested since the last commit is not in
git at all, and The Art of Perfumery was rewritten in exactly that state.
"""
import argparse
import glob
import os
import shutil
from datetime import datetime

from util.files import json_read_file, json_write_file
from util.parts import drop_unfinished_ending, part_markdown
from util.summary_checks import MAX_SUMMARY_WORDS, clean_title, needs_direct, word_count

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="fix and save; without it nothing is spent or changed")
    parser.add_argument("--book", default="", help="only books whose file name contains this (case-insensitive)")
    parser.add_argument("--only", choices=["cutoff", "long", "openers"],
                        help="fix one kind of problem only (openers covers layout references too)")
    args = parser.parse_args()
    do = {kind: args.only in (None, kind) for kind in ("cutoff", "long", "openers")}

    if args.write:
        # Imported only here: chunks pulls in util/chatgpt, which needs the API key, and
        # the dry run should not.
        from chunks import condense, make_direct

    backup_dir = os.path.join(REPO_ROOT, "data", "backups", "tidy-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    paths = sorted(glob.glob(os.path.join(REPO_ROOT, "books", "*", "*.json")))
    paths = [p for p in paths if args.book.lower() in os.path.basename(p).lower()]

    counts = {"cutoff": 0, "long": 0, "openers": 0, "titles": 0, "unmigrated": 0}
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

            if not isinstance(part.get("paragraphs"), list):
                counts["unmigrated"] += 1
                continue
            paragraphs = part["paragraphs"]

            if do["cutoff"]:
                paragraphs, dropped = drop_unfinished_ending(paragraphs)
                if dropped:
                    counts["cutoff"] += 1
                    print(f"  cutoff   {where}: drops \"{dropped.replace('**', '')[:70]}\"")
                    part["paragraphs"] = paragraphs
                    changed = True

            text = part_markdown(part)
            before = word_count(text)
            is_long = do["long"] and before > MAX_SUMMARY_WORDS
            is_opener = do["openers"] and needs_direct(text)
            if not (is_long or is_opener):
                continue
            counts["long" if is_long else "openers"] += 1
            kind = "long" if is_long else "opener"
            if not args.write:
                print(f"  {kind:<8} {where}: {before} words, \"{text.replace('**', '')[:50]}...\"")
                continue

            # Condensing already applies the same "say it directly" rule, so a part that is
            # both long and an opener needs one call, not two.
            fixed = condense(paragraphs) if is_long else make_direct(paragraphs)
            if fixed == paragraphs:
                print(f"  {kind:<8} {where}: unchanged, no fix passed the checks")
                continue
            part["paragraphs"] = fixed
            after = part_markdown(part)
            print(f"  {kind:<8} {where}: {before} -> {word_count(after)} words, \"{after.replace('**', '')[:50]}...\"")
            changed = True

        if changed and args.write:
            os.makedirs(backup_dir, exist_ok=True)
            shutil.copy2(path, os.path.join(backup_dir, os.path.basename(path)))
            json_write_file(path, book)

    verb = "Changed" if args.write else "Would change"
    print(f"{verb}: {counts['cutoff']} cut-off part(s), {counts['long']} overlong part(s), "
          f"{counts['openers']} opener(s), {counts['titles']} title(s).")
    if counts["unmigrated"]:
        print(f"{counts['unmigrated']} part(s) are still HTML and were skipped: "
              "run `node web/tools/migrate-structured.mjs --write` first.")
    if not args.write and any(counts[k] for k in ("cutoff", "long", "openers", "titles")):
        print("Run again with --write to apply.")
    if args.write and os.path.isdir(backup_dir):
        print(f"Originals saved in {backup_dir}")


if __name__ == "__main__":
    main()
