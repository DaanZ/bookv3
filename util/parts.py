"""A part of a summary, read the same way everywhere.

A part is stored as paragraphs of sentences, with highlights marked `**` inside a
sentence and nothing else:

    {"title": "Past the fun part",
     "paragraphs": [{"sentences": ["Grit beats talent.", "**Practice** is deliberate."]},
                    {"heading": "Lessons from Experience", "sentences": ["..."]}]}

It used to be one HTML string, `body`, from which the reader had to guess where every
sentence ended; each wrong guess put a paragraph break in the middle of a sentence. Books
from before the change are converted by `web/tools/migrate-structured.mjs`, which uses
the reader's own splitter, so they read exactly as they did. A part that still has only
a `body` (an old file, or one written by something that predates this) is read through
`legacy_paragraphs`, which is good enough for counting words and for prompts, not for
display: the reader has its own copy of the full rules.
"""
import re

from util.summary_checks import is_finished


def part_paragraphs(part):
    """[{"heading"?: str, "sentences": [str]}], from either format."""
    paragraphs = part.get("paragraphs")
    if isinstance(paragraphs, list):
        return paragraphs
    return legacy_paragraphs(part.get("body", ""))


def legacy_paragraphs(body):
    text = re.sub(r"<br\s*/?>", "\n\n", body or "", flags=re.I)
    text = re.sub(r"<h3[^>]*>(.*?)</h3\s*>", r"\n\n\1\n\n", text, flags=re.I | re.S)
    text = re.sub(r"<b(?:\s[^>]*)?>(.*?)</b>", r"**\1**", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    return [
        {"sentences": [s for s in re.split(r"(?<=[.?!])\s+", block.strip()) if s]}
        for block in re.split(r"\n\s*\n", text)
        if block.strip()
    ]


def all_sentences(part):
    return [s for p in part_paragraphs(part) for s in p.get("sentences", [])]


def part_markdown(part):
    """Paragraphs as text, sentences joined by spaces, ** kept: what a prompt is given."""
    blocks = []
    for paragraph in part_paragraphs(part):
        if paragraph.get("heading"):
            blocks.append(paragraph["heading"])
        if paragraph.get("sentences"):
            blocks.append(" ".join(paragraph["sentences"]))
    return "\n\n".join(blocks)


def part_text(part):
    """Plain text with no marks: for word counts, search and anything that is not display."""
    return part_markdown(part).replace("**", "")


def has_highlights(part):
    return any("**" in s for s in all_sentences(part))


def paragraphs_from_model(paragraphs):
    """The model's paragraphs (objects with `.sentences`) as stored dicts, blanks dropped."""
    stored = []
    for paragraph in paragraphs:
        sentences = [s.strip() for s in paragraph.sentences if s and s.strip()]
        if sentences:
            stored.append({"sentences": sentences})
    return stored


def last_sentence_finished(paragraphs):
    sentences = [s for p in paragraphs for s in p["sentences"]]
    return not sentences or is_finished(sentences[-1])


def drop_unfinished_ending(paragraphs):
    """(paragraphs, dropped): without a last sentence that was cut off, if there is one."""
    if last_sentence_finished(paragraphs):
        return paragraphs, ""
    paragraphs = [dict(p, sentences=list(p["sentences"])) for p in paragraphs]
    dropped = paragraphs[-1]["sentences"].pop()
    if not paragraphs[-1]["sentences"] and not paragraphs[-1].get("heading"):
        paragraphs.pop()
    return paragraphs, dropped
