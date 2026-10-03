from pydantic import Field, BaseModel

from util.chatgpt import llm_strict
from util.history import History
from util.split import page_chunk_bounds
from util.parts import drop_unfinished_ending, last_sentence_finished, paragraphs_from_model, part_markdown
from util.summary_checks import MAX_SUMMARY_WORDS, attributes, clean_title, is_finished, needs_direct, word_count


# Define the number of chunks
def get_page_chunks(pages, num_chunks: int = 10):
    # The boundaries live in util/split.py so api/estimate.py can price a book without
    # importing this module, which needs an API key at import time.
    bounds = page_chunk_bounds(len(pages), num_chunks)
    return [pages[start:end] for start, end in bounds]


# The length is in the description because "two paragraphs" alone is not a length. Across
# 3,071 committed parts the median is 133 words and the 99th percentile 332, but a few
# came back at 1,300+ (The Art of Perfumery part 2, The Elephant in the Brain part 5): two
# "paragraphs" of fifteen sentences each. The reader holds a part to five pages and packs
# the excess onto each page, so one such part reads as five walls of text. The limits
# below sit around the 95th percentile, so ordinary summaries are not asked to change.
#
# DIRECT is the other half: 12% of committed parts opened by describing the text ("This
# text provides a detailed overview...", "In this section, ...") instead of saying what it
# says. Every word of that is a word the reader spends on nothing. The passive is named
# too, because a model told only to drop "This text" writes "Various perfumes are
# discussed" instead, which is the same report in other words.
#
# HEDGES is the limit on that rule, learned the hard way. Told only to "state everything
# as fact", the condense step turned One Nation Under Blackmail's "the suspicious
# circumstances surrounding Vince Foster's death and its link to..." into "Vince Foster's
# death is linked to...", and "authors like Norman and Grabbe suggest" into plain fact.
# Dropping "This text discusses" is the point; dropping "allegedly" from a claim about a
# real person is a different and much worse thing.
HEDGES = "Keep every hedge and attribution the material gives a claim: words like 'alleged', 'suspicious', 'reportedly', 'may', and who makes the claim ('Grabbe suggests', 'according to the author') stay whenever the claim is disputed, unproven or one person's view."
#
# LAYOUT is the same problem pointed elsewhere: "In CHAPTER FIVE, the author...", "(Figure
# 21)", "as illustrated in Fig. 27.2". The reader of a summary has no chapters, figures or
# pages to turn to, so each one is a reference to nothing. 99 committed parts had one.
LAYOUT = "Never refer to the book's layout, which the reader cannot see: no chapter numbers or chapter names, figures, tables, pages or sections ('In Chapter Five', 'see Figure 1.5', '(Fig. 3)'). Say what is there instead."
DIRECT = "Write every sentence as content from the material itself, as if teaching it, and begin with the first concrete point: no opening sentence that announces or lists what follows. Never report on the text as a document: no 'This text', 'This section', 'In this chapter', 'The text discusses', 'provides an overview', 'Topics covered include', and no reporting passives such as 'is discussed', 'are explored', 'are provided' or 'is detailed'. " + LAYOUT + " " + HEDGES


# The answer is structured: paragraphs of sentences, highlights as ** inside a sentence.
# It used to be one string that format_text turned into HTML, and the reader then had to
# guess where each sentence ended: every wrong guess (an abbreviation, a quote, a <br>, a
# heading) became a paragraph break in the middle of a sentence. Asked for sentences, the
# model draws the boundaries itself and nothing downstream has to guess.
SENTENCES = "The paragraph's sentences in order, one complete sentence per item, each ending in . ? or !. Important words are highlighted with markdown ** inside the sentence; a highlight never runs from one sentence into the next. No other markup: no headings, no italics, no HTML."


class SummaryParagraph(BaseModel):
    sentences: list[str] = Field(..., description=SENTENCES)


class DisabilityBookFirstChunk(BaseModel):
    summary_paragraphs: list[SummaryParagraph] = Field(..., description="First summarize the chunk without title into one short paragraph of at most 120 words, in short sentences, for people with ADHD / Dyslexia, highlighting important words using markdown **. " + DIRECT)
    summary_title: str = Field(..., description="Title that belongs to the summary, as plain text without markdown")


class DisabilityBookNextChunk(DisabilityBookFirstChunk):
    summary_paragraphs: list[SummaryParagraph] = Field(..., description="First summarize the chunk without title into two short paragraphs of at most 220 words in total, in short sentences, for people with ADHD / Dyslexia, highlighting important words using markdown **. " + DIRECT)


class CondensedChunk(BaseModel):
    summary_paragraphs: list[SummaryParagraph] = Field(..., description="Shorten this summary for people with ADHD / Dyslexia into two short paragraphs of at most 200 words in total, in short sentences. Keep only the most important points and keep their markdown ** highlights. Add nothing that is not already in the summary. " + DIRECT)


# The fix is surgical, never a rewrite. Asked to rewrite a whole summary "directly", the
# model loses content: Deep Work part 2 came back 81 words shorter, without the two
# abilities the part is about, leaving "These abilities" pointing at nothing. Asked
# only to delete an announcing sentence, it rephrases it instead ("Detailed instructions
# are provided" became "Detailed instructions exist"). So it returns just the offending
# sentences, each with a replacement, and `make_direct` swaps those whole sentences:
# every other sentence is untouched by construction.
class SentenceFix(BaseModel):
    original: str = Field(..., description="One sentence copied exactly, character for character and including its ** marks, from the summary, that reports on the text instead of stating its content ('This text explores...', 'The text argues that...', 'In this section, ...', 'The chapter emphasizes...', 'Topics covered include...', '... are discussed'), or that points at the book's layout, which the reader cannot see ('In CHAPTER FIVE, the author...', 'Chapter 3 explains...', '... as illustrated in Fig. 27.2.', '... growth (Figure 21).').")
    replacement: str = Field(..., description="That sentence rewritten to state its content directly, keeping every specific name, fact and ** highlight. 'The text argues that mastering these abilities is essential for success' becomes 'Mastering these abilities is essential for success'. " + HEDGES + " 'The text discusses the suspicious circumstances of his death' becomes 'The circumstances of his death are suspicious', never 'His death was murder'. A reference to a chapter, figure, table, page or section is taken out and the content kept: 'In CHAPTER FIVE, the author made errors on the way to an interview' becomes 'The author made errors on the way to an interview', and 'OKRs drive growth (Figure 21).' becomes 'OKRs drive growth.'. The replacement never names the text in another way ('The text is about...', 'This book covers...'): it says the content itself. When the sentence says the text argues, suggests or claims something, that is the author's view and stays attributed: 'The text argues that focusing on racism alone is not enough' becomes 'The author argues that focusing on racism alone is not enough', never the bare claim. Empty only when the sentence names nothing specific at all, such as 'This text provides a detailed overview of various topics.'")


class DirectFixes(BaseModel):
    fixes: list[SentenceFix] = Field(..., description="Every sentence of the summary that reports on the text rather than stating its content, or that refers to a chapter, figure, table, page or section, each with its direct replacement. Sentences that already state content are not listed. A sentence that says whose view something is ('The author believes...', 'He suggests that...', 'Ball challenges the notion that...', 'which he sees as...') is content, not a report on the text: it is not listed, because without the attribution an opinion would read as fact.")


def _as_text(paragraphs):
    # What a follow-up prompt is shown: the paragraphs as text, ** kept.
    return part_markdown({"paragraphs": paragraphs})


def _words(paragraphs):
    return word_count(_as_text(paragraphs))


def make_direct(paragraphs, model=None):
    """Replace the sentences that report on the text or point at its layout, and nothing else.

    A fix applies only to a whole stored sentence, matched exactly; anything else is
    skipped rather than guessed at. Only a sentence the checks themselves flag may change,
    and its replacement must pass them: told in words to leave attribution alone, the
    model still turned "He also suggests that perhaps..." into "Perhaps..." and "which he
    sees as" into "is", making Scott Adams' opinions read as fact; in code it cannot. The
    worst case is a sentence left as it was, never a summary damaged.
    """
    history = History()
    history.system(_as_text(paragraphs))
    response = llm_strict(history, model_name=model, base_model=DirectFixes)

    fixes = {}
    for fix in response.fixes:
        original, replacement = fix.original.strip(), fix.replacement.strip()
        if (
            not needs_direct(original)
            or needs_direct(replacement)
            # "The text argues that X" is framing and attribution at once. The library run
            # kept only X, 17 times: Propaganda Blitz's "suggesting oil interests" became
            # "The motivations are oil interests", a contested claim stated as fact. A
            # replacement that drops the attribution is refused; "The author argues" passes.
            or (attributes(original) and not attributes(replacement))
            or replacement.count("**") % 2
            or len(replacement) > len(original) + 20
            or (replacement and not is_finished(replacement))
        ):
            continue
        fixes[original] = replacement

    result = []
    for paragraph in paragraphs:
        sentences = []
        for sentence in paragraph["sentences"]:
            replacement = fixes.get(sentence.strip(), sentence)
            if replacement:
                sentences.append(replacement)
        if sentences or paragraph.get("heading"):
            result.append({**paragraph, "sentences": sentences})
    return result


def condense(paragraphs, model=None):
    """One more call that shortens overlong paragraphs, keeping their ** highlights.

    The answer has to look finished before it replaces anything. Two One Nation Under
    Blackmail parts came back cut off mid-sentence ("...with CIA officials being"), one of
    them at 65 words from 374, and were saved like that. So a result whose last sentence
    is unfinished, or that keeps under a quarter of the words, gets one more try, and
    after that the long version stands: too long is a nuisance, cut off is wrong.
    """
    for _ in range(2):
        history = History()
        history.system(_as_text(paragraphs))
        shorter = paragraphs_from_model(
            llm_strict(history, model_name=model, base_model=CondensedChunk).summary_paragraphs
        )
        if shorter and last_sentence_finished(shorter) and _words(shorter) >= _words(paragraphs) / 4:
            return shorter
    return paragraphs


def highlight_chunk(pages, first=True, model=None):
    history = History()
    for page in pages:
        history.system(page.page_content)

    chunk_model = DisabilityBookFirstChunk
    if not first:
        chunk_model = DisabilityBookNextChunk
    print(chunk_model.__name__)
    response = llm_strict(history, model_name=model, base_model=chunk_model)
    paragraphs = paragraphs_from_model(response.summary_paragraphs)
    if not last_sentence_finished(paragraphs):
        # Cut off mid-sentence. llm_strict only retries when parsing fails, and a cut-off
        # answer parses fine, so 14 parts were saved ending "he concludes that **passion
        # is". One more try, then the last complete sentence, never a dangling half.
        print("Summary was cut off mid-sentence; asking again.")
        response = llm_strict(history, model_name=model, base_model=chunk_model)
        paragraphs = paragraphs_from_model(response.summary_paragraphs)
    paragraphs, dropped = drop_unfinished_ending(paragraphs)
    if dropped:
        print(f"Still cut off; dropped the unfinished sentence: {dropped!r}")
    if _words(paragraphs) > MAX_SUMMARY_WORDS:
        print(f"Summary ran to {_words(paragraphs)} words; condensing.")
        paragraphs = condense(paragraphs, model=model)
    if needs_direct(_as_text(paragraphs)):
        print("Summary reports on the text or points at its layout; fixing those sentences.")
        paragraphs = make_direct(paragraphs, model=model)
    return {"title": clean_title(response.summary_title), "paragraphs": paragraphs}

