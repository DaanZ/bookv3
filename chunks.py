import re

from pydantic import Field, BaseModel

from util.chatgpt import llm_strict
from util.history import History
from util.split import page_chunk_bounds
from util.summary_checks import MAX_SUMMARY_WORDS, clean_title, describes_the_text, word_count


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
DIRECT = "Write every sentence as content from the material itself, as if teaching it, and begin with the first concrete point: no opening sentence that announces or lists what follows. Never report on the text as a document: no 'This text', 'This section', 'In this chapter', 'The text discusses', 'provides an overview', 'Topics covered include', and no reporting passives such as 'is discussed', 'are explored', 'are provided' or 'is detailed'. " + HEDGES


class DisabilityBookFirstChunk(BaseModel):
    summary_chunk: str = Field(..., description="First summarize the chunk without title into one short paragraph of at most 120 words, in short sentences, for people with ADHD / Dyslexia, highlighting important words using markdown **. " + DIRECT)
    summary_title: str = Field(..., description="Title that belongs to the summary, as plain text without markdown")


class DisabilityBookNextChunk(DisabilityBookFirstChunk):
    summary_chunk: str = Field(..., description="First summarize the chunk without title into two short paragraphs of at most 220 words in total, in short sentences, for people with ADHD / Dyslexia, highlighting important words using markdown **. " + DIRECT)


class CondensedChunk(BaseModel):
    summary_chunk: str = Field(..., description="Shorten this summary for people with ADHD / Dyslexia into two short paragraphs of at most 200 words in total, in short sentences. Keep only the most important points and keep their markdown ** highlights. Add nothing that is not already in the summary. " + DIRECT)


# The fix is surgical, never a rewrite. Asked to rewrite a whole summary "directly", the
# model loses content: Deep Work part 2 came back 81 words shorter, without the two
# abilities the part is about, leaving "These abilities" pointing at nothing. Asked
# only to delete an announcing sentence, it rephrases it instead ("Detailed instructions
# are provided" became "Detailed instructions exist"). So it returns just the offending
# sentences, each with a replacement, and `make_direct` swaps those exact strings: every
# other word of the summary is untouched by construction.
class SentenceFix(BaseModel):
    original: str = Field(..., description="One sentence copied exactly, character for character and including its ** marks, from the summary, that reports on the text instead of stating its content: 'This text explores...', 'The text argues that...', 'In this section, ...', 'The chapter emphasizes...', 'Topics covered include...', '... are discussed'.")
    replacement: str = Field(..., description="That sentence rewritten to state its content directly, keeping every specific name, fact and ** highlight. 'The text argues that mastering these abilities is essential for success' becomes 'Mastering these abilities is essential for success'. " + HEDGES + " 'The text discusses the suspicious circumstances of his death' becomes 'The circumstances of his death are suspicious', never 'His death was murder'. Empty only when the sentence names nothing specific at all, such as 'This text provides a detailed overview of various topics.'")


class DirectFixes(BaseModel):
    fixes: list[SentenceFix] = Field(..., description="Every sentence of the summary that reports on the text rather than stating its content, each with its direct replacement. Sentences that already state content are not listed.")


def _rewrite(summary, base_model, model=None):
    # Same pattern as `highlight_chunk`: the material goes in as a system message and the
    # instruction lives in the schema's field description.
    history = History()
    history.system(summary)
    return llm_strict(history, model_name=model, base_model=base_model).summary_chunk


def make_direct(summary, model=None):
    """Replace the sentences that report on the text, and nothing else.

    Every fix is checked before it is applied, and the result after: the model's answers
    vary run to run, and one run of Deep Work part 11 came back with a fix that spanned a
    paragraph break and shifted every ** after it by one. So a fix is skipped unless it is
    one line, found verbatim, keeps its ** in pairs and does not grow; and if the result
    has lost a paragraph or unbalanced a highlight anyway, the summary is returned as it
    came in. The worst case is a sentence left as it was, never a summary damaged.
    """
    history = History()
    history.system(summary)
    response = llm_strict(history, model_name=model, base_model=DirectFixes)

    result = summary
    for fix in response.fixes:
        original = fix.original.strip()
        replacement = fix.replacement.strip()
        if (
            not original
            or original not in result
            or "\n" in original
            or "\n" in replacement
            or original.count("**") % 2
            or replacement.count("**") % 2
            or len(replacement) > len(original) + 20
        ):
            continue
        if replacement:
            result = result.replace(original, replacement, 1)
        else:
            # A dropped sentence takes one neighbouring space with it, not a paragraph break.
            result = re.sub(r"[ \t]*" + re.escape(original) + r"[ \t]*", " ", result, count=1)
    result = re.sub(r"[ \t]+\n", "\n", re.sub(r"\n[ \t]+", "\n", result)).strip()

    tags = lambda text: sorted(re.findall(r"<[^>]+>", text))
    if (
        result.count("\n\n") != summary.strip().count("\n\n")
        or result.count("**") % 2
        or tags(result) != tags(summary)
    ):
        return summary
    return result


_FINISHED = re.compile(r"[.!?…][\"'”’)\]*]*\s*$")


def condense(summary, model=None):
    """One more call that shortens an overlong summary, keeping its ** highlights.

    The answer has to look finished before it replaces anything. Two One Nation Under
    Blackmail parts came back cut off mid-sentence ("...with CIA officials being"), one of
    them at 65 words from 374, and were saved like that. So a result that does not end a
    sentence, or keeps under a quarter of the words, gets one more try, and after that
    the long summary stands: too long is a nuisance, cut off is wrong.
    """
    for _ in range(2):
        shorter = _rewrite(summary, CondensedChunk, model)
        if _FINISHED.search(shorter.strip()) and word_count(shorter) >= word_count(summary) / 4:
            return shorter
    return summary


def format_text(answer):
    if "```html" in answer:
        answer = answer.replace("```html", "").replace("```")

    if "**" in answer:
        # Replace **text** with <b>text</b>
        answer = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', answer)

    if "###" in answer:
        answer = re.sub(r'### (.*)', r'<h3>\1</h3>', answer)

    if "_" in answer:
        answer = re.sub(r'_(.*?)_', r'<em>\1</em>', answer)

    return answer\
        .replace("<b>", "<b style='color: forestgreen;'>")\
        .replace("<h3>", "<h3 style='color: forestgreen;'>")\
        .replace("<em>", "<em style='color: forestgreen;'>")


def highlight_chunk(pages, first=True, model=None):
    history = History()
    for page in pages:
        history.system(page.page_content)

    chunk_model = DisabilityBookFirstChunk
    if not first:
        chunk_model = DisabilityBookNextChunk
    print(chunk_model.__name__)
    response = llm_strict(history, model_name=model, base_model=chunk_model)
    summary = response.summary_chunk
    if word_count(summary) > MAX_SUMMARY_WORDS:
        print(f"Summary ran to {word_count(summary)} words; condensing.")
        summary = condense(summary, model=model)
    if describes_the_text(summary):
        print("Summary describes the text instead of its content; rewriting it directly.")
        summary = make_direct(summary, model=model)
    return {"title": clean_title(response.summary_title), "body": format_text(summary)}

