"""Checks on a finished summary, shared by the pipeline and `tidy_parts.py`.

Kept free of `util/chatgpt` so the repair script's dry run works without an API key.
"""
import re

# Above this a summary is condensed rather than trusted. Across 3,071 committed parts the
# median is 133 words and the 99th percentile 332, so this catches the runaways (1,300+
# words in The Art of Perfumery part 2) and leaves ordinary summaries alone.
MAX_SUMMARY_WORDS = 350

# A summary that describes the text instead of saying what it says. 370 of 3,071
# committed parts (12%) opened with "This text explores...", "In this section, ..." and
# the like, and more slip it in later ("The chapter emphasizes that..."). Told not to,
# a model dodges into the passive ("Various perfumes are discussed, including..."), so
# that is caught too, but only in the first sentence: further in, "requirements are
# detailed using use cases" is content, not a report about a text.
#
# The author is left alone on purpose: "The author argues" is often the point, when the
# part is an opinion or a story about them.
_TEXT = r"(text|section|chapter|passage|excerpt|document)"
_DESCRIBES_TEXT = re.compile(
    rf"^(this|the|in this)\s+{_TEXT}\b"
    rf"|\b(this|the)\s+{_TEXT}\s+(also\s+)?(discusses|explores|describes|covers|highlights|details|provides|delves|examines|outlines|focuses|offers|presents|emphasizes|explains|introduces|concludes|begins)\b"
    rf"|\bin this\s+{_TEXT}\b"
    r"|\btopics\s+(covered|discussed|include)\b",
    re.IGNORECASE,
)
_REPORTING_PASSIVE = re.compile(
    r"\b(is|are)\s+(also\s+)?(discussed|explored|covered|provided|presented|outlined|examined|addressed|introduced)\b",
    re.IGNORECASE,
)


# A summary that stops mid-sentence: the model's answer was cut off. 14 committed parts
# ended like that, How to Fail at Almost Everything part 2 on "he concludes that
# **passion is" with its highlight left open, which the reader then printed as "**".
_SENTENCE_END = re.compile(r"[.!?…](?:[\"'”’)\]]|</b>|\*\*)*(?=\s|<br|$)")


def is_finished(text):
    # Every *, not just **: three parts end "...financial losses.*", a complete sentence
    # with a leftover italic mark, and are not cut off.
    plain = re.sub(r"<[^>]+>|\*+", "", text).strip()
    return not plain or bool(re.search(r"[.!?…][\"'”’)\]]*$", plain))


def trim_to_last_sentence(text):
    """(trimmed, dropped): `text` cut back to its last complete sentence.

    Works on stored HTML or on markdown. A highlight left open by the cut is closed, and a
    lone ** is removed. Returns the text unchanged, with nothing dropped, when there is no
    complete sentence to fall back to.
    """
    ends = list(_SENTENCE_END.finditer(text))
    if not ends:
        return text, ""
    cut = ends[-1].end()
    trimmed, dropped = text[:cut].rstrip(), text[cut:].strip()
    if trimmed.count("<b") > trimmed.count("</b>"):
        trimmed += "</b>"
    if trimmed.count("**") % 2:
        head, _, tail = trimmed.rpartition("**")
        trimmed = head + tail
    return trimmed, re.sub(r"<[^>]+>|\*\*", "", dropped).strip()


# A pointer at the book's layout, which a reader of the summary cannot follow: "In CHAPTER
# FIVE, the author...", "(Figure 21)", "as illustrated in Fig. 27.2", "see page 45". 99
# committed parts had one. A number is required, so "figures like Henry Ford" and "turned
# the tables on GE" are not caught; only "previous/next chapter" and the like go without.
_NUMBER = (r"(?:\d+(?:\.\d+)*[a-z]?|[IVXLC]+|one|two|three|four|five|six|seven|eight|nine|ten|"
           r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)")
_LAYOUT = re.compile(
    rf"\b(?:fig(?:ure)?s?\.?|tables?|charts?|diagrams?|exhibits?|appendix|plates?)\s+{_NUMBER}\b"
    r"|\b(?:pages?|pp?\.)\s+\d+"
    rf"|\bchapters?\s+{_NUMBER}\b"
    r"|\bsections?\s+\d+(?:\.\d+)*\b"
    r"|\b(?:previous|next|following|preceding|earlier|later|last|first|final|opening|subsequent"
    r"|initial|introductory|remaining|closing|concluding)\s+chapters?\b",
    re.IGNORECASE,
)


def points_at_layout(text):
    return bool(_LAYOUT.search(re.sub(r"<[^>]+>|\*\*", "", text)))


def needs_direct(text):
    """Reports on the text, or points at its layout: both are fixed by `make_direct`."""
    return describes_the_text(text) or points_at_layout(text)


def word_count(text):
    return len(re.sub(r"<[^>]+>", " ", text).split())


def describes_the_text(text):
    plain = re.sub(r"<[^>]+>|\*\*", "", text).strip()
    first_sentence = re.split(r"(?<=[.?!])\s", plain, maxsplit=1)[0]
    return bool(_DESCRIBES_TEXT.search(plain) or _REPORTING_PASSIVE.search(first_sentence))


def clean_title(title):
    # Models sometimes wrap the title in ** or start it with a heading #, which the reader
    # then shows literally. Only those go: "Discipline #3 and #4" keeps its #.
    return re.sub(r"^#+\s+", "", title.replace("**", "")).strip()
