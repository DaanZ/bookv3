"""LLM access for the pipeline, routed through OpenRouter.

OpenRouter speaks the OpenAI wire protocol, so this stays the OpenAI SDK with a
different `base_url` — but two things about the switch are load bearing:

* **Model ids are namespaced.** `gpt-4o` is `openai/gpt-4o` here. `MODEL` is the one
  place that name lives; `api/estimate.py` prices whatever it is set to.
* **Not every model can do structured outputs**, and `llm_strict` is the whole pipeline.
  Pick a model whose OpenRouter entry lists `structured_outputs` in
  `supported_parameters`, or the parse call fails at runtime rather than at import.

TLS: this machine runs AVG, whose Web Shield intercepts HTTPS and presents a certificate
signed by AVG's own root. That root is in the Windows certificate store but not in the
`certifi` bundle Python validates against, so every API call fails with
CERTIFICATE_VERIFY_FAILED until Python is pointed at the OS trust store. `truststore`
does exactly that, and is a no-op on machines without the interception.
"""

import os
import time

from dotenv import load_dotenv
from openai import APIError, OpenAI
from pydantic import ValidationError

from util.history import History

try:  # Trust the OS certificate store, so a TLS-intercepting antivirus does not break us.
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover - only the machines that need it have it
    pass

load_dotenv()

BASE_URL = "https://openrouter.ai/api/v1"

# The default model for every pipeline call. Namespaced, as OpenRouter requires.
#
# gemini-2.5-flash, and no OpenAI model anywhere by preference. This is the one with
# production evidence behind it: both books on the shelf were summarized by it, 27 parts,
# every one highlighted. Models rejected on test returned fluent summaries with *no* `**`
# marks at all, which leaves the reader's highlighting nothing to colour — see
# `estimate.KNOWN_UNHIGHLIGHTING`. `jobs.py` now checks the first part for marks before
# buying the rest, so trying an untested model costs one chunk rather than a book.
MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")

# Kept as a KeyError so the guard in api/jobs.py still recognises a missing key and
# fails the one ingest job rather than the whole reader.
try:
    _api_key = os.environ["OPENROUTER_API_KEY"]
except KeyError:
    _api_key = os.environ["OPENAI_API_KEY"]  # raises KeyError when neither is set

# A request that never returns wedges everything. Jobs run one at a time on a single
# worker, so one hung call does not slow a book down — it stops the queue, and the job
# sits at "0 of 4 parts" with no error to show for it. Seen in practice at ten minutes
# and counting. The SDK's default is no timeout at all, so this has to be said.
#
# Generous rather than tight: a long chunk on a slow model legitimately takes a while,
# and `_retrying` will try twice more, so the worst case is three of these.
REQUEST_TIMEOUT_SECONDS = 180

openai_client = OpenAI(api_key=_api_key, base_url=BASE_URL, timeout=REQUEST_TIMEOUT_SECONDS)


def llm_question(query):
    logs = History()
    logs.user(query)
    answer = llm_chat(logs)
    return answer


def llm_chat(message_log: History, model_name: str = None):
    # Use OpenAI's ChatCompletion API to get the chatbot's response
    response = openai_client.chat.completions.create(
        model=model_name or MODEL,   # The name of the model to use, as OpenRouter names it
        messages=message_log.logs,   # The conversation history up to this point, as a list of dictionaries
        max_tokens=1000,        # The maximum number of tokens (words or subwords) in the generated response
        stop=None,              # The stopping sequence for the generated response, if any (not used here)
        temperature=0.0,        # The "creativity" of the generated response (higher temperature = more creative)
    )

    # Find the first response from the chatbot that has text in it (some responses may not have text)
    for choice in response.choices:
        if "text" in choice:
            return choice.text

    # If no response with text is found, return the first response's content (which may be empty)
    return response.choices[0].message.content


# A summarizing run is one call per part, and a book is a dozen or more of them, so a
# failure rate that is negligible per call is not negligible per book. Measured over
# twelve real chunks these calls parsed 12/12 — the failure that prompted this was a
# response truncated mid-string, 180 characters into the summary, which is transport
# rather than the model being unable to hold the schema. One retry would almost certainly
# have carried it.
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 1.5


def _retrying(call):
    """Retry a structured call through the failures that are worth retrying.

    `ValidationError` is in the list because that is how a truncated response arrives:
    the JSON stops mid-string and pydantic reports invalid JSON, not a schema mismatch.
    A model that genuinely cannot produce the schema fails all three attempts and still
    raises, so this hides nothing — it only absorbs the ones that pass.
    """
    last = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return call()
        except (ValidationError, APIError, ValueError) as ex:
            last = ex
            if attempt == RETRY_ATTEMPTS:
                break
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    raise last


def llm_strict(history: History, model_name: str = None, base_model: type = None):
    if base_model is None:
        return None
    def parse_once():
        completion = openai_client.beta.chat.completions.parse(
            model=model_name or MODEL,
            messages=history.logs,
            response_format=base_model,
        )
        message = completion.choices[0].message
        if message.parsed is None:
            # `parse` returns None rather than raising when the model answered with
            # something that is not the schema at all — a refusal, a preamble, an empty
            # message. Checked *inside* the retried call, so a one-off gets another go;
            # left outside it, this sailed through and surfaced pages later as
            # "'NoneType' object has no attribute 'summary_title'", which names the
            # symptom and not the cause.
            refusal = getattr(message, "refusal", None)
            raise ValueError(
                f"{model_name or MODEL} returned no structured answer"
                + (f": {refusal}" if refusal else " — the reply did not match the schema.")
            )
        return message.parsed

    return _retrying(parse_once)
